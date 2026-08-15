"""Conversation brain for the WOW outbound pre-sales voice agent."""

from typing import TYPE_CHECKING, Any

from app.agent.state import AgentState, initial_state

if TYPE_CHECKING:
    from app.agent.engine import ConversationEngine

__all__ = ["AgentState", "ConversationEngine", "initial_state"]


def __getattr__(name: str) -> Any:
    """Expose ConversationEngine lazily.

    Importing it eagerly would pull in the graph, which imports app.prompts,
    which imports app.agent.state — so `import app.prompts` on its own would
    hit a partially initialized package.
    """
    if name == "ConversationEngine":
        from app.agent.engine import ConversationEngine

        return ConversationEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
