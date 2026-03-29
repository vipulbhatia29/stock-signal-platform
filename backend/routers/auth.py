"""Authentication endpoints: register, login, refresh, logout, OIDC SSO."""

import logging
import re
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_async_session
from backend.dependencies import (
    COOKIE_ACCESS_TOKEN,
    COOKIE_PATH,
    COOKIE_REFRESH_TOKEN,
    COOKIE_SAMESITE,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from backend.models.user import User, UserPreference
from backend.rate_limit import limiter
from backend.schemas.auth import (
    TokenRefreshRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserRegisterResponse,
)
from backend.services.oidc_provider import (
    build_discovery_document,
    exchange_auth_code,
    store_auth_code,
)
from backend.services.token_blocklist import add_to_blocklist, is_blocklisted

logger = logging.getLogger(__name__)

router = APIRouter()

PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Z])(?=.*\d).{8,}$")


def _get_token_remaining_ttl(token: str) -> int:
    """Get remaining TTL in seconds for a JWT token.

    Decodes without verification (already validated by decode_token).
    Returns 0 if the token is already expired.
    """
    import time

    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={"verify_exp": False},
    )
    exp = payload.get("exp", 0)
    remaining = int(exp - time.time())
    return max(remaining, 0)


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Set httpOnly auth cookies on the response.

    Args:
        response: FastAPI Response object.
        access_token: JWT access token.
        refresh_token: JWT refresh token.
    """
    response.set_cookie(
        key=COOKIE_ACCESS_TOKEN,
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key=COOKIE_REFRESH_TOKEN,
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )


def _clear_auth_cookies(response: Response) -> None:
    """Clear httpOnly auth cookies from the response."""
    response.delete_cookie(key=COOKIE_ACCESS_TOKEN, path=COOKIE_PATH)
    response.delete_cookie(key=COOKIE_REFRESH_TOKEN, path=COOKIE_PATH)


@router.post(
    "/register",
    response_model=UserRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("3/minute")
async def register(
    request: Request,
    body: UserRegisterRequest,
    db: AsyncSession = Depends(get_async_session),
) -> User:
    """Register a new user.

    Creates the user and their default preferences.
    """
    # Validate password strength
    if not PASSWORD_PATTERN.match(body.password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters with 1 uppercase and 1 digit",
        )

    # Check for duplicate email
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create user
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    await db.flush()

    # Create default preferences
    preference = UserPreference(user_id=user.id)
    db.add(preference)

    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: UserLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_async_session),
) -> TokenResponse:
    """Authenticate user and return JWT token pair.

    Sets httpOnly cookies with the tokens for browser-based auth,
    and also returns them in the JSON body for non-browser clients.
    """
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled",
        )

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    _set_auth_cookies(response, access_token, refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("5/minute")
async def refresh_token(
    request: Request,
    body: TokenRefreshRequest,
    response: Response,
    db: AsyncSession = Depends(get_async_session),
) -> TokenResponse:
    """Exchange a refresh token for a new token pair.

    Validates the old token, checks the blocklist, issues new tokens,
    and blocklists the old refresh token to prevent replay attacks.
    """
    token_payload = decode_token(body.refresh_token, expected_type="refresh")

    # Check if the refresh token has been revoked
    if token_payload.jti and await is_blocklisted(token_payload.jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    # Verify user still exists and is active
    result = await db.execute(select(User).where(User.id == token_payload.user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    access_token = create_access_token(user.id)
    new_refresh_token = create_refresh_token(user.id)

    # Blocklist the old refresh token to prevent reuse
    if token_payload.jti:
        remaining_ttl = _get_token_remaining_ttl(body.refresh_token)
        await add_to_blocklist(token_payload.jti, expires_in_seconds=remaining_ttl)

    _set_auth_cookies(response, access_token, new_refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> None:
    """Log out by clearing auth cookies and revoking the refresh token.

    This endpoint does not require authentication — clearing cookies
    is safe even if the user is already logged out.
    """
    # Try to blocklist the refresh token if present
    refresh_token_value = request.cookies.get(COOKIE_REFRESH_TOKEN)
    if refresh_token_value:
        try:
            token_payload = decode_token(refresh_token_value, expected_type="refresh")
            if token_payload.jti:
                remaining_ttl = _get_token_remaining_ttl(refresh_token_value)
                await add_to_blocklist(token_payload.jti, expires_in_seconds=remaining_ttl)
        except HTTPException:
            # Token already expired or invalid — nothing to blocklist
            pass

    _clear_auth_cookies(response)


# ---------------------------------------------------------------------------
# OIDC endpoints (Langfuse SSO integration)
# ---------------------------------------------------------------------------


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
        redirect_uri: Where to redirect after authorization.
        state: Opaque state parameter passed through to the redirect.
        user: The authenticated user (injected by dependency).

    Returns:
        A redirect to the callback URI with the auth code.
    """
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

    code = await store_auth_code(user.id)

    params = {"code": code}
    if state:
        params["state"] = state
    redirect_url = f"{redirect_uri}?{urlencode(params)}"

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
