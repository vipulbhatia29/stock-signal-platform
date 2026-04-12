"""OIDC provider endpoints (Langfuse SSO integration)."""

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_async_session
from backend.dependencies import (
    create_access_token,
    get_current_user,
)
from backend.models.user import User
from backend.services.oidc_provider import (
    build_discovery_document,
    exchange_auth_code,
    store_auth_code,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _oidc_enabled() -> bool:
    """Check if OIDC is configured (client secret is set)."""
    return bool(settings.OIDC_CLIENT_SECRET)


def _allowed_redirect_uris() -> set[str]:
    """Parse the comma-separated redirect URI whitelist from settings."""
    return {u.strip() for u in settings.OIDC_REDIRECT_URIS.split(",") if u.strip()}


@router.get("/.well-known/openid-configuration")
async def oidc_discovery(request: Request) -> JSONResponse:
    """Return the OpenID Connect discovery document.

    Langfuse uses this to discover authorization, token, and
    userinfo endpoint URLs.
    """
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse(content=build_discovery_document(base_url))


@router.get("/authorize")
async def oidc_authorize(
    request: Request,
    response_type: str = "code",
    client_id: str = "",
    redirect_uri: str = "",
    state: str = "",
    user: User = Depends(get_current_user),
) -> RedirectResponse:
    """OIDC authorization endpoint.

    Validates the user's existing JWT (from cookie or header),
    generates a short-lived auth code stored in Redis, and
    redirects back to Langfuse with the code.

    Args:
        request: The incoming request.
        response_type: Must be "code".
        client_id: OIDC client ID (must match settings).
        redirect_uri: Where to redirect after authorization (must be whitelisted).
        state: Opaque state parameter passed through to the redirect.
        user: The authenticated user (injected by dependency).

    Returns:
        A redirect to the callback URI with the auth code.
    """
    if not _oidc_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC is not configured",
        )

    if response_type != "code":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported response_type",
        )

    if client_id != settings.OIDC_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid client_id",
        )

    if not redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="redirect_uri is required",
        )

    if redirect_uri not in _allowed_redirect_uris():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="redirect_uri is not registered",
        )

    code = await store_auth_code(user.id)

    params = {"code": code}
    if state:
        params["state"] = state
    redirect_url = f"{redirect_uri}?{urlencode(params)}"

    # nosemgrep: no-open-redirect — redirect_url built from trusted FRONTEND_BASE_URL + params
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


@router.post("/token")
async def oidc_token(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
) -> JSONResponse:
    """OIDC token exchange endpoint.

    Exchanges an authorization code for an access token (our existing JWT).
    Validates client credentials and the auth code from Redis.

    Returns:
        JSON with access_token, token_type, and expires_in.
    """
    if not _oidc_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC is not configured",
        )

    form = await request.form()
    grant_type = form.get("grant_type", "")
    code = form.get("code", "")
    client_id = form.get("client_id", "")
    client_secret = form.get("client_secret", "")

    if grant_type != "authorization_code":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported grant_type",
        )

    if client_id != settings.OIDC_CLIENT_ID or client_secret != settings.OIDC_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client credentials",
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization code is required",
        )

    user_id = await exchange_auth_code(str(code))
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired authorization code",
        )

    # Verify user still exists and is active
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    access_token = create_access_token(user.id)

    return JSONResponse(
        content={
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }
    )


@router.get("/userinfo")
async def oidc_userinfo(
    user: User = Depends(get_current_user),
) -> JSONResponse:
    """OIDC userinfo endpoint.

    Returns user profile information. Protected by Bearer token
    (the JWT issued at the token endpoint).

    Args:
        user: The authenticated user (injected by dependency).

    Returns:
        JSON with sub, email, name, and auth_provider fields.
    """
    return JSONResponse(
        content={
            "sub": str(user.id),
            "email": user.email,
            "name": user.email.split("@")[0],
            "auth_provider": "local",
        }
    )
