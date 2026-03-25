"""Redis-backed blocklist for revoked refresh token JTIs.

When a refresh token is rotated (via /refresh) or the user logs out,
the old token's JTI is added to this blocklist with a TTL matching
the token's remaining lifetime. Redis auto-expires entries, so no
manual cleanup is needed.
"""

from __future__ import annotations

import logging

from backend.services.redis_pool import get_redis

logger = logging.getLogger(__name__)

_KEY_PREFIX = "blocklist:jti:"


async def add_to_blocklist(jti: str, expires_in_seconds: int) -> None:
    """Add a revoked refresh token JTI to the blocklist.

    Args:
        jti: The JWT ID claim from the revoked token.
        expires_in_seconds: TTL in seconds (should match remaining token lifetime).
            If <= 0, the token is already expired and does not need blocklisting.
    """
    if expires_in_seconds <= 0:
        return
    r = await get_redis()
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
    r = await get_redis()
    key = f"{_KEY_PREFIX}{jti}"
    return await r.exists(key) > 0


async def close() -> None:
    """Close Redis — delegates to shared pool."""
    from backend.services.redis_pool import close_redis

    await close_redis()
