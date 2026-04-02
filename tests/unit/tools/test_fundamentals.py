"""Unit tests for the fundamentals tool.

Tests cover:
  - Piotroski F-Score computation from synthetic financial data
  - Fundamental metric extraction from yfinance info dict
  - Graceful degradation when data is missing or partial
  - fetch_fundamentals() with mocked yfinance Ticker

All tests are pure unit tests — no database, no network calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.tools.fundamentals import (
    FundamentalResult,
    compute_piotroski,
    fetch_fundamentals,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helper factories — build minimal yfinance-style data structures
# ─────────────────────────────────────────────────────────────────────────────


def _make_info(
    trailing_pe: float | None = 20.0,
    peg_ratio: float | None = 1.5,
    market_cap: float | None = 2_000_000_000,
    free_cashflow: float | None = 100_000_000,
    debt_to_equity: float | None = 0.5,
    total_debt: float | None = 500_000_000,
    total_assets: float | None = 2_000_000_000,
    current_ratio: float | None = 1.8,
    shares_outstanding: float | None = 1_000_000,
    gross_margins: float | None = 0.45,
    asset_turnover: float | None = 0.9,
    revenue: float | None = 500_000_000,
    revenue_prior: float | None = 450_000_000,
    gross_margins_prior: float | None = 0.42,
    asset_turnover_prior: float | None = 0.85,
    roa: float | None = 0.08,
    roa_prior: float | None = 0.06,
    long_term_debt: float | None = 300_000_000,
    long_term_debt_prior: float | None = 350_000_000,
    current_ratio_prior: float | None = 1.6,
    shares_prior: float | None = 1_050_000,
    operating_cashflow: float | None = 120_000_000,
) -> dict:
    """Build a minimal yfinance .info-style dict."""
    return {
        "trailingPE": trailing_pe,
        "pegRatio": peg_ratio,
        "marketCap": market_cap,
        "freeCashflow": free_cashflow,
        "debtToEquity": debt_to_equity,
        "totalDebt": total_debt,
        "totalAssets": total_assets,
        "currentRatio": current_ratio,
        "sharesOutstanding": shares_outstanding,
        "grossMargins": gross_margins,
        "assetTurnover": asset_turnover,
        "totalRevenue": revenue,
        "totalRevenuePrior": revenue_prior,
        "grossMarginsPrior": gross_margins_prior,
        "assetTurnoverPrior": asset_turnover_prior,
        "returnOnAssets": roa,
        "returnOnAssetsPrior": roa_prior,
        "longTermDebt": long_term_debt,
        "longTermDebtPrior": long_term_debt_prior,
        "currentRatioPrior": current_ratio_prior,
        "sharesPrior": shares_prior,
        "operatingCashflow": operating_cashflow,
    }


def _make_ticker_mock(info: dict) -> MagicMock:
    """Build a mock yfinance Ticker with the given info dict."""
    mock = MagicMock()
    mock.info = info
    return mock


# ─────────────────────────────────────────────────────────────────────────────
# FundamentalResult dataclass
# ─────────────────────────────────────────────────────────────────────────────


def test_fundamental_result_fields_exist():
    """FundamentalResult must expose all expected fields."""
    result = FundamentalResult(
        ticker="AAPL",
        pe_ratio=20.0,
        peg_ratio=1.5,
        fcf_yield=0.05,
        debt_to_equity=0.5,
        piotroski_score=7,
        piotroski_breakdown={},
    )
    assert result.ticker == "AAPL"
    assert result.pe_ratio == 20.0
    assert result.peg_ratio == 1.5
    assert result.fcf_yield == 0.05
    assert result.debt_to_equity == 0.5
    assert result.piotroski_score == 7


# ─────────────────────────────────────────────────────────────────────────────
# compute_piotroski — core scoring logic
# ─────────────────────────────────────────────────────────────────────────────


def test_piotroski_strong_company_scores_high():
    """A financially healthy company should score 8 or 9."""
    info = _make_info(
        roa=0.10,  # Profitability: positive ROA
        roa_prior=0.08,  # Profitability: improving ROA
        operating_cashflow=120_000_000,  # Profitability: positive CFO
        # CFO > Net income implied by ROA * assets
        total_assets=1_000_000_000,
        long_term_debt=100_000_000,
        long_term_debt_prior=150_000_000,  # Leverage: decreasing debt
        current_ratio=2.0,
        current_ratio_prior=1.5,  # Liquidity: improving
        shares_outstanding=1_000_000,
        shares_prior=1_050_000,  # No dilution: shares decreased
        gross_margins=0.50,
        gross_margins_prior=0.45,  # Efficiency: improving margins
        asset_turnover=1.0,
        asset_turnover_prior=0.9,  # Efficiency: improving turnover
        revenue=600_000_000,
    )
    score, breakdown = compute_piotroski(info)
    assert score >= 7, f"Expected score >= 7, got {score}. Breakdown: {breakdown}"


def test_piotroski_weak_company_scores_low():
    """A financially distressed company should score 2 or lower."""
    info = _make_info(
        roa=-0.05,  # Profitability: negative ROA
        roa_prior=-0.02,  # Profitability: worsening ROA
        operating_cashflow=-50_000_000,  # Profitability: negative CFO
        total_assets=1_000_000_000,
        long_term_debt=800_000_000,
        long_term_debt_prior=600_000_000,  # Leverage: increasing debt
        current_ratio=0.8,
        current_ratio_prior=1.2,  # Liquidity: deteriorating
        shares_outstanding=1_200_000,
        shares_prior=1_000_000,  # Dilution: shares increased
        gross_margins=0.20,
        gross_margins_prior=0.30,  # Efficiency: worsening margins
        asset_turnover=0.5,
        asset_turnover_prior=0.7,  # Efficiency: worsening turnover
        revenue=400_000_000,
    )
    score, breakdown = compute_piotroski(info)
    assert score <= 3, f"Expected score <= 3, got {score}. Breakdown: {breakdown}"


def test_piotroski_breakdown_keys():
    """compute_piotroski must return a breakdown with 9 binary criteria."""
    info = _make_info()
    score, breakdown = compute_piotroski(info)
    expected_keys = {
        "positive_roa",
        "positive_cfo",
        "improving_roa",
        "accruals",
        "decreasing_leverage",
        "improving_liquidity",
        "no_dilution",
        "improving_gross_margin",
        "improving_asset_turnover",
    }
    assert set(breakdown.keys()) == expected_keys
    for key, val in breakdown.items():
        assert val in (0, 1), f"Criterion {key} must be 0 or 1, got {val}"


def test_piotroski_score_equals_sum_of_breakdown():
    """Total score must equal sum of all binary criteria."""
    info = _make_info()
    score, breakdown = compute_piotroski(info)
    assert score == sum(breakdown.values())


def test_piotroski_missing_data_returns_none():
    """When financial data is entirely missing, return (None, {})."""
    score, breakdown = compute_piotroski({})
    assert score is None
    assert breakdown == {}


def test_piotroski_partial_data_skips_missing_criteria():
    """Partial data should score what's available, skip what isn't."""
    # Only provide ROA — other criteria will be None/missing
    info = {"returnOnAssets": 0.08, "operatingCashflow": 100_000_000, "totalAssets": 1_000_000_000}
    score, breakdown = compute_piotroski(info)
    # Score should be non-None (we have some data)
    assert score is not None
    assert isinstance(score, int)
    assert 0 <= score <= 9


# ─────────────────────────────────────────────────────────────────────────────
# fetch_fundamentals — full pipeline with mocked yfinance
# ─────────────────────────────────────────────────────────────────────────────


def test_fetch_fundamentals_returns_result():
    """fetch_fundamentals returns a FundamentalResult for a valid ticker."""
    info = _make_info(
        trailing_pe=25.0,
        peg_ratio=1.8,
        market_cap=3_000_000_000,
        free_cashflow=150_000_000,
        debt_to_equity=0.4,
    )
    mock_ticker = _make_ticker_mock(info)
    with patch("backend.services.stock_data.yf.Ticker", return_value=mock_ticker):
        result = fetch_fundamentals("AAPL")

    assert isinstance(result, FundamentalResult)
    assert result.ticker == "AAPL"
    assert result.pe_ratio == 25.0
    assert result.peg_ratio == 1.8
    assert result.debt_to_equity == 0.4


def test_fetch_fundamentals_computes_fcf_yield():
    """FCF yield = free_cashflow / market_cap."""
    info = _make_info(free_cashflow=100_000_000, market_cap=2_000_000_000)
    mock_ticker = _make_ticker_mock(info)
    with patch("backend.services.stock_data.yf.Ticker", return_value=mock_ticker):
        result = fetch_fundamentals("MSFT")

    expected_yield = round(100_000_000 / 2_000_000_000, 4)
    assert result.fcf_yield == pytest.approx(expected_yield, abs=1e-4)


def test_fetch_fundamentals_missing_pe_returns_none():
    """Missing P/E ratio should result in pe_ratio=None, not crash."""
    info = _make_info(trailing_pe=None)
    mock_ticker = _make_ticker_mock(info)
    with patch("backend.services.stock_data.yf.Ticker", return_value=mock_ticker):
        result = fetch_fundamentals("XYZ")

    assert result.pe_ratio is None


def test_fetch_fundamentals_zero_market_cap_gives_none_fcf_yield():
    """Zero market cap must not cause division by zero — fcf_yield should be None."""
    info = _make_info(market_cap=0, free_cashflow=50_000_000)
    mock_ticker = _make_ticker_mock(info)
    with patch("backend.services.stock_data.yf.Ticker", return_value=mock_ticker):
        result = fetch_fundamentals("BAD")

    assert result.fcf_yield is None


def test_fetch_fundamentals_empty_info_returns_none_fields():
    """An empty info dict should return all-None FundamentalResult without crashing."""
    mock_ticker = _make_ticker_mock({})
    with patch("backend.services.stock_data.yf.Ticker", return_value=mock_ticker):
        result = fetch_fundamentals("EMPTY")

    assert result.ticker == "EMPTY"
    assert result.pe_ratio is None
    assert result.peg_ratio is None
    assert result.fcf_yield is None
    assert result.debt_to_equity is None
    assert result.piotroski_score is None


def test_fetch_fundamentals_piotroski_included():
    """fetch_fundamentals must include a piotroski_score in the result."""
    info = _make_info()
    mock_ticker = _make_ticker_mock(info)
    with patch("backend.services.stock_data.yf.Ticker", return_value=mock_ticker):
        result = fetch_fundamentals("GOOG")

    assert result.piotroski_score is not None
    assert 0 <= result.piotroski_score <= 9
    assert isinstance(result.piotroski_breakdown, dict)


def test_fetch_fundamentals_ticker_uppercased():
    """Ticker should be stored uppercase regardless of input case."""
    info = _make_info()
    mock_ticker = _make_ticker_mock(info)
    with patch("backend.services.stock_data.yf.Ticker", return_value=mock_ticker):
        result = fetch_fundamentals("aapl")

    assert result.ticker == "AAPL"


def test_fetch_fundamentals_yfinance_exception_returns_none_result():
    """If yfinance raises, return a FundamentalResult with all None fields."""
    with patch("backend.services.stock_data.yf.Ticker", side_effect=Exception("network error")):
        result = fetch_fundamentals("FAIL")

    assert result.ticker == "FAIL"
    assert result.pe_ratio is None
    assert result.piotroski_score is None


# ─────────────────────────────────────────────────────────────────────────────
# Extended fundamentals: growth, margins, analyst data, persistence, tool
# (merged from test_fundamentals_tool.py)
# ─────────────────────────────────────────────────────────────────────────────


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
        from unittest.mock import AsyncMock

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
        from unittest.mock import AsyncMock

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
