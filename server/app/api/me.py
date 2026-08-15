from fastapi import APIRouter, Depends

from app.auth import require_admin
from app.config import settings

router = APIRouter(prefix="/api", tags=["auth"])


@router.get("/me", dependencies=[Depends(require_admin)])
async def me() -> dict[str, str | bool]:
    """Auth probe for the dashboard: 200 iff the bearer token is valid."""
    if settings.auth_url:
        mode = "auth_url"
    elif settings.admin_api_token:
        mode = "token"
    else:
        mode = "dev"
    return {"authenticated": True, "mode": mode}
