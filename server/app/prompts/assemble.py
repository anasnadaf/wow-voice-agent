"""Assemble system prompts — stage-specific for live turns, full for documentation."""

from app.agent.state import (
    SLOT_QUESTIONS,
    AgentState,
    answered_checkpoints,
    next_checkpoint,
)
from app.prompts.knowledge import knowledge_block
from app.prompts.sections import (
    BILINGUAL_RULES,
    EDGE_CASES,
    PERSONA,
    PRONUNCIATION,
    STAGE_POLICIES,
    TONE_RULES,
)

_SLOT_VALUE_LABELS = {
    "intent": {"self_use": "for their own use", "investment": "as an investment"},
    "geography": {
        "comfortable": "comfortable with the location",
        "hesitant": "hesitant about the location (your one gentle reframe is already "
        "used — do not push again)",
        "rejected": "not convinced by the location",
    },
    "budget": {
        "fit": "comfortable with the budget",
        "stretch": "the budget is a stretch but workable",
        "mismatch": "the budget does not fit",
    },
    "timeline": {
        "comfortable": "comfortable with the December two thousand twenty nine possession",
        "uncomfortable": "not comfortable with the possession timeline",
    },
}


def _live_context(state: AgentState) -> str:
    """Per-turn snapshot of what the agent must and must not do."""
    lines: list[str] = ["## Live call context"]
    if state.get("lead_name"):
        lines.append(f"- Caller's name: {state['lead_name']}.")
    lang = state.get("language", "en")
    lines.append(
        "- Current call language: "
        + ("Hindi — reply in natural Hinglish (Latin script)." if lang == "hi" else "English.")
    )
    slots = state["slots"]
    answered = answered_checkpoints(slots)
    if answered:
        detail = "; ".join(
            f"{name}: {_SLOT_VALUE_LABELS[name].get(slots[name], slots[name])}"  # type: ignore[literal-required]
            for name in answered
        )
        lines.append(f"- ALREADY ANSWERED checkpoints — never ask these again: {detail}.")
    pending = next_checkpoint(slots)
    if state["stage"] == "qualify":
        if pending is not None:
            lines.append(
                f"- Next checkpoint to pursue (exactly one question): {pending} — "
                f"{SLOT_QUESTIONS[pending]}."
            )
        else:
            lines.append("- All checkpoints are answered.")
    if state.get("irritation_level", 0) >= 1:
        lines.append(
            "- The caller has already sounded irritated once. If they sound irritated "
            "again, apologize and end the call gracefully."
        )
    if state.get("objection_count", 0) >= 1:
        lines.append("- A location reframe has already been offered once — never offer another.")
    return "\n".join(lines)


def system_prompt_for_turn(state: AgentState) -> str:
    """The single system prompt behind the one streaming reply call for this turn."""
    stage_policy = STAGE_POLICIES.get(state["stage"], STAGE_POLICIES["done"])
    return "\n\n".join(
        [
            PERSONA,
            TONE_RULES,
            PRONUNCIATION,
            BILINGUAL_RULES,
            stage_policy,
            EDGE_CASES,
            "## Project knowledge base\n" + knowledge_block(),
            _live_context(state),
        ]
    )


def full_system_prompt() -> str:
    """Complete, well-organized prompt document (also the PDF deliverable)."""
    stage_docs = "\n\n".join(STAGE_POLICIES[stage] for stage in STAGE_POLICIES)
    return "\n\n".join(
        [
            "# System prompt — Divyasree WOW pre-sales voice agent",
            PERSONA,
            TONE_RULES,
            PRONUNCIATION,
            BILINGUAL_RULES,
            "# Stage policies\n\n"
            "Exactly one stage policy is active per turn, selected by the conversation "
            "graph from call state.\n\n" + stage_docs,
            EDGE_CASES,
            "## Project knowledge base\n" + knowledge_block(),
            "## Live call context\n"
            "At runtime the prompt ends with a per-turn context block: the caller's "
            "name, the current call language, checkpoints already answered (which must "
            "never be asked again), the single next checkpoint to pursue, and any "
            "irritation or objection history that constrains the reply.",
        ]
    )
