"""Tests for compute_quantstats_stock() — per-stock QuantStats metrics."""

import numpy as np
import pandas as pd
import pytest

from backend.services.signals import compute_quantstats_stock


@pytest.fixture()
def stock_closes() -> pd.Series:
    """Generate 300 days of realistic stock prices."""
    np.random.seed(42)
    prices = 100 + np.cumsum(np.random.randn(300) * 1.5)
    dates = pd.bdate_range("2025-01-01", periods=300)
    return pd.Series(prices, index=dates, dtype=float)


@pytest.fixture()
def spy_closes() -> pd.Series:
    """Generate 300 days of SPY-like prices."""
    np.random.seed(123)
    prices = 450 + np.cumsum(np.random.randn(300) * 1.0)
    dates = pd.bdate_range("2025-01-01", periods=300)
    return pd.Series(prices, index=dates, dtype=float)


class TestComputeQuantstatsStock:
    def test_returns_all_keys(self, stock_closes, spy_closes):
        result = compute_quantstats_stock(stock_closes, spy_closes)
        assert set(result.keys()) == {"sortino", "max_drawdown", "alpha", "beta", "data_days"}

    def test_sortino_is_finite(self, stock_closes, spy_closes):
        result = compute_quantstats_stock(stock_closes, spy_closes)
        assert result["sortino"] is not None
        assert np.isfinite(result["sortino"])

    def test_max_drawdown_is_positive(self, stock_closes, spy_closes):
        result = compute_quantstats_stock(stock_closes, spy_closes)
        assert result["max_drawdown"] is not None
        assert result["max_drawdown"] >= 0

    def test_alpha_beta_computed(self, stock_closes, spy_closes):
        result = compute_quantstats_stock(stock_closes, spy_closes)
        assert result["alpha"] is not None
        assert result["beta"] is not None

    def test_insufficient_data_returns_nulls(self):
        """Under 30 common trading days → all None."""
        short = pd.Series([100, 101, 102], index=pd.bdate_range("2025-01-01", periods=3))
        spy = pd.Series([450, 451, 452], index=pd.bdate_range("2025-01-01", periods=3))
        result = compute_quantstats_stock(short, spy)
        assert result["sortino"] is None
        assert result["max_drawdown"] is None
        assert result["alpha"] is None
        assert result["beta"] is None

    def test_no_overlapping_dates_returns_nulls(self, stock_closes):
        """Non-overlapping date ranges → all None."""
        spy = pd.Series(
            [450] * 50,
            index=pd.bdate_range("2020-01-01", periods=50),
        )
        result = compute_quantstats_stock(stock_closes, spy)
        assert result["sortino"] is None

    def test_values_are_rounded_to_4_decimals(self, stock_closes, spy_closes):
        result = compute_quantstats_stock(stock_closes, spy_closes)
        for key in ["sortino", "max_drawdown", "alpha", "beta"]:
            val = result[key]
            if val is not None:
                # Check max 4 decimal places
                assert val == round(val, 4)
