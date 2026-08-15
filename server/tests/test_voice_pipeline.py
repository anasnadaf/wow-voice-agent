import pytest

from app.config import Settings
from app.voice.providers import build_llm_service, build_stt, build_tts, llm_endpoint


def make_settings(**overrides) -> Settings:
    base = dict(
        _env_file=None,
        sarvam_api_key="test-key",
        groq_api_key="test-groq",
        cerebras_api_key="test-cerebras",
    )
    base.update(overrides)
    return Settings(**base)


def test_default_registry_resolves_sarvam_and_groq():
    cfg = make_settings()
    from pipecat.services.sarvam.stt import SarvamSTTService
    from pipecat.services.sarvam.tts import SarvamTTSService

    assert isinstance(build_stt(cfg), SarvamSTTService)
    assert isinstance(build_tts(cfg), SarvamTTSService)
    base_url, key = llm_endpoint(cfg)
    assert "groq" in base_url and key == "test-groq"


def test_llm_vendor_swap_is_config_only():
    cfg = make_settings(llm_provider="cerebras")
    base_url, key = llm_endpoint(cfg)
    assert "cerebras" in base_url and key == "test-cerebras"
    assert build_llm_service(cfg) is not None


def rumik_settings(**overrides) -> Settings:
    base = dict(tts_provider="rumik", rumik_api_key="test-rumik", rumik_gateway_url="https://gw")
    base.update(overrides)
    return make_settings(**base)


def test_tts_vendor_swap_is_config_only():
    from pipecat_rumik import RumikTTSService

    tts = build_tts(rumik_settings())
    assert isinstance(tts, RumikTTSService)
    assert tts._settings.model == "mulberry"


def test_mulberry_describes_the_voice_instead_of_pinning_one():
    """An unset RUMIK_VOICE must send description alone — never voice alone."""
    tts = build_tts(rumik_settings(rumik_voice=""))
    assert tts._settings.voice is None
    assert tts._settings.description


def test_a_named_mulberry_voice_is_passed_through_when_configured():
    tts = build_tts(rumik_settings(rumik_voice="ira"))
    assert tts._settings.voice == "ira"


def test_muga_carries_no_mulberry_only_fields():
    tts = build_tts(rumik_settings(rumik_model="muga"))
    assert tts._settings.model == "muga"
    assert tts._settings.voice is None and tts._settings.description is None


@pytest.mark.parametrize("missing", ["rumik_api_key", "rumik_gateway_url"])
def test_rumik_without_credentials_fails_loudly(missing):
    """A half-configured vendor must not reach a live call as a runtime error."""
    with pytest.raises(ValueError, match="RUMIK"):
        build_tts(rumik_settings(**{missing: ""}))


@pytest.mark.parametrize("field", ["stt_provider", "tts_provider", "llm_provider"])
def test_unknown_vendor_rejected(field):
    cfg = make_settings(**{field: "nope"})
    builder = {
        "stt_provider": build_stt,
        "tts_provider": build_tts,
        "llm_provider": llm_endpoint,
    }[field]
    with pytest.raises(ValueError, match="nope"):
        builder(cfg)


async def test_voice_session_assembles_without_network(tmp_path):
    """The whole per-call pipeline must construct offline — vendors connect lazily."""
    from pipecat.transports.base_transport import TransportParams
    from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
    from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

    from app.voice.pipeline import create_voice_session

    cfg = make_settings(recordings_dir=str(tmp_path / "rec"))
    transport = SmallWebRTCTransport(
        webrtc_connection=SmallWebRTCConnection(),
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    )
    session = create_voice_session(transport, call_id="test-call", settings=cfg)
    assert session.recording_path.name == "test-call.wav"
    assert session.turns == []
