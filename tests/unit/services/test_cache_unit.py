"""Cache unit tests using fakeredis.

Tests TTL correctness, cache-aside pattern, write-through invalidation,
pattern invalidation, graceful Redis failures, CachedUser serialization,
and token blocklist behavior.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest

from backend.services.cache import CacheService, CacheTier

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_redis():
    """Provide an in-memory async fakeredis instance."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def cache(fake_redis):
    """CacheService backed by fakeredis."""
    return CacheService(fake_redis)


# ---------------------------------------------------------------------------
# TTL tests
# ---------------------------------------------------------------------------


@pytest.mark.cache
@pytest.mark.asyncio
async def test_volatile_ttl_within_range(fake_redis) -> None:
    """VOLATILE tier TTL should be ~300s (with ±10% jitter, so 270-330s)."""
    cache = CacheService(fake_redis)
    await cache.set("app:price:AAPL", '{"price": 185}', CacheTier.VOLATILE)
    ttl = await fake_redis.ttl("app:price:AAPL")
    assert 270 <= ttl <= 330, f"VOLATILE TTL={ttl} out of expected range [270, 330]"


@pytest.mark.cache
@pytest.mark.asyncio
async def test_standard_ttl_within_range(fake_redis) -> None:
    """STANDARD tier TTL should be ~1800s (±10% jitter, so 1620-1980s)."""
    cache = CacheService(fake_redis)
    await cache.set("app:signals:AAPL", '{"score": 7.5}', CacheTier.STANDARD)
    ttl = await fake_redis.ttl("app:signals:AAPL")
    assert 1620 <= ttl <= 1980, f"STANDARD TTL={ttl} out of expected range [1620, 1980]"


@pytest.mark.cache
@pytest.mark.asyncio
async def test_stable_ttl_within_range(fake_redis) -> None:
    """STABLE tier TTL should be ~86400s (±10% jitter, so 77760-95040s)."""
    cache = CacheService(fake_redis)
    await cache.set("app:fundamentals:AAPL", '{"pe": 25}', CacheTier.STABLE)
    ttl = await fake_redis.ttl("app:fundamentals:AAPL")
    assert 77760 <= ttl <= 95040, f"STABLE TTL={ttl} out of expected range"


@pytest.mark.cache
@pytest.mark.asyncio
async def test_session_ttl_fixed(fake_redis) -> None:
    """SESSION tier TTL should be exactly 7200s (no jitter)."""
    cache = CacheService(fake_redis)
    await cache.set("session:abc123", '{"data": true}', CacheTier.SESSION)
    ttl = await fake_redis.ttl("session:abc123")
    assert ttl == 7200, f"SESSION TTL={ttl} must be exactly 7200"


# ---------------------------------------------------------------------------
# Cache-aside pattern
# ---------------------------------------------------------------------------


@pytest.mark.cache
@pytest.mark.asyncio
async def test_cache_aside_miss_then_hit(cache: CacheService, fake_redis) -> None:
    """Cache miss → populate → subsequent call hits cache (1 DB call total)."""
    key = "app:signals:MSFT"
    db_call_count = 0

    async def _simulate_db_fetch():
        nonlocal db_call_count
        db_call_count += 1
        return '{"score": 8.0}'

    # First call — cache miss
    cached = await cache.get(key)
    assert cached is None, "Should be a cache miss initially"
    # Simulate DB fetch + populate cache
    value = await _simulate_db_fetch()
    await cache.set(key, value, CacheTier.STANDARD)

    # Second call — should be cache hit
    cached2 = await cache.get(key)
    assert cached2 == '{"score": 8.0}'
    assert db_call_count == 1, "DB should only be called once"


@pytest.mark.cache
@pytest.mark.asyncio
async def test_cache_miss_returns_none(cache: CacheService) -> None:
    """A key not in cache must return None."""
    result = await cache.get("app:nonexistent:KEY")
    assert result is None


