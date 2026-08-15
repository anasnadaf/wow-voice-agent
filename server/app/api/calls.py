import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import telephony
from app.api.deps import DbSession
from app.api.ratelimit import client_ip, public_call_limiter
from app.api.schemas import CallCreate, CallDetailOut, CallOut
from app.auth import require_admin, verify_admin
from app.db.models import Call, Lead

router = APIRouter(prefix="/api/calls", tags=["calls"])


async def _resolve_lead_public(body: CallCreate, request: Request, db: AsyncSession) -> Lead:
    """Public shape: {name, phone, consent} — upsert the lead by phone."""
    if not body.name or not body.phone:
        raise HTTPException(status_code=422, detail="name and phone are required")
    if body.consent is not True:
        raise HTTPException(status_code=422, detail="consent is required to request a call")
    public_call_limiter.check(client_ip(request))

    lead = await db.scalar(select(Lead).where(Lead.phone == body.phone))
    if lead:
        lead.name = body.name
        lead.consent = True
    else:
        lead = Lead(name=body.name, phone=body.phone, source="web", consent=True)
        db.add(lead)
        await db.flush()
    return lead


@router.post("", response_model=CallOut, status_code=201)
async def create_call(body: CallCreate, request: Request, db: DbSession) -> Call:
    if body.lead_id is not None:
        # admin shape: {lead_id}
        await verify_admin(request.headers.get("authorization"))
        lead = await db.get(Lead, body.lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="Lead not found")
    else:
        lead = await _resolve_lead_public(body, request, db)

    if lead.dnc:
        raise HTTPException(status_code=403, detail="This number has opted out of calls")

    call = Call(lead_id=lead.id)
    db.add(call)
    await db.flush()

    call.provider_call_id = await telephony.originate_call(call, lead)
    await db.commit()

    row = await db.scalar(select(Call).where(Call.id == call.id).options(selectinload(Call.lead)))
    assert row is not None
    return row


@router.get("", response_model=list[CallOut], dependencies=[Depends(require_admin)])
async def list_calls(db: DbSession, limit: int = 50, offset: int = 0) -> list[Call]:
    rows = await db.scalars(
        select(Call)
        .options(selectinload(Call.lead))
        .order_by(Call.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows)


@router.get("/{call_id}", response_model=CallDetailOut, dependencies=[Depends(require_admin)])
async def get_call(call_id: uuid.UUID, db: DbSession) -> CallDetailOut:
    call = await db.scalar(
        select(Call)
        .where(Call.id == call_id)
        .options(
            selectinload(Call.lead),
            selectinload(Call.turns),
            selectinload(Call.qualification),
        )
    )
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    out = CallDetailOut.model_validate(call)
    if call.recording_path and Path(call.recording_path).is_file():
        out.recording_url = f"/api/calls/{call.id}/recording"
    return out


@router.get("/{call_id}/recording", dependencies=[Depends(require_admin)])
async def get_recording(call_id: uuid.UUID, db: DbSession) -> FileResponse:
    call = await db.get(Call, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    if not call.recording_path or not Path(call.recording_path).is_file():
        raise HTTPException(status_code=404, detail="No recording for this call")
    return FileResponse(call.recording_path)  # media type inferred from the file name
