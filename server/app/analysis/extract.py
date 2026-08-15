"""Post-call qualification extraction.

A DSPy module turns the finished transcript into the structured record the
dashboard shows and the CRM handoff needs. Runs after hangup, so it uses
ChainOfThought for quality — latency is irrelevant here — on the fast
extraction model.
"""

from typing import Literal

import dspy
from pydantic import BaseModel

from app.config import Settings

Intent = Literal["self_use", "investment", "mixed", "unknown"]
Geography = Literal["comfortable", "objection", "unknown"]
Budget = Literal["fits", "stretch", "mismatch", "unknown"]
Timeline = Literal["comfortable", "concern", "unknown"]
Disposition = Literal["qualified", "not_qualified", "callback", "dnc", "wrong_person", "incomplete"]


class QualificationResult(BaseModel):
    intent: Intent
    geography: Geography
    budget: Budget
    timeline: Timeline
    language: Literal["en", "hi", "mixed"]
    sentiment: Literal["positive", "neutral", "negative", "irritated"]
    disposition: Disposition
    next_action: str
    summary: str


class QualificationSignature(dspy.Signature):
    """Assess a pre-sales call for 'Whispers of the Wind' premium villa plots
    (Nandi Valley, North Bengaluru; ₹92.4 lakh+ starting price; possession Dec 2029).

    Judge only from what the prospect actually said. A checkpoint the call never
    reached is 'unknown'. 'qualified' requires: permission was granted, no DNC
    request, and intent + budget at least partially positive. An explicit
    'don't call me' is always disposition 'dnc'.
    """

    transcript: str = dspy.InputField(desc="speaker-labelled transcript, one turn per line")
    intent: Intent = dspy.OutputField(desc="self-use vs investment interest")
    geography: Geography = dspy.OutputField(desc="comfort with the Nandi Hills/Devanahalli area")
    budget: Budget = dspy.OutputField(desc="fitment with the ₹92.4 lakh+ starting price")
    timeline: Timeline = dspy.OutputField(desc="comfort with ongoing project / Dec 2029 possession")
    language: Literal["en", "hi", "mixed"] = dspy.OutputField()
    sentiment: Literal["positive", "neutral", "negative", "irritated"] = dspy.OutputField()
    disposition: Disposition = dspy.OutputField()
    next_action: str = dspy.OutputField(desc="one concrete follow-up for the sales team")
    summary: str = dspy.OutputField(desc="2-3 sentence factual call summary")


class QualificationExtractor(dspy.Module):
    def __init__(self):
        super().__init__()
        self.assess = dspy.ChainOfThought(QualificationSignature)

    def forward(self, transcript: str) -> dspy.Prediction:
        return self.assess(transcript=transcript)


_DSPY_PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1", "groq_api_key"),
    "cerebras": ("https://api.cerebras.ai/v1", "cerebras_api_key"),
}


def build_extraction_lm(settings: Settings) -> dspy.LM:
    try:
        api_base, key_field = _DSPY_PROVIDERS[settings.llm_provider]
    except KeyError:
        raise ValueError(f"Unknown LLM_PROVIDER {settings.llm_provider!r}") from None
    return dspy.LM(
        f"openai/{settings.extract_model}",
        api_base=api_base,
        api_key=getattr(settings, key_field),
        temperature=0.0,
        max_tokens=1500,
    )


def format_transcript(turns: list[tuple[str, str]]) -> str:
    labels = {"user": "Prospect", "assistant": "Agent"}
    return "\n".join(f"{labels.get(role, role)}: {text}" for role, text in turns)


def extract_qualification(
    turns: list[tuple[str, str]],
    settings: Settings,
    lm: dspy.LM | None = None,
) -> QualificationResult:
    """Run the extractor over a finished call. `lm` is injectable for tests."""
    extractor = QualificationExtractor()
    with dspy.context(lm=lm or build_extraction_lm(settings)):
        pred = extractor(transcript=format_transcript(turns))
    return QualificationResult(
        intent=pred.intent,
        geography=pred.geography,
        budget=pred.budget,
        timeline=pred.timeline,
        language=pred.language,
        sentiment=pred.sentiment,
        disposition=pred.disposition,
        next_action=pred.next_action,
        summary=pred.summary,
    )