# ---------------------------------------------------------------------------
# Write-through invalidation
# ---------------------------------------------------------------------------


@pytest.mark.cache
@pytest.mark.asyncio
async def test_write_through_invalidation_clears_key(cache: CacheService, fake_redis) -> None:
    """After a DB write, cache.delete() should clear the key."""
    key = "app:signals:GOOG"
    await cache.set(key, '{"score": 7.0}', CacheTier.STANDARD)
    # Verify it's set
    assert await cache.get(key) == '{"score": 7.0}'
    # Simulate DB write → invalidate
    await cache.delete(key)
    # Should be gone
    assert await cache.get(key) is None


@pytest.mark.cache
@pytest.mark.asyncio
async def test_write_through_invalidate_ticker(cache: CacheService, fake_redis) -> None:
    """invalidate_ticker() must clear all ticker-related keys."""
    ticker = "TSLA"
    await cache.set(f"app:signals:{ticker}", '{"score": 6.0}', CacheTier.STANDARD)
    await cache.set(f"app:price:{ticker}", '{"price": 200}', CacheTier.VOLATILE)
    await cache.set(f"app:fundamentals:{ticker}", '{"pe": 40}', CacheTier.STABLE)

    await cache.invalidate_ticker(ticker)

    assert await cache.get(f"app:signals:{ticker}") is None
    assert await cache.get(f"app:price:{ticker}") is None
    assert await cache.get(f"app:fundamentals:{ticker}") is None


# ---------------------------------------------------------------------------
# Pattern invalidation
# ---------------------------------------------------------------------------


@pytest.mark.cache
@pytest.mark.asyncio
async def test_pattern_invalidation_clears_user_keys(cache: CacheService, fake_redis) -> None:
    """delete_pattern('user:{id}:*') must clear all user cache keys."""
    user_id = str(uuid.uuid4())
    keys = [
        f"user:{user_id}:portfolio",
        f"user:{user_id}:watchlist",
        f"user:{user_id}:preferences",
    ]
    for key in keys:
        await fake_redis.set(key, "data", ex=3600)

    # Verify keys exist
    for key in keys:
        assert await cache.get(key) is not None

    # Invalidate all user keys
    deleted = await cache.delete_pattern(f"user:{user_id}:*")
    assert deleted == 3, f"Expected 3 deleted keys, got {deleted}"

    # Verify all gone
    for key in keys:
        assert await cache.get(key) is None


# ---------------------------------------------------------------------------
# Graceful Redis down — cache operations should not raise
# ---------------------------------------------------------------------------


@pytest.mark.cache
@pytest.mark.asyncio
async def test_cache_get_redis_down_returns_none() -> None:
    """When Redis is unavailable, get() returns None instead of raising."""
    broken_redis = AsyncMock()
    broken_redis.get.side_effect = ConnectionError("Redis unavailable")
    cache = CacheService(broken_redis)
    result = await cache.get("any:key")
    assert result is None


@pytest.mark.cache
@pytest.mark.asyncio
async def test_cache_set_redis_down_does_not_raise() -> None:
    """When Redis is unavailable, set() swallows the error gracefully."""
    broken_redis = AsyncMock()
    broken_redis.set.side_effect = ConnectionError("Redis unavailable")
    cache = CacheService(broken_redis)
    # Should not raise
    await cache.set("any:key", "value", CacheTier.STANDARD)


# ---------------------------------------------------------------------------
# CachedUser serialization roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.cache
@pytest.mark.asyncio
async def test_cached_user_json_roundtrip(cache: CacheService) -> None:
    """CachedUser JSON roundtrip must preserve all fields including email_verified, has_password."""
    user_id = str(uuid.uuid4())
    cached_user = {
        "id": user_id,
        "email": "test@example.com",
        "role": "USER",
        "email_verified": True,
        "has_password": False,
        "is_active": True,
    }
    key = f"user:{user_id}:profile"
    serialized = json.dumps(cached_user)
    await cache.set(key, serialized, CacheTier.SESSION)
    raw = await cache.get(key)
    assert raw is not None
    recovered = json.loads(raw)
    assert recovered["email_verified"] is True, "email_verified must survive roundtrip"
    assert recovered["has_password"] is False, "has_password must survive roundtrip"
    assert recovered["id"] == user_id
    assert recovered["email"] == "test@example.com"


