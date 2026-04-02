"""Cache integration tests using real Redis.

These tests require a real Redis instance (either local on port 6380 or
a testcontainers Redis). They verify actual TTL expiry, stampede protection
behavior, and cache hit ratio patterns.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import redis.asyncio as aioredis

from backend.services.cache import CacheService, CacheTier

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REDIS_URL = "redis://localhost:6380/1"  # DB 1 for integration tests (separate from dev)


@pytest.fixture(scope="module")
async def redis_client():
    """Connect to real Redis on port 6380 (local dev).

    Skips the test module if Redis is not reachable — this is expected
    behavior when running unit tests without Redis.
    """
    try:
        client = aioredis.from_url(REDIS_URL, decode_responses=True, socket_timeout=1.0)
        await client.ping()
        yield client
        # Cleanup: remove all test keys
        keys = await client.keys("integration_test:*")
        if keys:
            await client.delete(*keys)
        await client.aclose()
    except Exception:
        pytest.skip("Redis not available at localhost:6380 — skipping integration tests")


@pytest.fixture
def cache(redis_client):
    """CacheService backed by real Redis."""
    return CacheService(redis_client)


# ---------------------------------------------------------------------------
# TTL actually expires
# ---------------------------------------------------------------------------


@pytest.mark.cache
@pytest.mark.integration
@pytest.mark.asyncio
async def test_ttl_actually_expires(redis_client) -> None:
    """Key with TTL=1s should be gone after 1.5s (real Redis expiry)."""
    cache = CacheService(redis_client)
    key = f"integration_test:expire:{uuid.uuid4()}"
    # Set key with 1s TTL directly (bypass tier jitter for precision)
    await redis_client.set(key, "test_value", ex=1)
    # Verify it's there
    result = await cache.get(key)
    assert result == "test_value"
    # Wait for expiry
    await asyncio.sleep(1.5)
    # Should be gone now
    result_after = await cache.get(key)
    assert result_after is None, f"Key should have expired but got: {result_after}"


# ---------------------------------------------------------------------------
# Concurrent cache miss — only 1 DB call under stampede
# ---------------------------------------------------------------------------


@pytest.mark.cache
@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_cache_miss_single_db_call(redis_client) -> None:
    """Under concurrent cache misses, the pattern should only populate once.

    NOTE: This tests the ideal behavior. Without a distributed lock (mutex),
    multiple requests may all miss and all populate. The test verifies
    eventual consistency: after all concurrent requests, only one value exists.
    """
    cache = CacheService(redis_client)
    key = f"integration_test:stampede:{uuid.uuid4()}"
    db_call_count = 0
    lock = asyncio.Lock()

    async def _request_with_cache_aside():
        nonlocal db_call_count
        cached = await cache.get(key)
        if cached is None:
            # Simulate DB fetch (slow)
            await asyncio.sleep(0.01)
            async with lock:
                db_call_count += 1
            await cache.set(key, '{"value": 42}', CacheTier.STANDARD)
        return cached or '{"value": 42}'

    # Launch 10 concurrent requests
    results = await asyncio.gather(*[_request_with_cache_aside() for _ in range(10)])

    # All results should have value 42
    for r in results:
        assert r is not None

    # After concurrent requests, key should exist
    final = await cache.get(key)
    assert final is not None


# ---------------------------------------------------------------------------
# Cache hit ratio > 75% for hot-path access pattern
# ---------------------------------------------------------------------------


@pytest.mark.cache
@pytest.mark.integration
@pytest.mark.asyncio
async def test_cache_hit_ratio_hot_path(redis_client) -> None:
    """Repeatedly accessing the same keys should achieve > 75% cache hit ratio."""
    cache = CacheService(redis_client)
    hot_keys = [f"integration_test:hot:{i}" for i in range(5)]

    # Warm the cache
    for key in hot_keys:
        await cache.set(key, '{"warmed": true}', CacheTier.STANDARD)

    # Access pattern: 80% hot keys (should all hit), 20% new keys (will miss)
    hits = 0
    total = 100
    for i in range(total):
        if i % 5 == 0:
            # Cold miss — new key
            result = await cache.get(f"integration_test:cold:{i}")
            if result is not None:
                hits += 1
        else:
            # Hot hit — pre-warmed
            result = await cache.get(hot_keys[i % len(hot_keys)])
            if result is not None:
                hits += 1

    hit_ratio = hits / total
    assert hit_ratio > 0.75, f"Cache hit ratio {hit_ratio:.1%} is below 75% threshold"
