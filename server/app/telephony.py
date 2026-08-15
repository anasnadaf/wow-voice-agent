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


_telephony: Telephony = NullTelephony()


def get_telephony() -> Telephony:
    return _telephony


def set_telephony(impl: Telephony) -> None:
    global _telephony
    _telephony = impl


async def originate_call(call: Call, lead: Lead) -> str | None:
    return await get_telephony().originate_call(call, lead)
