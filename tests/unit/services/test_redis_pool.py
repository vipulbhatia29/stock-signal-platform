"""Tests for shared Redis connection pool."""

from unittest.mock import AsyncMock, patch

import pytest


class TestGetRedis:
    """Tests for get_redis singleton."""

    @pytest.mark.asyncio
    async def test_returns_redis_instance(self) -> None:
        """get_redis should return a Redis client."""
        from backend.services import redis_pool

        redis_pool._pool = None
        with patch("backend.services.redis_pool.aioredis") as mock_redis:
            mock_client = AsyncMock()
            mock_redis.from_url.return_value = mock_client
            result = await redis_pool.get_redis()
            assert result is mock_client
            mock_redis.from_url.assert_called_once()
        redis_pool._pool = None

    @pytest.mark.asyncio
    async def test_returns_same_instance(self) -> None:
        """get_redis should return singleton on second call."""
        from backend.services import redis_pool

        redis_pool._pool = None
        with patch("backend.services.redis_pool.aioredis") as mock_redis:
            mock_client = AsyncMock()
            mock_redis.from_url.return_value = mock_client
            first = await redis_pool.get_redis()
            second = await redis_pool.get_redis()
            assert first is second
            assert mock_redis.from_url.call_count == 1
        redis_pool._pool = None

    @pytest.mark.asyncio
    async def test_close_redis(self) -> None:
        """close_redis should close and clear the singleton."""
        from backend.services import redis_pool

        mock_client = AsyncMock()
        redis_pool._pool = mock_client
        await redis_pool.close_redis()
        mock_client.aclose.assert_awaited_once()
        assert redis_pool._pool is None
