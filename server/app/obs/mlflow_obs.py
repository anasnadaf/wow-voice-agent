"""MLflow observability: one run per call, traces via autolog.

init_mlflow() is called once at startup; CallRun wraps the per-call lifecycle
so the voice pipeline and post-call analysis only ever talk to this module —
swapping the tracking backend stays a config change.
"""

import json
import tempfile
from pathlib import Path
from typing import Any

import mlflow
from loguru import logger

from app.config import Settings

EXPERIMENT = "wow-voice-agent"


def init_mlflow(settings: Settings) -> None:
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(EXPERIMENT)
    # Trace every LangChain/LangGraph turn and DSPy call automatically.
    try:
        mlflow.langchain.autolog()
    except Exception as exc:  # autolog availability depends on installed extras
        logger.warning(f"mlflow langchain autolog unavailable: {exc}")
    try:
        mlflow.dspy.autolog()
    except Exception as exc:
        logger.warning(f"mlflow dspy autolog unavailable: {exc}")
    logger.info(f"mlflow tracking → {settings.mlflow_tracking_uri} ({EXPERIMENT})")


class CallRun:
    """MLflow run scoped to a single phone call."""

    def __init__(self, call_id: str, settings: Settings):
        self._settings = settings
        self._run = mlflow.start_run(run_name=call_id, tags={"call_id": call_id})
        mlflow.log_params(
            {
                "stt_provider": settings.stt_provider,
                "tts_provider": settings.tts_provider,
                "llm_provider": settings.llm_provider,
                "convo_model": settings.convo_model,
                "extract_model": settings.extract_model,
            }
        )

    def log_metrics(self, metrics: dict[str, float], step: int | None = None) -> None:
        mlflow.log_metrics(metrics, step=step)

    def log_json(self, name: str, payload: dict[str, Any] | list[Any]) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / name
            p.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
            mlflow.log_artifact(str(p))

    def log_file(self, path: str | Path) -> None:
        path = Path(path)
        if path.exists():
            mlflow.log_artifact(str(path))

    def end(self, status: str = "FINISHED") -> None:
        mlflow.end_run(status=status)

    def __enter__(self) -> "CallRun":
        return self

    def __exit__(self, exc_type, *_):
        self.end(status="FAILED" if exc_type else "FINISHED")
