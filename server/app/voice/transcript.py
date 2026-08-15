import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pipecat.frames.frames import (
    TranscriptionFrame,
    TTSStoppedFrame,
    TTSTextFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService


@dataclass
class TranscriptTurn:
    role: str  # "user" | "assistant"
    text: str
    t_offset_ms: int


class TranscriptRecorder(BaseObserver):
    """Collects the spoken conversation as it happens.

    User turns come from final STT transcriptions; assistant turns are the
    TTS text chunks aggregated until the TTS stops speaking — so the record
    reflects what was actually spoken, including barge-in truncation.
    """

    def __init__(self, on_turn: Callable[[TranscriptTurn], Awaitable[None]] | None = None):
        super().__init__()
        self.on_turn = on_turn
        self.turns: list[TranscriptTurn] = []
        self._started_at = time.monotonic()
        self._assistant_chunks: list[str] = []

    def _offset_ms(self) -> int:
        return int((time.monotonic() - self._started_at) * 1000)

    async def _emit(self, role: str, text: str) -> None:
        text = text.strip()
        if not text:
            return
        turn = TranscriptTurn(role=role, text=text, t_offset_ms=self._offset_ms())
        self.turns.append(turn)
        if self.on_turn:
            await self.on_turn(turn)

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame
        if isinstance(frame, TranscriptionFrame) and isinstance(data.source, STTService):
            await self._emit("user", frame.text)
        elif isinstance(frame, TTSTextFrame) and isinstance(data.source, TTSService):
            self._assistant_chunks.append(frame.text)
        elif isinstance(frame, TTSStoppedFrame) and isinstance(data.source, TTSService):
            await self._emit("assistant", " ".join(self._assistant_chunks))
            self._assistant_chunks.clear()
