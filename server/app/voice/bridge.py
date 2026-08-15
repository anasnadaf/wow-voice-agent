"""Bridge between the Pipecat pipeline and the LangGraph conversation engine.

Drop-in replacement for a vendor LLM service: on each aggregated user turn
(LLMContextFrame) it streams the engine's reply into the TTS instead of
calling a chat API directly — the engine owns prompts, state, and routing.
When the engine declares the conversation finished, the pipeline is asked to
end gracefully (TTS flushes the goodbye first), which also hangs up the phone
leg via the serializer's auto-hang-up.
"""

import asyncio

from loguru import logger
from pipecat.frames.frames import (
    EndTaskFrame,
    Frame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    UserStartedSpeakingFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.llm_service import LLMService

from app.agent.engine import ConversationEngine
from app.prompts import speech_tags_required
from app.prompts.speech import normalize_tone_tag, strip_speech_tags

# a tone tag is "[excited] " at most, so the opening is never held longer
_TAG_LOOKAHEAD = 24

# How long the line stays open after the agent's closing words. Long enough for
# a caller gathering themselves to get a word in; short enough that a finished
# call does not sit there.
HANGUP_SILENCE_S = 7.0


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
        self._hangup: asyncio.Task | None = None

    @property
    def engine(self) -> ConversationEngine:
        return self._engine

    def can_generate_metrics(self) -> bool:
        return True

    async def run_inference(self, context, max_tokens=None, system_instruction=None) -> str | None:
        return None  # out-of-band inference is not meaningful for a stateful engine

    def _open_speech(self, head: str) -> str:
        """Shape the first words of a reply for the configured voice.

        muga reads a leading tone tag as delivery instead of speech, but only
        for the six tags it knows — an invented one would be spoken aloud, so
        the opening is corrected here rather than trusted to the model. Voices
        without tone tags get any stray markup removed instead.
        """
        return normalize_tone_tag(head) if speech_tags_required() else strip_speech_tags(head)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, UserStartedSpeakingFrame):
            self._cancel_hangup()
        if isinstance(frame, LLMContextFrame):
            await self._run_turn(frame.context)
        else:
            await self.push_frame(frame, direction)

    def _cancel_hangup(self) -> None:
        """The caller spoke into the closing silence — answer them if we still can.

        The engine has the final say: a do-not-call request is never reopened by
        someone talking over the goodbye. When it refuses, the pending hangup is
        deliberately left running, so refusing to reopen can never strand a
        finished call with the line still up.
        """
        if self._hangup is None or self._hangup.done():
            return
        if not self._engine.resume():
            return
        self._hangup.cancel()
        self._hangup = None
        logger.info("caller spoke after the close; reopening for a final exchange")

    def _schedule_hangup(self) -> None:
        """Hang up once the line has been quiet for long enough.

        The conversation is over, but the caller may still be drawing breath to
        ask one more thing. Ending the moment the agent stops speaking cuts those
        people off, so the goodbye is followed by a listening pause and the call
        only drops if nothing comes back.
        """

        async def wait_then_end() -> None:
            try:
                await asyncio.sleep(HANGUP_SILENCE_S)
            except asyncio.CancelledError:
                return
            outcome = self._engine.state.get("outcome")
            logger.info(
                f"engine finished (outcome={outcome}); "
                f"{HANGUP_SILENCE_S:.0f}s of silence — ending pipeline"
            )
            await self.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)

        self._hangup = self.create_task(wait_then_end())

    async def _run_turn(self, context: LLMContext):
        user_text = latest_user_text(context)
        if not user_text or self._engine.is_done:
            return
        try:
            await self.push_frame(LLMFullResponseStartFrame())
            await self.start_processing_metrics()
            await self.start_ttfb_metrics()
            first = True
            opening: list[str] = []  # held back only while the tone tag resolves
            async for chunk in self._engine.stream_turn(user_text):
                if first:
                    await self.stop_ttfb_metrics()
                    first = False
                if opening is not None:
                    opening.append(chunk)
                    head = "".join(opening)
                    if "]" not in head and len(head) < _TAG_LOOKAHEAD:
                        continue  # the tag is still arriving
                    chunk, opening = self._open_speech(head), None
                await self.push_frame(LLMTextFrame(chunk))
        except Exception as e:
            await self.push_error(error_msg=f"engine turn failed: {e}", exception=e)
        finally:
            await self.stop_processing_metrics()
            await self.push_frame(LLMFullResponseEndFrame())

        if self._engine.is_done:
            self._schedule_hangup()
