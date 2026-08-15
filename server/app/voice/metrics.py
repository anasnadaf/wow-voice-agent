"""Aggregates Pipecat's per-service metrics frames into a per-call summary."""

from collections import defaultdict

from pipecat.frames.frames import MetricsFrame
from pipecat.metrics.metrics import ProcessingMetricsData, TTFBMetricsData
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.services.llm_service import LLMService
from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService


def _bucket(source: object) -> str | None:
    if isinstance(source, STTService):
        return "stt"
    if isinstance(source, LLMService):
        return "llm"
    if isinstance(source, TTSService):
        return "tts"
    return None


class MetricsSummaryObserver(BaseObserver):
    """Collects TTFB/processing samples; summary() yields MLflow-ready floats."""

    def __init__(self):
        super().__init__()
        self._ttfb: dict[str, list[float]] = defaultdict(list)
        self._processing: dict[str, list[float]] = defaultdict(list)

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame
        if not isinstance(frame, MetricsFrame):
            return
        bucket = _bucket(data.source)
        if bucket is None:
            return
        for item in frame.data:
            if isinstance(item, TTFBMetricsData) and item.value > 0:
                self._ttfb[bucket].append(item.value)
            elif isinstance(item, ProcessingMetricsData) and item.value > 0:
                self._processing[bucket].append(item.value)

    def summary(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for name, series in (("ttfb", self._ttfb), ("processing", self._processing)):
            for bucket, values in series.items():
                if values:
                    out[f"{bucket}_{name}_avg_s"] = round(sum(values) / len(values), 4)
                    out[f"{bucket}_{name}_max_s"] = round(max(values), 4)
        return out
