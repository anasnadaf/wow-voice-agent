"""Browser voice surface — the public demo, and the local testing surface.

POST /api/webrtc/offer negotiates a SmallWebRTC session and runs the exact
production pipeline over it: same STT, same conversation graph, same TTS, same
recording, transcript persistence and post-call analysis. Only the transport
carrying the audio differs from a phone call, so a browser session produces the
same Call row, recording and qualification a phone call would.

Pipecat's prebuilt client is mounted at /client in dev; the public demo page
lives in the web app and speaks the same protocol.
"""

import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from app import call_flow
from app.agent.engine import ConversationEngine
from app.config import settings
from app.db.models import CallStatus
from app.voice.pipeline import create_voice_session

router = APIRouter()

_connections: dict[str, SmallWebRTCConnection] = {}


def _ice_servers() -> list[str]:
    """STUN lets a browser behind NAT learn its public address.

    Configurable because a restricted network may need its own STUN/TURN;
    an empty setting disables the lookup.
    """
    return [url.strip() for url in settings.stun_servers.split(",") if url.strip()]


@router.post("/api/webrtc/offer")
async def webrtc_offer(request: dict, background_tasks: BackgroundTasks):
    pc_id = request.get("pc_id")

    if pc_id and pc_id in _connections:
        connection = _connections[pc_id]
        await connection.renegotiate(
            sdp=request["sdp"],
            type=request["type"],
            restart_pc=request.get("restart_pc", False),
        )
        answer = connection.get_answer()
        _connections[answer["pc_id"]] = connection
        return answer

    visitor_name = (request.get("visitor_name") or "").strip()[:200] or None

    # Build the brain before persisting anything: if the server is missing
    # provider keys, say so plainly rather than stranding a half-open
    # connection and an orphan call row.
    call_id = uuid.uuid4()
    try:
        engine = ConversationEngine(str(call_id), visitor_name)
    except (RuntimeError, ValueError) as exc:
        logger.error(f"cannot start web session: {exc}")
        raise HTTPException(
            status_code=503,
            detail="The voice agent is not configured on this server.",
        ) from exc

    connection = SmallWebRTCConnection(ice_servers=_ice_servers())
    await connection.initialize(sdp=request["sdp"], type=request["type"])

    @connection.event_handler("closed")
    async def _closed(conn: SmallWebRTCConnection):
        logger.info(f"call {call_id}: webrtc connection {conn.pc_id} closed")
        _connections.pop(conn.pc_id, None)

    transport = SmallWebRTCTransport(
        webrtc_connection=connection,
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    async def on_turn(turn):
        await call_flow.persist_turn(call_id, turn)

    # Assembling the pipeline is the last thing that can fail on bad config
    # (an unset vendor key, an unknown provider name), so the call row is only
    # written once the whole session is known to be constructible.
    try:
        session = create_voice_session(transport, str(call_id), engine=engine, on_turn=on_turn)
    except (RuntimeError, ValueError) as exc:
        logger.error(f"cannot start web session: {exc}")
        await connection.disconnect()
        raise HTTPException(
            status_code=503,
            detail="The voice agent is not configured on this server.",
        ) from exc

    await call_flow.create_web_call(visitor_name, call_id=call_id)

    async def run_session() -> None:
        await call_flow.mark_stream_connected(call_id)
        try:
            await session.run()
        except Exception:
            logger.exception(f"call {call_id}: web session failed")
            await call_flow.set_status(call_id, CallStatus.failed)
        finally:
            await call_flow.finalize_call(
                call_id,
                turns=session.turns,
                recording_path=session.recording_path,
                agent_snapshot=session.agent_snapshot(),
                metrics=session.metrics.summary(),
            )

    background_tasks.add_task(run_session)
    logger.info(f"call {call_id}: web session starting (visitor={visitor_name or 'anonymous'})")

    answer = connection.get_answer()
    _connections[answer["pc_id"]] = connection
    return answer


@router.get("/api/webrtc/health")
async def webrtc_health() -> dict[str, object]:
    """Lets the demo page distinguish 'not configured' from 'call failed'.

    Readiness follows the configured vendors, so swapping TTS_PROVIDER does not
    quietly leave this reporting on the credentials of the vendor it replaced.
    """
    return {
        "ready": bool(settings.sarvam_api_key and settings.groq_api_key and _tts_ready()),
        "active_sessions": len(_connections),
    }


def _tts_ready() -> bool:
    match settings.tts_provider:
        case "rumik":
            return bool(settings.rumik_api_key and settings.rumik_gateway_url)
        case "gnani":
            return bool(settings.gnani_api_key)
        case _:
            return bool(settings.sarvam_api_key)
