"""Shared FastAPI dependencies: auth, database, redis."""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt as _bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import PyJWTError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_async_session
from backend.models.user import User, UserRole
from backend.services.cache import CacheService, CacheTier

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TokenPayload:
    """Decoded JWT token payload."""

    user_id: uuid.UUID
    jti: str | None = None
    iat: datetime | None = None


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

# ---------- Cached user schema (no hashed_password) ----------


class CachedUser(BaseModel):
    """Lightweight user representation for Redis cache.

    Excludes hashed_password for security. Fields mirror User ORM model
    so downstream code can use .id, .email, .role, .is_active transparently.
    """

    model_config = {"from_attributes": True}

    id: uuid.UUID
    email: str
    role: UserRole
    is_active: bool
    email_verified: bool
    has_password: bool  # True if hashed_password is not None
    created_at: datetime
    updated_at: datetime


# Cookie configuration constants
COOKIE_ACCESS_TOKEN = "access_token"  # nosemgrep: no-secrets-in-code — cookie key, not a secret
COOKIE_REFRESH_TOKEN = "refresh_token"  # nosemgrep: no-secrets-in-code — cookie key, not a secret
COOKIE_CSRF_TOKEN = "csrf_token"  # nosemgrep: no-secrets-in-code — cookie key, not a secret
COOKIE_SAMESITE = "lax"
COOKIE_PATH = "/"


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return _bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def create_access_token(user_id: uuid.UUID) -> str:
    """Create a short-lived JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "access",
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: uuid.UUID) -> str:
    """Create a longer-lived JWT refresh token with a unique JTI claim."""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, expected_type: str = "access") -> TokenPayload:
    """Decode and validate a JWT token, returning the token payload.

    Args:
        token: The JWT token string.
        expected_type: Expected token type ("access" or "refresh").

    Returns:
        TokenPayload with user_id and optional jti.

    Raises:
        HTTPException: If the token is invalid, expired, or wrong type.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id_str: str | None = payload.get("sub")
        token_type: str | None = payload.get("type")
        if user_id_str is None or token_type != expected_type:
            raise credentials_exception
        iat_raw = payload.get("iat")
        iat = datetime.fromtimestamp(iat_raw, tz=timezone.utc) if iat_raw else None
        return TokenPayload(
            user_id=uuid.UUID(user_id_str),
            jti=payload.get("jti"),
            iat=iat,
        )
    except (PyJWTError, ValueError) as e:
        try:
            from backend.observability.instrumentation.auth import emit_auth_event
            from backend.observability.schema.auth_events import AuthEventType, AuthOutcome

            emit_auth_event(
                auth_event_type=AuthEventType.JWT_VERIFY_FAILURE,
                outcome=AuthOutcome.FAILURE,
                failure_reason="expired" if "expired" in str(e).lower() else "malformed",
            )
        except Exception:  # noqa: BLE001 — emission must never block auth
            pass
        raise credentials_exception


def _extract_token(request: Request) -> str | None:
    """Extract JWT access token from Authorization header or cookie.

    Header takes precedence over cookie for backward compatibility with
    non-browser clients (e.g. tests, scripts, mobile apps).
    """
    # 1. Try Authorization header first
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.removeprefix("Bearer ").strip()

    # 2. Fall back to httpOnly cookie
    return request.cookies.get(COOKIE_ACCESS_TOKEN)


def _get_cache(request: Request) -> CacheService | None:
    """Safely retrieve CacheService from app state. Returns None if unavailable."""
    return getattr(request.app.state, "cache", None)


def _user_cache_key(user_id: uuid.UUID) -> str:
    """Build the Redis cache key for a user's auth lookup."""
    return f"user:{user_id}:auth"


async def _get_cached_user(cache: CacheService, user_id: uuid.UUID) -> CachedUser | None:
    """Attempt to load a CachedUser from Redis.

    Returns None on cache miss or any deserialization error.
    """
    try:
        raw = await cache.get(_user_cache_key(user_id))
        if raw is None:
            return None
        return CachedUser.model_validate_json(raw)
    except Exception:
        logger.debug("Cache deserialization failed for user %s", user_id, exc_info=True)
        return None


async def _set_cached_user(cache: CacheService, user: User) -> None:
    """Serialize and store a User in Redis (excluding hashed_password)."""
    try:
        cached = CachedUser(
            id=user.id,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            email_verified=user.email_verified,
            has_password=user.hashed_password is not None,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
        await cache.set(
            _user_cache_key(user.id),
            cached.model_dump_json(),
            CacheTier.VOLATILE,
        )
    except Exception:
        logger.debug("Cache set failed for user %s", user.id, exc_info=True)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
) -> User | CachedUser:
    """FastAPI dependency: decode JWT and return the current user.

    Uses Redis cache (VOLATILE tier, ~300s TTL) to avoid hitting the DB
    on every authenticated request. Falls back to DB on cache miss or
    when Redis is unavailable.

    Supports dual-mode authentication:
    - Authorization: Bearer <token> header (takes precedence)
    - httpOnly access_token cookie (fallback for browser clients)

    Raises:
        HTTPException: 401 if no token found, token invalid, or user not found/inactive.
    """
    token = _extract_token(request)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token_payload = decode_token(token, expected_type="access")
    user_id = token_payload.user_id

    # User-level revocation check (graceful — skip if Redis unavailable)
    if token_payload.iat:
        try:
            from backend.services.token_blocklist import check_user_revocation

            if await check_user_revocation(token_payload.user_id, token_payload.iat):
                raise credentials_exception
        except credentials_exception.__class__:
            raise
        except Exception:
            pass  # Redis down — allow request through

    # 1. Try cache first (graceful degradation if cache unavailable)
    cache = _get_cache(request)
    if cache is not None:
        cached = await _get_cached_user(cache, user_id)
        if cached is not None:
            if not cached.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found or inactive",
                )
            return cached

    # 2. Cache miss or no cache — query DB
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # 3. Populate cache for next request
    if cache is not None:
        await _set_cached_user(cache, user)

    return user


def require_admin(user: User | CachedUser) -> User | CachedUser:
    """Raise 403 if user is not an admin.

    Args:
        user: The authenticated user.

    Returns:
        The user if admin.

    Raises:
        HTTPException: 403 if not admin.
    """
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_verified_email(user: User | CachedUser) -> User | CachedUser:
    """Raise 403 if user email is not verified."""
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Email verification required")
    return user
