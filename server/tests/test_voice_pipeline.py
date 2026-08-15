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
