"""Tests for extended fundamentals and FundamentalsTool."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestExtendedFundamentals:
    """Tests for extended FundamentalResult fields."""

    def test_fetch_fundamentals_includes_growth_margins(self) -> None:
        """Extended fundamentals should include revenue growth, margins, ROE."""
        with patch("backend.services.stock_data.yf.Ticker") as mock_ticker:
            mock_info = {
                "trailingPE": 28.5,
                "pegRatio": 1.2,
                "debtToEquity": 45.0,
                "freeCashflow": 1_000_000,
                "marketCap": 362_000_000_000,
                "revenueGrowth": 0.21,
                "grossMargins": 0.82,
                "operatingMargins": 0.41,
                "profitMargins": 0.36,
                "returnOnEquity": 0.26,
                "enterpriseValue": 365_000_000_000,
            }
            mock_ticker.return_value.info = mock_info

            from backend.tools.fundamentals import fetch_fundamentals

            result = fetch_fundamentals("PLTR")

            assert result.revenue_growth == 0.21
            assert result.gross_margins == 0.82
            assert result.operating_margins == 0.41
            assert result.profit_margins == 0.36
            assert result.return_on_equity == 0.26
            assert result.market_cap == 362_000_000_000
            assert result.enterprise_value == 365_000_000_000

    def test_fetch_fundamentals_missing_growth_returns_none(self) -> None:
        """Missing growth/margin fields should be None, not error."""
        with patch("backend.services.stock_data.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.info = {"trailingPE": 15.0}

            from backend.tools.fundamentals import fetch_fundamentals

            result = fetch_fundamentals("AAPL")

            assert result.pe_ratio == 15.0
            assert result.revenue_growth is None
            assert result.gross_margins is None
            assert result.market_cap is None


class TestFetchAnalystData:
    """Tests for fetch_analyst_data."""

    def test_returns_analyst_targets(self) -> None:
        """Should extract analyst target prices from yfinance info."""
        with patch("backend.services.stock_data.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.info = {
                "targetMeanPrice": 186.60,
                "targetHighPrice": 260.0,
                "targetLowPrice": 70.0,
                "longBusinessSummary": "Palantir builds software.",
                "fullTimeEmployees": 3800,
                "website": "https://palantir.com",
            }
            mock_ticker.return_value.recommendations = MagicMock(
                empty=True,
            )

            from backend.tools.fundamentals import fetch_analyst_data

            result = fetch_analyst_data("PLTR")

            assert result["analyst_target_mean"] == 186.60
            assert result["analyst_target_high"] == 260.0
            assert result["analyst_target_low"] == 70.0
            assert result["business_summary"] == "Palantir builds software."
            assert result["employees"] == 3800
            assert result["website"] == "https://palantir.com"

    def test_yfinance_failure_returns_empty_dict(self) -> None:
        """If yfinance fails, return empty dict (no crash)."""
        with patch("backend.services.stock_data.yf.Ticker", side_effect=Exception("boom")):
            from backend.tools.fundamentals import fetch_analyst_data

            result = fetch_analyst_data("INVALID")
            assert result == {}


class TestPersistEnrichedFundamentals:
    """Tests for persist_enriched_fundamentals."""

    @pytest.mark.asyncio
    async def test_persists_growth_margins_to_stock(self) -> None:
        """Should set growth/margin fields on the Stock object."""
        from dataclasses import dataclass

        @dataclass
        class FakeFundamentals:
            ticker: str = "PLTR"
            revenue_growth: float | None = 0.21
            gross_margins: float | None = 0.82
            operating_margins: float | None = 0.41
            profit_margins: float | None = 0.36
            return_on_equity: float | None = 0.26
            market_cap: float | None = 362_000_000_000

        class FakeStock:
            ticker = "PLTR"
            revenue_growth = None
            gross_margins = None
            operating_margins = None
            profit_margins = None
            return_on_equity = None
            market_cap = None
            analyst_target_mean = None
            analyst_target_high = None
            analyst_target_low = None
            analyst_buy = None
            analyst_hold = None
            analyst_sell = None
            business_summary = None
            employees = None
            website = None

        mock_db = MagicMock()
        stock = FakeStock()
        fundamentals = FakeFundamentals()
        analyst_data = {
            "analyst_target_mean": 186.60,
            "analyst_buy": 12,
            "analyst_hold": 5,
            "analyst_sell": 2,
            "business_summary": "Test summary",
        }

        from backend.tools.fundamentals import persist_enriched_fundamentals

        await persist_enriched_fundamentals(stock, fundamentals, analyst_data, mock_db)

        assert stock.revenue_growth == 0.21
        assert stock.gross_margins == 0.82
        assert stock.market_cap == 362_000_000_000
        assert stock.analyst_target_mean == 186.60
        assert stock.analyst_buy == 12
        assert stock.business_summary == "Test summary"
        mock_db.add.assert_called_once_with(stock)


class TestFundamentalsTool:
    """Tests for FundamentalsTool.execute (reads from DB)."""

    @pytest.mark.asyncio
    async def test_returns_fundamentals_from_db(self) -> None:
        """Should return enriched data from the Stock model."""

        class FakeStock:
            ticker = "PLTR"
            name = "Palantir Technologies"
            sector = "Technology"
            industry = "Software - Infrastructure"
            market_cap = 362_000_000_000
            revenue_growth = 0.21
            gross_margins = 0.82
            operating_margins = 0.41
            profit_margins = 0.36
            return_on_equity = 0.26

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = FakeStock()
        mock_session.execute.return_value = mock_result

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_session
        mock_cm.__aexit__.return_value = None

        with patch("backend.database.async_session_factory", return_value=mock_cm):
            from backend.tools.fundamentals_tool import FundamentalsTool

            tool = FundamentalsTool()
            result = await tool.execute({"ticker": "PLTR"})

            assert result.status == "ok"
            assert result.data["ticker"] == "PLTR"
            assert result.data["revenue_growth"] == 0.21
            assert result.data["market_cap"] == 362_000_000_000

    @pytest.mark.asyncio
    async def test_returns_error_for_missing_ticker(self) -> None:
        """Should return error if ticker not in DB."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_session
        mock_cm.__aexit__.return_value = None

        with patch("backend.database.async_session_factory", return_value=mock_cm):
            from backend.tools.fundamentals_tool import FundamentalsTool

            tool = FundamentalsTool()
            result = await tool.execute({"ticker": "INVALID"})

            assert result.status == "error"
            assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_returns_error_for_empty_ticker(self) -> None:
        """Should return error for empty ticker param."""
        from backend.tools.fundamentals_tool import FundamentalsTool

        tool = FundamentalsTool()
        result = await tool.execute({"ticker": ""})
        assert result.status == "error"
