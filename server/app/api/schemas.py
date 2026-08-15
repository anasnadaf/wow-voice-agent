import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def validate_e164(phone: str) -> str:
    phone = re.sub(r"[\s\-()]", "", phone)
    if not E164_RE.fullmatch(phone):
        raise ValueError("phone must be E.164, e.g. +919876543210")
    return phone


class LeadCreate(BaseModel):
    name: str
    phone: str
    consent: bool = False
    source: str = "dashboard"

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return validate_e164(v)


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    phone: str
    source: str
    consent: bool
    dnc: bool
    created_at: datetime


class CallCreate(BaseModel):
    """Either {lead_id} (admin) or {name, phone, consent} (public)."""

    lead_id: uuid.UUID | None = None
    name: str | None = None
    phone: str | None = None
    consent: bool | None = None

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        return validate_e164(v) if v is not None else None


class TurnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    text: str
    t_offset_ms: int
    created_at: datetime


class QualificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    intent: str | None
    geography: str | None
    budget: str | None
    timeline: str | None
    language: str | None
    sentiment: str | None
    disposition: str | None
    next_action: str | None
    summary: str | None
    created_at: datetime


class CallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lead_id: uuid.UUID
    provider_call_id: str | None
    status: str
    language: str | None
    started_at: datetime | None
    ended_at: datetime | None
    duration_s: int | None
    created_at: datetime
    lead: LeadOut

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v: object) -> object:
        return v.value if hasattr(v, "value") else v


class CallDetailOut(CallOut):
    turns: list[TurnOut]
    qualification: QualificationOut | None
    recording_url: str | None = None
