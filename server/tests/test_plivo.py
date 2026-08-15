import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.voice.plivo_client import PlivoError, originate_call
from app.voice.plivo_ws import answer_xml, stream_url


def make_settings(**overrides) -> Settings:
    base = dict(
        _env_file=None,
        public_base_url="https://wow.anasnadaf.com",
        plivo_auth_id="MA_TEST",
        plivo_auth_token="tok",
        plivo_from_number="+911234567890",
    )
    base.update(overrides)
    return Settings(**base)


def test_stream_url_derives_wss(monkeypatch):
    monkeypatch.setattr("app.voice.plivo_ws.settings", make_settings())
    assert stream_url("abc") == "wss://wow.anasnadaf.com/ws/plivo/abc"


def test_answer_xml_shape(monkeypatch):
    monkeypatch.setattr("app.voice.plivo_ws.settings", make_settings())
    xml = answer_xml("abc")
    assert 'bidirectional="true"' in xml
    assert 'keepCallAlive="true"' in xml
    assert "audio/x-mulaw;rate=8000" in xml
    assert "wss://wow.anasnadaf.com/ws/plivo/abc" in xml


def test_answer_endpoint_returns_xml():
    from app.main import app

    resp = TestClient(app).get("/api/plivo/answer/some-call")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    assert "<Stream" in resp.text


async def test_originate_call_posts_expected_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["json"] = request.read()
        return httpx.Response(201, json={"request_uuid": "ruuid-1"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    cfg = make_settings()
    uuid = await originate_call(cfg, "+919999999999", "call-1", client=client)
    assert uuid == "ruuid-1"
    assert "MA_TEST/Call/" in seen["url"]
    body = seen["json"].decode()
    assert "/api/plivo/answer/call-1" in body
    assert "+919999999999" in body


async def test_originate_call_raises_on_error():
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(401, text="denied"))
    )
    with pytest.raises(PlivoError, match="401"):
        await originate_call(make_settings(), "+911", "c", client=client)
