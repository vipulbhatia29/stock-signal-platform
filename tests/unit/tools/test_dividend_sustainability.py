"""Tests for DividendSustainabilityTool and RiskNarrativeTool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.tools.dividend_sustainability import _classify_sustainability


class TestClassifySustainability:
    """Tests for the sustainability classification logic."""

    def test_safe_low_payout_high_coverage(self) -> None:
        """Low payout + high FCF coverage = safe."""
        assert _classify_sustainability(0.3, 3.0) == "safe"

    def test_at_risk_high_payout_low_coverage(self) -> None:
        """Payout > 100% + FCF < 1x = at_risk."""
        assert _classify_sustainability(1.2, 0.8) == "at_risk"

    def test_moderate_high_payout_ok_coverage(self) -> None:
        """High payout but OK FCF = moderate."""
        assert _classify_sustainability(0.8, 2.0) == "moderate"

    def test_unknown_when_both_none(self) -> None:
        """No data = unknown."""
        assert _classify_sustainability(None, None) == "unknown"

    def test_moderate_only_payout_high(self) -> None:
        """Only payout ratio available and high = moderate."""
        assert _classify_sustainability(0.9, None) == "moderate"


class TestDividendSustainabilityTool:
    """Tests for the DividendSustainabilityTool."""

    @pytest.mark.asyncio
    async def test_non_dividend_payer(self) -> None:
        """Should return pays_dividend=False for non-payers."""
        from backend.tools.dividend_sustainability import (
            DividendSustainabilityTool,
        )

        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.info = {
                "dividendRate": None,
                "dividendYield": None,
            }

            tool = DividendSustainabilityTool()
            result = await tool.execute({"ticker": "TSLA"})

        assert result.status == "ok"
        assert result.data["pays_dividend"] is False

    @pytest.mark.asyncio
    async def test_dividend_payer_with_metrics(self) -> None:
        """Should return dividend metrics for payers."""
        from backend.tools.dividend_sustainability import (
            DividendSustainabilityTool,
        )

        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.info = {
                "dividendRate": 3.28,
                "dividendYield": 0.015,
                "payoutRatio": 0.42,
                "freeCashflow": 100_000_000_000,
                "trailingEps": 6.50,
                "marketCap": 3_000_000_000_000,
            }

            tool = DividendSustainabilityTool()
            result = await tool.execute({"ticker": "AAPL"})

        assert result.status == "ok"
        assert result.data["pays_dividend"] is True
        assert result.data["dividend_rate"] == 3.28
        assert result.data["sustainability"] == "safe"

    @pytest.mark.asyncio
    async def test_missing_ticker_returns_error(self) -> None:
        """Should return error for missing ticker."""
        from backend.tools.dividend_sustainability import (
            DividendSustainabilityTool,
        )

        tool = DividendSustainabilityTool()
        result = await tool.execute({})

        assert result.status == "error"
        assert "Missing" in result.error


def _make_session_cm(query_result: MagicMock) -> AsyncMock:
    """Create a mock async context manager returning a session with one execute result."""
    mock_session = AsyncMock()
    mock_session.execute.return_value = query_result
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None
    return mock_cm


class TestRiskNarrativeTool:
    """Tests for the RiskNarrativeTool."""

    @pytest.mark.asyncio
    async def test_low_risk_healthy_stock(self) -> None:
        """Should return low risk for a healthy stock."""
        from backend.tools.risk_narrative import RiskNarrativeTool

        mock_stock = MagicMock()
        mock_stock.ticker = "AAPL"
        mock_stock.name = "Apple Inc"
        mock_stock.sector = "Technology"
        mock_stock.return_on_equity = 1.5
        mock_stock.revenue_growth = 0.08

        mock_signal = MagicMock()
        mock_signal.composite_score = 7.5
        mock_signal.rsi_14 = 55.0

        stock_result = MagicMock()
        stock_result.scalar_one_or_none.return_value = mock_stock
        sig_result = MagicMock()
        sig_result.scalar_one_or_none.return_value = mock_signal
        fc_result = MagicMock()
        fc_result.scalar_one_or_none.return_value = None

        # 4 sessions: stock (seq), then signal + forecast + sector ETF (parallel)
        with patch(
            "backend.database.async_session_factory",
            side_effect=[
                _make_session_cm(stock_result),
                _make_session_cm(sig_result),
                _make_session_cm(fc_result),
                _make_session_cm(fc_result),
            ],
        ):
            tool = RiskNarrativeTool()
            result = await tool.execute({"ticker": "AAPL"})

        assert result.status == "ok"
        assert result.data["risk_level"] == "low"
        assert len(result.data["risk_factors"]) == 0

    @pytest.mark.asyncio
    async def test_high_risk_weak_stock(self) -> None:
        """Should return high risk for a stock with multiple red flags."""
        from backend.tools.risk_narrative import RiskNarrativeTool

        mock_stock = MagicMock()
        mock_stock.ticker = "SNAP"
        mock_stock.name = "Snap Inc"
        mock_stock.sector = "Communication Services"
        mock_stock.return_on_equity = -0.2
        mock_stock.revenue_growth = -0.15

        mock_signal = MagicMock()
        mock_signal.composite_score = 2.1
        mock_signal.rsi_14 = 75.0

        stock_result = MagicMock()
        stock_result.scalar_one_or_none.return_value = mock_stock
        sig_result = MagicMock()
        sig_result.scalar_one_or_none.return_value = mock_signal
        fc_result = MagicMock()
        fc_result.scalar_one_or_none.return_value = None

        # 4 sessions: stock (seq), then signal + forecast + sector ETF (parallel)
        with patch(
            "backend.database.async_session_factory",
            side_effect=[
                _make_session_cm(stock_result),
                _make_session_cm(sig_result),
                _make_session_cm(fc_result),
                _make_session_cm(fc_result),
            ],
        ):
            tool = RiskNarrativeTool()
            result = await tool.execute({"ticker": "SNAP"})

        assert result.status == "ok"
        assert result.data["risk_level"] == "high"
        assert len(result.data["risk_factors"]) >= 3

    @pytest.mark.asyncio
    async def test_missing_ticker_returns_error(self) -> None:
        """Should return error for missing ticker."""
        from backend.tools.risk_narrative import RiskNarrativeTool

        tool = RiskNarrativeTool()
        result = await tool.execute({})

        assert result.status == "error"
        assert "Missing" in result.error

    @pytest.mark.asyncio
    async def test_includes_forecast_context(self) -> None:
        """Should include forecast context when available."""
        from datetime import date

        from backend.tools.risk_narrative import RiskNarrativeTool

        mock_stock = MagicMock()
        mock_stock.ticker = "NVDA"
        mock_stock.name = "NVIDIA"
        mock_stock.sector = "Technology"
        mock_stock.return_on_equity = 0.5
        mock_stock.revenue_growth = 0.2

        mock_signal = MagicMock()
        mock_signal.composite_score = 8.0
        mock_signal.rsi_14 = 60.0

        mock_forecast = MagicMock()
        mock_forecast.expected_return_pct = 3.33
        mock_forecast.return_lower_pct = -6.67
        mock_forecast.return_upper_pct = 13.33
        mock_forecast.confidence_score = 0.65
        mock_forecast.direction = "bullish"
        mock_forecast.base_price = 145.0
        mock_forecast.actual_return_pct = None
        mock_forecast.forecast_signal = None
        mock_forecast.drivers = None
        mock_forecast.target_date = date(2026, 6, 20)

        stock_r = MagicMock()
        stock_r.scalar_one_or_none.return_value = mock_stock
        sig_r = MagicMock()
        sig_r.scalar_one_or_none.return_value = mock_signal
        fc_r = MagicMock()
        fc_r.scalar_one_or_none.return_value = mock_forecast
        etf_r = MagicMock()
        etf_r.scalar_one_or_none.return_value = None

        # 4 sessions: stock (seq), then signal + forecast + sector ETF (parallel)
        with patch(
            "backend.database.async_session_factory",
            side_effect=[
                _make_session_cm(stock_r),
                _make_session_cm(sig_r),
                _make_session_cm(fc_r),
                _make_session_cm(etf_r),
            ],
        ):
            tool = RiskNarrativeTool()
            result = await tool.execute({"ticker": "NVDA"})

        assert result.status == "ok"
        assert result.data["forecast_context"] is not None
        assert result.data["forecast_context"]["expected_return_pct"] == 3.33
        # 40% spread is > 30% threshold → should add risk factor
        wide_fc = [f for f in result.data["risk_factors"] if "forecast" in f["factor"].lower()]
        assert len(wide_fc) == 1
