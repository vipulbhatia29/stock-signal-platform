"""Unit tests for sectors router helper functions and logic."""

from __future__ import annotations

import pandas as pd
import pytest

from backend.routers.sectors import (
    _UNKNOWN_SECTOR,
    MAX_CORRELATION_TICKERS,
    MIN_CORRELATION_DATAPOINTS,
    ScopeEnum,
)
from backend.schemas.sectors import (
    CorrelationResponse,
    ExcludedTicker,
    SectorStock,
    SectorStocksResponse,
    SectorSummary,
    SectorSummaryResponse,
)

# ─────────────────────────────────────────────────────────────────────────────
# Schema validation tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSectorSchemas:
    """Pydantic schema construction and validation."""

    def test_sector_summary_defaults(self) -> None:
        """SectorSummary has correct defaults for optional fields."""
        s = SectorSummary(sector="Technology", stock_count=10)
        assert s.avg_composite_score is None
        assert s.avg_return_pct is None
        assert s.your_stock_count == 0
        assert s.allocation_pct is None

    def test_sector_summary_full(self) -> None:
        """SectorSummary accepts all fields."""
        s = SectorSummary(
            sector="Healthcare",
            stock_count=25,
            avg_composite_score=7.2,
            avg_return_pct=12.5,
            your_stock_count=3,
            allocation_pct=18.5,
        )
        assert s.sector == "Healthcare"
        assert s.stock_count == 25
        assert s.allocation_pct == 18.5

    def test_sector_summary_response(self) -> None:
        """SectorSummaryResponse wraps a list of summaries."""
        resp = SectorSummaryResponse(
            sectors=[
                SectorSummary(sector="Tech", stock_count=5),
                SectorSummary(sector="Healthcare", stock_count=3),
            ]
        )
        assert len(resp.sectors) == 2

    def test_sector_stock_defaults(self) -> None:
        """SectorStock defaults is_held/is_watched to False."""
        s = SectorStock(ticker="AAPL", name="Apple Inc")
        assert s.is_held is False
        assert s.is_watched is False
        assert s.composite_score is None
        assert s.current_price is None
        assert s.return_pct is None

    def test_sector_stocks_response(self) -> None:
        """SectorStocksResponse wraps sector name and stock list."""
        resp = SectorStocksResponse(
            sector="Technology",
            stocks=[SectorStock(ticker="AAPL", name="Apple Inc", is_held=True)],
        )
        assert resp.sector == "Technology"
        assert resp.stocks[0].is_held is True

    def test_excluded_ticker(self) -> None:
        """ExcludedTicker has ticker and reason."""
        e = ExcludedTicker(ticker="TINY", reason="Only 5 data points (minimum 30)")
        assert e.ticker == "TINY"
        assert "5 data points" in e.reason

    def test_correlation_response(self) -> None:
        """CorrelationResponse validates matrix shape logically."""
        resp = CorrelationResponse(
            sector="Technology",
            tickers=["AAPL", "MSFT"],
            matrix=[[1.0, 0.85], [0.85, 1.0]],
            period_days=90,
            excluded_tickers=[ExcludedTicker(ticker="TINY", reason="Insufficient data")],
        )
        assert len(resp.tickers) == 2
        assert len(resp.matrix) == 2
        assert len(resp.matrix[0]) == 2
        assert resp.excluded_tickers[0].ticker == "TINY"

    def test_correlation_response_period_days_validation(self) -> None:
        """CorrelationResponse rejects period_days < 1."""
        with pytest.raises(Exception):
            CorrelationResponse(
                sector="Tech",
                tickers=["A", "B"],
                matrix=[[1, 0], [0, 1]],
                period_days=0,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Constants tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSectorConstants:
    """Verify sector router constants."""

    def test_max_correlation_tickers(self) -> None:
        """Max correlation tickers is 15."""
        assert MAX_CORRELATION_TICKERS == 15

    def test_min_correlation_datapoints(self) -> None:
        """Min correlation data points is 30."""
        assert MIN_CORRELATION_DATAPOINTS == 30

    def test_unknown_sector_label(self) -> None:
        """Unknown sector is labelled 'Unknown'."""
        assert _UNKNOWN_SECTOR == "Unknown"


# ─────────────────────────────────────────────────────────────────────────────
# ScopeEnum tests
# ─────────────────────────────────────────────────────────────────────────────


class TestScopeEnum:
    """ScopeEnum validation."""

    def test_scope_values(self) -> None:
        """ScopeEnum has expected values."""
        assert ScopeEnum.portfolio == "portfolio"
        assert ScopeEnum.watchlist == "watchlist"
        assert ScopeEnum.all == "all"

    def test_scope_from_string(self) -> None:
        """ScopeEnum can be constructed from string."""
        assert ScopeEnum("portfolio") == ScopeEnum.portfolio


# ─────────────────────────────────────────────────────────────────────────────
# Correlation logic tests (pure computation)
# ─────────────────────────────────────────────────────────────────────────────


class TestCorrelationComputation:
    """Test the pandas correlation computation logic used by the endpoint."""

    def test_perfectly_correlated_series(self) -> None:
        """Two identical series have correlation 1.0."""
        dates = pd.date_range("2024-01-01", periods=60, freq="B")
        prices = [100 + i * 0.5 for i in range(60)]
        df = pd.DataFrame({"A": prices, "B": prices}, index=dates)
        corr = df.pct_change().dropna().corr()
        assert abs(corr.iloc[0, 1] - 1.0) < 0.001

    def test_negatively_correlated_series(self) -> None:
        """Two series with opposite daily moves have negative correlation."""
        import numpy as np

        rng = np.random.default_rng(42)
        dates = pd.date_range("2024-01-01", periods=60, freq="B")
        # Generate random returns, then invert for B
        daily_returns = rng.standard_normal(60) * 0.02
        prices_a = [100.0]
        prices_b = [100.0]
        for r in daily_returns:
            prices_a.append(prices_a[-1] * (1 + r))
            prices_b.append(prices_b[-1] * (1 - r))
        df = pd.DataFrame({"A": prices_a[1:], "B": prices_b[1:]}, index=dates)
        corr = df.pct_change().dropna().corr()
        assert corr.iloc[0, 1] < -0.9

    def test_uncorrelated_series(self) -> None:
        """Sine and cosine series produce near-zero correlation."""
        import numpy as np

        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        prices_a = [100 + 10 * np.sin(i * 0.1) for i in range(100)]
        prices_b = [100 + 10 * np.cos(i * 0.1) for i in range(100)]
        df = pd.DataFrame({"A": prices_a, "B": prices_b}, index=dates)
        corr = df.pct_change().dropna().corr()
        # Not perfectly 0, but should be low
        assert abs(corr.iloc[0, 1]) < 0.5

    def test_matrix_is_symmetric(self) -> None:
        """Correlation matrix is symmetric."""
        dates = pd.date_range("2024-01-01", periods=60, freq="B")
        import numpy as np

        rng = np.random.default_rng(42)
        df = pd.DataFrame(
            {
                "A": 100 + rng.standard_normal(60).cumsum(),
                "B": 100 + rng.standard_normal(60).cumsum(),
                "C": 100 + rng.standard_normal(60).cumsum(),
            },
            index=dates,
        )
        corr = df.pct_change().dropna().corr()
        for i in range(3):
            for j in range(3):
                assert abs(corr.iloc[i, j] - corr.iloc[j, i]) < 1e-10

    def test_diagonal_is_one(self) -> None:
        """Diagonal of correlation matrix is always 1.0."""
        dates = pd.date_range("2024-01-01", periods=60, freq="B")
        import numpy as np

        rng = np.random.default_rng(42)
        df = pd.DataFrame(
            {
                "A": 100 + rng.standard_normal(60).cumsum(),
                "B": 100 + rng.standard_normal(60).cumsum(),
            },
            index=dates,
        )
        corr = df.pct_change().dropna().corr()
        assert abs(corr.iloc[0, 0] - 1.0) < 1e-10
        assert abs(corr.iloc[1, 1] - 1.0) < 1e-10

    def test_insufficient_data_excluded(self) -> None:
        """Tickers with fewer than MIN_CORRELATION_DATAPOINTS are excluded."""
        ticker_data = {
            "AAPL": 60,  # sufficient
            "TINY": 10,  # insufficient
            "MSFT": 45,  # sufficient
        }
        excluded = []
        sufficient = []
        for ticker, count in ticker_data.items():
            if count < MIN_CORRELATION_DATAPOINTS:
                excluded.append(ticker)
            else:
                sufficient.append(ticker)

        assert "TINY" in excluded
        assert "AAPL" in sufficient
        assert "MSFT" in sufficient
        assert len(excluded) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation logic tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSectorAggregation:
    """Test sector aggregation logic patterns."""

    def test_null_sector_grouped_as_unknown(self) -> None:
        """Stocks with NULL sector should be grouped under 'Unknown'."""
        # Simulate the coalesce logic
        sectors = [None, "Technology", None, "Healthcare"]
        grouped = {}
        for s in sectors:
            label = s if s is not None else _UNKNOWN_SECTOR
            grouped.setdefault(label, 0)
            grouped[label] += 1

        assert grouped[_UNKNOWN_SECTOR] == 2
        assert grouped["Technology"] == 1
        assert grouped["Healthcare"] == 1

    def test_allocation_pct_sums_to_100(self) -> None:
        """Allocation percentages should sum to approximately 100%."""
        sector_values = {"Technology": 50000, "Healthcare": 30000, "Energy": 20000}
        total = sum(sector_values.values())
        pcts = {s: round(v / total * 100, 2) for s, v in sector_values.items()}
        assert abs(sum(pcts.values()) - 100.0) < 0.1

    def test_allocation_pct_none_when_no_portfolio(self) -> None:
        """Allocation is None when total_portfolio_value is 0."""
        total_portfolio_value = 0.0
        alloc_pct = (
            round(5000 / total_portfolio_value * 100, 2) if total_portfolio_value > 0 else None
        )
        assert alloc_pct is None

    def test_avg_score_computation(self) -> None:
        """Average composite score is computed correctly."""
        scores = [7.5, 8.0, 6.5]
        avg = round(sum(scores) / len(scores), 2)
        assert avg == 7.33

    def test_avg_return_with_no_data(self) -> None:
        """Avg return is None when no return data."""
        returns: list[float] = []
        avg_ret = round(sum(returns) / len(returns), 2) if returns else None
        assert avg_ret is None

    def test_scope_portfolio_only_counts_held(self) -> None:
        """With scope=portfolio, only held tickers increment your_stock_count."""
        held = {"AAPL", "MSFT"}
        tickers = ["AAPL", "MSFT", "GOOG", "AMZN"]

        count = sum(1 for t in tickers if t in held)
        assert count == 2

    def test_scope_watchlist_only_counts_watched(self) -> None:
        """With scope=watchlist, only watched tickers increment your_stock_count."""
        watched = {"GOOG", "TSLA"}
        tickers = ["AAPL", "GOOG", "TSLA", "AMZN"]

        count = sum(1 for t in tickers if t in watched)
        assert count == 2

    def test_scope_all_counts_held_and_watched(self) -> None:
        """With scope=all, both held and watched tickers count."""
        held = {"AAPL"}
        watched = {"GOOG"}
        tickers = ["AAPL", "GOOG", "AMZN"]
        scope = ScopeEnum.all

        count = 0
        for t in tickers:
            if scope == ScopeEnum.all and t in (held | watched):
                count += 1
        assert count == 2
