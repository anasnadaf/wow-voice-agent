from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Vendors are selected here, never imported directly."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    public_base_url: str = "http://localhost:8080"
    cors_origins: str = "http://localhost:3000"  # comma-separated
    database_url: str = "postgresql+asyncpg://wow:wow@localhost:5432/wow"

    # vendor selection — the adapter registry resolves these names
    stt_provider: str = "sarvam"
    tts_provider: str = "sarvam"
    llm_provider: str = "groq"
    telephony_provider: str = "plivo"

    # provider credentials (empty in dev until the relevant milestone needs them)
    sarvam_api_key: str = ""
    gnani_api_key: str = ""
    rumik_api_key: str = ""
    rumik_gateway_url: str = ""
    groq_api_key: str = ""
    cerebras_api_key: str = ""
    plivo_auth_id: str = ""
    plivo_auth_token: str = ""
    plivo_from_number: str = ""

    # models — conversation needs quality at speed, extraction just needs speed
    convo_model: str = "llama-3.3-70b-versatile"
    extract_model: str = "llama-3.1-8b-instant"
    # Reasoning models (gpt-oss, GLM) spend their token budget thinking before
    # they say anything, which on a phone call is pure dead air — and at a tight
    # max_tokens it starves the reply to empty. Set 'low'/'medium'/'high' for
    # those models; empty sends nothing, which is what plain models expect.
    llm_reasoning_effort: str = ""

    # voice tuning
    stt_model: str = ""  # empty → vendor default
    stt_mode: str = "codemix"  # Hinglish-friendly transcription
    tts_model: str = "bulbul:v2"
    tts_voice: str = "anushka"
    tts_language: str = "en"
    # Rumik keeps its own voice settings so TTS_PROVIDER stays a one-line swap
    # in both directions rather than dragging three other vars along with it.
    rumik_model: str = "mulberry"  # 'mulberry' (described voices) or 'muga' (tone-tagged)
    # Empty pins nothing: mulberry generates the voice from the description
    # below. Set to a named voice (ira, siya, aisha, …) to fix one instead.
    rumik_voice: str = ""
    rumik_description: str = (
        "warm, poised Indian woman in her early thirties with clear Hinglish diction, "
        "an unhurried premium consultative delivery, natural pauses and gentle warmth"
    )
    recordings_dir: str = "recordings"
    # STUN for the browser demo; empty disables the lookup
    stun_servers: str = "stun:stun.l.google.com:19302"

    mlflow_tracking_uri: str = "http://localhost:5001"

    # dashboard auth (portfolio-auth bearer verification, nonstick pattern)
    auth_url: str = ""
    # static admin bearer token fallback when no auth service is configured
    admin_api_token: str = ""


settings = Settings()
