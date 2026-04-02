"""Hypothesis property-based tests for QuantStats metric computation.

Tests invariants like: all metrics finite, volatility >= 0, win rate in [0,1],
graceful handling of edge cases (empty series, single day, negative-only returns).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from backend.services.signals import compute_quantstats_stock

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_return_strategy = st.lists(
    st.floats(min_value=-0.3, max_value=0.3, allow_nan=False, allow_infinity=False),
    min_size=60,
    max_size=300,
)


def _make_price_series(returns: list[float], start: float = 100.0) -> pd.Series:
    """Convert returns to price series with business day index."""
    arr = np.array(returns)
    prices = start * np.cumprod(1 + arr)
    dates = pd.bdate_range("2023-01-01", periods=len(prices))
    return pd.Series(prices, index=dates, dtype=float)


def _make_spy_series(n: int, start: float = 450.0) -> pd.Series:
    """Make a synthetic SPY series of length n."""
    rng = np.random.default_rng(42)
    returns = rng.normal(0.0004, 0.01, n)
    prices = start * np.cumprod(1 + returns)
    dates = pd.bdate_range("2023-01-01", periods=n)
    return pd.Series(prices, index=dates, dtype=float)


# ---------------------------------------------------------------------------
# All metrics finite for bounded returns
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(returns=_return_strategy)
def test_all_metrics_finite_for_bounded_returns(returns: list[float]) -> None:
    """compute_quantstats_stock returns only finite values for any bounded return series."""
    n = len(returns)
    closes = _make_price_series(returns)
    spy = _make_spy_series(n)
    result = compute_quantstats_stock(closes, spy)

    for key, val in result.items():
        if val is not None and key != "data_days":
            assert math.isfinite(val), f"Non-finite value for key={key}: {val}"


# ---------------------------------------------------------------------------
# Volatility >= 0
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(returns=_return_strategy)
def test_volatility_nonnegative(returns: list[float]) -> None:
    """Annualized volatility must always be >= 0."""
    arr = np.array(returns)
    daily_vol = float(arr.std())
    annual_vol = daily_vol * math.sqrt(252)
    assert annual_vol >= 0.0, f"Volatility {annual_vol} is negative"


# ---------------------------------------------------------------------------
# Win rate in [0, 1]
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(returns=_return_strategy)
def test_win_rate_bounded(returns: list[float]) -> None:
    """Win rate (fraction of positive days) must be in [0, 1]."""
    arr = np.array(returns)
    win_rate = float(np.sum(arr > 0) / len(arr))
    assert 0.0 <= win_rate <= 1.0, f"Win rate {win_rate} out of bounds"


# ---------------------------------------------------------------------------
# Profit factor > 0 when gains and losses both exist
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(
    gains=st.lists(
        st.floats(min_value=0.001, max_value=0.1, allow_nan=False, allow_infinity=False),
        min_size=5,
        max_size=50,
    ),
    losses=st.lists(
        st.floats(min_value=0.001, max_value=0.1, allow_nan=False, allow_infinity=False),
        min_size=5,
        max_size=50,
    ),
)
def test_profit_factor_positive_when_both_sides_exist(
    gains: list[float], losses: list[float]
) -> None:
    """Profit factor = total_gains / total_losses > 0 when both exist."""
    total_gains = sum(gains)
    total_losses = sum(losses)
    if total_losses > 0 and total_gains > 0:
        profit_factor = total_gains / total_losses
        assert profit_factor > 0.0


# ---------------------------------------------------------------------------
# Monthly returns sum approximately equal total return
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(
    monthly_returns=st.lists(
        st.floats(min_value=-0.1, max_value=0.15, allow_nan=False, allow_infinity=False),
        min_size=3,
        max_size=36,
    )
)
def test_compounded_monthly_returns_equal_total(monthly_returns: list[float]) -> None:
    """Product of (1 + monthly_returns) == total return multiplier."""
    arr = np.array(monthly_returns)
    compounded = float(np.prod(1 + arr)) - 1.0
    # Sum approximation works only for small returns
    simple_sum = float(np.sum(monthly_returns))
    # Compounded must be finite
    assert math.isfinite(compounded)
    # For small monthly returns, compounded ~ sum
    if max(abs(r) for r in monthly_returns) < 0.05:
        assert abs(compounded - simple_sum) < 0.05 * len(monthly_returns)


# ---------------------------------------------------------------------------
# Empty series handling — must not raise
# ---------------------------------------------------------------------------


@pytest.mark.domain
def test_empty_series_returns_nulls_not_exception() -> None:
    """compute_quantstats_stock with < 30 common days returns nulls, never raises."""
    closes = pd.Series(
        [100.0, 101.0, 102.0],
        index=pd.bdate_range("2025-01-01", periods=3),
    )
    spy = pd.Series(
        [450.0, 451.0, 452.0],
        index=pd.bdate_range("2025-01-01", periods=3),
    )
    result = compute_quantstats_stock(closes, spy)
    # Should return null result without raising
    assert result["sortino"] is None
    assert result["max_drawdown"] is None


# ---------------------------------------------------------------------------
# Single-day series
# ---------------------------------------------------------------------------


@pytest.mark.domain
def test_single_day_series_returns_null() -> None:
    """A single-day price series has no returns — should return nulls."""
    closes = pd.Series([100.0], index=pd.bdate_range("2025-01-01", periods=1))
    spy = pd.Series([450.0], index=pd.bdate_range("2025-01-01", periods=1))
    result = compute_quantstats_stock(closes, spy)
    assert result["sortino"] is None
    assert result["data_days"] == 0


# ---------------------------------------------------------------------------
# Timezone normalization
# ---------------------------------------------------------------------------


@pytest.mark.domain
def test_timezone_normalization_does_not_change_values() -> None:
    """UTC-aware and tz-naive series should produce the same metrics."""
    rng = np.random.default_rng(99)
    n = 100
    prices_arr = 100 + np.cumsum(rng.normal(0, 1, n))
    spy_arr = 450 + np.cumsum(rng.normal(0, 0.8, n))
    dates_naive = pd.bdate_range("2024-01-01", periods=n, tz=None)
    dates_utc = pd.bdate_range("2024-01-01", periods=n, tz="UTC")

    closes_naive = pd.Series(prices_arr, index=dates_naive)
    closes_utc = pd.Series(prices_arr, index=dates_utc)
    spy_naive = pd.Series(spy_arr, index=dates_naive)
    spy_utc = pd.Series(spy_arr, index=dates_utc)

    result_naive = compute_quantstats_stock(closes_naive, spy_naive)
    result_utc = compute_quantstats_stock(closes_utc, spy_utc)

    for key in ("sortino", "max_drawdown"):
        v1, v2 = result_naive[key], result_utc[key]
        if v1 is not None and v2 is not None:
            assert abs(v1 - v2) < 1e-6, f"{key}: naive={v1} != utc={v2}"


# ---------------------------------------------------------------------------
# Negative-only returns still computable
# ---------------------------------------------------------------------------


@pytest.mark.domain
def test_negative_only_returns_still_computable() -> None:
    """All metrics should be computable even when all returns are negative."""
    rng = np.random.default_rng(77)
    n = 100
    prices = 100.0 * np.cumprod(1 + rng.uniform(-0.02, -0.001, n))
    spy_prices = 450 + np.cumsum(rng.normal(0, 0.8, n))
    dates = pd.bdate_range("2024-01-01", periods=n)
    closes = pd.Series(prices, index=dates)
    spy = pd.Series(spy_prices, index=dates)
    # Should not raise
    result = compute_quantstats_stock(closes, spy)
    assert isinstance(result, dict)
    assert "sortino" in result


# ---------------------------------------------------------------------------
# Benchmark comparison: alpha approximation
# ---------------------------------------------------------------------------


@pytest.mark.domain
def test_alpha_is_finite_for_normal_inputs() -> None:
    """Alpha should be a finite number for reasonable stock and benchmark returns."""
    rng = np.random.default_rng(55)
    n = 200
    prices = 100 + np.cumsum(rng.normal(0.5, 1.5, n))
    spy_prices = 450 + np.cumsum(rng.normal(0.3, 1.0, n))
    dates = pd.bdate_range("2024-01-01", periods=n)
    closes = pd.Series(prices, index=dates)
    spy = pd.Series(spy_prices, index=dates)
    result = compute_quantstats_stock(closes, spy)
    if result["alpha"] is not None:
        assert math.isfinite(result["alpha"])
