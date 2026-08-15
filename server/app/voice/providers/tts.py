from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.services.tts_service import TTSService

from app.config import Settings


def build_tts(settings: Settings) -> TTSService:
    """Resolve the configured TTS vendor to a Pipecat service.

    enable_preprocessing matters for this agent: replies are frequently
    code-mixed (Hinglish, rupee amounts, unit names) and bulbul normalizes
    those much better with preprocessing on.
    """
    match settings.tts_provider:
        case "sarvam":
            return SarvamTTSService(
                api_key=settings.sarvam_api_key,
                model=settings.tts_model,
                voice_id=settings.tts_voice,
                params=SarvamTTSService.InputParams(
                    language=settings.tts_language,  # type: ignore[arg-type]
                    enable_preprocessing=True,
                ),
            )
        case "gnani":
            from app.voice.providers.gnani import GnaniTTSService

            return GnaniTTSService(api_key=settings.gnani_api_key)
        case other:
            raise ValueError(f"Unknown TTS_PROVIDER {other!r} (expected 'sarvam' or 'gnani')")
