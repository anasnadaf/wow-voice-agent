"""A live call ended itself when speech-to-text turned background noise into
"Eggworks" and the extractor called it a wrong number. These pin that shut."""

from app.agent.graph import _sanitize_exit_signals
from app.agent.state import initial_state


def state(**overrides):
    st = initial_state("call-1", "Asha")
    st.update(overrides)
    return st


def test_garbled_short_turn_cannot_end_the_call():
    ex = {"wrong_person": True, "not_interested": True, "busy": True}
    assert _sanitize_exit_signals(ex, state(), "Eggworks") == {}


def test_noise_transcribed_as_filler_cannot_end_the_call():
    assert _sanitize_exit_signals({"wrong_person": True}, state(), "Hmm hmm") == {}


def test_wrong_number_is_still_honoured_early_in_the_call():
    ex = {"wrong_person": True}
    kept = _sanitize_exit_signals(ex, state(permission_granted=False), "Sorry, wrong number")
    assert kept["wrong_person"] is True


def test_wrong_person_is_ignored_once_the_caller_has_engaged():
    ex = {"wrong_person": True}
    kept = _sanitize_exit_signals(ex, state(permission_granted=True), "No, I said a site visit")
    assert "wrong_person" not in kept


def test_a_real_refusal_still_ends_the_call():
    ex = {"not_interested": True}
    kept = _sanitize_exit_signals(ex, state(), "I am really not interested in this, thank you")
    assert kept["not_interested"] is True


def test_do_not_call_survives_even_a_short_turn():
    """dnc comes from an explicit-phrase regex, so noise cannot forge it."""
    ex = {"dnc": True}
    assert _sanitize_exit_signals(ex, state(permission_granted=True), "stop calling")["dnc"]


def test_checkpoint_answers_are_never_stripped():
    ex = {"intent": "investment", "budget": "fit", "permission": "granted"}
    assert _sanitize_exit_signals(dict(ex), state(), "Yes") == ex
