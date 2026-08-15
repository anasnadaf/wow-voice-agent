"""Graded evaluation: run persona simulations, score them, log to MLflow.

`scripts.simulate` shows what a call sounds like; this decides whether it was
any good. Each persona is played against the real ConversationEngine, then a
DSPy judge scores the transcript against the assignment's requirements and the
qualification extractor is checked against the outcome the persona should
produce. Everything lands in one MLflow run per evaluation, so a prompt change
can be compared against the previous score instead of eyeballed.

Usage (needs GROQ_API_KEY, or CEREBRAS_API_KEY with llm_provider=cerebras):

    cd server && uv run python -m scripts.evaluate
    cd server && uv run python -m scripts.evaluate irritated hindi_speaker
    cd server && uv run python -m scripts.evaluate --no-mlflow
"""

import argparse
import asyncio
import json
import sys
from typing import Literal

import dspy

from app.analysis.extract import build_extraction_lm, extract_qualification, format_transcript
from app.config import settings
from scripts.simulate import PERSONAS, play

# What each persona must produce for the run to count as correct. Disposition
# is what the post-call extractor should conclude; outcome is what the graph
# should have decided.
EXPECTED: dict[str, dict[str, tuple[str, ...]]] = {
    "eager_investor": {"outcome": ("qualified",), "disposition": ("qualified",)},
    "self_use_budget_fit": {"outcome": ("qualified",), "disposition": ("qualified",)},
    "budget_mismatch": {
        "outcome": ("not_qualified", "qualified"),
        "disposition": ("not_qualified", "incomplete"),
    },
    "location_objection_budget_fit": {
        "outcome": ("qualified", "not_qualified"),
        "disposition": ("qualified", "not_qualified"),
    },
    "irritated": {
        "outcome": ("declined", "not_qualified", "abandoned"),
        "disposition": ("not_qualified", "incomplete"),
    },
    "hindi_speaker": {"outcome": ("qualified", "callback"), "disposition": ("qualified",)},
    "busy_callback": {"outcome": ("callback", "declined"), "disposition": ("callback",)},
}


class CallJudge(dspy.Signature):
    """Grade one outbound pre-sales call for Divyasree's "Whispers of the Wind".

    The agent must: open by naming itself, the project and the location, and ask
    permission before continuing; establish four checkpoints (intent, geography,
    budget, timeline) conversationally without ever re-asking something the
    prospect already answered; give an aspirational pitch of the Private Valley
    lifestyle; and ask for a follow-up with a Property Expert. Replies must be
    short and speakable, premium in tone, never pushy.

    Judge only what the transcript shows. A call that ends early for a good
    reason (the prospect refused permission, asked not to be called, was busy,
    or was clearly out of budget) should NOT be penalised for skipping later
    stages — score those as 'not_applicable'.
    """

    transcript: str = dspy.InputField(desc="speaker-labelled transcript, one turn per line")
    persona: str = dspy.InputField(desc="the character the prospect was playing")
    asked_permission: bool = dspy.OutputField(desc="opened properly and asked permission")
    checkpoints_covered: int = dspy.OutputField(desc="how many of the four were established (0-4)")
    repeated_a_question: bool = dspy.OutputField(desc="re-asked something already answered")
    pitch_quality: Literal["strong", "adequate", "weak", "not_applicable"] = dspy.OutputField()
    made_cta: Literal["yes", "no", "not_applicable"] = dspy.OutputField()
    tone: Literal["premium", "acceptable", "pushy", "robotic"] = dspy.OutputField()
    brevity: Literal["good", "wordy"] = dspy.OutputField(desc="replies short enough for speech")
    handled_edge_case: Literal["well", "poorly", "not_applicable"] = dspy.OutputField()
    notes: str = dspy.OutputField(desc="one sentence on the biggest weakness")


