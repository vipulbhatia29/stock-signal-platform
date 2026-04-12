"""Core auth endpoints: register, login, refresh, logout, me."""

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_async_session
from backend.dependencies import (
    COOKIE_REFRESH_TOKEN,
    CachedUser,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from backend.models.user import User, UserPreference
from backend.rate_limit import limiter
from backend.routers.auth._helpers import (
    PASSWORD_PATTERN,
    _clear_auth_cookies,
    _get_token_remaining_ttl,
    _record_login_attempt_bg,
    _send_verification_bg,
    _set_auth_cookies,
)
from backend.schemas.auth import (
    TokenRefreshRequest,
    TokenResponse,
    UserLoginRequest,
    UserProfileResponse,
    UserRegisterRequest,
    UserRegisterResponse,
)
from backend.services.email import generate_token
from backend.services.redis_pool import get_redis
from backend.services.token_blocklist import add_to_blocklist, is_blocklisted

logger = logging.getLogger(__name__)

router = APIRouter()


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

    # Send verification email (or auto-verify in dev mode)
    if settings.ENVIRONMENT == "development":
        user.email_verified = True
        user.email_verified_at = datetime.now(timezone.utc)
        await db.commit()
    else:
        token = generate_token()
        redis = await get_redis()
        if redis:
            await redis.set(  # nosemgrep: no-unbounded-redis-key
                f"email_verify:{token}",
                str(user.id),
                ex=86400,
            )
            await redis.set(  # nosemgrep: no-unbounded-redis-key
                f"email_verify_current:{user.id}",
                token,
                ex=86400,
            )
        asyncio.create_task(_send_verification_bg(user.email, token))

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

    if user is None:
        _record_login_attempt_bg(
            email=body.email,
            success=False,
            user_id=None,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "")[:500],
            failure_reason="invalid_credentials",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Check for deleted account (before is_active check)
    if user.deleted_at is not None:
        _record_login_attempt_bg(
            email=body.email,
            success=False,
            user_id=user.id,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "")[:500],
            failure_reason="account_deleted",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This account has been deleted. Contact support within 30 days to recover.",
        )

    if not user.is_active:
        _record_login_attempt_bg(
            email=body.email,
            success=False,
            user_id=user.id,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "")[:500],
            failure_reason="account_disabled",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled",
        )

    # Google-only user has no password
    if user.hashed_password is None:
        _record_login_attempt_bg(
            email=body.email,
            success=False,
            user_id=user.id,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "")[:500],
            failure_reason="no_password_set",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No password set. Use Google Sign-In or set a password in Account Settings.",
        )

    if not verify_password(body.password, user.hashed_password):
        _record_login_attempt_bg(
            email=body.email,
            success=False,
            user_id=user.id,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "")[:500],
            failure_reason="invalid_credentials",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    _set_auth_cookies(response, access_token, refresh_token)

    _record_login_attempt_bg(
        email=body.email,
        success=True,
        user_id=user.id,
        ip_address=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", "")[:500],
    )

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


@router.get("/me", response_model=UserProfileResponse)
async def get_me(
    user: User | CachedUser = Depends(get_current_user),
) -> UserProfileResponse:
    """Return the current authenticated user's profile.

    Returns:
        The user's id, email, role, and active status.
    """
    return UserProfileResponse(
        id=user.id,
        email=user.email,
        role=user.role.value,
        is_active=user.is_active,
    )
