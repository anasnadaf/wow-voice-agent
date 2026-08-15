"""LangGraph conversation graph for the WOW pre-sales agent.

Per user turn the graph runs ONE superstep with two concurrent branches:

    START ──(conditional: current stage)──> intro|qualify|pitch|cta   (streaming reply)
          └───────────────────────────────> extract                   (fast slot parse)
    both branches ──> advance (merge signals, route next stage) ──> END

The reply branch is the only latency-critical path — its tokens stream to the caller
as they are produced. The extract branch runs concurrently on the fast model and its
result is folded into state by `advance`, i.e. extraction never blocks the spoken
reply; it shapes routing for the NEXT turn. The reply model still handles the current
turn's content correctly because it sees the caller's latest words in the transcript
and every stage prompt carries the edge-case playbook.

No-re-asking is enforced structurally: extraction fills any volunteered checkpoint
regardless of stage, `advance` never overwrites a filled slot, and the reply prompt
lists filled checkpoints as off-limits with exactly one next target.
"""

import json
import re

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.state import AgentState, next_checkpoint
from app.prompts import system_prompt_for_turn

REPLY_NODES = ("intro", "qualify", "pitch", "cta")

EXTRACTION_PROMPT = """\
You label ONE caller turn from an outbound real-estate call about premium villa plots \
near Nandi Hills, North Bengaluru (entry price about 92.4 lakh rupees, possession \
December 2029). Respond with ONLY a JSON object, no prose, using exactly this schema \
(null / false when the caller's LATEST message does not clearly express it):
{
  "language": "en" | "hi",
  "permission": "granted" | "denied" | null,
  "intent": "self_use" | "investment" | null,
  "geography": "positive" | "negative" | null,
  "budget": "fit" | "stretch" | "mismatch" | null,
  "timeline": "comfortable" | "uncomfortable" | null,
  "irritated": true | false,
  "busy": true | false,
  "callback_time": string | null,
  "wrong_person": true | false,
  "not_interested": true | false,
  "dnc": true | false,
  "cta_accepted": true | false | null
}
Guidance:
- "language" is "hi" if the message is in Hindi or romanized Hindi/Hinglish.
- "permission" labels the answer to "is this a good time to talk".
- "geography" is comfort with the Nandi Hills / Devanahalli area; "budget" is fitment
  with the ~92.4 lakh entry price ("mismatch" only when clearly out of reach);
  "timeline" is comfort with possession in December 2029.
- Volunteered information counts even if it was not asked for.
- "busy" means they want to talk another time; "dnc" only for an explicit request to
  stop calling; "not_interested" is a refusal of the project, not mere hesitation.
- "cta_accepted" labels the answer to the offer of a Property Expert follow-up call.
"""

_DNC_RE = re.compile(
    r"\b(do not call|don'?t (?:ever )?call|stop calling|never call( me)? again|"
    r"remove (?:my|this) number|take me off)\b",
    re.IGNORECASE,
)
_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")


def _chunk_text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return ""


def _history_messages(state: AgentState) -> list[BaseMessage]:
    return [
        HumanMessage(content=m["content"])
        if m["role"] == "user"
        else AIMessage(content=m["content"])
        for m in state["history"]
    ]


def _last_user_text(state: AgentState) -> str:
    for message in reversed(state["history"]):
        if message["role"] == "user":
            return message["content"]
    return ""


def _last_assistant_text(state: AgentState) -> str:
    for message in reversed(state["history"]):
        if message["role"] == "assistant":
            return message["content"]
    return ""


def _make_reply_node(stage: str, llm: BaseChatModel):
    async def reply(state: AgentState) -> dict:
        messages = [SystemMessage(content=system_prompt_for_turn(state))]
        messages.extend(_history_messages(state))
        parts: list[str] = []
        async for chunk in llm.astream(messages):
            parts.append(_chunk_text(chunk))
        return {"last_reply": "".join(parts)}

    reply.__name__ = stage
    return reply


