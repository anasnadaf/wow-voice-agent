from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="WOW Voice Agent", lifespan=lifespan)

if settings.app_env == "dev":
    # Browser-mic voice testing: prebuilt client at /client, offer endpoint under /api
    from pipecat_ai_small_webrtc_prebuilt.frontend import SmallWebRTCPrebuiltUI

    from app.voice.webrtc import router as webrtc_router

    app.include_router(webrtc_router)
    app.mount("/client", SmallWebRTCPrebuiltUI)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}
