"""Browser demo sessions are first-class calls: no phone lead, same artifacts."""

import pytest

from app import call_flow
from app.db.models import Call, CallStatus
from app.voice.transcript import TranscriptTurn


@pytest.fixture
def use_test_db(db_sessionmaker, monkeypatch):
    monkeypatch.setattr("app.db.session.SessionLocal", db_sessionmaker)
    return db_sessionmaker


async def test_web_call_is_created_without_a_lead(use_test_db):
    call_id = await call_flow.create_web_call("Priya")
    async with use_test_db() as db:
        call = await db.get(Call, call_id)
        assert call.channel == "web"
        assert call.lead_id is None
        assert call.visitor_name == "Priya"
        assert call.status is CallStatus.requested


async def test_anonymous_visitor_is_allowed(use_test_db):
    call_id = await call_flow.create_web_call(None)
    async with use_test_db() as db:
        assert (await db.get(Call, call_id)).visitor_name is None


async def test_web_call_produces_the_same_artifacts_as_a_phone_call(use_test_db):
    call_id = await call_flow.create_web_call("Priya")
    await call_flow.mark_stream_connected(call_id)
    await call_flow.persist_turn(
        call_id, TranscriptTurn(role="assistant", text="Is now a good time?", t_offset_ms=400)
    )
    await call_flow.persist_turn(
        call_id, TranscriptTurn(role="user", text="Yes, go ahead.", t_offset_ms=3000)
    )
    await call_flow.finalize_call(
        call_id,
        turns=[],
        recording_path=None,
        agent_snapshot={"language": "en", "outcome": "qualified"},
    )
    async with use_test_db() as db:
        call = await db.get(Call, call_id)
        assert call.status is CallStatus.completed
        assert call.ended_at is not None
        assert call.agent_snapshot["outcome"] == "qualified"
        await db.refresh(call, ["turns"])
        assert len(call.turns) == 2


async def test_set_status_marks_failure_and_respects_terminal(use_test_db):
    call_id = await call_flow.create_web_call(None)
    await call_flow.set_status(call_id, CallStatus.failed)
    async with use_test_db() as db:
        call = await db.get(Call, call_id)
        assert call.status is CallStatus.failed
        assert call.ended_at is not None

    await call_flow.set_status(call_id, CallStatus.in_progress)
    async with use_test_db() as db:
        assert (await db.get(Call, call_id)).status is CallStatus.failed


async def test_call_detail_endpoint_renders_a_leadless_call(client, use_test_db):
    call_id = await call_flow.create_web_call("Priya")
    resp = await client.get(f"/api/calls/{call_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["lead"] is None
    assert body["channel"] == "web"
    assert body["visitor_name"] == "Priya"


async def test_calls_list_includes_web_calls(client, use_test_db):
    await call_flow.create_web_call("Priya")
    resp = await client.get("/api/calls")
    assert resp.status_code == 200
    assert [c["channel"] for c in resp.json()] == ["web"]
