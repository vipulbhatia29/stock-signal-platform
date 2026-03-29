"""OIDC provider service for Langfuse SSO integration.

Implements a minimal OIDC-compatible layer so Langfuse can authenticate
users against our existing JWT auth system. Stores short-lived auth codes
in Redis and exchanges them for JWTs at the token endpoint.
"""

import logging
import secrets
import uuid

import redis.asyncio as aioredis

from backend.config import settings

logger = logging.getLogger(__name__)

# Redis key prefix for OIDC auth codes
_AUTH_CODE_PREFIX = "oidc:authcode:"
_AUTH_CODE_TTL_SECONDS = 300  # 5 minutes


async def _get_async_redis() -> aioredis.Redis:
    """Create an async Redis client from settings."""
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def store_auth_code(user_id: uuid.UUID) -> str:
    """Generate a random auth code and store it in Redis mapped to the user ID.

    Args:
        user_id: The authenticated user's UUID.

    Returns:
        The generated auth code string.
    """
    code = secrets.token_urlsafe(48)
    r = await _get_async_redis()
    try:
        await r.setex(
            f"{_AUTH_CODE_PREFIX}{code}",
            _AUTH_CODE_TTL_SECONDS,
            str(user_id),
        )
    finally:
        await r.aclose()
    return code


async def exchange_auth_code(code: str) -> uuid.UUID | None:
    """Exchange an auth code for the user ID, consuming the code.

    Args:
        code: The auth code to exchange.

    Returns:
        The user's UUID if the code is valid, None otherwise.
    """
    r = await _get_async_redis()
    try:
        key = f"{_AUTH_CODE_PREFIX}{code}"
        user_id_str = await r.getdel(key)
        if user_id_str is None:
            return None
        return uuid.UUID(user_id_str)
    except (ValueError, AttributeError):
        logger.exception("Failed to exchange OIDC auth code")
        return None
    finally:
        await r.aclose()


def build_discovery_document(base_url: str) -> dict:
    """Build the OpenID Connect discovery document.

    Args:
        base_url: The application's base URL (e.g. http://localhost:8181).

    Returns:
        A dictionary conforming to the OIDC discovery specification.
    """
    auth_prefix = f"{base_url}/api/v1/auth"
    return {
        "issuer": f"{base_url}/api/v1/auth",
        "authorization_endpoint": f"{auth_prefix}/authorize",
        "token_endpoint": f"{auth_prefix}/token",
        "userinfo_endpoint": f"{auth_prefix}/userinfo",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": [settings.JWT_ALGORITHM],
        "scopes_supported": ["openid", "profile", "email"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
    }