@pytest.mark.cache
@pytest.mark.asyncio
async def test_cached_user_all_fields_preserved(cache: CacheService) -> None:
    """JSON serialization must preserve all CachedUser fields faithfully."""
    user_id = str(uuid.uuid4())
    cached_user = {
        "id": user_id,
        "email": "admin@example.com",
        "role": "ADMIN",
        "email_verified": False,
        "has_password": True,
        "is_active": True,
    }
    key = f"user:{user_id}:profile"
    await cache.set(key, json.dumps(cached_user), CacheTier.SESSION)
    raw = await cache.get(key)
    recovered = json.loads(raw)
    for field, expected_value in cached_user.items():
        assert recovered[field] == expected_value, (
            f"Field {field}: expected {expected_value}, got {recovered[field]}"
        )


# ---------------------------------------------------------------------------
# Token blocklist tests (fakeredis)
# ---------------------------------------------------------------------------


@pytest.mark.cache
@pytest.mark.asyncio
async def test_token_blocklist_revoked_token_detected(fake_redis) -> None:
    """A revoked JTI added to blocklist must be detectable."""
    from unittest.mock import AsyncMock

    jti = str(uuid.uuid4())

    with patch("backend.services.token_blocklist.get_redis", return_value=AsyncMock()) as mock_get:
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=1)  # Exists → revoked
        mock_get.return_value = mock_redis

        from backend.services.token_blocklist import add_to_blocklist, is_blocklisted

        await add_to_blocklist(jti, expires_in_seconds=3600)
        result = await is_blocklisted(jti)
        assert result is True, "Revoked JTI should be detected in blocklist"


@pytest.mark.cache
@pytest.mark.asyncio
async def test_token_blocklist_non_revoked_passes(fake_redis) -> None:
    """A JTI not in the blocklist should pass (not be revoked)."""
    from unittest.mock import AsyncMock

    jti = str(uuid.uuid4())

    with patch("backend.services.token_blocklist.get_redis") as mock_get:
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=0)  # Not found → not revoked
        mock_get.return_value = mock_redis

        from backend.services.token_blocklist import is_blocklisted

        result = await is_blocklisted(jti)
        assert result is False, "Non-revoked JTI should not be in blocklist"


@pytest.mark.cache
@pytest.mark.asyncio
async def test_token_blocklist_expired_ttl_not_added() -> None:
    """add_to_blocklist with expires_in_seconds <= 0 should not set any key."""
    from unittest.mock import AsyncMock

    jti = str(uuid.uuid4())

    with patch("backend.services.token_blocklist.get_redis") as mock_get:
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        mock_get.return_value = mock_redis

        from backend.services.token_blocklist import add_to_blocklist

        await add_to_blocklist(jti, expires_in_seconds=0)
        mock_redis.set.assert_not_awaited()


@pytest.mark.cache
@pytest.mark.asyncio
async def test_token_blocklist_fail_closed_redis_down() -> None:
    """When Redis is down, is_blocklisted should raise (fail-closed) for security.

    The fail-closed behavior means we cannot verify if a token is revoked,
    so we conservatively reject (the caller in /refresh should reject).
    """
    from unittest.mock import AsyncMock

    jti = str(uuid.uuid4())

    with patch("backend.services.token_blocklist.get_redis") as mock_get:
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(side_effect=ConnectionError("Redis down"))
        mock_get.return_value = mock_redis

        from backend.services.token_blocklist import is_blocklisted

        # When Redis is down during blocklist check, it should raise (fail-closed)
        # so the caller can reject the token
        with pytest.raises(Exception):
            await is_blocklisted(jti)
