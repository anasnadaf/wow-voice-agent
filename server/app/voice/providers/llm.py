from pipecat.services.openai.llm import OpenAILLMService

from app.config import Settings

# Both fast-inference vendors speak the OpenAI protocol, so switching is a
# base-URL + key swap — no code path differs between them.
_OPENAI_COMPAT: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "cerebras": "https://api.cerebras.ai/v1",
}


def llm_endpoint(settings: Settings) -> tuple[str, str]:
    """Return (base_url, api_key) for the configured LLM vendor."""
    try:
        base_url = _OPENAI_COMPAT[settings.llm_provider]
    except KeyError:
        raise ValueError(
            f"Unknown LLM_PROVIDER {settings.llm_provider!r} "
            f"(expected one of {sorted(_OPENAI_COMPAT)})"
        ) from None
    api_key = getattr(settings, f"{settings.llm_provider}_api_key")
    return base_url, api_key


def build_llm_service(settings: Settings) -> OpenAILLMService:
    base_url, api_key = llm_endpoint(settings)
    return OpenAILLMService(api_key=api_key, base_url=base_url, model=settings.convo_model)
