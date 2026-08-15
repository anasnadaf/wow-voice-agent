"""Conversation graph tests — run entirely on scripted fake LLMs, no API key needed."""

import json

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.agent import ConversationEngine
from app.agent.state import next_checkpoint
from app.prompts import system_prompt_for_turn

OK = "Understood, thank you."


def scripted(*texts: str) -> GenericFakeChatModel:
    """A chat model that replays the given responses in order (streams word by word)."""
    return GenericFakeChatModel(messages=iter([AIMessage(content=t) for t in texts]))


def make_engine(
    replies: list[str], extractions: list[str], lead_name: str | None = "Rahul"
) -> ConversationEngine:
    return ConversationEngine(
        "call-test",
        lead_name,
        reply_llm=scripted(*replies),
        extract_llm=scripted(*extractions),
    )


async def run_turn(engine: ConversationEngine, text: str) -> str:
    return "".join([chunk async for chunk in engine.stream_turn(text)])


def test_opening_line_mentions_project_location_and_permission():
    engine = make_engine([], [])
    line = engine.opening_line()
    assert "Whispers of the Wind" in line
    assert "Nandi Hills" in line
    assert "Rahul" in line
    assert "good time" in line.lower()
    # the greeting is already part of the transcript
    assert engine.state["history"][0]["content"] == line


async def test_permission_denied_polite_exit():
    engine = make_engine(
        ["No problem at all — thank you for your time, have a lovely day."],
        ['{"permission": "denied"}'],
    )
    reply = await run_turn(engine, "No, I'm not interested in talking.")
    assert "thank you" in reply.lower()
    assert engine.state["outcome"] == "declined"
    assert engine.state["stage"] == "done"
    assert engine.is_done


async def test_slots_fill_across_turns_and_are_never_reasked():
    engine = make_engine(
        [OK] * 4,
        [
            '{"permission": "granted"}',
            # two checkpoints volunteered at once, out of order
            '{"intent": "self_use", "timeline": "comfortable"}',
            '{"geography": "positive"}',
            '{"budget": "fit"}',
        ],
    )
    await run_turn(engine, "Sure, go ahead.")
    assert engine.state["permission_granted"]
    assert engine.state["stage"] == "qualify"

    await run_turn(engine, "It's for my own use, and the 2029 possession is fine with us.")
    slots = engine.state["slots"]
    assert slots["intent"] == "self_use"
    assert slots["timeline"] == "comfortable"
    # neither volunteered answer may be asked again; next target skips to geography
    assert next_checkpoint(slots) == "geography"
    prompt = system_prompt_for_turn(engine.state)
    assert "never ask these again" in prompt
    assert "intent:" in prompt and "timeline:" in prompt
    assert "Next checkpoint to pursue (exactly one question): geography" in prompt

    await run_turn(engine, "North Bengaluru works for us.")
    assert engine.state["slots"]["geography"] == "comfortable"
    assert "Next checkpoint to pursue (exactly one question): budget" in system_prompt_for_turn(
        engine.state
    )

    await run_turn(engine, "Budget is fine.")
    assert next_checkpoint(engine.state["slots"]) is None
    assert engine.state["stage"] == "pitch"
    assert engine.state["outcome"] is None


async def test_dnc_phrase_marks_dnc():
    engine = make_engine(
        ["I completely understand — you won't receive further calls from us. Sorry to disturb."],
        ['{"dnc": true}'],
    )
    await run_turn(engine, "Stop calling this number.")
    assert engine.state["outcome"] == "dnc"
    assert engine.is_done


async def test_dnc_regex_guard_catches_extractor_miss():
    engine = make_engine(["Of course, apologies for the disturbance."], ["{}"])
    await run_turn(engine, "Please don't call me again.")
    assert engine.state["outcome"] == "dnc"


async def test_irritation_deescalates_once_then_exits():
    engine = make_engine(
        [
            "I'm sorry to catch you at a bad moment — shall I keep it to thirty seconds?",
            "My apologies for the trouble — I'll let you go. Have a good day.",
        ],
        ['{"irritated": true}', '{"irritated": true}'],
    )
    await run_turn(engine, "Ugh, another sales call?")
    assert engine.state["irritation_level"] == 1
    assert not engine.is_done
    assert "already sounded irritated" in system_prompt_for_turn(engine.state)

    await run_turn(engine, "I said I don't want this, stop bothering me!")
    assert engine.state["irritation_level"] == 2
    assert engine.state["outcome"] == "abandoned"
    assert engine.is_done


