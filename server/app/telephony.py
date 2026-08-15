"""Telephony seam.

The API layer only ever calls ``await originate_call(call, lead)``; which vendor
actually dials is decided behind this interface. M4 ships ``NullTelephony`` (logs
and fabricates a provider call id). The telephony milestone plugs Plivo in behind
the same protocol via ``set_telephony`` without touching the API layer.
"""

import uuid
from typing import Protocol

from loguru import logger

from app.db.models import Call, Lead


class Telephony(Protocol):
    async def originate_call(self, call: Call, lead: Lead) -> str | None:
        """Start an outbound call to the lead. Returns the provider's call id."""
        ...


class NullTelephony:
    """Dev/test stand-in: no real dialing, just a log line and a fake id."""

    async def originate_call(self, call: Call, lead: Lead) -> str | None:
        provider_call_id = f"null-{uuid.uuid4().hex[:12]}"
        logger.info(
            "NullTelephony: would originate call {} to {} ({}) -> {}",
            call.id,
            lead.phone,
            lead.name,
            provider_call_id,
        )
        return provider_call_id


class PlivoTelephony:
    """Real dialing via Plivo's REST API; the answer XML bridges the audio
    into /ws/plivo/{call_id} (see app/voice/plivo_ws.py)."""

    async def originate_call(self, call: Call, lead: Lead) -> str | None:
        from app.config import settings
        from app.voice.plivo_client import originate_call as plivo_originate

        return await plivo_originate(settings, lead.phone, str(call.id))


def configure_from_settings() -> None:
    """Pick the vendor at startup; stays on NullTelephony when unconfigured
    so dev and CI never dial anything real."""
    from app.config import settings

    if settings.telephony_provider == "plivo" and settings.plivo_auth_id:
        set_telephony(PlivoTelephony())
        logger.info("telephony: Plivo configured (from {})", settings.plivo_from_number)
    else:
        set_telephony(NullTelephony())
        logger.info("telephony: NullTelephony active (no provider credentials)")


_telephony: Telephony = NullTelephony()


def get_telephony() -> Telephony:
    return _telephony


def set_telephony(impl: Telephony) -> None:
    global _telephony
    _telephony = impl


async def originate_call(call: Call, lead: Lead) -> str | None:
    return await get_telephony().originate_call(call, lead)
