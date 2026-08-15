"""A live call cut off mid-exchange: the caller asked to be reached on WhatsApp,
the agent replied "could you please share your number?" — and hung up on its own
question. The reply and the outcome are decided in the same superstep, so the
graph can find a call finished on the very turn it asked for something."""

from app.agent.graph import _advance, _awaits_answer
from app.agent.state import initial_state


def state(**overrides):
    st = initial_state("call-1", None)
    st["permission_granted"] = True
    st["stage"] = "qualify"
    st.update(overrides)
    return st


def turn(role, content):
    return {"role": role, "content": content}


def test_a_reply_ending_in_a_question_is_recognised():
    assert _awaits_answer("Could you share your WhatsApp number?")
    assert not _awaits_answer("Thank you for your time, and all the best.")
    assert not _awaits_answer("  Wonderful. I'll have them call you.  ")


def test_the_call_stays_open_when_the_agent_just_asked_something():
    """The exact shape of the reported hang-up."""
    st = state(
        extracted={"busy": True},
        last_reply="Absolutely, could you please share your WhatsApp number?",
        history=[turn("user", "Can you just reach me out on WhatsApp and connect later?")],
    )
    out = _advance(st)
    assert out["outcome"] is None
    assert out["stage"] != "done"
    assert out["closing_deferred"] == 1


def test_the_call_ends_when_the_agent_closed_properly():
    st = state(
        extracted={"busy": True},
        last_reply="Of course — I'll have our Property Expert call you tomorrow evening.",
        history=[turn("user", "I'm in a meeting, call me later please")],
    )
    out = _advance(st)
    assert out["outcome"] == "callback"
    assert out["stage"] == "done"


def test_closing_is_only_held_once():
    """Bounded, so a talkative agent can never keep a finished call alive."""
    st = state(
        closing_deferred=1,
        extracted={"busy": True},
        last_reply="And what time would suit you best?",
        history=[turn("user", "Not now, some other time")],
    )
    out = _advance(st)
    assert out["outcome"] == "callback"
    assert out["stage"] == "done"


def test_a_do_not_call_request_is_honoured_immediately():
    """Respecting it outranks the tidiness of the goodbye."""
    st = state(
        last_reply="I understand — may I ask what prompted that?",
        history=[turn("user", "Please stop calling me, remove my number")],
    )
    out = _advance(st)
    assert out["outcome"] == "dnc"
    assert out["stage"] == "done"


def test_the_deferred_outcome_is_reached_on_the_following_turn():
    """Holding buys one turn to close on; it must not lose the outcome."""
    first = _advance(
        state(
            extracted={"busy": True},
            last_reply="Certainly, when would be a good time to call back?",
            history=[turn("user", "Can we do this later, I'm driving")],
        )
    )
    assert first["outcome"] is None

    second = _advance(
        state(
            closing_deferred=first["closing_deferred"],
            extracted={"busy": True, "callback_time": "tomorrow at six"},
            last_reply="Perfect, I'll have our Property Expert call you then.",
            history=[turn("user", "Tomorrow at six in the evening")],
        )
    )
    assert second["outcome"] == "callback"
    assert second["callback_time"] == "tomorrow at six"
