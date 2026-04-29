"""Tests for forecast agent tools (GetForecast, GetSectorForecast, etc.)."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_forecast_result(
    ticker: str = "AAPL",
    horizon_days: int = 90,
    expected_return_pct: float = 3.33,
    return_lower_pct: float = -6.67,
    return_upper_pct: float = 13.33,
    confidence_score: float = 0.65,
    direction: str = "bullish",
    base_price: float = 150.0,
    forecast_date: date | None = None,
    target_date: date | None = None,
) -> MagicMock:
    """Create a mock ForecastResult."""
    f = MagicMock()
    f.ticker = ticker
    f.horizon_days = horizon_days
    f.expected_return_pct = expected_return_pct
    f.return_lower_pct = return_lower_pct
    f.return_upper_pct = return_upper_pct
    f.confidence_score = confidence_score
    f.direction = direction
    f.base_price = base_price
    f.drivers = None
    f.forecast_signal = None
    f.forecast_date = forecast_date or date(2026, 3, 22)
    f.target_date = target_date or date(2026, 6, 20)
    # Legacy fields still referenced by forecast_tools.py (not yet migrated to return-based)
    implied_price = round(base_price * (1 + expected_return_pct / 100), 2)
    f.predicted_price = implied_price
    f.predicted_lower = round(base_price * (1 + return_lower_pct / 100), 2)
    f.predicted_upper = round(base_price * (1 + return_upper_pct / 100), 2)
    return f


class TestGetForecastTool:
    """Tests for GetForecastTool."""

    @pytest.mark.asyncio
    async def test_returns_three_horizons_with_confidence(self) -> None:
        """Should return 3 horizon forecasts with confidence level."""
        from backend.tools.forecast_tools import GetForecastTool

        forecasts = [
            _make_forecast_result(
                horizon_days=90,
                expected_return_pct=3.33,
                return_lower_pct=-6.67,
                return_upper_pct=13.33,
            ),
            _make_forecast_result(
                horizon_days=180,
                expected_return_pct=5.00,
                return_lower_pct=-3.33,
                return_upper_pct=13.33,
            ),
            _make_forecast_result(
                horizon_days=270,
                expected_return_pct=6.67,
                return_lower_pct=-1.67,
                return_upper_pct=15.00,
            ),
        ]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = forecasts
        mock_session.execute.return_value = mock_result

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_session
        mock_cm.__aexit__.return_value = None

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=mock_cm,
            ),
            patch(
                "backend.tools.forecasting.compute_sharpe_direction",
                new_callable=AsyncMock,
                return_value="improving",
            ),
        ):
            tool = GetForecastTool()
            result = await tool.execute({"ticker": "AAPL"})

        assert result.status == "ok"
        assert len(result.data["horizons"]) == 3
        assert result.data["horizons"][0]["horizon_days"] == 90
        assert result.data["confidence"] in ("high", "moderate", "low")

    @pytest.mark.asyncio
    async def test_missing_ticker_returns_error(self) -> None:
        """Should return error when ticker param is missing."""
        from backend.tools.forecast_tools import GetForecastTool

        tool = GetForecastTool()
        result = await tool.execute({})

        assert result.status == "error"
        assert "Missing" in result.error

    @pytest.mark.asyncio
    async def test_no_forecast_data_returns_error(self) -> None:
        """Should return error when no forecast exists for ticker."""
        from backend.tools.forecast_tools import GetForecastTool

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_session
        mock_cm.__aexit__.return_value = None

        with patch("backend.database.async_session_factory", return_value=mock_cm):
            tool = GetForecastTool()
            result = await tool.execute({"ticker": "ZZZZ"})

        assert result.status == "error"
        assert "No forecast data" in result.error


class TestGetSectorForecastTool:
    """Tests for GetSectorForecastTool."""

    @pytest.mark.asyncio
    async def test_maps_technology_to_xlk(self) -> None:
        """Should map 'Technology' sector to XLK ETF ticker."""
        from backend.tools.forecast_tools import GetSectorForecastTool

        forecasts = [
            _make_forecast_result(ticker="XLK", horizon_days=90),
            _make_forecast_result(ticker="XLK", horizon_days=180),
            _make_forecast_result(ticker="XLK", horizon_days=270),
        ]

        # ETF forecast session mock
        fc_result = MagicMock()
        fc_result.scalars.return_value.all.return_value = forecasts
        mock_fc_session = AsyncMock()
        mock_fc_session.execute.return_value = fc_result
        mock_fc_cm = AsyncMock()
        mock_fc_cm.__aenter__.return_value = mock_fc_session
        mock_fc_cm.__aexit__.return_value = None

        # Sector count session mock
        count_result = MagicMock()
        count_result.scalar.return_value = 42
        mock_count_session = AsyncMock()
        mock_count_session.execute.return_value = count_result
        mock_count_cm = AsyncMock()
        mock_count_cm.__aenter__.return_value = mock_count_session
        mock_count_cm.__aexit__.return_value = None

        # Return different session contexts on successive calls
        with patch(
            "backend.database.async_session_factory",
            side_effect=[mock_fc_cm, mock_count_cm],
        ):
            tool = GetSectorForecastTool()
            result = await tool.execute({"sector": "Technology"})

        assert result.status == "ok"
        assert result.data["etf_ticker"] == "XLK"
        assert result.data["forecast_available"] is True
        assert result.data["tracked_stocks_in_sector"] == 42

    @pytest.mark.asyncio
    async def test_unknown_sector_returns_error(self) -> None:
        """Should return error for unknown sector name."""
        from backend.tools.forecast_tools import GetSectorForecastTool

        tool = GetSectorForecastTool()
        result = await tool.execute({"sector": "Imaginary"})

        assert result.status == "error"
        assert "Unknown sector" in result.error


class TestCompareStocksTool:
    """Tests for CompareStocksTool."""

    @pytest.mark.asyncio
    async def test_compare_two_tickers(self) -> None:
        """Should return side-by-side comparison for 2 stocks."""
        from backend.tools.forecast_tools import CompareStocksTool

        # Mock stocks
        stock_aapl = MagicMock()
        stock_aapl.ticker = "AAPL"
        stock_aapl.name = "Apple Inc"
        stock_aapl.sector = "Technology"
        stock_aapl.market_cap = 3_000_000_000_000
        stock_aapl.revenue_growth = 0.08
        stock_aapl.gross_margins = 0.46
        stock_aapl.operating_margins = 0.31
        stock_aapl.profit_margins = 0.26
        stock_aapl.return_on_equity = 1.71

        stock_msft = MagicMock()
        stock_msft.ticker = "MSFT"
        stock_msft.name = "Microsoft Corp"
        stock_msft.sector = "Technology"
        stock_msft.market_cap = 2_800_000_000_000
        stock_msft.revenue_growth = 0.17
        stock_msft.gross_margins = 0.69
        stock_msft.operating_margins = 0.45
        stock_msft.profit_margins = 0.37
        stock_msft.return_on_equity = 0.39

        # Mock signals
        sig_aapl = MagicMock()
        sig_aapl.ticker = "AAPL"
        sig_aapl.composite_score = 7.2
        sig_aapl.rsi_14 = 55.0
        sig_aapl.recommendation = "BUY"

        sig_msft = MagicMock()
        sig_msft.ticker = "MSFT"
        sig_msft.composite_score = 6.8
        sig_msft.rsi_14 = 48.0
        sig_msft.recommendation = "WATCH"

        # Stocks session mock
        stock_result = MagicMock()
        stock_result.scalars.return_value.all.return_value = [stock_aapl, stock_msft]
        mock_stock_session = AsyncMock()
        mock_stock_session.execute.return_value = stock_result
        mock_stock_cm = AsyncMock()
        mock_stock_cm.__aenter__.return_value = mock_stock_session
        mock_stock_cm.__aexit__.return_value = None

        # Signals session mock
        signal_result = MagicMock()
        signal_result.scalars.return_value.all.return_value = [sig_aapl, sig_msft]
        mock_signal_session = AsyncMock()
        mock_signal_session.execute.return_value = signal_result
        mock_signal_cm = AsyncMock()
        mock_signal_cm.__aenter__.return_value = mock_signal_session
        mock_signal_cm.__aexit__.return_value = None

        # Forecasts session mock
        fc_result = MagicMock()
        fc_result.scalars.return_value.all.return_value = []
        mock_fc_session = AsyncMock()
        mock_fc_session.execute.return_value = fc_result
        mock_fc_cm = AsyncMock()
        mock_fc_cm.__aenter__.return_value = mock_fc_session
        mock_fc_cm.__aexit__.return_value = None

        with patch(
            "backend.database.async_session_factory",
            side_effect=[mock_stock_cm, mock_signal_cm, mock_fc_cm],
        ):
            tool = CompareStocksTool()
            result = await tool.execute({"tickers": ["AAPL", "MSFT"]})

        assert result.status == "ok"
        assert len(result.data["comparisons"]) == 2
        assert result.data["comparisons"][0]["ticker"] == "AAPL"
        assert result.data["comparisons"][1]["ticker"] == "MSFT"
        assert result.data["comparisons"][0]["signals"]["composite_score"] == 7.2

    @pytest.mark.asyncio
    async def test_too_few_tickers_returns_error(self) -> None:
        """Should reject comparison with fewer than 2 tickers."""
        from backend.tools.forecast_tools import CompareStocksTool

        tool = CompareStocksTool()
        result = await tool.execute({"tickers": ["AAPL"]})

        assert result.status == "error"
        assert "at least 2" in result.error

    @pytest.mark.asyncio
    async def test_too_many_tickers_returns_error(self) -> None:
        """Should reject comparison with more than 5 tickers."""
        from backend.tools.forecast_tools import CompareStocksTool

        tool = CompareStocksTool()
        result = await tool.execute({"tickers": ["A", "B", "C", "D", "E", "F"]})

        assert result.status == "error"
        assert "Maximum 5" in result.error


class TestGetPortfolioForecastTool:
    """Tests for GetPortfolioForecastTool."""

    @pytest.mark.asyncio
    async def test_missing_user_id_returns_error(self) -> None:
        """Should return error when user_id is missing."""
        from backend.tools.forecast_tools import GetPortfolioForecastTool

        tool = GetPortfolioForecastTool()
        result = await tool.execute({})

        assert result.status == "error"
        assert "Missing" in result.error

    @pytest.mark.asyncio
    async def test_invalid_user_id_returns_error(self) -> None:
        """Should return error for non-UUID user_id."""
        from backend.tools.forecast_tools import GetPortfolioForecastTool

        tool = GetPortfolioForecastTool()
        result = await tool.execute({"user_id": "not-a-uuid"})

        assert result.status == "error"
        assert "Invalid" in result.error

    @pytest.mark.asyncio
    async def test_no_portfolio_returns_message(self) -> None:
        """Should return informational message when no portfolio exists."""
        from backend.tools.forecast_tools import GetPortfolioForecastTool

        mock_session = AsyncMock()
        # First execute: portfolio lookup returns None
        portfolio_result = MagicMock()
        portfolio_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = portfolio_result

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_session
        mock_cm.__aexit__.return_value = None

        with patch("backend.database.async_session_factory", return_value=mock_cm):
            tool = GetPortfolioForecastTool()
            result = await tool.execute({"user_id": "12345678-1234-5678-1234-567812345678"})

        assert result.status == "ok"
        assert "No portfolio found" in result.data["message"]

    @pytest.mark.asyncio
    async def test_no_positions_returns_message(self) -> None:
        """Should return informational message when portfolio is empty."""
        from backend.tools.forecast_tools import GetPortfolioForecastTool

        mock_session = AsyncMock()

        # First execute: portfolio lookup returns a portfolio
        mock_portfolio = MagicMock()
        mock_portfolio.id = "portfolio-uuid"
        portfolio_result = MagicMock()
        portfolio_result.scalar_one_or_none.return_value = mock_portfolio

        # Second execute: positions query returns empty
        positions_result = MagicMock()
        positions_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [portfolio_result, positions_result]

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_session
        mock_cm.__aexit__.return_value = None

        with patch("backend.database.async_session_factory", return_value=mock_cm):
            tool = GetPortfolioForecastTool()
            result = await tool.execute({"user_id": "12345678-1234-5678-1234-567812345678"})

        assert result.status == "ok"
        assert "No open positions" in result.data["message"]
