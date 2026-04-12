"""Tests for Redis token-bucket rate limiter."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest


class TestTokenBucketLimiter:
    """Tests for the token bucket acquire/refill logic."""

    @pytest.mark.asyncio
    async def test_acquire_succeeds_when_tokens_available(self) -> None:
        """Fresh bucket has full capacity — acquire returns True immediately."""
        from backend.services.rate_limiter import TokenBucketLimiter

        limiter = TokenBucketLimiter("test", capacity=5, refill_per_sec=1.0)
        with patch("backend.services.rate_limiter.get_redis") as mock_redis_fn:
            mock_redis = AsyncMock()
            mock_redis.evalsha.return_value = 1
            mock_redis.script_load.return_value = "fake-sha"
            mock_redis_fn.return_value = mock_redis

            result = await limiter.acquire(timeout=1.0)
            assert result is True

    @pytest.mark.asyncio
    async def test_acquire_times_out_when_bucket_empty(self) -> None:
        """Empty bucket — acquire returns False after timeout."""
        from backend.services.rate_limiter import TokenBucketLimiter

        limiter = TokenBucketLimiter("test", capacity=5, refill_per_sec=1.0)
        with patch("backend.services.rate_limiter.get_redis") as mock_redis_fn:
            mock_redis = AsyncMock()
            mock_redis.evalsha.return_value = 0
            mock_redis.script_load.return_value = "fake-sha"
            mock_redis_fn.return_value = mock_redis

            start = time.monotonic()
            result = await limiter.acquire(timeout=0.5)
            elapsed = time.monotonic() - start

            assert result is False
            assert elapsed >= 0.4  # Waited at least close to timeout

    @pytest.mark.asyncio
    async def test_acquire_noop_when_script_load_fails(self) -> None:
        """If script_load raises, acquire returns True (permissive fallback)."""
        from backend.services.rate_limiter import TokenBucketLimiter

        limiter = TokenBucketLimiter("test", capacity=5, refill_per_sec=1.0)
        with patch("backend.services.rate_limiter.get_redis") as mock_redis_fn:
            mock_redis = AsyncMock()
            mock_redis.script_load.side_effect = ConnectionError("refused")
            mock_redis_fn.return_value = mock_redis

            result = await limiter.acquire(timeout=1.0)
            assert result is True

    @pytest.mark.asyncio
    async def test_named_limiters_are_isolated(self) -> None:
        """Different limiter names use different Redis keys."""
        from backend.services.rate_limiter import TokenBucketLimiter

        limiter_a = TokenBucketLimiter("provider_a", capacity=5, refill_per_sec=1.0)
        limiter_b = TokenBucketLimiter("provider_b", capacity=5, refill_per_sec=1.0)

        with patch("backend.services.rate_limiter.get_redis") as mock_redis_fn:
            mock_redis = AsyncMock()
            mock_redis.evalsha.return_value = 1
            mock_redis.script_load.return_value = "fake-sha"
            mock_redis_fn.return_value = mock_redis

            await limiter_a.acquire(timeout=1.0)
            await limiter_b.acquire(timeout=1.0)

            # Verify they use different keys
            calls = mock_redis.evalsha.call_args_list
            key_a = calls[0][0][2]  # 3rd positional arg is the key
            key_b = calls[1][0][2]
            assert key_a == "ratelimit:provider_a"
            assert key_b == "ratelimit:provider_b"

    @pytest.mark.asyncio
    async def test_script_load_called_once(self) -> None:
        """Lua script is loaded once then reused via SHA."""
        from backend.services.rate_limiter import TokenBucketLimiter

        limiter = TokenBucketLimiter("test", capacity=5, refill_per_sec=1.0)
        with patch("backend.services.rate_limiter.get_redis") as mock_redis_fn:
            mock_redis = AsyncMock()
            mock_redis.evalsha.return_value = 1
            mock_redis.script_load.return_value = "sha123"
            mock_redis_fn.return_value = mock_redis

            await limiter.acquire(timeout=1.0)
            await limiter.acquire(timeout=1.0)

            assert mock_redis.script_load.call_count == 1


class TestRedisFallbackPaths:
    """Tests for Redis error scenarios — the actual production fallback paths."""

    @pytest.mark.asyncio
    async def test_acquire_returns_true_on_connection_error(self) -> None:
        """If Redis raises ConnectionError, acquire permits the request."""
        from backend.services.rate_limiter import TokenBucketLimiter

        limiter = TokenBucketLimiter("test", capacity=5, refill_per_sec=1.0)
        with patch("backend.services.rate_limiter.get_redis") as mock_redis_fn:
            mock_redis_fn.side_effect = ConnectionError("Redis unavailable")

            result = await limiter.acquire(timeout=1.0)
            assert result is True

    @pytest.mark.asyncio
    async def test_acquire_recovers_from_noscript_error(self) -> None:
        """NOSCRIPT error resets _sha and retries on next iteration."""
        from redis.exceptions import ResponseError

        from backend.services.rate_limiter import TokenBucketLimiter

        limiter = TokenBucketLimiter("test", capacity=5, refill_per_sec=1.0)
        with patch("backend.services.rate_limiter.get_redis") as mock_redis_fn:
            mock_redis = AsyncMock()
            mock_redis.script_load.return_value = "new-sha"
            # First evalsha raises NOSCRIPT, second succeeds
            mock_redis.evalsha.side_effect = [
                ResponseError("NOSCRIPT No matching script"),
                1,
            ]
            mock_redis_fn.return_value = mock_redis

            result = await limiter.acquire(timeout=2.0)
            assert result is True
            # SHA was reset and script reloaded
            assert mock_redis.script_load.call_count == 2
            assert limiter._sha == "new-sha"

    @pytest.mark.asyncio
    async def test_acquire_returns_true_on_unexpected_redis_error(self) -> None:
        """Unexpected Redis errors are permissive (allow request)."""
        from backend.services.rate_limiter import TokenBucketLimiter

        limiter = TokenBucketLimiter("test", capacity=5, refill_per_sec=1.0)
        with patch("backend.services.rate_limiter.get_redis") as mock_redis_fn:
            mock_redis = AsyncMock()
            mock_redis.script_load.return_value = "sha"
            mock_redis.evalsha.side_effect = RuntimeError("unexpected")
            mock_redis_fn.return_value = mock_redis

            result = await limiter.acquire(timeout=1.0)
            assert result is True


class TestNamedLimiterInstances:
    """Verify the module-level singleton instances have correct config."""

    def test_yfinance_limiter_config(self) -> None:
        """yfinance limiter: 30 capacity, 0.5/sec refill (30 RPM)."""
        from backend.services.rate_limiter import yfinance_limiter

        assert yfinance_limiter.name == "yfinance"
        assert yfinance_limiter.capacity == 30
        assert yfinance_limiter.refill_per_sec == 0.5

    def test_finnhub_limiter_config(self) -> None:
        """Finnhub limiter: 60 capacity, 1.0/sec refill (60 RPM)."""
        from backend.services.rate_limiter import finnhub_limiter

        assert finnhub_limiter.name == "finnhub"
        assert finnhub_limiter.capacity == 60
        assert finnhub_limiter.refill_per_sec == 1.0

    def test_edgar_limiter_config(self) -> None:
        """EDGAR limiter: 10 capacity, 10/sec refill (10 RPS)."""
        from backend.services.rate_limiter import edgar_limiter

        assert edgar_limiter.name == "edgar"
        assert edgar_limiter.capacity == 10
        assert edgar_limiter.refill_per_sec == 10.0

    def test_google_news_limiter_config(self) -> None:
        """Google News limiter: 20 capacity, 0.33/sec refill (20 RPM)."""
        from backend.services.rate_limiter import google_news_limiter

        assert google_news_limiter.name == "google_news"
        assert google_news_limiter.capacity == 20

    def test_fed_limiter_config(self) -> None:
        """Fed/FRED limiter: 5 capacity, 0.5/sec refill."""
        from backend.services.rate_limiter import fed_limiter

        assert fed_limiter.name == "fed"
        assert fed_limiter.capacity == 5
        assert fed_limiter.refill_per_sec == 0.5
