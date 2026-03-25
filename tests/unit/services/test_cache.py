"""Tests for CacheService — Redis cache with TTL tiers."""

from unittest.mock import AsyncMock

import pytest

from backend.services.cache import CacheService, CacheTier


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Mock Redis client."""
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock()
    r.delete = AsyncMock()
    r.scan = AsyncMock(return_value=(0, []))
    return r


@pytest.fixture
def cache(mock_redis: AsyncMock) -> CacheService:
    """CacheService with mocked Redis."""
    return CacheService(mock_redis)


class TestGet:
    """Tests for cache get."""

    @pytest.mark.asyncio
    async def test_returns_none_on_miss(self, cache: CacheService, mock_redis: AsyncMock) -> None:
        """Cache miss should return None."""
        result = await cache.get("app:signals:AAPL")
        assert result is None
        mock_redis.get.assert_awaited_once_with("app:signals:AAPL")

    @pytest.mark.asyncio
    async def test_returns_value_on_hit(self, cache: CacheService, mock_redis: AsyncMock) -> None:
        """Cache hit should return stored value."""
        mock_redis.get.return_value = '{"score": 8.5}'
        result = await cache.get("app:signals:AAPL")
        assert result == '{"score": 8.5}'

    @pytest.mark.asyncio
    async def test_get_error_returns_none(self, cache: CacheService, mock_redis: AsyncMock) -> None:
        """Redis error on get should return None, not raise."""
        mock_redis.get.side_effect = ConnectionError("Redis down")
        result = await cache.get("app:signals:AAPL")
        assert result is None


class TestSet:
    """Tests for cache set with TTL tiers."""

    @pytest.mark.asyncio
    async def test_volatile_ttl(self, cache: CacheService, mock_redis: AsyncMock) -> None:
        """Volatile tier should use ~300s TTL."""
        await cache.set("app:price:AAPL", '{"price": 185}', CacheTier.VOLATILE)
        mock_redis.set.assert_awaited_once()
        call_kwargs = mock_redis.set.call_args
        ttl = call_kwargs[1]["ex"]
        assert 270 <= ttl <= 330

    @pytest.mark.asyncio
    async def test_standard_ttl(self, cache: CacheService, mock_redis: AsyncMock) -> None:
        """Standard tier should use ~1800s TTL."""
        await cache.set("app:signals:AAPL", "{}", CacheTier.STANDARD)
        call_kwargs = mock_redis.set.call_args
        ttl = call_kwargs[1]["ex"]
        assert 1620 <= ttl <= 1980

    @pytest.mark.asyncio
    async def test_stable_ttl(self, cache: CacheService, mock_redis: AsyncMock) -> None:
        """Stable tier should use ~86400s TTL."""
        await cache.set("app:indexes", "{}", CacheTier.STABLE)
        call_kwargs = mock_redis.set.call_args
        ttl = call_kwargs[1]["ex"]
        assert 77760 <= ttl <= 95040

    @pytest.mark.asyncio
    async def test_session_ttl_no_jitter(self, cache: CacheService, mock_redis: AsyncMock) -> None:
        """Session tier should use exactly 7200s TTL (no jitter)."""
        await cache.set("session:abc:tool:x", "{}", CacheTier.SESSION)
        call_kwargs = mock_redis.set.call_args
        assert call_kwargs[1]["ex"] == 7200


class TestDelete:
    """Tests for cache delete."""

    @pytest.mark.asyncio
    async def test_delete_single_key(self, cache: CacheService, mock_redis: AsyncMock) -> None:
        """Should delete a single key."""
        await cache.delete("app:signals:AAPL")
        mock_redis.delete.assert_awaited_once_with("app:signals:AAPL")


class TestInvalidateTicker:
    """Tests for ticker-level invalidation."""

    @pytest.mark.asyncio
    async def test_invalidate_deletes_matching_keys(
        self, cache: CacheService, mock_redis: AsyncMock
    ) -> None:
        """Should delete known prefix keys + scan for extras."""
        mock_redis.scan.return_value = (0, ["app:extra:AAPL"])
        deleted = await cache.invalidate_ticker("AAPL")
        assert deleted >= 4  # 4 known prefixes + extras
        assert mock_redis.delete.call_count >= 4


class TestDeletePattern:
    """Tests for pattern-based deletion."""

    @pytest.mark.asyncio
    async def test_delete_pattern_uses_scan(
        self, cache: CacheService, mock_redis: AsyncMock
    ) -> None:
        """Should use SCAN (not KEYS) for safe pattern deletion."""
        mock_redis.scan.return_value = (0, ["app:screener:abc", "app:screener:def"])
        deleted = await cache.delete_pattern("app:screener:*")
        assert deleted == 2
        mock_redis.scan.assert_awaited()

    @pytest.mark.asyncio
    async def test_delete_pattern_empty_returns_zero(
        self, cache: CacheService, mock_redis: AsyncMock
    ) -> None:
        """No matching keys should return 0."""
        mock_redis.scan.return_value = (0, [])
        deleted = await cache.delete_pattern("app:nonexistent:*")
        assert deleted == 0
