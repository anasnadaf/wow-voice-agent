from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Vendors are selected here, never imported directly."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    public_base_url: str = "http://localhost:8080"
    database_url: str = "postgresql+asyncpg://wow:wow@localhost:5432/wow"

    # vendor selection — the adapter registry resolves these names
    stt_provider: str = "sarvam"
    tts_provider: str = "sarvam"
    llm_provider: str = "groq"
    telephony_provider: str = "plivo"

    # provider credentials (empty in dev until the relevant milestone needs them)
    sarvam_api_key: str = ""
    gnani_api_key: str = ""
    groq_api_key: str = ""
    cerebras_api_key: str = ""
    plivo_auth_id: str = ""
    plivo_auth_token: str = ""
    plivo_from_number: str = ""

    # models — conversation needs quality at speed, extraction just needs speed
    convo_model: str = "llama-3.3-70b-versatile"
    extract_model: str = "llama-3.1-8b-instant"

    mlflow_tracking_uri: str = "http://localhost:5000"

    # dashboard auth (portfolio-auth bearer verification, nonstick pattern)
    auth_url: str = ""


settings = Settings()
