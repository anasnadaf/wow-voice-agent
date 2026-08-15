from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.services.tts_service import TTSService

from app.config import Settings


def build_tts(settings: Settings) -> TTSService:
    """Resolve the configured TTS vendor to a Pipecat service.

    enable_preprocessing matters for Sarvam: replies are frequently code-mixed
    (Hinglish, rupee amounts, unit names) and bulbul normalizes those much
    better with preprocessing on. Rumik normalizes unconditionally, so there is
    no equivalent switch there.
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
        case "rumik":
            return _build_rumik(settings)
        case "gnani":
            from app.voice.providers.gnani import GnaniTTSService

            return GnaniTTSService(api_key=settings.gnani_api_key)
        case other:
            raise ValueError(
                f"Unknown TTS_PROVIDER {other!r} (expected 'sarvam', 'rumik' or 'gnani')"
            )


def _build_rumik(settings: Settings) -> TTSService:
    """Rumik's websocket service — the interruptible one, as this is a live call.

    The two models want different inputs: mulberry is described (a prose voice
    description, optionally pinned to a named voice), while muga is tone-tagged
    and ignores both. Sending mulberry's fields to muga would be noise, so each
    model gets only what it uses.

    Selecting muga also changes what the agent writes: app.prompts.speech adds
    the tone-tag rules to the system prompt and keeps the tags out of the
    transcript, all keyed off this same setting.
    """
    from pipecat_rumik import RumikTTSService

    if not settings.rumik_api_key or not settings.rumik_gateway_url:
        raise ValueError(
            "TTS_PROVIDER=rumik needs both RUMIK_API_KEY and RUMIK_GATEWAY_URL to be set"
        )

    if settings.rumik_model == "muga":
        params = RumikTTSService.Settings(model="muga")
    else:
        # description alone lets mulberry generate the voice; a named voice is
        # only sent when one is explicitly configured (never voice alone).
        params = RumikTTSService.Settings(
            model=settings.rumik_model,
            description=settings.rumik_description,
            **({"voice": settings.rumik_voice} if settings.rumik_voice else {}),
        )

    return RumikTTSService(
        api_key=settings.rumik_api_key,
        gateway_url=settings.rumik_gateway_url,
        settings=params,
    )
