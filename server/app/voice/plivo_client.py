"""Thin Plivo REST client for call origination — httpx, no SDK dependency."""

import httpx
from loguru import logger

from app.config import Settings

PLIVO_API = "https://api.plivo.com/v1/Account"


class PlivoError(RuntimeError):
    pass


async def originate_call(
    settings: Settings,
    to_number: str,
    call_id: str,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Start an outbound call; returns Plivo's request UUID.

    Plivo fetches answer_url when the callee picks up, and our XML there
    bridges the audio into /ws/plivo/{call_id}.
    """
    base = settings.public_base_url
    payload = {
        "from": settings.plivo_from_number,
        "to": to_number,
        "answer_url": f"{base}/api/plivo/answer/{call_id}",
        "answer_method": "GET",
        "hangup_url": f"{base}/api/plivo/status/{call_id}",
        "hangup_method": "POST",
        "ring_url": f"{base}/api/plivo/status/{call_id}",
        "ring_method": "POST",
    }
    auth = (settings.plivo_auth_id, settings.plivo_auth_token)
    if client is not None:
        resp = await client.post(f"{PLIVO_API}/{settings.plivo_auth_id}/Call/", json=payload)
    else:
        async with httpx.AsyncClient(auth=auth) as c:
            resp = await c.post(f"{PLIVO_API}/{settings.plivo_auth_id}/Call/", json=payload)
    if resp.status_code not in (200, 201):
        raise PlivoError(f"originate failed: {resp.status_code} {resp.text[:300]}")
    request_uuid = resp.json().get("request_uuid", "")
    logger.info(f"call {call_id}: originated to {to_number} (request_uuid={request_uuid})")
    return request_uuid


async def hangup_call(settings: Settings, call_uuid: str) -> None:
    async with httpx.AsyncClient(auth=(settings.plivo_auth_id, settings.plivo_auth_token)) as c:
        resp = await c.delete(f"{PLIVO_API}/{settings.plivo_auth_id}/Call/{call_uuid}/")
    if resp.status_code not in (204, 404):
        raise PlivoError(f"hangup failed: {resp.status_code} {resp.text[:300]}")
