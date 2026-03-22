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
    with patch("backend.tools.fundamentals.yf.Ticker", return_value=mock_ticker):
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
    with patch("backend.tools.fundamentals.yf.Ticker", return_value=mock_ticker):
        result = fetch_fundamentals("MSFT")

    expected_yield = round(100_000_000 / 2_000_000_000, 4)
    assert result.fcf_yield == pytest.approx(expected_yield, abs=1e-4)


def test_fetch_fundamentals_missing_pe_returns_none():
    """Missing P/E ratio should result in pe_ratio=None, not crash."""
    info = _make_info(trailing_pe=None)
    mock_ticker = _make_ticker_mock(info)
    with patch("backend.tools.fundamentals.yf.Ticker", return_value=mock_ticker):
        result = fetch_fundamentals("XYZ")

    assert result.pe_ratio is None


def test_fetch_fundamentals_zero_market_cap_gives_none_fcf_yield():
    """Zero market cap must not cause division by zero — fcf_yield should be None."""
    info = _make_info(market_cap=0, free_cashflow=50_000_000)
    mock_ticker = _make_ticker_mock(info)
    with patch("backend.tools.fundamentals.yf.Ticker", return_value=mock_ticker):
        result = fetch_fundamentals("BAD")

    assert result.fcf_yield is None


def test_fetch_fundamentals_empty_info_returns_none_fields():
    """An empty info dict should return all-None FundamentalResult without crashing."""
    mock_ticker = _make_ticker_mock({})
    with patch("backend.tools.fundamentals.yf.Ticker", return_value=mock_ticker):
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
    with patch("backend.tools.fundamentals.yf.Ticker", return_value=mock_ticker):
        result = fetch_fundamentals("GOOG")

    assert result.piotroski_score is not None
    assert 0 <= result.piotroski_score <= 9
    assert isinstance(result.piotroski_breakdown, dict)


def test_fetch_fundamentals_ticker_uppercased():
    """Ticker should be stored uppercase regardless of input case."""
    info = _make_info()
    mock_ticker = _make_ticker_mock(info)
    with patch("backend.tools.fundamentals.yf.Ticker", return_value=mock_ticker):
        result = fetch_fundamentals("aapl")

    assert result.ticker == "AAPL"


def test_fetch_fundamentals_yfinance_exception_returns_none_result():
    """If yfinance raises, return a FundamentalResult with all None fields."""
    with patch("backend.tools.fundamentals.yf.Ticker", side_effect=Exception("network error")):
        result = fetch_fundamentals("FAIL")

    assert result.ticker == "FAIL"
    assert result.pe_ratio is None
    assert result.piotroski_score is None
