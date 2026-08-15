"""Call lifecycle: DB state transitions and the post-call analysis chain.

The voice pipeline and the Plivo webhooks both land here; this module is the
only writer of Call/Turn/Qualification rows outside the REST API. Sessions
come from a module-level factory so tests can swap in SQLite.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import select

from app.analysis.extract import extract_qualification
from app.config import settings
from app.db import session as db_session
from app.db.models import Call, CallStatus, Lead, Qualification, Turn
from app.voice.transcript import TranscriptTurn

# Terminal states never regress (a late "ringing" webhook must not resurrect
# a completed call).
_TERMINAL = {CallStatus.completed, CallStatus.failed, CallStatus.no_answer, CallStatus.busy}

_PLIVO_STATUS_MAP = {
    "ringing": CallStatus.ringing,
    "in-progress": CallStatus.in_progress,
    "completed": CallStatus.completed,
    "busy": CallStatus.busy,
    "failed": CallStatus.failed,
    "timeout": CallStatus.no_answer,
    "no-answer": CallStatus.no_answer,
    "cancel": CallStatus.failed,
}


def _now() -> datetime:
    return datetime.now(UTC)


def _elapsed_s(started: datetime, ended: datetime) -> int:
    """Seconds between two stamps, tolerating naive values.

    Postgres hands back timezone-aware datetimes; SQLite (tests) drops the
    offset, so a stored stamp can come back naive and refuse to subtract.
    """
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    if ended.tzinfo is None:
        ended = ended.replace(tzinfo=UTC)
    return int((ended - started).total_seconds())


async def create_web_call(visitor_name: str | None, call_id: uuid.UUID | None = None) -> uuid.UUID:
    """A browser demo session gets a real Call row, with no phone lead.

    The caller may supply the id so it can name things (the agent, the
    recording) before the row exists.
    """
    async with db_session.SessionLocal() as db:
        call = Call(
            id=call_id or uuid.uuid4(),
            channel="web",
            visitor_name=visitor_name,
            status=CallStatus.requested,
        )
        db.add(call)
        await db.commit()
        return call.id


async def set_status(call_id: uuid.UUID, status: CallStatus) -> None:
    async with db_session.SessionLocal() as db:
        call = await db.get(Call, call_id)
        if call is None or call.status in _TERMINAL:
            return
        call.status = status
        if status in _TERMINAL:
            call.ended_at = call.ended_at or _now()
        await db.commit()


async def load_call(call_id: uuid.UUID) -> tuple[Call, Lead | None] | None:
    """Load a call and its lead, if it has one — web demo calls do not."""
    async with db_session.SessionLocal() as db:
        call = await db.get(Call, call_id)
        if call is None:
            return None
        lead = await db.get(Lead, call.lead_id) if call.lead_id else None
        return call, lead


async def mark_stream_connected(call_id: uuid.UUID) -> None:
    async with db_session.SessionLocal() as db:
        call = await db.get(Call, call_id)
        if call is None:
            return
        if call.status not in _TERMINAL:
            call.status = CallStatus.in_progress
            call.started_at = call.started_at or _now()
            await db.commit()


async def persist_turn(call_id: uuid.UUID, turn: TranscriptTurn) -> None:
    async with db_session.SessionLocal() as db:
        db.add(Turn(call_id=call_id, role=turn.role, text=turn.text, t_offset_ms=turn.t_offset_ms))
        await db.commit()


async def apply_provider_status(call_id: uuid.UUID, params: dict[str, Any]) -> None:
    raw = str(params.get("CallStatus") or params.get("Event") or "").lower()
    status = _PLIVO_STATUS_MAP.get(raw)
    if status is None:
        return
    async with db_session.SessionLocal() as db:
        call = await db.get(Call, call_id)
        if call is None or call.status in _TERMINAL:
            return
        call.status = status
        if status is CallStatus.in_progress and call.started_at is None:
            call.started_at = _now()
        if status in _TERMINAL:
            call.ended_at = call.ended_at or _now()
            if call.started_at and call.duration_s is None:
                call.duration_s = _elapsed_s(call.started_at, call.ended_at)
        if params.get("CallUUID") and not call.provider_call_id:
            call.provider_call_id = str(params["CallUUID"])
        await db.commit()


async def finalize_call(
    call_id: uuid.UUID,
    *,
    turns: list[TranscriptTurn],
    recording_path: Path | None,
    agent_snapshot: dict | None,
    metrics: dict[str, float] | None = None,
) -> None:
    """Voice session ended: close out the row, then run analysis + observability."""
    async with db_session.SessionLocal() as db:
        call = await db.get(Call, call_id)
        if call is None:
            return
        if call.status not in _TERMINAL:
            call.status = CallStatus.completed
        call.ended_at = call.ended_at or _now()
        if call.started_at and call.duration_s is None:
            call.duration_s = _elapsed_s(call.started_at, call.ended_at)
        if recording_path and Path(recording_path).is_file():
            call.recording_path = str(recording_path)
        if agent_snapshot:
            call.agent_snapshot = agent_snapshot
            call.language = agent_snapshot.get("language") or call.language
        await db.commit()

    await _analyze_call(call_id, turns, recording_path, agent_snapshot, metrics or {})


async def _analyze_call(
    call_id: uuid.UUID,
    turns: list[TranscriptTurn],
    recording_path: Path | None,
    agent_snapshot: dict | None,
    metrics: dict[str, float],
) -> None:
    qualification = None
    if len(turns) >= 2:
        try:
            qualification = await asyncio.to_thread(
                extract_qualification,
                [(t.role, t.text) for t in turns],
                settings,
            )
        except Exception as exc:
            logger.warning(f"call {call_id}: qualification extraction failed: {exc}")

    if qualification is not None:
        async with db_session.SessionLocal() as db:
            existing = await db.scalar(
                select(Qualification).where(Qualification.call_id == call_id)
            )
            row = existing or Qualification(call_id=call_id)
            for field in (
                "intent",
                "geography",
                "budget",
                "timeline",
                "language",
                "sentiment",
                "disposition",
                "next_action",
                "summary",
            ):
                setattr(row, field, getattr(qualification, field))
            row.raw = qualification.model_dump()
            if existing is None:
                db.add(row)
            await db.commit()

    try:
        _log_to_mlflow(call_id, turns, recording_path, agent_snapshot, metrics, qualification)
    except Exception as exc:  # observability must never break the call path
        logger.warning(f"call {call_id}: mlflow logging failed: {exc}")


def _log_to_mlflow(call_id, turns, recording_path, agent_snapshot, metrics, qualification):
    from app.obs.mlflow_obs import CallRun

    with CallRun(str(call_id), settings) as run:
        run.log_metrics(
            {
                "turns_total": len(turns),
                "turns_user": sum(1 for t in turns if t.role == "user"),
                **({"duration_s": turns[-1].t_offset_ms / 1000} if turns else {}),
                **metrics,
            }
        )
        run.log_json(
            "transcript.json",
            [{"role": t.role, "text": t.text, "t_offset_ms": t.t_offset_ms} for t in turns],
        )
        if agent_snapshot:
            run.log_json("agent_state.json", agent_snapshot)
        if qualification is not None:
            run.log_json("qualification.json", qualification.model_dump())
        if recording_path:
            run.log_file(recording_path)
