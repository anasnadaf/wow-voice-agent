import asyncio
import wave
from pathlib import Path

from loguru import logger
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor

from app.config import Settings


def make_call_recorder(call_id: str, settings: Settings) -> tuple[AudioBufferProcessor, Path]:
    """AudioBufferProcessor that writes the full call to recordings/<call_id>.wav.

    buffer_size=0 accumulates in memory and flushes once on stop — a bounded
    cost here because calls are capped at a few minutes.
    """
    out_dir = Path(settings.recordings_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{call_id}.wav"

    audiobuffer = AudioBufferProcessor(buffer_size=0)

    @audiobuffer.event_handler("on_audio_data")
    async def _save(_, audio: bytes, sample_rate: int, num_channels: int):
        def write() -> None:
            with wave.open(str(path), "wb") as f:
                f.setnchannels(num_channels)
                f.setsampwidth(2)
                f.setframerate(sample_rate)
                f.writeframes(audio)

        await asyncio.get_running_loop().run_in_executor(None, write)
        logger.info(f"call {call_id}: recording saved to {path}")

    return audiobuffer, path
