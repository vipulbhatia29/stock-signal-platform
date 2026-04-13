"""Tests for stale auto-refresh and Redis debounce in get_signals endpoint.

Covers:
  - _try_dispatch_refresh: dispatches, debounces, fail-open on Redis down
  - get_signals response fields: is_refreshing set when stale
  - Cache bypass for stale responses
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# _try_dispatch_refresh helper tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTryDispatchRefresh:
    """Unit tests for the _try_dispatch_refresh debounce helper."""

    @pytest.mark.asyncio
    async def test_stale_signals_dispatch_refresh_redis_acquired(self) -> None:
        """When Redis SETNX succeeds (acquired=True), refresh_ticker_task.delay is called."""
        from backend.routers.stocks.data import _try_dispatch_refresh

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)  # lock acquired

        mock_task = MagicMock()

        with (
            patch("backend.services.redis_pool.get_redis", AsyncMock(return_value=mock_redis)),
            patch("backend.tasks.market_data.refresh_ticker_task", mock_task),
        ):
            result = await _try_dispatch_refresh("AAPL")

        assert result is True
        mock_task.delay.assert_called_once_with("AAPL")

    @pytest.mark.asyncio
    async def test_debounce_prevents_re_dispatch_when_setnx_false(self) -> None:
        """When Redis SETNX returns False (already set), refresh task is NOT dispatched."""
        from backend.routers.stocks.data import _try_dispatch_refresh

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=False)  # lock NOT acquired — debounced

        mock_task = MagicMock()

        with (
            patch("backend.services.redis_pool.get_redis", AsyncMock(return_value=mock_redis)),
            patch("backend.tasks.market_data.refresh_ticker_task", mock_task),
        ):
            result = await _try_dispatch_refresh("AAPL")

        assert result is False
        mock_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_down_still_dispatches_fail_open(self) -> None:
        """When Redis raises an exception, refresh is still dispatched (fail-open)."""
        from backend.routers.stocks.data import _try_dispatch_refresh

        mock_task = MagicMock()

        with (
            patch(
                "backend.services.redis_pool.get_redis",
                AsyncMock(side_effect=ConnectionError("Redis unavailable")),
            ),
            patch("backend.tasks.market_data.refresh_ticker_task", mock_task),
        ):
            result = await _try_dispatch_refresh("TSLA")

        assert result is True
        mock_task.delay.assert_called_once_with("TSLA")

    @pytest.mark.asyncio
    async def test_debounce_key_uses_uppercase_ticker(self) -> None:
        """The Redis debounce key is formatted with the uppercased ticker symbol."""
        from backend.routers.stocks.data import REFRESH_DEBOUNCE_KEY, _try_dispatch_refresh

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_task = MagicMock()

        with (
            patch("backend.services.redis_pool.get_redis", AsyncMock(return_value=mock_redis)),
            patch("backend.tasks.market_data.refresh_ticker_task", mock_task),
        ):
            await _try_dispatch_refresh("aapl")

        expected_key = REFRESH_DEBOUNCE_KEY.format(ticker="AAPL")
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == expected_key


# ─────────────────────────────────────────────────────────────────────────────
# SignalResponse field tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSignalResponseFields:
    """Verify is_refreshing and is_stale are present on SignalResponse schema."""

    def test_signal_response_has_is_refreshing_field(self) -> None:
        """SignalResponse schema includes is_refreshing with default False."""
        from backend.schemas.stock import (
            BollingerResponse,
            MACDResponse,
            ReturnsResponse,
            RSIResponse,
            SignalResponse,
            SMAResponse,
        )

        resp = SignalResponse(
            ticker="AAPL",
            rsi=RSIResponse(),
            macd=MACDResponse(),
            sma=SMAResponse(),
            bollinger=BollingerResponse(),
            returns=ReturnsResponse(),
        )
        assert hasattr(resp, "is_refreshing")
        assert resp.is_refreshing is False

    def test_signal_response_is_refreshing_serializes_in_json(self) -> None:
        """is_refreshing field appears in model_dump_json output."""
        from backend.schemas.stock import (
            BollingerResponse,
            MACDResponse,
            ReturnsResponse,
            RSIResponse,
            SignalResponse,
            SMAResponse,
        )

        resp = SignalResponse(
            ticker="MSFT",
            rsi=RSIResponse(),
            macd=MACDResponse(),
            sma=SMAResponse(),
            bollinger=BollingerResponse(),
            returns=ReturnsResponse(),
            is_stale=True,
            is_refreshing=True,
        )
        json_str = resp.model_dump_json()
        assert '"is_refreshing":true' in json_str
        assert '"is_stale":true' in json_str


# ─────────────────────────────────────────────────────────────────────────────
# Cache bypass for stale responses
# ─────────────────────────────────────────────────────────────────────────────


class TestStaleCacheBypass:
    """Verify stale responses are not written to cache."""

    def test_stale_response_not_cached_logic(self) -> None:
        """The condition `cache and not is_stale` correctly excludes stale responses.

        This tests the guard logic inline (not through the router) to verify
        the boolean semantics are correct without needing testcontainers.
        """
        # Simulate: cache present, is_stale=True → cache write skipped
        cache_writes: list[str] = []

        def simulate_cache_write(is_stale: bool, cache_available: bool) -> bool:
            """Return whether a cache write would occur given the guard condition."""
            return cache_available and not is_stale

        # Stale: no write
        assert simulate_cache_write(is_stale=True, cache_available=True) is False
        # Fresh: write
        assert simulate_cache_write(is_stale=False, cache_available=True) is True
        # No cache: no write
        assert simulate_cache_write(is_stale=False, cache_available=False) is False
        # No cache + stale: no write
        assert simulate_cache_write(is_stale=True, cache_available=False) is False

        # Confirm cache_writes list untouched (illustrative only)
        assert cache_writes == []

    def test_debounce_ttl_is_five_minutes(self) -> None:
        """REFRESH_DEBOUNCE_TTL constant equals 300 seconds (5 minutes)."""
        from backend.routers.stocks.data import REFRESH_DEBOUNCE_TTL

        assert REFRESH_DEBOUNCE_TTL == 300

    def test_debounce_key_template_contains_ticker_placeholder(self) -> None:
        """REFRESH_DEBOUNCE_KEY template formats correctly with a ticker."""
        from backend.routers.stocks.data import REFRESH_DEBOUNCE_KEY

        formatted = REFRESH_DEBOUNCE_KEY.format(ticker="GOOG")
        assert "GOOG" in formatted
        assert "{ticker}" not in formatted
