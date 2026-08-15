"""Bridge between the Pipecat pipeline and the LangGraph conversation engine.

Drop-in replacement for a vendor LLM service: on each aggregated user turn
(LLMContextFrame) it streams the engine's reply into the TTS instead of
calling a chat API directly — the engine owns prompts, state, and routing.
When the engine declares the conversation finished, the pipeline is asked to
end gracefully (TTS flushes the goodbye first), which also hangs up the phone
leg via the serializer's auto-hang-up.
"""

from loguru import logger
from pipecat.frames.frames import (
    EndTaskFrame,
    Frame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.llm_service import LLMService

from app.agent.engine import ConversationEngine


def latest_user_text(context: LLMContext) -> str | None:
    for message in reversed(context.get_messages()):
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):  # multimodal parts — keep the text ones
                texts = [p.get("text", "") for p in content if isinstance(p, dict)]
                return " ".join(t for t in texts if t) or None
    return None


class EngineLLMService(LLMService):
    def __init__(self, engine: ConversationEngine, **kwargs):
        super().__init__(**kwargs)
        self._engine = engine

    @property
    def engine(self) -> ConversationEngine:
        return self._engine

    def can_generate_metrics(self) -> bool:
        return True

    async def run_inference(self, context, max_tokens=None, system_instruction=None) -> str | None:
        return None  # out-of-band inference is not meaningful for a stateful engine

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame):
            await self._run_turn(frame.context)
        else:
            await self.push_frame(frame, direction)

    async def _run_turn(self, context: LLMContext):
        user_text = latest_user_text(context)
        if not user_text or self._engine.is_done:
            return
        try:
            await self.push_frame(LLMFullResponseStartFrame())
            await self.start_processing_metrics()
            await self.start_ttfb_metrics()
            first = True
            async for chunk in self._engine.stream_turn(user_text):
                if first:
                    await self.stop_ttfb_metrics()
                    first = False
                await self.push_frame(LLMTextFrame(chunk))
        except Exception as e:
            await self.push_error(error_msg=f"engine turn failed: {e}", exception=e)
        finally:
            await self.stop_processing_metrics()
            await self.push_frame(LLMFullResponseEndFrame())

        if self._engine.is_done:
            outcome = self._engine.state.get("outcome")
            logger.info(f"engine finished (outcome={outcome}); ending pipeline")
            await self.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)
