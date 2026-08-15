import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app import telephony
from app.db.models import Call, CallStatus, Lead, Qualification, Turn

PUBLIC_BODY = {"name": "Asha Rao", "phone": "+919876543210", "consent": True}


async def test_public_call_creates_lead_and_call(client, db):
    resp = await client.post("/api/calls", json=PUBLIC_BODY)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "requested"
    assert data["provider_call_id"].startswith("null-")  # NullTelephony stub was hit
    assert data["lead"]["phone"] == "+919876543210"
    assert data["lead"]["source"] == "web"
    assert data["lead"]["consent"] is True


async def test_lead_upsert_by_phone(client, db):
    r1 = await client.post("/api/calls", json=PUBLIC_BODY)
    r2 = await client.post("/api/calls", json={**PUBLIC_BODY, "name": "Asha R."})
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["lead"]["id"] == r2.json()["lead"]["id"]

    leads = (await db.scalars(select(Lead))).all()
    assert len(leads) == 1
    assert leads[0].name == "Asha R."  # upsert refreshed the name


async def test_consent_required(client):
    for body in (
        {"name": "X", "phone": "+919876543210", "consent": False},
        {"name": "X", "phone": "+919876543210"},
    ):
        resp = await client.post("/api/calls", json=body)
        assert resp.status_code == 422


async def test_invalid_phone_rejected(client):
    resp = await client.post("/api/calls", json={**PUBLIC_BODY, "phone": "98765"})
    assert resp.status_code == 422


async def test_dnc_lead_rejected(client, db):
    db.add(Lead(name="Opted Out", phone="+919812345678", consent=True, dnc=True))
    await db.commit()
    resp = await client.post(
        "/api/calls", json={"name": "Opted Out", "phone": "+919812345678", "consent": True}
    )
    assert resp.status_code == 403


async def test_null_telephony_stub_invoked(client, monkeypatch):
    seen: list[tuple[uuid.UUID, str]] = []

    class Recorder:
        async def originate_call(self, call, lead):
            seen.append((call.id, lead.phone))
            return "rec-123"

    monkeypatch.setattr(telephony, "_telephony", Recorder())
    resp = await client.post("/api/calls", json=PUBLIC_BODY)
    assert resp.status_code == 201
    assert resp.json()["provider_call_id"] == "rec-123"
    assert len(seen) == 1
    assert seen[0][1] == "+919876543210"


async def test_call_detail_shape(client, db):
    lead = Lead(name="Ravi", phone="+919811111111", consent=True)
    db.add(lead)
    await db.flush()
    call = Call(
        lead_id=lead.id,
        status=CallStatus.completed,
        duration_s=182,
        started_at=datetime.now(UTC),
        ended_at=datetime.now(UTC),
    )
    db.add(call)
    await db.flush()
    db.add(
        Turn(call_id=call.id, role="assistant", text="Hello, am I speaking to Ravi?", t_offset_ms=0)
    )
    db.add(Turn(call_id=call.id, role="user", text="Yes, speaking.", t_offset_ms=2400))
    db.add(
        Qualification(
            call_id=call.id,
            intent="investment",
            geography="Whitefield, Bengaluru",
            budget=None,
            timeline="3-6 months",
            disposition="qualified",
            next_action="schedule site visit",
            summary="Interested investor, budget pending.",
        )
    )
    await db.commit()

    resp = await client.get(f"/api/calls/{call.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["duration_s"] == 182
    assert data["lead"]["name"] == "Ravi"
    assert [t["role"] for t in data["turns"]] == ["assistant", "user"]
    assert data["turns"][1]["t_offset_ms"] == 2400
    q = data["qualification"]
    assert q["intent"] == "investment"
    assert q["budget"] is None
    assert q["disposition"] == "qualified"
    assert data["recording_url"] is None  # no recording on disk


async def test_call_detail_404(client):
    resp = await client.get(f"/api/calls/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_calls_list_embeds_lead(client):
    await client.post("/api/calls", json=PUBLIC_BODY)
    resp = await client.get("/api/calls?limit=10&offset=0")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["lead"]["name"] == "Asha Rao"


async def test_admin_call_shape_by_lead_id(client, db):
    lead = Lead(name="Meena", phone="+919822222222", consent=True)
    db.add(lead)
    await db.commit()
    resp = await client.post("/api/calls", json={"lead_id": str(lead.id)})
    assert resp.status_code == 201
    assert resp.json()["lead"]["name"] == "Meena"


async def test_public_rate_limit(client):
    for i in range(5):
        r = await client.post(
            "/api/calls",
            json={"name": f"N{i}", "phone": f"+9198765432{10 + i}", "consent": True},
        )
        assert r.status_code == 201
    r = await client.post(
        "/api/calls", json={"name": "N6", "phone": "+919876543216", "consent": True}
    )
    assert r.status_code == 429