def score(judgement, expected: dict, outcome: str, disposition: str) -> tuple[float, dict]:
    """Reduce a judgement to one comparable number plus its components."""
    parts = {
        "asked_permission": 1.0 if judgement.asked_permission else 0.0,
        "checkpoints": min(int(judgement.checkpoints_covered), 4) / 4,
        "no_repeats": 0.0 if judgement.repeated_a_question else 1.0,
        "pitch": {"strong": 1.0, "adequate": 0.6, "weak": 0.2, "not_applicable": 1.0}[
            judgement.pitch_quality
        ],
        "cta": {"yes": 1.0, "no": 0.0, "not_applicable": 1.0}[judgement.made_cta],
        "tone": {"premium": 1.0, "acceptable": 0.6, "pushy": 0.0, "robotic": 0.2}[judgement.tone],
        "brevity": 1.0 if judgement.brevity == "good" else 0.4,
        "edge_case": {"well": 1.0, "poorly": 0.0, "not_applicable": 1.0}[
            judgement.handled_edge_case
        ],
        "outcome_correct": 1.0 if outcome in expected["outcome"] else 0.0,
        "disposition_correct": 1.0 if disposition in expected["disposition"] else 0.0,
    }
    return round(sum(parts.values()) / len(parts), 3), parts


async def evaluate(key: str, judge: dspy.Module) -> dict:
    persona = PERSONAS[key]
    snapshot = await play(persona)

    turns = [(m["role"], m["content"]) for m in snapshot["history"]]
    transcript = format_transcript(turns)

    qualification = extract_qualification(turns, settings)
    judgement = judge(transcript=transcript, persona=persona.profile)
    expected = EXPECTED.get(key, {"outcome": (), "disposition": ()})
    total, parts = score(judgement, expected, snapshot["outcome"], qualification.disposition)

    print(f"\n--- score ({key}): {total} ---")
    print(json.dumps(parts, indent=2))
    print(f"judge: {judgement.notes}")
    return {
        "persona": key,
        "score": total,
        "parts": parts,
        "outcome": snapshot["outcome"],
        "disposition": qualification.disposition,
        "turns": len(turns),
        "notes": judgement.notes,
        "transcript": transcript,
        "qualification": qualification.model_dump(),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("personas", nargs="*", help="persona keys to evaluate (default: all)")
    parser.add_argument("--no-mlflow", action="store_true", help="skip MLflow logging")
    args = parser.parse_args()

    keys = args.personas or list(PERSONAS)
    if unknown := [k for k in keys if k not in PERSONAS]:
        sys.exit(f"unknown persona(s): {', '.join(unknown)}")

    dspy.configure(lm=build_extraction_lm(settings))
    judge = dspy.ChainOfThought(CallJudge)

    results = [await evaluate(key, judge) for key in keys]
    overall = round(sum(r["score"] for r in results) / len(results), 3)

    print(f"\n{'=' * 72}")
    for r in results:
        print(f"{r['persona']:32s} {r['score']:.3f}  {r['outcome']:14s} {r['disposition']}")
    print(f"{'OVERALL':32s} {overall:.3f}")

    if not args.no_mlflow:
        _log(results, overall)


def _log(results: list[dict], overall: float) -> None:
    import mlflow

    from app.obs.mlflow_obs import init_mlflow

    init_mlflow(settings)
    with mlflow.start_run(run_name=f"eval-{len(results)}-personas"):
        mlflow.log_params(
            {
                "convo_model": settings.convo_model,
                "extract_model": settings.extract_model,
                "llm_provider": settings.llm_provider,
                "personas": ",".join(r["persona"] for r in results),
            }
        )
        mlflow.log_metric("overall_score", overall)
        for r in results:
            mlflow.log_metric(f"score.{r['persona']}", r["score"])
            for part, value in r["parts"].items():
                mlflow.log_metric(f"{part}.{r['persona']}", value)
        mlflow.log_table(
            {
                "persona": [r["persona"] for r in results],
                "score": [r["score"] for r in results],
                "outcome": [r["outcome"] for r in results],
                "disposition": [r["disposition"] for r in results],
                "notes": [r["notes"] for r in results],
                "transcript": [r["transcript"] for r in results],
            },
            artifact_file="evaluation.json",
        )
    print(f"\nlogged to MLflow at {settings.mlflow_tracking_uri}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as exc:
        sys.exit(f"error: {exc}\nhint: set GROQ_API_KEY in server/.env before evaluating")
