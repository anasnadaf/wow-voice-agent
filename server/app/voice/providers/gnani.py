"""Gnani.ai STT/TTS adapters — the secondary voice vendor seam.

Gnani exposes WebSocket streaming and REST APIs for ASR and neural TTS
(https://www.gnani.ai). There is no upstream Pipecat service for it, so the
adapter implements Pipecat's STTService/TTSService interfaces directly.

The interfaces are registered and selectable via STT_PROVIDER/TTS_PROVIDER
today; the transport implementation lands when a Gnani key is provisioned,
against their current WebSocket protocol docs.
"""

from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService

_NOT_WIRED = (
    "The Gnani adapter is registered but its streaming transport is not wired yet; "
    "set {var}=sarvam or provision a Gnani key and implement app/voice/providers/gnani.py"
)


class GnaniSTTService(STTService):
    def __init__(self, *, api_key: str, **kwargs):
        raise NotImplementedError(_NOT_WIRED.format(var="STT_PROVIDER"))


class GnaniTTSService(TTSService):
    def __init__(self, *, api_key: str, **kwargs):
        raise NotImplementedError(_NOT_WIRED.format(var="TTS_PROVIDER"))