def parse_extraction(raw: str) -> dict:
    """Leniently pull the first JSON object out of a model response."""
    start, stop = raw.find("{"), raw.rfind("}")
    if start == -1 or stop <= start:
        return {}
    try:
        parsed = json.loads(raw[start : stop + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _make_extract_node(llm: BaseChatModel):
    async def extract(state: AgentState) -> dict:
        context = (
            f"Call stage: {state['stage']}\n"
            f'Agent said: "{_last_assistant_text(state)}"\n'
            f'Caller replied: "{_last_user_text(state)}"'
        )
        result = await llm.ainvoke(
            [SystemMessage(content=EXTRACTION_PROMPT), HumanMessage(content=context)]
        )
        return {"extracted": parse_extraction(_chunk_text(result))}

    return extract


def _merge_slots(state: AgentState, ex: dict) -> tuple[dict, int]:
    """Fold extracted checkpoint signals into slots. Filled slots are never cleared,
    and only geography may be refined (comfortable can supersede hesitant)."""
    slots = dict(state["slots"])
    objections = state["objection_count"]
    if ex.get("intent") in ("self_use", "investment") and slots["intent"] is None:
        slots["intent"] = ex["intent"]
    geography = ex.get("geography")
    if geography == "positive" and slots["geography"] in (None, "hesitant"):
        slots["geography"] = "comfortable"
    elif geography == "negative":
        if slots["geography"] is None:
            # first objection: record it, the prompt then allows exactly one reframe
            slots["geography"] = "hesitant"
            objections += 1
        elif slots["geography"] == "hesitant":
            slots["geography"] = "rejected"
            objections += 1
    if ex.get("budget") in ("fit", "stretch", "mismatch") and slots["budget"] is None:
        slots["budget"] = ex["budget"]
    if ex.get("timeline") in ("comfortable", "uncomfortable") and slots["timeline"] is None:
        slots["timeline"] = ex["timeline"]
    return slots, objections


def _decide_outcome(state: AgentState, ex: dict, slots: dict, irritation: int) -> str | None:
    if ex.get("dnc"):
        return "dnc"
    if ex.get("wrong_person"):
        return "abandoned"
    if ex.get("not_interested"):
        return "declined"
    if ex.get("busy"):
        return "callback"
    if state["stage"] == "intro" and ex.get("permission") == "denied":
        return "declined"
    if irritation >= 2:
        return "abandoned"
    if slots["budget"] == "mismatch":
        return "not_qualified"
    if slots["geography"] == "rejected":
        return "not_qualified"
    if state["stage"] == "cta":
        if ex.get("cta_accepted") is True:
            return "qualified"
        if ex.get("cta_accepted") is False:
            return "declined"
    return None


def _next_stage(state: AgentState, permission: bool, slots: dict) -> str:
    previous = state["stage"]
    if previous == "intro":
        if not permission:
            return "intro"
        return "pitch" if next_checkpoint(slots) is None else "qualify"
    if previous == "qualify":
        return "pitch" if next_checkpoint(slots) is None else "qualify"
    if previous == "pitch":
        # the pitch node also delivers the CTA, so the next turn interprets the answer
        return "cta"
    return previous


def _advance(state: AgentState) -> dict:
    ex = dict(state.get("extracted") or {})

    # deterministic guards — additive only, they never unset an extracted signal
    user_text = _last_user_text(state)
    if _DEVANAGARI_RE.search(user_text):
        ex["language"] = "hi"
    if _DNC_RE.search(user_text.lower()):
        ex["dnc"] = True

    irritation = state["irritation_level"] + (1 if ex.get("irritated") else 0)
    permission = state["permission_granted"] or ex.get("permission") == "granted"
    slots, objections = _merge_slots(state, ex)

    outcome = state["outcome"] or _decide_outcome(state, ex, slots, irritation)
    stage = "done" if outcome else _next_stage(state, permission, slots)

    history = list(state["history"])
    if state["last_reply"]:
        history.append({"role": "assistant", "content": state["last_reply"]})

    updates: dict = {
        "irritation_level": irritation,
        "permission_granted": permission,
        "slots": slots,
        "objection_count": objections,
        "outcome": outcome,
        "stage": stage,
        "history": history,
        "extracted": {},
        "last_reply": "",
    }
    if ex.get("language") in ("en", "hi"):
        updates["language"] = ex["language"]
    if ex.get("wrong_person"):
        updates["wrong_person"] = True
    if ex.get("callback_time"):
        updates["callback_time"] = str(ex["callback_time"])
    return updates


def _route_turn(state: AgentState) -> list[str]:
    stage = state["stage"]
    reply_node = stage if stage in REPLY_NODES else "cta"
    return ["extract", reply_node]


def build_graph(reply_llm: BaseChatModel, extract_llm: BaseChatModel) -> CompiledStateGraph:
    graph = StateGraph(AgentState)
    for stage in REPLY_NODES:
        graph.add_node(stage, _make_reply_node(stage, reply_llm))
    graph.add_node("extract", _make_extract_node(extract_llm))
    graph.add_node("advance", _advance)
    graph.add_conditional_edges(START, _route_turn, ["extract", *REPLY_NODES])
    for stage in REPLY_NODES:
        graph.add_edge(stage, "advance")
    graph.add_edge("extract", "advance")
    graph.add_edge("advance", END)
    return graph.compile()
