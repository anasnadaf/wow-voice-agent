import dspy
import pytest

from app.analysis.extract import (
    QualificationResult,
    build_extraction_lm,
    extract_qualification,
    format_transcript,
)
from app.config import Settings


def make_settings(**overrides) -> Settings:
    base = dict(_env_file=None, groq_api_key="k", cerebras_api_key="k2")
    base.update(overrides)
    return Settings(**base)


def test_format_transcript_labels_speakers():
    text = format_transcript([("assistant", "Hello!"), ("user", "Who is this?")])
    assert text == "Agent: Hello!\nProspect: Who is this?"


def test_extraction_lm_vendor_swap():
    assert "groq" in build_extraction_lm(make_settings()).kwargs["api_base"]
    assert (
        "cerebras" in build_extraction_lm(make_settings(llm_provider="cerebras")).kwargs["api_base"]
    )
    with pytest.raises(ValueError):
        build_extraction_lm(make_settings(llm_provider="nope"))


def test_extract_qualification_with_fake_lm():
    """End-to-end through DSPy with a canned LM — no network."""
    answer = {
        "reasoning": "Prospect asked to invest, fine with location and budget.",
        "intent": "investment",
        "geography": "comfortable",
        "budget": "fits",
        "timeline": "comfortable",
        "language": "en",
        "sentiment": "positive",
        "disposition": "qualified",
        "next_action": "Book a follow-up with a Property Expert.",
        "summary": "Interested investor, all four checkpoints positive.",
    }
    fake = dspy.utils.DummyLM([answer])
    result = extract_qualification(
        [("assistant", "May I speak?"), ("user", "Yes, I want to invest, budget is fine.")],
        make_settings(),
        lm=fake,
    )
    assert isinstance(result, QualificationResult)
    assert result.disposition == "qualified"
    assert result.intent == "investment"
