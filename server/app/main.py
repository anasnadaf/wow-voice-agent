from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api import calls, leads, me
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app import telephony
    from app.obs.mlflow_obs import init_mlflow

    telephony.configure_from_settings()
    try:
        init_mlflow(settings)
    except Exception as exc:  # a down tracking server must never block calls
        logger.warning(f"mlflow init failed: {exc}")
    yield


app = FastAPI(title="WOW Voice Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(leads.router)
app.include_router(calls.router)
app.include_router(me.router)

from app.voice.plivo_ws import router as plivo_router  # noqa: E402

app.include_router(plivo_router)

if settings.app_env == "dev":
    # Browser-mic voice testing: prebuilt client at /client, offer endpoint under /api
    from pipecat_ai_small_webrtc_prebuilt.frontend import SmallWebRTCPrebuiltUI

    from app.voice.webrtc import router as webrtc_router

    app.include_router(webrtc_router)
    app.mount("/client", SmallWebRTCPrebuiltUI)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}
