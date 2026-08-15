"""Integration seams: engine↔pipeline bridge, call lifecycle, telephony vendor pick."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app import call_flow
from app.db.models import Call, CallStatus, Lead, Turn
from app.voice.bridge import latest_user_text
from app.voice.transcript import TranscriptTurn


@pytest.fixture
def use_test_db(db_sessionmaker, monkeypatch):
    monkeypatch.setattr("app.db.session.SessionLocal", db_sessionmaker)
    return db_sessionmaker


async def seed_call(db_sessionmaker) -> tuple[uuid.UUID, uuid.UUID]:
    async with db_sessionmaker() as db:
        lead = Lead(name="Asha Rao", phone="+919876543210", consent=True)
        db.add(lead)
        await db.flush()
        call = Call(lead_id=lead.id)
        db.add(call)
        await db.commit()
        return call.id, lead.id


def test_latest_user_text_picks_last_user_message():
    from pipecat.processors.aggregators.llm_context import LLMContext

    ctx = LLMContext(
        messages=[
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "second"},
        ]
    )
    assert latest_user_text(ctx) == "second"


async def test_stream_lifecycle_transitions(use_test_db):
    call_id, _ = await seed_call(use_test_db)

    await call_flow.mark_stream_connected(call_id)
    async with use_test_db() as db:
        call = await db.get(Call, call_id)
        assert call.status is CallStatus.in_progress
        assert call.started_at is not None

    await call_flow.persist_turn(
        call_id, TranscriptTurn(role="assistant", text="Hello!", t_offset_ms=100)
    )
    await call_flow.persist_turn(
        call_id, TranscriptTurn(role="user", text="Yes, tell me more", t_offset_ms=4000)
    )

    await call_flow.finalize_call(
        call_id,
        turns=[],  # < 2 turns → extraction skipped; mlflow guarded
        recording_path=None,
        agent_snapshot={"language": "hi", "outcome": "qualified"},
        metrics={"llm_ttfb_avg_s": 0.4},
    )
    async with use_test_db() as db:
        call = await db.get(Call, call_id)
        assert call.status is CallStatus.completed
        assert call.ended_at is not None
        assert call.language == "hi"
        assert call.agent_snapshot["outcome"] == "qualified"
        turns = (await db.scalars(select(Turn).where(Turn.call_id == call_id))).all()
        assert {t.role for t in turns} == {"assistant", "user"}


async def test_provider_status_maps_and_never_regresses(use_test_db):
    call_id, _ = await seed_call(use_test_db)

    await call_flow.apply_provider_status(call_id, {"CallStatus": "ringing", "CallUUID": "cu-1"})
    async with use_test_db() as db:
        call = await db.get(Call, call_id)
        assert call.status is CallStatus.ringing
        assert call.provider_call_id == "cu-1"

    await call_flow.apply_provider_status(call_id, {"CallStatus": "no-answer"})
    async with use_test_db() as db:
        call = await db.get(Call, call_id)
        assert call.status is CallStatus.no_answer
        assert call.ended_at is not None

    # a late webhook must not resurrect the call
    await call_flow.apply_provider_status(call_id, {"CallStatus": "ringing"})
    async with use_test_db() as db:
        call = await db.get(Call, call_id)
        assert call.status is CallStatus.no_answer


async def test_finalize_is_idempotent_on_terminal_calls(use_test_db):
    call_id, _ = await seed_call(use_test_db)
    async with use_test_db() as db:
        call = await db.get(Call, call_id)
        call.status = CallStatus.busy
        call.ended_at = datetime.now(UTC)
        await db.commit()

    await call_flow.finalize_call(call_id, turns=[], recording_path=None, agent_snapshot=None)
    async with use_test_db() as db:
        call = await db.get(Call, call_id)
        assert call.status is CallStatus.busy  # terminal status preserved


async def test_bridge_streams_engine_reply_and_ends_pipeline(monkeypatch):
    from pipecat.frames.frames import (
        EndTaskFrame,
        LLMFullResponseEndFrame,
        LLMFullResponseStartFrame,
        LLMTextFrame,
    )
    from pipecat.processors.aggregators.llm_context import LLMContext

    from app.voice.bridge import EngineLLMService

    class StubEngine:
        def __init__(self):
            self.done = False
            self.state = {"outcome": "qualified"}

        @property
        def is_done(self):
            return self.done

        async def stream_turn(self, text):
            assert text == "I want to invest"
            yield "Wonderful — "
            yield "let me note that."
            self.done = True

    svc = EngineLLMService(StubEngine())
    pushed: list = []

    async def capture(frame, direction=None):
        pushed.append(frame)

    monkeypatch.setattr(svc, "push_frame", capture)
    for m in (
        "start_processing_metrics",
        "stop_processing_metrics",
        "start_ttfb_metrics",
        "stop_ttfb_metrics",
    ):

        async def noop():
            pass

        monkeypatch.setattr(svc, m, noop)

    ctx = LLMContext(messages=[{"role": "user", "content": "I want to invest"}])
    await svc._run_turn(ctx)

    kinds = [type(f) for f in pushed]
    assert kinds[0] is LLMFullResponseStartFrame
    assert kinds.count(LLMTextFrame) == 2
    assert LLMFullResponseEndFrame in kinds
    assert kinds[-1] is EndTaskFrame  # engine done → pipeline asked to end
    texts = [f.text for f in pushed if isinstance(f, LLMTextFrame)]
    assert "".join(texts) == "Wonderful — let me note that."


def test_telephony_vendor_selection(monkeypatch):
    from app import telephony

    monkeypatch.setattr("app.config.settings.telephony_provider", "plivo")
    monkeypatch.setattr("app.config.settings.plivo_auth_id", "MA_X")
    telephony.configure_from_settings()
    assert isinstance(telephony.get_telephony(), telephony.PlivoTelephony)

    monkeypatch.setattr("app.config.settings.plivo_auth_id", "")
    telephony.configure_from_settings()
    assert isinstance(telephony.get_telephony(), telephony.NullTelephony)
