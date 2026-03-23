"""Redis-backed blocklist for revoked refresh token JTIs.

When a refresh token is rotated (via /refresh) or the user logs out,
the old token's JTI is added to this blocklist with a TTL matching
the token's remaining lifetime. Redis auto-expires entries, so no
manual cleanup is needed.
"""

import logging

import redis.asyncio as aioredis

from backend.config import settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "blocklist:jti:"

# Lazy singleton — created on first use, reused thereafter.
_redis_client: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    """Get or create the async Redis client singleton."""
    global _redis_client  # noqa: PLW0603
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
    return _redis_client


async def add_to_blocklist(jti: str, expires_in_seconds: int) -> None:
    """Add a revoked refresh token JTI to the blocklist.

    Args:
        jti: The JWT ID claim from the revoked token.
        expires_in_seconds: TTL in seconds (should match remaining token lifetime).
            If <= 0, the token is already expired and does not need blocklisting.
    """
    if expires_in_seconds <= 0:
        return
    r = _get_redis()
    key = f"{_KEY_PREFIX}{jti}"
    await r.set(key, "1", ex=expires_in_seconds)
    logger.debug("Blocklisted JTI %s (TTL=%ds)", jti, expires_in_seconds)


async def is_blocklisted(jti: str) -> bool:
    """Check if a refresh token JTI has been revoked.

    Args:
        jti: The JWT ID claim to check.

    Returns:
        True if the JTI is in the blocklist (revoked), False otherwise.
    """
    r = _get_redis()
    key = f"{_KEY_PREFIX}{jti}"
    return await r.exists(key) > 0


async def close() -> None:
    """Close the Redis connection pool. Call on app shutdown."""
    global _redis_client  # noqa: PLW0603
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
