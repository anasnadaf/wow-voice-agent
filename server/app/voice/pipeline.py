from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from pipecat.frames.frames import TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.transports.base_transport import BaseTransport

from app.config import Settings
from app.config import settings as default_settings
from app.voice.metrics import MetricsSummaryObserver
from app.voice.providers import build_llm_service, build_stt, build_tts
from app.voice.recorder import make_call_recorder
from app.voice.transcript import TranscriptRecorder, TranscriptTurn

if TYPE_CHECKING:
    from app.agent.engine import ConversationEngine

# Stands in until the LangGraph conversation engine (feat/agent-graph) is
# bridged into the pipeline; keeps the voice loop testable on its own.
PLACEHOLDER_SYSTEM_PROMPT = (
    "You are a warm, professional pre-sales consultant for Divyasree Developers calling about "
    "'Whispers of the Wind', premium villa plots in Nandi Valley, North Bengaluru. Keep every "
    "reply to one or two short conversational sentences suitable for speech. Never use lists, "
    "markdown, or emojis."
)

PLACEHOLDER_GREETING = (
    "Hello! This is Anaya calling from Divyasree Developers about our Whispers of the Wind "
    "project near Nandi Hills. Is this a good time to talk for a couple of minutes?"
)


@dataclass
class VoiceSession:
    task: PipelineTask
    runner: PipelineRunner
    transcript: TranscriptRecorder
    metrics: "MetricsSummaryObserver"
    recording_path: Path
    greeting: str
    engine: "ConversationEngine | None" = None

    async def run(self) -> None:
        await self.runner.run(self.task)

    @property
    def turns(self) -> list[TranscriptTurn]:
        return self.transcript.turns

    def agent_snapshot(self) -> dict | None:
        return self.engine.snapshot() if self.engine else None


def create_voice_session(
    transport: BaseTransport,
    call_id: str,
    *,
    settings: Settings | None = None,
    engine: "ConversationEngine | None" = None,
    system_prompt: str = PLACEHOLDER_SYSTEM_PROMPT,
    greeting: str = PLACEHOLDER_GREETING,
    on_turn=None,
) -> VoiceSession:
    """Assemble the full voice pipeline for one call.

    Pure construction — no network happens until run(). The transport decides
    the medium (browser WebRTC in dev, Plivo websocket in production); all
    vendor services come from the provider registry.
    """
    cfg = settings or default_settings

    stt = build_stt(cfg)
    tts = build_tts(cfg)
    if engine is not None:
        # The LangGraph engine owns prompts and state; the context aggregator
        # only carries the per-turn user text to the bridge.
        from app.voice.bridge import EngineLLMService

        llm: object = EngineLLMService(engine)
        greeting = engine.opening_line()
        context = LLMContext(messages=[])
    else:
        llm = build_llm_service(cfg)
        context = LLMContext(messages=[{"role": "system", "content": system_prompt}])
    aggregators = LLMContextAggregatorPair(context)

    audiobuffer, recording_path = make_call_recorder(call_id, cfg)
    transcript = TranscriptRecorder(on_turn=on_turn)
    metrics = MetricsSummaryObserver()

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            aggregators.user(),
            llm,
            tts,
            transport.output(),
            audiobuffer,
            aggregators.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[transcript, metrics],
    )

    @transport.event_handler("on_client_connected")
    async def _on_connected(transport, client):
        logger.info(f"call {call_id}: client connected")
        await audiobuffer.start_recording()
        await task.queue_frame(TTSSpeakFrame(greeting))

    @transport.event_handler("on_client_disconnected")
    async def _on_disconnected(transport, client):
        logger.info(f"call {call_id}: client disconnected")
        await audiobuffer.stop_recording()
        await task.cancel()

    return VoiceSession(
        task=task,
        runner=PipelineRunner(handle_sigint=False),
        transcript=transcript,
        metrics=metrics,
        recording_path=recording_path,
        greeting=greeting,
        engine=engine,
    )
