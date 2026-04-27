"""Tests for market briefing tool."""

from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestFetchIndexPerformance:
    """Tests for index data fetching via Ticker.fast_info."""

    def test_returns_index_data(self) -> None:
        """Should return formatted index performance from fast_info."""
        from backend.tools.market_briefing import _fetch_index_performance

        mock_ticker = MagicMock()
        mock_ticker.fast_info.previous_close = 5000.0
        mock_ticker.fast_info.last_price = 5050.0
        with patch("backend.tools.market_briefing.yf.Ticker", return_value=mock_ticker):
            result = _fetch_index_performance("^GSPC", "S&P 500")
        assert result is not None
        assert result["name"] == "S&P 500"
        assert result["price"] == 5050.0
        assert result["change_pct"] == pytest.approx(1.0, abs=0.1)

    def test_missing_previous_close_returns_none(self) -> None:
        """Missing previous_close should return None."""
        from backend.tools.market_briefing import _fetch_index_performance

        mock_ticker = MagicMock()
        mock_ticker.fast_info.previous_close = None
        mock_ticker.fast_info.last_price = 5050.0
        with patch("backend.tools.market_briefing.yf.Ticker", return_value=mock_ticker):
            result = _fetch_index_performance("^GSPC", "S&P 500")
        assert result is None

    def test_zero_previous_close_returns_none(self) -> None:
        """Zero previous_close should return None (can't compute change)."""
        from backend.tools.market_briefing import _fetch_index_performance

        mock_ticker = MagicMock()
        mock_ticker.fast_info.previous_close = 0
        mock_ticker.fast_info.last_price = 5050.0
        with patch("backend.tools.market_briefing.yf.Ticker", return_value=mock_ticker):
            result = _fetch_index_performance("^GSPC", "S&P 500")
        assert result is None

    def test_exception_returns_none(self) -> None:
        """yfinance exception should return None."""
        from backend.tools.market_briefing import _fetch_index_performance

        with patch(
            "backend.tools.market_briefing.yf.Ticker",
            side_effect=Exception("API down"),
        ):
            result = _fetch_index_performance("^GSPC", "S&P 500")
        assert result is None


class TestFetchTopMovers:
    """Tests for _fetch_top_movers signal snapshot queries (DISTINCT ON pattern)."""

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_lists(self) -> None:
        """Returns empty lists when no snapshots exist."""
        from backend.tools.market_briefing import _fetch_top_movers

        mock_session = AsyncMock()
        # Gainers query returns empty, losers query returns empty
        gainers_result = MagicMock()
        gainers_result.all.return_value = []
        losers_result = MagicMock()
        losers_result.all.return_value = []
        mock_session.execute.side_effect = [gainers_result, losers_result]

        result = await _fetch_top_movers(mock_session)
        assert result == {"gainers": [], "losers": []}

    @pytest.mark.asyncio
    async def test_returns_sorted_gainers_and_losers(self) -> None:
        """Returns gainers (change_pct > 0) and losers (change_pct < 0)."""
        from backend.tools.market_briefing import _fetch_top_movers

        Row = namedtuple(
            "Row",
            ["ticker", "current_price", "change_pct", "macd_signal_label", "composite_score"],
        )

        mock_session = AsyncMock()

        # First call: gainers (only positive change_pct)
        gainers_result = MagicMock()
        gainers_result.all.return_value = [
            Row("AAPL", 180.0, 5.2, "bullish", 8.5),
            Row("MSFT", 420.0, 3.1, "bullish", 7.8),
        ]

        # Second call: losers (only negative change_pct)
        losers_result = MagicMock()
        losers_result.all.return_value = [
            Row("INTC", 25.0, -4.5, "bearish", 3.2),
            Row("BA", 190.0, -2.1, "bearish", 4.1),
        ]

        mock_session.execute.side_effect = [gainers_result, losers_result]

        result = await _fetch_top_movers(mock_session)
        assert len(result["gainers"]) == 2
        assert len(result["losers"]) == 2
        assert result["gainers"][0]["ticker"] == "AAPL"
        assert result["gainers"][0]["change_pct"] == 5.2
        assert result["losers"][0]["ticker"] == "INTC"
        assert result["losers"][0]["change_pct"] == -4.5

    @pytest.mark.asyncio
    async def test_rounds_change_pct(self) -> None:
        """Change percentages are rounded to 2 decimal places."""
        from backend.tools.market_briefing import _fetch_top_movers

        Row = namedtuple(
            "Row",
            ["ticker", "current_price", "change_pct", "macd_signal_label", "composite_score"],
        )

        mock_session = AsyncMock()

        gainers_result = MagicMock()
        gainers_result.all.return_value = [
            Row("AAPL", 180.0, 5.123456, "bullish", 8.5),
        ]

        losers_result = MagicMock()
        losers_result.all.return_value = []

        mock_session.execute.side_effect = [gainers_result, losers_result]

        result = await _fetch_top_movers(mock_session)
        assert result["gainers"][0]["change_pct"] == 5.12


