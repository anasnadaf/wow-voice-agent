"""Text-mode simulation: LLM-played lead personas talk to the ConversationEngine.

Usage (needs GROQ_API_KEY, or CEREBRAS_API_KEY with llm_provider=cerebras):

    cd server && uv run python -m scripts.simulate                 # all personas
    cd server && uv run python -m scripts.simulate irritated hindi_speaker
    cd server && uv run python -m scripts.simulate --list

Personas are plain data — add one by appending a Persona to the list below.
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agent.engine import ConversationEngine, _default_llm
from app.config import settings

HANGUP = "[HANGUP]"

PLAYER_RULES = (
    "You are role-playing a lead receiving an outbound phone call from a real-estate "
    "consultant about premium villa plots near Nandi Hills, Bengaluru. Stay fully in "
    "character per the profile below. Reply with ONLY your next spoken line — one or "
    "two short sentences, no quotes, no stage directions. If the consultant has "
    f"clearly ended the call (goodbye, hang-up), reply with exactly {HANGUP}.\n\n"
    "Your profile:\n"
)


@dataclass(frozen=True)
class Persona:
    key: str
    lead_name: str
    profile: str
    max_turns: int = 8


PERSONAS: dict[str, Persona] = {
    p.key: p
    for p in [
        Persona(
            key="eager_investor",
            lead_name="Vikram",
            profile=(
                "Vikram, a Dubai-based NRI CXO hunting for a land investment near the "
                "Bengaluru airport corridor. Enthusiastic, decisive, budget up to three "
                "crore rupees. Answers quickly, volunteers information, happily agrees "
                "to a Property Expert call."
            ),
        ),
        Persona(
            key="self_use_budget_fit",
            lead_name="Meera",
            profile=(
                "Meera, a Bengaluru CTO looking for a plot to build a weekend villa for "
                "her family. Warm but thorough: asks one question about the clubhouse or "
                "possession date before answering. Budget around one and a half crore. "
                "Comfortable with 2029 possession. Agrees to the follow-up call."
            ),
        ),
        Persona(
            key="budget_mismatch",
            lead_name="Suresh",
            profile=(
                "Suresh, a mid-level manager who likes the idea of a plot near Nandi "
                "Hills but has a hard budget of forty lakh rupees. Polite and honest — "
                "says the budget plainly when price comes up."
            ),
        ),
        Persona(
            key="location_objection_budget_fit",
            lead_name="Anita",
            profile=(
                "Anita, a well-off marketing director. Budget of one to two crore is no "
                "problem, but she feels Doddaballapura / Nandi Hills is too far from her "
                "Indiranagar home and says so. If the consultant makes one reasonable "
                "point about airport connectivity she softens slightly but stays "
                "undecided; if pushed twice she firmly declines."
            ),
        ),
        Persona(
            key="irritated",
            lead_name="Rajesh",
            profile=(
                "Rajesh, interrupted during work and fed up with spam calls. Starts "
                "curt ('Who gave you this number?'), gets angrier if the pitch "
                "continues, and demands the call end."
            ),
            max_turns=5,
        ),
        Persona(
            key="hindi_speaker",
            lead_name="Ramesh",
            profile=(
                "Ramesh from Delhi, more comfortable in Hindi. Opens with 'Haan ji, "
                "boliye, kaun bol raha hai?' and continues in romanized Hindi/Hinglish "
                "throughout. Genuinely interested: buying for family use, budget around "
                "one crore, fine with the location and timeline."
            ),
        ),
        Persona(
            key="busy_callback",
            lead_name="Priya",
            profile=(
                "Priya, walking into a meeting. Not hostile, but cannot talk now — asks "
                "to be called back tomorrow around six in the evening and ends quickly."
            ),
            max_turns=4,
        ),
    ]
}


@dataclass
class TranscriptLine:
    speaker: str
    text: str


async def play(persona: Persona) -> dict:
    print(f"\n{'=' * 72}\nPERSONA: {persona.key} — {persona.lead_name}\n{'=' * 72}")
    engine = ConversationEngine(f"sim-{persona.key}", persona.lead_name)
    # The persona only has to sound like a caller, so it runs on the small
    # model — using the conversation model here doubled the token cost of a run.
    player = _default_llm(settings.extract_model, temperature=0.8, max_tokens=120)
    system = SystemMessage(content=PLAYER_RULES + persona.profile)
    transcript: list[TranscriptLine] = [TranscriptLine("agent", engine.opening_line())]
    print(f"\nAGENT: {engine.opening_line()}")

    for _ in range(persona.max_turns):
        # persona sees agent lines as incoming ("human") and its own as prior replies
        messages: list = [system]
        for line in transcript:
            cls = HumanMessage if line.speaker == "agent" else AIMessage
            messages.append(cls(content=line.text))
        lead_text = (await player.ainvoke(messages)).content.strip()
        if not lead_text or HANGUP in lead_text:
            break
        transcript.append(TranscriptLine("lead", lead_text))
        print(f"\nLEAD:  {lead_text}")

        print("\nAGENT: ", end="", flush=True)
        parts = []
        async for chunk in engine.stream_turn(lead_text):
            parts.append(chunk)
            print(chunk, end="", flush=True)
        print()
        transcript.append(TranscriptLine("agent", "".join(parts)))
        if engine.is_done:
            break

    snapshot = engine.snapshot()
    print(f"\n--- final state ({persona.key}) ---")
    print(json.dumps({k: v for k, v in snapshot.items() if k != "history"}, indent=2))
    return snapshot


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("personas", nargs="*", help="persona keys to run (default: all)")
    parser.add_argument("--list", action="store_true", help="list available personas")
    args = parser.parse_args()

    if args.list:
        for persona in PERSONAS.values():
            print(f"{persona.key:32s} {persona.profile[:70]}...")
        return

    keys = args.personas or list(PERSONAS)
    unknown = [k for k in keys if k not in PERSONAS]
    if unknown:
        sys.exit(f"unknown persona(s): {', '.join(unknown)} — try --list")

    outcomes = {}
    for key in keys:
        snapshot = await play(PERSONAS[key])
        outcomes[key] = snapshot["outcome"]
    print(f"\n{'=' * 72}\nOUTCOMES: {json.dumps(outcomes, indent=2)}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as exc:
        sys.exit(f"error: {exc}\nhint: set GROQ_API_KEY in server/.env before simulating")
