"""Re-run post-call extraction over calls that never got one.

Extraction is best-effort during a call — a provider hiccup is logged and the
call still completes — so a run of failures can leave real conversations with an
empty Qualification card. This replays them from the stored transcript.

    uv run python -m scripts.backfill_qualifications          # what's missing
    uv run python -m scripts.backfill_qualifications --apply  # extract and save
"""

import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.analysis.extract import extract_qualification
from app.config import settings
from app.db import session as db_session
from app.db.models import Call, Qualification


async def _calls_missing_qualification() -> list[Call]:
    async with db_session.SessionLocal() as db:
        result = await db.execute(
            select(Call)
            .outerjoin(Qualification)
            .where(Qualification.id.is_(None))
            .options(selectinload(Call.turns))
            .order_by(Call.created_at)
        )
        return list(result.scalars())


async def _save(call_id, qualification) -> None:
    async with db_session.SessionLocal() as db:
        row = Qualification(call_id=call_id)
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
        db.add(row)
        await db.commit()


async def main(apply: bool) -> None:
    calls = await _calls_missing_qualification()
    # the live path skips these too — one exchange is not a conversation
    eligible = [c for c in calls if len(c.turns) >= 2]
    skipped = len(calls) - len(eligible)

    print(f"{len(calls)} calls without a qualification ({skipped} too short to extract)")
    if not apply:
        for call in eligible:
            print(f"  would extract {call.id}  ({len(call.turns)} turns)")
        if eligible:
            print("\nre-run with --apply to extract and save")
        return

    for call in eligible:
        turns = sorted(call.turns, key=lambda t: t.t_offset_ms)
        try:
            result = await asyncio.to_thread(
                extract_qualification, [(t.role, t.text) for t in turns], settings
            )
        except Exception as exc:
            print(f"  FAILED  {call.id}: {exc}")
            continue
        await _save(call.id, result)
        print(f"  saved   {call.id}  disposition={result.disposition} sentiment={result.sentiment}")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
