"""Tests for Redis-backed HTTP request metrics middleware."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.observability.metrics.http_middleware import (
    HttpMetricsCollector,
    HttpMetricsMiddleware,
    normalize_path,
)


# ---------------------------------------------------------------------------
# normalize_path
# ---------------------------------------------------------------------------
class TestNormalizePath:
    """Tests for the path normalisation helper."""

    def test_static_path_unchanged(self) -> None:
        """Static API path should pass through without modification."""
        assert normalize_path("/api/v1/stocks") == "/api/v1/stocks"

    def test_uuid_replaced(self) -> None:
        """UUID segments should be replaced with {id}."""
        path = "/api/v1/portfolio/a1b2c3d4-e5f6-7890-abcd-ef1234567890/positions"
        assert normalize_path(path) == "/api/v1/portfolio/{id}/positions"

    def test_ticker_replaced(self) -> None:
        """Uppercase 1-5 char segments (tickers) should become {param}."""
        path = "/api/v1/stocks/AAPL"
        assert normalize_path(path) == "/api/v1/stocks/{param}"

    def test_numeric_replaced(self) -> None:
        """Numeric-only segments should become {num}."""
        path = "/api/v1/alerts/42"
        assert normalize_path(path) == "/api/v1/alerts/{num}"

    def test_excluded_health(self) -> None:
        """Health endpoint should be excluded (returns None)."""
        assert normalize_path("/api/v1/health") is None

    def test_excluded_health_subpath(self) -> None:
        """Health sub-paths should also be excluded."""
        assert normalize_path("/api/v1/health/ready") is None

    def test_excluded_command_center(self) -> None:
        """Command center admin paths should be excluded."""
        assert normalize_path("/api/v1/admin/command-center/metrics") is None

    def test_multi_char_ticker(self) -> None:
        """Multi-character tickers like MSFT should become {param}."""
        path = "/api/v1/stocks/MSFT/signals"
        assert normalize_path(path) == "/api/v1/stocks/{param}/signals"

    def test_lowercase_not_treated_as_ticker(self) -> None:
        """Lowercase path segments should not be replaced as tickers."""
        path = "/api/v1/chat/stream"
        assert normalize_path(path) == "/api/v1/chat/stream"

    def test_root_path(self) -> None:
        """Root path is excluded — only /api/ paths are tracked."""
        assert normalize_path("/") is None


# ---------------------------------------------------------------------------
# HttpMetricsCollector
# ---------------------------------------------------------------------------
class TestHttpMetricsCollector:
    """Tests for the Redis-backed metrics collector."""

    @pytest.fixture()
    def mock_redis(self) -> MagicMock:
        """Return a mock Redis with pipeline support."""
        redis = AsyncMock()
        pipe = MagicMock()
        pipe.hincrby = MagicMock(return_value=pipe)
        pipe.zadd = MagicMock(return_value=pipe)
        pipe.incr = MagicMock(return_value=pipe)
        pipe.execute = AsyncMock(return_value=[])
        # pipeline() is sync (not awaited in record())
        redis.pipeline = MagicMock(return_value=pipe)
        return redis

    @pytest.mark.asyncio()
    async def test_record_calls_pipeline(self, mock_redis: MagicMock) -> None:
        """Successful record should use pipeline with hincrby, zadd, incr."""
        collector = HttpMetricsCollector(redis=mock_redis, window_seconds=300)
        await collector.record("GET", "/api/v1/stocks", 200, 12.5)

        mock_redis.pipeline.assert_called_once_with(transaction=False)
        pipe = mock_redis.pipeline.return_value
        pipe.hincrby.assert_called_once()
        pipe.zadd.assert_called_once()
        # incr called once (today counter, no error)
        assert pipe.incr.call_count == 1
        pipe.execute.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_record_error_increments_error_keys(self, mock_redis: MagicMock) -> None:
        """Status >= 400 should also increment error hash and today_err."""
        collector = HttpMetricsCollector(redis=mock_redis, window_seconds=300)
        await collector.record("POST", "/api/v1/chat", 500, 45.0)

        pipe = mock_redis.pipeline.return_value
        # hincrby called twice: count + errors
        assert pipe.hincrby.call_count == 2
        # incr called twice: today + today_err
        assert pipe.incr.call_count == 2

    @pytest.mark.asyncio()
    async def test_record_swallows_exception(self, mock_redis: MagicMock) -> None:
        """Redis errors in record() should be silently logged, never raised."""
        mock_redis.pipeline.side_effect = RuntimeError("connection lost")
        collector = HttpMetricsCollector(redis=mock_redis, window_seconds=300)
        # Should not raise
        await collector.record("GET", "/api/v1/stocks", 200, 5.0)

    @pytest.mark.asyncio()
    async def test_get_stats_few_samples_returns_null_percentiles(self) -> None:
        """Fewer than 20 latency samples should yield null percentiles."""
        redis = AsyncMock()
        redis.zremrangebyscore = AsyncMock()
        redis.zrangebyscore = AsyncMock(return_value=[b"abc123:10.00", b"def456:20.00"])
        redis.hgetall = AsyncMock(side_effect=[{}, {}])  # count hash, error hash
        redis.get = AsyncMock(return_value=None)

        collector = HttpMetricsCollector(redis=redis, window_seconds=300)
        stats = await collector.get_stats()

        assert stats["latency_p50_ms"] is None
        assert stats["latency_p95_ms"] is None
        assert stats["latency_p99_ms"] is None
        assert stats["rps_avg"] == round(2 / 300, 2)

    @pytest.mark.asyncio()
    async def test_get_stats_enough_samples_computes_percentiles(self) -> None:
        """With >= 20 latency samples, p50/p95/p99 should be computed."""
        # Build 25 latency members
        members = [f"{i:012x}:{float(i + 1):.2f}".encode() for i in range(25)]

        redis = AsyncMock()
        redis.zremrangebyscore = AsyncMock()
        redis.zrangebyscore = AsyncMock(return_value=members)
        redis.hgetall = AsyncMock(
            side_effect=[
                {b"GET:/api:200": b"25"},  # count hash
                {},  # error hash (no errors)
            ]
        )
        redis.get = AsyncMock(return_value=b"25")

        collector = HttpMetricsCollector(redis=redis, window_seconds=300)
        stats = await collector.get_stats()

        assert stats["latency_p50_ms"] is not None
        assert stats["latency_p95_ms"] is not None
        assert stats["latency_p99_ms"] is not None
        assert stats["total_requests_today"] == 25
        assert stats["error_rate_pct"] == 0.0
        assert len(stats["top_endpoints"]) == 1

    @pytest.mark.asyncio()
    async def test_get_stats_error_returns_safe_defaults(self) -> None:
        """Redis failure in get_stats should return safe zero defaults."""
        redis = AsyncMock()
        redis.zremrangebyscore = AsyncMock(side_effect=RuntimeError("boom"))

        collector = HttpMetricsCollector(redis=redis, window_seconds=300)
        stats = await collector.get_stats()

        assert stats["rps_avg"] == 0
        assert stats["latency_p50_ms"] is None
        assert stats["top_endpoints"] == []

    @pytest.mark.asyncio()
    async def test_get_stats_top_endpoints_sorted(self) -> None:
        """Top endpoints should be sorted by count descending."""
        redis = AsyncMock()
        redis.zremrangebyscore = AsyncMock()
        redis.zrangebyscore = AsyncMock(return_value=[])
        redis.hgetall = AsyncMock(
            side_effect=[
                # count hash
                {b"GET:/a:200": b"5", b"POST:/b:200": b"15", b"GET:/c:200": b"10"},
                # error hash
                {},
            ]
        )
        redis.get = AsyncMock(return_value=b"30")

        collector = HttpMetricsCollector(redis=redis, window_seconds=300)
        stats = await collector.get_stats()

        endpoints = stats["top_endpoints"]
        assert endpoints[0]["endpoint"] == "POST:/b"
        assert endpoints[0]["count"] == 15


# ---------------------------------------------------------------------------
# HttpMetricsMiddleware
# ---------------------------------------------------------------------------
class TestHttpMetricsMiddleware:
    """Tests for the ASGI middleware."""

    @pytest.mark.asyncio()
    async def test_excluded_path_bypasses_recording(self) -> None:
        """Excluded paths (health) should skip collector.record entirely."""
        middleware = HttpMetricsMiddleware(app=MagicMock())
        collector = AsyncMock(spec=HttpMetricsCollector)

        request = MagicMock(spec=["app", "url", "method"])
        request.app.state.http_metrics = collector
        request.url.path = "/api/v1/health"
        request.method = "GET"

        mock_response = MagicMock()
        mock_response.status_code = 200

        async def call_next(req: MagicMock) -> MagicMock:
            return mock_response

        response = await middleware.dispatch(request, call_next)

        assert response == mock_response
        collector.record.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_normal_path_records_metrics(self) -> None:
        """Normal paths should fire collector.record with method, path, status, latency."""
        middleware = HttpMetricsMiddleware(app=MagicMock())
        collector = AsyncMock(spec=HttpMetricsCollector)

        request = MagicMock(spec=["app", "url", "method"])
        request.app.state.http_metrics = collector
        request.url.path = "/api/v1/stocks"
        request.method = "GET"

        mock_response = MagicMock()
        mock_response.status_code = 200

        async def call_next(req: MagicMock) -> MagicMock:
            return mock_response

        response = await middleware.dispatch(request, call_next)

        # Let the fire-and-forget task run
        await asyncio.sleep(0.05)

        assert response == mock_response
        collector.record.assert_awaited_once()
        args = collector.record.call_args[0]
        assert args[0] == "GET"
        assert args[1] == "/api/v1/stocks"
        assert args[2] == 200
        assert isinstance(args[3], float)

    @pytest.mark.asyncio()
    async def test_no_collector_passes_through(self) -> None:
        """When no collector on app.state, middleware should pass through."""
        middleware = HttpMetricsMiddleware(app=MagicMock())

        request = MagicMock(spec=["app", "url", "method"])
        request.app.state = MagicMock(spec=[])  # no http_metrics attr

        mock_response = MagicMock()

        async def call_next(req: MagicMock) -> MagicMock:
            return mock_response

        response = await middleware.dispatch(request, call_next)
        assert response == mock_response
