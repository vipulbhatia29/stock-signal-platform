"""Redis-backed blocklist for revoked refresh token JTIs.

When a refresh token is rotated (via /refresh) or the user logs out,
the old token's JTI is added to this blocklist with a TTL matching
the token's remaining lifetime. Redis auto-expires entries, so no
manual cleanup is needed.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from backend.config import settings
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


async def set_user_revocation(user_id: uuid.UUID) -> None:
    """Set a user-level revocation timestamp. All tokens issued before this are invalid.

    Args:
        user_id: The UUID of the user whose tokens should be revoked.
    """
    r = await get_redis()
    key = f"user_revocation:{user_id}"
    timestamp = datetime.now(timezone.utc).isoformat()
    ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    await r.set(key, timestamp, ex=ttl)
    logger.debug("Set user-level revocation for user %s (TTL=%ds)", user_id, ttl)


async def check_user_revocation(user_id: uuid.UUID, token_iat: datetime) -> bool:
    """Check if a token is revoked based on user-level revocation timestamp.

    Args:
        user_id: The UUID of the user who owns the token.
        token_iat: The issued-at datetime from the token's ``iat`` claim.

    Returns:
        True if the token should be rejected (iat before revocation time),
        False otherwise (including when no revocation record exists).
    """
    r = await get_redis()
    if r is None:
        return False  # Graceful degradation — allow if Redis unavailable
    key = f"user_revocation:{user_id}"
    revocation_ts = await r.get(key)
    if revocation_ts is None:
        return False
    if isinstance(revocation_ts, bytes):
        revocation_ts = revocation_ts.decode()
    revocation_time = datetime.fromisoformat(revocation_ts)
    return token_iat < revocation_time


async def close() -> None:
    """Close Redis — delegates to shared pool."""
    from backend.services.redis_pool import close_redis

    await close_redis()
