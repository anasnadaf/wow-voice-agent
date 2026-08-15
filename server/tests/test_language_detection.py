"""Language detection decides which language the agent speaks, so it is worth
pinning down precisely. Real lines from simulated calls, no model involved."""

import pytest

from app.agent.graph import _detect_language


@pytest.mark.parametrize(
    "text",
    [
        "मुझे प्लॉट के बारे में जानकारी चाहिए",  # devanagari always wins
        "Haan ji, boliye, kaun bol raha hai? Main Ramesh hoon.",
        "Bilkul, mujhe yeh project acha laga",
        "Haan ji, aapke liye dhanyavad, main wait karunga",
    ],
)
def test_hindi_and_hinglish_are_detected(text):
    assert _detect_language(text, "en") == "hi"


@pytest.mark.parametrize(
    "text",
    [
        "Yes, this is Vikram, and it's a great time to talk.",
        # the bug this guards: Indian English is not Hinglish
        "My budget is up to three crore rupees, around ninety two lakh is fine.",
        "Namaste, I am looking for a plot near the airport.",
        "I would like to know about the clubhouse and the possession timeline.",
    ],
)
def test_indian_english_stays_english(text):
    assert _detect_language(text, "en") == "en"


def test_a_single_marker_does_not_flip_the_call():
    """One stray word is too weak to decide, so the call stays where it was."""
    assert _detect_language("Haan, that works for me", "en") == "en"
    assert _detect_language("Haan, that works for me", "hi") == "hi"


def test_clear_english_switches_back_from_hindi():
    assert _detect_language("Sorry, could you continue in English please?", "hi") == "en"


def test_empty_turn_leaves_the_language_alone():
    assert _detect_language("", "hi") is None
    assert _detect_language("   ", "en") is None
