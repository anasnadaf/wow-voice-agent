"""Bearer auth for admin routes.

Resolution order (nonstick's portfolio-auth pattern):
1. AUTH_URL set — validate the bearer against the external auth service with
   ``GET {AUTH_URL}/auth/me``, forwarding the Authorization header as-is.
2. ADMIN_API_TOKEN set — constant-time compare against the static token.
3. Neither — dev mode, everything is allowed.
"""

import secrets

import httpx
from fastapi import Header, HTTPException

from app.config import settings


async def verify_admin(authorization: str | None) -> None:
    """Raise HTTPException unless the Authorization header proves admin access."""
    if settings.auth_url:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token")
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.get(
                    f"{settings.auth_url.rstrip('/')}/auth/me",
                    headers={"Authorization": authorization},
                )
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=503, detail="Auth service unavailable") from exc
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid token")
        return

    if settings.admin_api_token:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token")
        token = authorization.split(" ", 1)[1].strip()
        if not secrets.compare_digest(token, settings.admin_api_token):
            raise HTTPException(status_code=401, detail="Invalid token")
        return

    # dev mode: no auth configured, allow
    return


async def require_admin(authorization: str | None = Header(default=None)) -> None:
    await verify_admin(authorization)
