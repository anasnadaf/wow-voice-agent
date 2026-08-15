"""Graph state for the conversation brain.

The state is a plain TypedDict so LangGraph channel updates stay cheap and the
whole thing serializes to JSON with no ceremony (see ConversationEngine.snapshot).
"""

from typing import Literal, TypedDict

Language = Literal["en", "hi"]

# Stages route each user turn to exactly one reply node:
#   intro    — greeting delivered, waiting on permission to proceed
#   qualify  — working through unanswered checkpoints
#   pitch    — all checkpoints answered; deliver lifestyle pitch + expert-call CTA
#   cta      — CTA delivered; interpret the response and close
#   done     — terminal, no further turns expected
Stage = Literal["intro", "qualify", "pitch", "cta", "done"]

Outcome = Literal["qualified", "not_qualified", "callback", "dnc", "declined", "abandoned"]

# Checkpoints are always pursued in this order; extraction may fill them in any
# order (volunteered answers count) and a filled slot is never asked again.
SLOT_ORDER = ("intent", "geography", "budget", "timeline")

SLOT_QUESTIONS = {
    "intent": "whether they are exploring for their own use or as an investment",
    "geography": "how they feel about the Nandi Hills / Devanahalli corridor in North Bengaluru",
    "budget": "whether a starting price of ninety two point four lakh rupees works for them",
    "timeline": "how they feel about an ongoing project with possession in December 2029",
}


class Slots(TypedDict):
    # intent: "self_use" | "investment"
    intent: str | None
    # geography: "comfortable" | "hesitant" (one reframe used) | "rejected"
    geography: str | None
    # budget: "fit" | "stretch" | "mismatch"
    budget: str | None
    # timeline: "comfortable" | "uncomfortable"
    timeline: str | None


class AgentState(TypedDict):
    call_id: str
    lead_name: str | None
    language: Language
    stage: Stage
    permission_granted: bool
    slots: Slots
    objection_count: int
    irritation_level: int
    outcome: Outcome | None
    # routing helpers
    wrong_person: bool
    callback_time: str | None
    # how many times closing was held back because the agent's own reply ended
    # on a question — bounded so a call always reaches an ending
    closing_deferred: int
    # transcript as {"role": "assistant"|"user", "content": str} dicts
    history: list[dict]
    # written by the reply node each turn, folded into history by advance
    last_reply: str
    # written by the extract node each turn, consumed by advance
    extracted: dict


def initial_state(call_id: str, lead_name: str | None = None) -> AgentState:
    return AgentState(
        call_id=call_id,
        lead_name=lead_name,
        language="en",
        stage="intro",
        permission_granted=False,
        slots=Slots(intent=None, geography=None, budget=None, timeline=None),
        objection_count=0,
        irritation_level=0,
        outcome=None,
        wrong_person=False,
        callback_time=None,
        closing_deferred=0,
        history=[],
        last_reply="",
        extracted={},
    )


def next_checkpoint(slots: Slots) -> str | None:
    """First unanswered checkpoint in canonical order, or None when all are filled."""
    for name in SLOT_ORDER:
        if slots.get(name) is None:
            return name
    return None


def answered_checkpoints(slots: Slots) -> list[str]:
    return [name for name in SLOT_ORDER if slots.get(name) is not None]
