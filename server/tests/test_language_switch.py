"""A live Hindi call kept getting answered in English. The cause was ordering:
the language was stored by `advance`, which runs after the reply, so every turn
was answered in the language of the turn before it. These pin the ordering."""

from app.agent.graph import _resolve_language
from app.agent.state import initial_state
from app.prompts import language_directive, system_prompt_for_turn


def state(language="en", history=()):
    st = initial_state("call-1", None)
    st["language"] = language
    st["history"] = list(history)
    return st


def turn(text):
    return {"role": "user", "content": text}


def test_the_turn_the_caller_switches_is_already_hindi():
    """The bug: this used to resolve to 'en' and answer the Hindi turn in English."""
    st = state("en", [turn("अच्छा है यार, देख सकते हैं।")])
    assert _resolve_language(st) == "hi"


def test_the_language_holds_across_later_turns():
    st = state("hi", [turn("Haan ji, aage bataiye mujhe")])
    assert _resolve_language(st) == "hi"


def test_a_clear_english_turn_switches_back():
    st = state("hi", [turn("Actually, let's continue in English please.")])
    assert _resolve_language(st) == "en"


def test_an_ambiguous_turn_leaves_the_language_alone():
    st = state("hi", [turn("Haan, that works")])
    assert _resolve_language(st) == "hi"


def test_hindi_directive_forbids_both_english_and_devanagari():
    d = language_directive("hi")
    assert "Hinglish" in d and "Latin script" in d
    assert "Do NOT reply in English" in d and "Devanagari" in d


def test_the_directive_is_the_last_thing_in_the_prompt():
    """It only overrides the English history if the model reads it last."""
    prompt = system_prompt_for_turn(state("hi")).rstrip()
    assert prompt.endswith('Kya main aage bataun?"')


def test_english_calls_still_defer_to_a_caller_who_switches():
    assert "unless the caller does" in language_directive("en")
