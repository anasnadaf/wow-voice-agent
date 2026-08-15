from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.stt_service import STTService

from app.config import Settings


def build_stt(settings: Settings) -> STTService:
    """Resolve the configured STT vendor to a Pipecat service.

    Language is deliberately left unset for Sarvam: the API then defaults to
    "unknown", which enables auto-detection — required for mid-call
    English/Hindi switching.
    """
    match settings.stt_provider:
        case "sarvam":
            return SarvamSTTService(
                api_key=settings.sarvam_api_key,
                model=settings.stt_model or None,
                params=SarvamSTTService.InputParams(
                    mode=settings.stt_mode or None,  # type: ignore[arg-type]
                    vad_signals=True,
                ),
            )
        case "gnani":
            from app.voice.providers.gnani import GnaniSTTService

            return GnaniSTTService(api_key=settings.gnani_api_key)
        case other:
            raise ValueError(f"Unknown STT_PROVIDER {other!r} (expected 'sarvam' or 'gnani')")
