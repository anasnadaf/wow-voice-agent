from app.config import settings

AUTH = {"Authorization": "Bearer sekrit-token"}


async def test_admin_routes_401_without_token(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "sekrit-token")
    for path in ("/api/leads", "/api/calls", "/api/me"):
        resp = await client.get(path)
        assert resp.status_code == 401, path


async def test_admin_routes_ok_with_token(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "sekrit-token")
    resp = await client.get("/api/leads", headers=AUTH)
    assert resp.status_code == 200

    resp = await client.get("/api/me", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() == {"authenticated": True, "mode": "token"}


async def test_wrong_token_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "sekrit-token")
    resp = await client.get("/api/leads", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


async def test_public_call_shape_needs_no_token(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "sekrit-token")
    resp = await client.post(
        "/api/calls", json={"name": "Public", "phone": "+919833333333", "consent": True}
    )
    assert resp.status_code == 201


async def test_admin_call_shape_needs_token(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "sekrit-token")
    import uuid

    resp = await client.post("/api/calls", json={"lead_id": str(uuid.uuid4())})
    assert resp.status_code == 401


async def test_dev_mode_allows_all(client):
    assert settings.auth_url == "" and settings.admin_api_token == ""
    resp = await client.get("/api/me")
    assert resp.status_code == 200
    assert resp.json()["mode"] == "dev"
