"""Tests for AnalyzeStockTool auto-ingest behaviour (KAN-404)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from backend.tools.analyze_stock import AnalyzeStockTool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_cm(session: AsyncMock) -> AsyncMock:
    """Return an async context-manager mock that yields *session*."""
    cm = AsyncMock()
    cm.__aenter__.return_value = session
    cm.__aexit__.return_value = None
    return cm


def _fake_signals() -> MagicMock:
    """Return a MagicMock that looks like a SignalResult."""
    s = MagicMock()
    s.composite_score = 7.5
    s.rsi_value = 45.0
    s.rsi_signal = "neutral"
    s.macd_value = 0.12
    s.macd_signal_label = "bullish"
    s.sma_signal = "above"
    s.bb_position = 0.6
    s.annual_return = 0.18
    s.volatility = 0.22
    s.sharpe_ratio = 1.1
    return s


def _non_empty_df() -> pd.DataFrame:
    """Return a minimal non-empty price DataFrame."""
    return pd.DataFrame({"close": [150.0, 151.0]})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAnalyzeStockAutoIngest:
    """Tests for the auto-ingest path in AnalyzeStockTool.execute."""

    @pytest.mark.asyncio
    async def test_autoingest_when_no_price_data_returns_signals(self) -> None:
        """First load_prices_df returns empty df; after auto-ingest second call returns data."""
        tool = AnalyzeStockTool()
        session = AsyncMock()

        # load_prices_df: first call empty, second call populated
        load_prices_df_mock = AsyncMock(side_effect=[pd.DataFrame(), _non_empty_df()])
        ensure_stock_exists_mock = AsyncMock(return_value=None)
        fetch_prices_delta_mock = AsyncMock(return_value=None)
        compute_signals_mock = MagicMock(return_value=_fake_signals())

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=_make_session_cm(session),
            ),
            patch(
                "backend.tools.market_data.load_prices_df",
                load_prices_df_mock,
            ),
            patch(
                "backend.tools.signals.compute_signals",
                compute_signals_mock,
            ),
            patch(
                "backend.services.stock_data.ensure_stock_exists",
                ensure_stock_exists_mock,
            ),
            patch(
                "backend.services.stock_data.fetch_prices_delta",
                fetch_prices_delta_mock,
            ),
        ):
            result = await tool.execute({"ticker": "NVDA"})

        assert result.status == "ok"
        assert result.data["ticker"] == "NVDA"
        assert result.data["composite_score"] == 7.5
        ensure_stock_exists_mock.assert_awaited_once()
        fetch_prices_delta_mock.assert_awaited_once()
        assert load_prices_df_mock.await_count == 2

    @pytest.mark.asyncio
    async def test_invalid_ticker_format_returns_error(self) -> None:
        """Ticker containing digits or too long should be rejected before any DB call."""
        tool = AnalyzeStockTool()

        for bad_ticker in ("INVALID123", "12345", "TOOLONG", "A B", ""):
            result = await tool.execute({"ticker": bad_ticker})
            if bad_ticker == "":
                assert result.status == "error"
                assert "Missing" in result.error
            else:
                assert result.status == "error", f"Expected error for ticker={bad_ticker!r}"
                assert "Invalid" in result.error, (
                    f"Expected 'Invalid' in error for ticker={bad_ticker!r}"
                )

    @pytest.mark.asyncio
    async def test_ingest_failure_returns_ticker_error(self) -> None:
        """When ensure_stock_exists raises ValueError, returns error to verify the ticker."""
        tool = AnalyzeStockTool()
        session = AsyncMock()

        load_prices_df_mock = AsyncMock(return_value=pd.DataFrame())  # always empty
        ensure_stock_exists_mock = AsyncMock(side_effect=ValueError("unknown ticker"))

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=_make_session_cm(session),
            ),
            patch(
                "backend.tools.market_data.load_prices_df",
                load_prices_df_mock,
            ),
            patch(
                "backend.services.stock_data.ensure_stock_exists",
                ensure_stock_exists_mock,
            ),
        ):
            result = await tool.execute({"ticker": "FAKE"})

        assert result.status == "error"
        assert "Verify" in result.error or "verify" in result.error

    @pytest.mark.asyncio
    async def test_happy_path_no_ingest_needed(self) -> None:
        """When price data already exists, signals are returned without calling ingest functions."""
        tool = AnalyzeStockTool()
        session = AsyncMock()

        load_prices_df_mock = AsyncMock(return_value=_non_empty_df())
        ensure_stock_exists_mock = AsyncMock()
        fetch_prices_delta_mock = AsyncMock()
        compute_signals_mock = MagicMock(return_value=_fake_signals())

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=_make_session_cm(session),
            ),
            patch(
                "backend.tools.market_data.load_prices_df",
                load_prices_df_mock,
            ),
            patch(
                "backend.tools.signals.compute_signals",
                compute_signals_mock,
            ),
            patch(
                "backend.services.stock_data.ensure_stock_exists",
                ensure_stock_exists_mock,
            ),
            patch(
                "backend.services.stock_data.fetch_prices_delta",
                fetch_prices_delta_mock,
            ),
        ):
            result = await tool.execute({"ticker": "AAPL"})

        assert result.status == "ok"
        assert result.data["ticker"] == "AAPL"
        ensure_stock_exists_mock.assert_not_awaited()
        fetch_prices_delta_mock.assert_not_awaited()
        assert load_prices_df_mock.await_count == 1

    @pytest.mark.asyncio
    async def test_ingest_succeeds_but_still_no_data_returns_error(self) -> None:
        """When ingest succeeds but load_prices_df is still empty, returns a no-data error."""
        tool = AnalyzeStockTool()
        session = AsyncMock()

        # Both calls return empty DataFrame
        load_prices_df_mock = AsyncMock(return_value=pd.DataFrame())
        ensure_stock_exists_mock = AsyncMock(return_value=None)
        fetch_prices_delta_mock = AsyncMock(return_value=None)

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=_make_session_cm(session),
            ),
            patch(
                "backend.tools.market_data.load_prices_df",
                load_prices_df_mock,
            ),
            patch(
                "backend.services.stock_data.ensure_stock_exists",
                ensure_stock_exists_mock,
            ),
            patch(
                "backend.services.stock_data.fetch_prices_delta",
                fetch_prices_delta_mock,
            ),
        ):
            result = await tool.execute({"ticker": "XYZW"})

        assert result.status == "error"
        assert "after ingestion" in result.error

    @pytest.mark.asyncio
    async def test_unexpected_exception_in_compute_signals_returns_generic_error(
        self,
    ) -> None:
        """Unexpected exception from compute_signals triggers the outer catch-all.

        The outer except block must return the generic 'Stock analysis failed'
        message rather than leaking stack trace or raw exception text to the caller.
        """
        tool = AnalyzeStockTool()
        session = AsyncMock()

        load_prices_df_mock = AsyncMock(return_value=_non_empty_df())
        compute_signals_mock = MagicMock(side_effect=RuntimeError("unexpected internal error"))

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=_make_session_cm(session),
            ),
            patch(
                "backend.tools.market_data.load_prices_df",
                load_prices_df_mock,
            ),
            patch(
                "backend.tools.signals.compute_signals",
                compute_signals_mock,
            ),
        ):
            result = await tool.execute({"ticker": "AAPL"})

        assert result.status == "error"
        assert result.error == "Stock analysis failed. Please try again."
