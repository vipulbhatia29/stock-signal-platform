"""Unit tests for dividend tools: fetch_dividends and get_dividend_summary."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from backend.tools.dividends import fetch_dividends, get_dividend_summary


class TestFetchDividends:
    """Tests for the yfinance dividend fetcher."""

    @patch("backend.tools.dividends.yf.Ticker")
    def test_returns_dividends_list(self, mock_ticker_cls: MagicMock) -> None:
        """Successful fetch returns list of dicts with ticker, ex_date, amount."""
        dates = pd.to_datetime(["2025-11-15", "2026-02-14"])
        div_series = pd.Series([0.25, 0.26], index=dates)
        mock_ticker_cls.return_value.dividends = div_series

        result = fetch_dividends("AAPL")

        assert len(result) == 2
        assert result[0]["ticker"] == "AAPL"
        assert result[0]["amount"] == Decimal("0.25")
        assert result[0]["ex_date"].tzinfo == timezone.utc
        assert result[1]["amount"] == Decimal("0.26")

    @patch("backend.tools.dividends.yf.Ticker")
    def test_normalises_ticker_uppercase(self, mock_ticker_cls: MagicMock) -> None:
        """Ticker is normalised to uppercase."""
        div_series = pd.Series([0.5], index=pd.to_datetime(["2026-01-10"]))
        mock_ticker_cls.return_value.dividends = div_series

        result = fetch_dividends("  aapl  ")

        assert result[0]["ticker"] == "AAPL"
        mock_ticker_cls.assert_called_once_with("AAPL")

    @patch("backend.tools.dividends.yf.Ticker")
    def test_empty_dividends_returns_empty_list(self, mock_ticker_cls: MagicMock) -> None:
        """Ticker with no dividend history returns empty list."""
        mock_ticker_cls.return_value.dividends = pd.Series(dtype=float)

        result = fetch_dividends("TSLA")

        assert result == []

    @patch("backend.tools.dividends.yf.Ticker")
    def test_none_dividends_returns_empty_list(self, mock_ticker_cls: MagicMock) -> None:
        """If yfinance returns None for dividends, return empty list."""
        mock_ticker_cls.return_value.dividends = None

        result = fetch_dividends("UNKNOWN")

        assert result == []

    @patch("backend.tools.dividends.yf.Ticker")
    def test_yfinance_exception_returns_empty_list(self, mock_ticker_cls: MagicMock) -> None:
        """If yfinance raises an exception, return empty list gracefully."""
        mock_ticker_cls.side_effect = Exception("Network error")

        result = fetch_dividends("AAPL")

        assert result == []


class TestGetDividendSummary:
    """Tests for the dividend summary aggregation logic."""

    @pytest.mark.asyncio
    @patch("backend.tools.dividends.get_dividends", new_callable=AsyncMock)
    async def test_empty_dividends_returns_zero_summary(self, mock_get: AsyncMock) -> None:
        """No dividend records returns zeroed summary."""
        mock_get.return_value = []
        db = AsyncMock()

        result = await get_dividend_summary("AAPL", db)

        assert result["ticker"] == "AAPL"
        assert result["total_received"] == 0.0
        assert result["annual_dividends"] == 0.0
        assert result["dividend_yield"] is None
        assert result["last_ex_date"] is None
        assert result["payment_count"] == 0
        assert result["history"] == []

    @pytest.mark.asyncio
    @patch("backend.tools.dividends.get_dividends", new_callable=AsyncMock)
    async def test_summary_with_dividends(self, mock_get: AsyncMock) -> None:
        """Summary correctly totals and computes annual dividends."""
        now = datetime.now(timezone.utc)
        six_months_ago = now.replace(month=max(1, now.month - 6))
        two_years_ago = now.replace(year=now.year - 2)

        # Create mock DividendPayment objects
        recent = MagicMock()
        recent.amount = Decimal("0.25")
        recent.ex_date = six_months_ago
        recent.ticker = "AAPL"

        old = MagicMock()
        old.amount = Decimal("0.20")
        old.ex_date = two_years_ago
        old.ticker = "AAPL"

        mock_get.return_value = [recent, old]  # desc order
        db = AsyncMock()

        result = await get_dividend_summary("AAPL", db, current_price=200.0)

        assert result["ticker"] == "AAPL"
        assert result["total_received"] == 0.45
        assert result["annual_dividends"] == 0.25  # only recent is within 12 months
        assert result["payment_count"] == 2
        assert result["last_ex_date"] == six_months_ago
        # yield = (0.25 / 200) * 100 = 0.125 → 0.12 or 0.13 depending on rounding
        assert result["dividend_yield"] is not None
        assert result["dividend_yield"] > 0

    @pytest.mark.asyncio
    @patch("backend.tools.dividends.get_dividends", new_callable=AsyncMock)
    async def test_summary_without_price_has_no_yield(self, mock_get: AsyncMock) -> None:
        """Without current_price, dividend_yield is None."""
        recent = MagicMock()
        recent.amount = Decimal("0.25")
        recent.ex_date = datetime.now(timezone.utc)
        recent.ticker = "AAPL"

        mock_get.return_value = [recent]
        db = AsyncMock()

        result = await get_dividend_summary("AAPL", db, current_price=None)

        assert result["dividend_yield"] is None

    @pytest.mark.asyncio
    @patch("backend.tools.dividends.get_dividends", new_callable=AsyncMock)
    async def test_summary_normalises_ticker(self, mock_get: AsyncMock) -> None:
        """Ticker in response is normalised to uppercase."""
        mock_get.return_value = []
        db = AsyncMock()

        result = await get_dividend_summary("  aapl  ", db)

        assert result["ticker"] == "AAPL"
