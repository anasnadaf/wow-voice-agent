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
from loguru import logger

from app.agent.state import AgentState, next_checkpoint
from app.prompts import language_directive, speech_tags_required, system_prompt_for_turn
from app.prompts.speech import MUGA_TONE_REMINDER, strip_speech_tags

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
- "language" is the language THE PROSPECT just spoke, not the one you replied in.
  Use "hi" only when Hindi words carry the sentence (Devanagari, or romanized Hindi
  such as "haan, mujhe plot chahiye"). Indian English is still "en": lakh, crore,
  namaste, sir, ji or an Indian place name inside an otherwise English sentence
  does NOT make it Hindi.
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

# Romanized Hindi function words. Content words (lakh, crore, namaste) are
# deliberately absent — they appear constantly in Indian English, and flipping
# the call to Hindi on one of them strands an English speaker in Hinglish.
_HINGLISH_RE = re.compile(
    r"\b(hai|hain|haan|nahi|nahin|aap|aapka|aapke|aapko|kya|kyun|kyunki|mujhe|"
    r"mera|meri|mere|main|hum|humein|hoon|hun|ji|yeh|ye|woh|wo|karo|karna|karta|"
    r"karti|karunga|karungi|kar|raha|rahi|rahe|chahiye|bata|batao|bataiye|boliye|"
    r"thik|theek|acha|accha|bilkul|abhi|kitna|kitne|kaise|kahan|kaha|mein|liye|"
    r"lekin|magar|par|se|ka|ki|ko|bahut|thoda|sab|kuch|dhanyavad|shukriya)\b",
    re.IGNORECASE,
)
# One stray "haan" in an English sentence is not a switch to Hindi; equally, a
# short Hinglish line ("Haan ji, theek hai") should not read as English. Two
# markers commit, zero markers release, and one is too weak to decide either
# way — so an ambiguous turn leaves the language where it already was.
_HINGLISH_COMMIT = 2


def _chunk_text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return ""


# A 2-3 minute call stays well inside this, and the live-context block already
# carries the facts that matter (answered checkpoints, objections), so older
# turns cost tokens — and latency — without earning them.
_HISTORY_TURNS = 10


def _history_messages(state: AgentState) -> list[BaseMessage]:
    return [
        HumanMessage(content=m["content"])
        if m["role"] == "user"
        else AIMessage(content=m["content"])
        for m in state["history"][-_HISTORY_TURNS:]
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
        # `advance` stores the language, but it runs after this node — so the
        # stored value describes the previous turn. Detection is a regex over
        # the caller's own words, costing nothing, so the reply resolves it
        # first-hand and answers the language being spoken right now rather
        # than the one spoken a turn ago.
        state = {**state, "language": _resolve_language(state)}  # type: ignore[assignment]
        messages = [SystemMessage(content=system_prompt_for_turn(state))]
        messages.extend(_history_messages(state))
        # Repeated last, after the transcript. Once a call switches to Hindi the
        # history is still mostly English, and a rule sitting thousands of tokens
        # back loses to that precedent — the model keeps answering in English.
        # Restating it in the final position is what makes the switch stick, and
        # the tone tag rides along because it has the same recency problem.
        directive = language_directive(state["language"])
        if speech_tags_required():
            directive = f"{directive}\n{MUGA_TONE_REMINDER}"
        messages.append(SystemMessage(content=directive))
        parts: list[str] = []
        async for chunk in llm.astream(messages):
            parts.append(_chunk_text(chunk))
        # The tag steers the synthesiser; what the agent remembers saying is the
        # sentence itself, so history never carries the markup.
        return {"last_reply": strip_speech_tags("".join(parts))}

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


# Live speech-to-text emits short garbage from background noise ("Hmm hmm",
# "Eggworks"). Ending a call on one of those is the worst possible failure, so
# signals that hang up need a turn with enough words to actually carry them.
_MIN_WORDS_FOR_EXIT = 3


def _sanitize_exit_signals(ex: dict, state: AgentState, user_text: str) -> dict:
    """Drop hang-up signals a garbled or nonsensical turn cannot support.

    `dnc` is deliberately exempt: it is set by an explicit-phrase regex, never
    by the model, so it cannot fire on noise — and honouring it always matters
    more than the risk of a false positive.
    """
    if len(user_text.split()) < _MIN_WORDS_FOR_EXIT:
        for signal in ("wrong_person", "not_interested", "busy"):
            ex.pop(signal, None)
    # Someone who has been answering questions for several turns is not
    # suddenly the wrong person; that label mid-call is an extraction artifact.
    if state["permission_granted"] and ex.get("wrong_person"):
        ex.pop("wrong_person")
    return ex


# The reply and the outcome are decided in the same superstep, so the graph can
# find a call finished on the very turn the agent asked something. Hanging up
# then cuts the caller off mid-answer — the abrupt ending they hear.
_MAX_CLOSING_DEFERRALS = 1
# A do-not-call request is honoured immediately whatever the reply looked like:
# respecting it matters more than the tidiness of the goodbye.
_HARD_EXITS = ("dnc",)


def _awaits_answer(reply: str) -> bool:
    """Whether the agent's own last words left a question hanging."""
    return reply.strip().endswith("?")


def _hold_for_answer(outcome: str | None, state: AgentState) -> bool:
    return bool(
        outcome
        and outcome not in _HARD_EXITS
        and state["closing_deferred"] < _MAX_CLOSING_DEFERRALS
        and _awaits_answer(state["last_reply"])
    )


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


def _detect_language(user_text: str, current: str) -> str | None:
    """Decide the caller's language from their own words.

    The extractor labels Indian English as Hinglish more often than not, so the
    caller's text decides this rather than the model. Returns None when the turn
    is too ambiguous to move (an empty or one-marker turn), leaving the call in
    whatever language it was already in.
    """
    if _DEVANAGARI_RE.search(user_text):
        return "hi"
    if not user_text.strip():
        return None
    markers = len(_HINGLISH_RE.findall(user_text))
    if markers >= _HINGLISH_COMMIT:
        return "hi"
    if markers == 0:
        return "en"
    return current


def _resolve_language(state: AgentState) -> str:
    """The language the caller is speaking on this turn, decided from their text."""
    return _detect_language(_last_user_text(state), state["language"]) or state["language"]


def _advance(state: AgentState) -> dict:
    ex = dict(state.get("extracted") or {})

    # deterministic guards — additive only, they never unset an extracted signal
    user_text = _last_user_text(state)
    ex["language"] = _resolve_language(state)
    ex = _sanitize_exit_signals(ex, state, user_text)
    if _DNC_RE.search(user_text.lower()):
        ex["dnc"] = True

    irritation = state["irritation_level"] + (1 if ex.get("irritated") else 0)
    permission = state["permission_granted"] or ex.get("permission") == "granted"
    slots, objections = _merge_slots(state, ex)

    outcome = state["outcome"] or _decide_outcome(state, ex, slots, irritation)
    deferred = state["closing_deferred"]
    if _hold_for_answer(outcome, state):
        # let the caller answer; the outcome is re-decided next turn, by which
        # point the agent has something to close on
        logger.info(f"call {state['call_id']}: holding {outcome} — the agent just asked a question")
        outcome, deferred = None, deferred + 1
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
        "closing_deferred": deferred,
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
