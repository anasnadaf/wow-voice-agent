"""Rumik's muga voice reads a leading tone tag as delivery rather than speech.

That makes the tag audio markup: it must reach the synthesiser intact, must be
one of the six tags muga knows, and must never appear in the transcript, the
dashboard or the agent's memory of what it said.
"""

import pytest

from app.prompts.speech import (
    MUGA_TONE_RULES,
    TONE_TAGS,
    normalize_tone_tag,
    strip_speech_tags,
)


@pytest.mark.parametrize("tone", TONE_TAGS)
def test_a_supported_tag_is_left_alone(tone):
    line = f"[{tone}] Bilkul, main aapko bata deti hoon."
    assert normalize_tone_tag(line) == line


def test_a_missing_tag_gets_the_neutral_default():
    assert normalize_tone_tag("May I ask your budget?") == "[neutral] May I ask your budget?"


def test_an_invented_tag_is_corrected_rather_than_spoken():
    """The model reaching for '[warm]' must not put brackets in the caller's ear."""
    assert normalize_tone_tag("[warm] Lovely, thank you.") == "[neutral] Lovely, thank you."


def test_tag_casing_from_the_model_is_accepted():
    assert normalize_tone_tag("[Happy] Great!") == "[happy] Great!"


def test_only_the_opening_tag_counts():
    out = normalize_tone_tag("[happy] Good. [sad] Bad.")
    assert out.startswith("[happy] ")


@pytest.mark.parametrize(
    "raw,clean",
    [
        ("[happy] Bilkul, yeh accha option hai.", "Bilkul, yeh accha option hai."),
        ("[neutral] May I ask your budget?", "May I ask your budget?"),
        ("<sigh> I understand completely.", "I understand completely."),
        ("[excited] Wonderful! <laugh> Truly.", "Wonderful! Truly."),
        ("No tags at all here.", "No tags at all here."),
    ],
)
def test_the_transcript_shows_what_the_caller_heard(raw, clean):
    assert strip_speech_tags(raw) == clean


def test_stripping_survives_a_round_trip():
    spoken = "May I ask whether this is for your own use or as an investment?"
    assert strip_speech_tags(normalize_tone_tag(spoken)) == spoken


def test_the_rules_name_every_tag_the_model_may_use():
    for tone in TONE_TAGS:
        assert f"[{tone}]" in MUGA_TONE_RULES
