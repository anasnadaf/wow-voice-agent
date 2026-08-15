"""Plivo call surface: answer XML + the bidirectional audio websocket.

Outbound flow: origination (app/voice/plivo_client.py) points Plivo's
answer_url at /api/plivo/answer/{call_id}; the XML we return tells Plivo to
open a bidirectional audio stream to /ws/plivo/{call_id}, where the same
pipeline that serves the dev browser surface takes over.

Lifecycle callbacks land on /api/plivo/status/{call_id}; persistence hooks
attach there once the call/DB layer merges.
"""

import uuid

from fastapi import APIRouter, Request, WebSocket
from fastapi.responses import Response
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.plivo import PlivoFrameSerializer
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from app import call_flow
from app.agent.engine import ConversationEngine
from app.config import settings
from app.voice.pipeline import create_voice_session

router = APIRouter()


def stream_url(call_id: str) -> str:
    base = settings.public_base_url.replace("https://", "wss://").replace("http://", "ws://")
    return f"{base}/ws/plivo/{call_id}"


def answer_xml(call_id: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        '    <Stream bidirectional="true" keepCallAlive="true" '
        'contentType="audio/x-mulaw;rate=8000">'
        f"{stream_url(call_id)}</Stream>\n"
        "</Response>"
    )


@router.api_route("/api/plivo/answer/{call_id}", methods=["GET", "POST"])
async def plivo_answer(call_id: str) -> Response:
    logger.info(f"call {call_id}: answered, returning stream XML")
    return Response(content=answer_xml(call_id), media_type="application/xml")


@router.api_route("/api/plivo/status/{call_id}", methods=["GET", "POST"])
async def plivo_status(call_id: str, request: Request) -> dict[str, str]:
    form = dict(await request.form()) if request.method == "POST" else dict(request.query_params)
    logger.info(
        f"call {call_id}: status={form.get('CallStatus') or form.get('Event')} "
        f"uuid={form.get('CallUUID')}"
    )
    try:
        await call_flow.apply_provider_status(uuid.UUID(call_id), form)
    except ValueError:
        logger.warning(f"plivo status for non-uuid call id {call_id!r}")
    return {"status": "ok"}


@router.websocket("/ws/plivo/{call_id}")
async def plivo_stream(websocket: WebSocket, call_id: str):
    await websocket.accept()

    try:
        call_uuid = uuid.UUID(call_id)
    except ValueError:
        logger.error(f"rejecting stream for non-uuid call id {call_id!r}")
        await websocket.close(code=4404)
        return
    loaded = await call_flow.load_call(call_uuid)
    if loaded is None:
        logger.error(f"rejecting stream for unknown call {call_id}")
        await websocket.close(code=4404)
        return
    _, lead = loaded

    transport_type, call_data = await parse_telephony_websocket(websocket)
    logger.info(
        f"call {call_id}: {transport_type} stream connected "
        f"(stream={call_data['stream_id']}, uuid={call_data['call_id']})"
    )
    await call_flow.mark_stream_connected(call_uuid)

    serializer = PlivoFrameSerializer(
        stream_id=call_data["stream_id"],
        call_id=call_data["call_id"],
        # auth enables auto hang-up from our side when the pipeline ends the call
        auth_id=settings.plivo_auth_id or None,
        auth_token=settings.plivo_auth_token or None,
    )
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    async def on_turn(turn):
        await call_flow.persist_turn(call_uuid, turn)

    engine = ConversationEngine(call_id, lead.name if lead else None)
    session = create_voice_session(transport, call_id, engine=engine, on_turn=on_turn)
    try:
        await session.run()
    finally:
        logger.info(f"call {call_id}: session ended with {len(session.turns)} turns")
        await call_flow.finalize_call(
            call_uuid,
            turns=session.turns,
            recording_path=session.recording_path,
            agent_snapshot=session.agent_snapshot(),
            metrics=session.metrics.summary(),
        )
