"""Database models for leads, calls, transcript turns, and qualifications.

Types are kept portable (generic Uuid/JSON, non-native enums) so the same
metadata runs on Postgres (asyncpg) in prod and SQLite (aiosqlite) in tests.
"""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class CallStatus(enum.Enum):
    requested = "requested"
    ringing = "ringing"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    no_answer = "no_answer"
    busy = "busy"


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # E.164
    source: Mapped[str] = mapped_column(String(20), default="web")  # "web" | "dashboard"
    consent: Mapped[bool] = mapped_column(Boolean, default=False)
    dnc: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    calls: Mapped[list["Call"]] = relationship(back_populates="lead")


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Web demo sessions have no phone lead, so this is optional; phone calls
    # always carry one.
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("leads.id"), index=True, nullable=True
    )
    channel: Mapped[str] = mapped_column(String(10), default="phone")  # "phone" | "web"
    visitor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    provider_call_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[CallStatus] = mapped_column(
        Enum(CallStatus, name="call_status", native_enum=False, length=20),
        default=CallStatus.requested,
    )
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recording_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    agent_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    lead: Mapped[Lead | None] = relationship(back_populates="calls")
    turns: Mapped[list["Turn"]] = relationship(
        back_populates="call", order_by="Turn.t_offset_ms", cascade="all, delete-orphan"
    )
    qualification: Mapped["Qualification | None"] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    call_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calls.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # "user" | "assistant"
    text: Mapped[str] = mapped_column(Text)
    t_offset_ms: Mapped[int] = mapped_column(Integer)  # offset from call start
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    call: Mapped[Call] = relationship(back_populates="turns")


class Qualification(Base):
    __tablename__ = "qualifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    call_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calls.id"), unique=True, index=True)
    # the four qualification checkpoints — null means "not yet established"
    intent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    geography: Mapped[str | None] = mapped_column(String(500), nullable=True)
    budget: Mapped[str | None] = mapped_column(String(500), nullable=True)
    timeline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(50), nullable=True)
    disposition: Mapped[str | None] = mapped_column(String(50), nullable=True)
    next_action: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    call: Mapped[Call] = relationship(back_populates="qualification")
