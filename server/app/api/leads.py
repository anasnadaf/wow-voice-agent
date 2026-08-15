from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.deps import DbSession
from app.api.schemas import LeadCreate, LeadOut
from app.auth import require_admin
from app.db.models import Lead

router = APIRouter(prefix="/api/leads", tags=["leads"], dependencies=[Depends(require_admin)])


@router.post("", response_model=LeadOut, status_code=201)
async def create_lead(body: LeadCreate, db: DbSession) -> Lead:
    existing = await db.scalar(select(Lead).where(Lead.phone == body.phone))
    if existing:
        raise HTTPException(status_code=409, detail="A lead with this phone already exists")
    lead = Lead(name=body.name, phone=body.phone, consent=body.consent, source=body.source)
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead


@router.get("", response_model=list[LeadOut])
async def list_leads(db: DbSession, limit: int = 100, offset: int = 0) -> list[Lead]:
    rows = await db.scalars(
        select(Lead).order_by(Lead.created_at.desc()).limit(limit).offset(offset)
    )
    return list(rows)