async def test_hindi_detection_flips_language_and_back():
    engine = make_engine(
        [OK] * 3,
        ['{"language": "hi", "permission": "granted"}', "{}", '{"language": "en"}'],
    )
    await run_turn(engine, "Haan boliye, kya hai yeh project?")
    assert engine.state["language"] == "hi"
    assert "Hinglish" in system_prompt_for_turn(engine.state)

    # Devanagari guard works even when the extractor returns nothing
    await run_turn(engine, "मुझे थोड़ा और बताइए")
    assert engine.state["language"] == "hi"

    await run_turn(engine, "Actually let's continue in English.")
    assert engine.state["language"] == "en"


async def test_busy_user_gets_callback():
    engine = make_engine(
        ["Of course — I'll arrange a call tomorrow at six in the evening. Thank you!"],
        ['{"busy": true, "callback_time": "tomorrow 6 pm"}'],
    )
    await run_turn(engine, "I'm in a meeting, call me tomorrow evening around 6.")
    assert engine.state["outcome"] == "callback"
    assert engine.state["callback_time"] == "tomorrow 6 pm"
    assert engine.is_done


async def test_budget_mismatch_polite_exit():
    engine = make_engine(
        [OK, "Completely understood — I'll keep you in mind for suitable launches. Thank you!"],
        ['{"permission": "granted"}', '{"budget": "mismatch"}'],
    )
    await run_turn(engine, "Yes, tell me.")
    await run_turn(engine, "That's way beyond us — we were thinking under forty lakhs.")
    assert engine.state["outcome"] == "not_qualified"
    assert engine.is_done


async def test_location_objection_gets_one_reframe_then_exit():
    engine = make_engine(
        [OK, OK, "That's fair — thank you so much for your time."],
        [
            '{"permission": "granted"}',
            '{"geography": "negative", "budget": "fit"}',
            '{"geography": "negative"}',
        ],
    )
    await run_turn(engine, "Sure.")
    await run_turn(engine, "Budget is fine but Doddaballapura feels too far out.")
    assert engine.state["slots"]["geography"] == "hesitant"
    assert engine.state["objection_count"] == 1
    assert not engine.is_done
    assert "reframe has already been offered once" in system_prompt_for_turn(engine.state)

    await run_turn(engine, "No, it's really too far for us.")
    assert engine.state["slots"]["geography"] == "rejected"
    assert engine.state["outcome"] == "not_qualified"


async def test_happy_path_pitch_cta_qualified():
    pitch = (
        "Picture a thirty eight acre valley near Nandi Hills with seventy four percent "
        "open spaces and a twenty thousand square feet clubhouse. May I arrange a call "
        "with our Property Expert?"
    )
    engine = make_engine(
        [OK, OK, OK, OK, pitch, "Perfect — our Property Expert will call you. Thank you!"],
        [
            '{"permission": "granted"}',
            '{"intent": "investment"}',
            '{"geography": "positive", "timeline": "comfortable"}',
            '{"budget": "fit"}',
            "{}",
            '{"cta_accepted": true}',
        ],
    )
    await run_turn(engine, "Yes, go ahead.")
    await run_turn(engine, "Purely as an investment.")
    await run_turn(engine, "The area is great, and 2029 possession is fine.")
    await run_turn(engine, "Budget-wise we're comfortable around a crore.")
    assert engine.state["stage"] == "pitch"

    chunks = [chunk async for chunk in engine.stream_turn("Okay, sounds interesting.")]
    assert len(chunks) > 1  # reply arrives as a stream, not one blob
    assert "".join(chunks) == pitch
    assert engine.state["stage"] == "cta"

    await run_turn(engine, "Yes, please set that up.")
    assert engine.state["outcome"] == "qualified"
    assert engine.is_done
    # transcript captured both sides of every exchange
    assert engine.state["history"][-1]["content"].startswith("Perfect")
    assert engine.state["history"][-2]["content"] == "Yes, please set that up."


async def test_snapshot_is_json_serializable():
    engine = make_engine([OK], ['{"permission": "granted"}'])
    await run_turn(engine, "Sure.")
    snapshot = engine.snapshot()
    restored = json.loads(json.dumps(snapshot))
    assert restored["call_id"] == "call-test"
    assert restored["stage"] == "qualify"
