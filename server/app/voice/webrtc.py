"""Browser-mic testing surface for development.

POST /api/webrtc/offer negotiates a SmallWebRTC session and runs the exact
production pipeline over it — same STT, agent, TTS, recording, transcript —
just with the browser instead of a phone line as transport. The prebuilt
client UI is mounted at /client by app.main in dev.
"""

import uuid

from fastapi import APIRouter, BackgroundTasks
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from app.voice.pipeline import create_voice_session

router = APIRouter()

_connections: dict[str, SmallWebRTCConnection] = {}


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
    else:
        connection = SmallWebRTCConnection()
        await connection.initialize(sdp=request["sdp"], type=request["type"])

        @connection.event_handler("closed")
        async def _closed(conn: SmallWebRTCConnection):
            logger.info(f"webrtc connection {conn.pc_id} closed")
            _connections.pop(conn.pc_id, None)

        transport = SmallWebRTCTransport(
            webrtc_connection=connection,
            params=TransportParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
            ),
        )
        call_id = f"dev-{uuid.uuid4().hex[:8]}"
        try:
            # Same brain as a phone call; browser sessions have no Call row,
            # so nothing persists — this surface exists to hear the agent.
            from app.agent.engine import ConversationEngine

            engine = ConversationEngine(call_id, None)
        except (RuntimeError, ValueError) as exc:
            logger.warning(f"engine unavailable ({exc}); using placeholder LLM loop")
            engine = None
        session = create_voice_session(transport, call_id=call_id, engine=engine)
        background_tasks.add_task(session.run)

    answer = connection.get_answer()
    _connections[answer["pc_id"]] = connection
    return answer