class TestFetchSectorEtfPerformance:
    """Tests for parallel sector ETF fetching."""

    @pytest.mark.asyncio
    async def test_sector_etf_fetch_handles_single_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One ETF failure should not crash the entire batch."""
        from backend.tools.market_briefing import _fetch_sector_etf_performance

        def mock_ticker(symbol: str) -> MagicMock:
            if symbol == "XLF":
                raise Exception("yfinance timeout")
            mock = MagicMock()
            mock.fast_info.previous_close = 100.0
            mock.fast_info.last_price = 102.0
            return mock

        monkeypatch.setattr("backend.tools.market_briefing.yf.Ticker", mock_ticker)
        result = await _fetch_sector_etf_performance()
        sectors = {r["sector"] for r in result}
        assert "Financial Services" not in sectors  # XLF failed
        assert len(result) > 0  # other sectors succeeded

    @pytest.mark.asyncio
    async def test_sector_etf_normalizes_names(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sector names should be normalized via normalize_sector."""
        from backend.tools.market_briefing import _fetch_sector_etf_performance

        mock = MagicMock()
        mock.fast_info.previous_close = 100.0
        mock.fast_info.last_price = 101.0
        monkeypatch.setattr("backend.tools.market_briefing.yf.Ticker", lambda _: mock)

        result = await _fetch_sector_etf_performance()
        names = {r["sector"] for r in result}
        # "Consumer Discretionary" should be normalized to "Consumer Cyclical"
        assert "Consumer Discretionary" not in names
        # "Financials" should be normalized to "Financial Services"
        assert "Financials" not in names
        # Normalized names should be present
        assert "Consumer Cyclical" in names
        assert "Financial Services" in names

    @pytest.mark.asyncio
    async def test_sector_etf_includes_xlc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Communication Services (XLC) should be included in results."""
        from backend.tools.market_briefing import _fetch_sector_etf_performance

        mock = MagicMock()
        mock.fast_info.previous_close = 100.0
        mock.fast_info.last_price = 103.0
        monkeypatch.setattr("backend.tools.market_briefing.yf.Ticker", lambda _: mock)

        result = await _fetch_sector_etf_performance()
        etfs = {r["etf"] for r in result}
        assert "XLC" in etfs

    @pytest.mark.asyncio
    async def test_sector_etf_skips_zero_prev_close(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ETFs with zero previous_close should be skipped."""
        from backend.tools.market_briefing import _fetch_sector_etf_performance

        mock = MagicMock()
        mock.fast_info.previous_close = 0
        mock.fast_info.last_price = 100.0
        monkeypatch.setattr("backend.tools.market_briefing.yf.Ticker", lambda _: mock)

        result = await _fetch_sector_etf_performance()
        assert len(result) == 0
