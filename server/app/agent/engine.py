"""Public conversation interface consumed by the voice pipeline.

LLM access goes through langchain-openai's ChatOpenAI against whichever
OpenAI-compatible vendor `settings.llm_provider` selects, so switching Groq and
Cerebras is a pure config swap and `mlflow.langchain.autolog()` traces every call.
Both models are injectable for tests and simulations.
"""

from collections.abc import AsyncIterator
from copy import deepcopy

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.agent.graph import REPLY_NODES, _chunk_text, build_graph
from app.agent.state import AgentState, initial_state
from app.config import settings

_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "cerebras": "https://api.cerebras.ai/v1",
}


def _default_llm(model: str, *, temperature: float, max_tokens: int) -> ChatOpenAI:
    provider = settings.llm_provider
    if provider not in _BASE_URLS:
        raise ValueError(f"unsupported llm_provider {provider!r}; expected one of {_BASE_URLS}")
    api_key = {"groq": settings.groq_api_key, "cerebras": settings.cerebras_api_key}[provider]
    if not api_key:
        raise RuntimeError(f"{provider}_api_key is not configured")
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=_BASE_URLS[provider],
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=30,
    )


def _compose_opening(lead_name: str | None) -> str:
    who = f"am I speaking with {lead_name}? This" if lead_name else "this"
    return (
        f"Hello, {who} is Ananya calling from Divyasree Developers. "
        "I'm reaching out about Whispers of the Wind, our premium villa plot community "
        "near Nandi Hills in North Bengaluru. Is this a good time to talk for a couple "
        "of minutes?"
    )


class ConversationEngine:
    """One instance per call. Feed it user turns, stream back the spoken reply."""

    def __init__(
        self,
        call_id: str,
        lead_name: str | None = None,
        *,
        reply_llm: BaseChatModel | None = None,
        extract_llm: BaseChatModel | None = None,
    ):
        self._reply_llm = reply_llm or _default_llm(
            settings.convo_model, temperature=0.6, max_tokens=160
        )
        self._extract_llm = extract_llm or _default_llm(
            settings.extract_model, temperature=0.0, max_tokens=350
        )
        self._graph = build_graph(self._reply_llm, self._extract_llm)
        self._state: AgentState = initial_state(call_id, lead_name)
        self._opening = _compose_opening(lead_name)
        # the deterministic opening is part of the transcript from the start
        self._state["history"].append({"role": "assistant", "content": self._opening})

    def opening_line(self) -> str:
        """Deterministic greeting (project + location + permission ask). No LLM call."""
        return self._opening

    async def stream_turn(self, user_text: str) -> AsyncIterator[str]:
        """Run one turn: stream the reply text while extraction runs concurrently.

        The reply call starts immediately from the current state; the extract call's
        result is merged after the reply node finishes and steers the next turn.
        """
        if self.is_done:
            raise RuntimeError(f"call {self._state['call_id']} is already complete")
        state_in: AgentState = {
            **self._state,
            "history": [*self._state["history"], {"role": "user", "content": user_text}],
        }
        final = state_in
        async for mode, payload in self._graph.astream(
            state_in, stream_mode=["messages", "values"]
        ):
            if mode == "messages":
                chunk, metadata = payload
                if metadata.get("langgraph_node") in REPLY_NODES:
                    text = _chunk_text(chunk)
                    if text:
                        yield text
            else:
                final = payload
        self._state = final

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def is_done(self) -> bool:
        return self._state["outcome"] is not None or self._state["stage"] == "done"

    def snapshot(self) -> dict:
        """JSON-serializable copy of the full call state for persistence."""
        return deepcopy(dict(self._state))
