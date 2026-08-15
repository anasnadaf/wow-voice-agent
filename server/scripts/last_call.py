"""Show what the agent made of the most recent call.

Run this straight after hanging up a test call — it prints the transcript as it
was stored, the state the graph ended in, and the post-call extraction, which is
everything needed to tell a good call from a regression.

    uv run python -m scripts.last_call        # the latest call
    uv run python -m scripts.last_call 3      # the latest three
"""

import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import Call, Qualification, Turn
from app.db.session import SessionLocal

_RULE = "─" * 78


def _fmt_turn(turn: Turn) -> str:
    who = "CALLER" if turn.role == "user" else "ANANYA"
    return f"  {turn.t_offset_ms / 1000:6.1f}s  {who}  {turn.text}"


def _fmt_snapshot(snapshot: dict | None) -> list[str]:
    if not snapshot:
        return ["  (no agent state recorded — the call never reached the engine)"]
    slots = snapshot.get("slots") or {}
    answered = {k: v for k, v in slots.items() if v is not None}
    lines = [
        f"  outcome          {snapshot.get('outcome') or '—'}",
        f"  stage            {snapshot.get('stage')}",
        f"  language         {snapshot.get('language')}",
        f"  checkpoints      {answered or '— none answered —'}",
    ]
    if snapshot.get("callback_time"):
        lines.append(f"  callback time    {snapshot['callback_time']}")
    # the guards that decide whether a call ends, and why
    for field, label in (
        ("closing_deferred", "closing held"),
        ("irritation_level", "irritation"),
        ("objection_count", "objections"),
    ):
        if snapshot.get(field):
            lines.append(f"  {label:15s}  {snapshot[field]}")
    return lines


def _fmt_qualification(q: Qualification | None) -> list[str]:
    if q is None:
        return ["  (not extracted — calls under two turns are skipped)"]
    return [
        f"  disposition      {q.disposition or '—'}",
        f"  sentiment        {q.sentiment or '—'}",
        f"  next action      {q.next_action or '—'}",
        f"  summary          {q.summary or '—'}",
    ]


async def main(limit: int) -> None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Call)
            .options(selectinload(Call.turns), selectinload(Call.qualification))
            .order_by(Call.created_at.desc())
            .limit(limit)
        )
        calls = list(result.scalars())

    if not calls:
        print("no calls recorded yet")
        return

    for call in reversed(calls):
        duration = f"{call.duration_s}s" if call.duration_s is not None else "—"
        print(f"\n{_RULE}\ncall {call.id}  [{call.status}]  {duration}\n{_RULE}")
        turns = sorted(call.turns, key=lambda t: t.t_offset_ms)
        print("\n".join(_fmt_turn(t) for t in turns) or "  (no turns recorded)")
        print("\n  ── agent state ──")
        print("\n".join(_fmt_snapshot(call.agent_snapshot)))
        print("\n  ── post-call extraction ──")
        print("\n".join(_fmt_qualification(call.qualification)))
        if call.recording_path:
            print(f"\n  recording        {call.recording_path}")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 1))
