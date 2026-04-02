"""Google OAuth 2.0 Authorization Code flow service.

Uses httpx + PyJWT — no authlib dependency needed.
"""

from __future__ import annotations

import json
import logging
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient

from backend.config import settings

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_SCOPES = "openid email profile"

# Cache the JWKS client (thread-safe, caches keys internally)
_jwks_client = PyJWKClient(GOOGLE_JWKS_URL, cache_keys=True)


@dataclass(frozen=True)
class GoogleUserInfo:
    """User info extracted from Google ID token."""

    sub: str  # Stable unique Google user ID
    email: str
    email_verified: bool
    name: str | None = None
    picture: str | None = None


async def build_auth_url(next_url: str = "/dashboard") -> tuple[str, str]:
    """Build Google OAuth authorization URL with state + nonce.

    Args:
        next_url: URL to redirect to after successful auth.

    Returns:
        Tuple of (google_auth_url, state).
    """
    from backend.services.redis_pool import (
        get_redis,  # noqa: PLC0415 — lazy import to avoid circular imports
    )

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)

    # Store state → {nonce, next_url} in Redis with 5-min TTL
    redis = await get_redis()
    if redis:
        state_data = json.dumps({"nonce": nonce, "next_url": next_url})
        await redis.set(f"oauth_state:{state}", state_data, ex=300)

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "state": state,
        "nonce": nonce,
        "access_type": "offline",
        "prompt": "select_account",
    }
    url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return url, state


async def exchange_code(code: str, state: str) -> tuple[GoogleUserInfo, str]:
    """Exchange authorization code for tokens and extract user info.

    Args:
        code: Authorization code from Google callback.
        state: State parameter from callback (validated against Redis).

    Returns:
        Tuple of (GoogleUserInfo, next_url) — user info and redirect target.

    Raises:
        ValueError: If state is invalid/expired or token validation fails.
        httpx.HTTPError: If Google API request fails.
    """
    from backend.services.redis_pool import (
        get_redis,  # noqa: PLC0415 — lazy import to avoid circular imports
    )

    # Validate state
    redis = await get_redis()
    if not redis:
        msg = "Redis unavailable for OAuth state validation"
        raise ValueError(msg)

    state_key = f"oauth_state:{state}"
    state_data_raw = await redis.get(state_key)
    if not state_data_raw:
        msg = "Invalid or expired OAuth state"
        raise ValueError(msg)

    # Delete state immediately (single-use)
    await redis.delete(state_key)

    if isinstance(state_data_raw, bytes):
        state_data_raw = state_data_raw.decode()
    state_data = json.loads(state_data_raw)
    expected_nonce = state_data["nonce"]
    next_url = state_data.get("next_url", "/dashboard")

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        token_response.raise_for_status()
        tokens = token_response.json()

    id_token_str = tokens.get("id_token")
    if not id_token_str:
        msg = "No id_token in Google token response"
        raise ValueError(msg)

    # Validate ID token
    user_info = _validate_id_token(id_token_str, expected_nonce)

    # Validate next_url is a safe relative path (prevent open redirect)
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/dashboard"

    return user_info, next_url


def _validate_id_token(id_token: str, expected_nonce: str) -> GoogleUserInfo:
    """Validate Google ID token signature and claims.

    Args:
        id_token: JWT ID token from Google.
        expected_nonce: Nonce stored during auth URL generation.

    Returns:
        GoogleUserInfo extracted from validated token.

    Raises:
        ValueError: If token is invalid, expired, or nonce mismatch.
    """
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(id_token)
        payload = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.GOOGLE_CLIENT_ID,
            issuer=["https://accounts.google.com", "accounts.google.com"],
            options={"verify_exp": True},
        )
    except jwt.exceptions.PyJWTError as e:
        msg = "Invalid Google ID token"
        raise ValueError(msg) from e

    # Verify nonce
    if payload.get("nonce") != expected_nonce:
        msg = "Nonce mismatch in Google ID token"
        raise ValueError(msg)

    return GoogleUserInfo(
        sub=payload["sub"],
        email=payload["email"],
        email_verified=payload.get("email_verified", False),
        name=payload.get("name"),
        picture=payload.get("picture"),
    )


def get_next_url_from_state(state_data_raw: str) -> str:
    """Extract next_url from stored state data.

    Args:
        state_data_raw: JSON string stored in Redis.

    Returns:
        The next_url to redirect to after auth.
    """
    try:
        data = json.loads(state_data_raw)
        return data.get("next_url", "/dashboard")
    except (json.JSONDecodeError, KeyError):
        return "/dashboard"
