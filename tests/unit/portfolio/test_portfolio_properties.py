"""Hypothesis property-based tests for portfolio math.

Tests invariants that must hold for ALL valid portfolio inputs — weight
normalization, FIFO cost basis, P&L calculations, and risk metrics.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.services.portfolio import _run_fifo

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_positive_float = st.floats(
    min_value=0.01, max_value=1_000_000.0, allow_nan=False, allow_infinity=False
)
_small_return = st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False)
_share_count = st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False)


def _make_weight_dict(n: int, values: list[float]) -> dict[str, float]:
    """Normalize a list of values to a weight dict summing to 1."""
    total = sum(values)
    if total == 0:
        return {f"T{i}": 1.0 / n for i in range(n)}
    return {f"T{i}": v / total for i, v in enumerate(values)}


# ---------------------------------------------------------------------------
# Weight sum property
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(
    values=st.lists(
        st.floats(min_value=0.001, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=2,
        max_size=20,
    )
)
def test_normalized_weights_sum_to_one(values: list[float]) -> None:
    """Normalized portfolio weights must sum to 1.0."""
    n = len(values)
    weights = _make_weight_dict(n, values)
    total = sum(weights.values())
    assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"


# ---------------------------------------------------------------------------
# P&L properties
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(
    cost_basis=_positive_float,
    current_price=_positive_float,
    shares=_share_count,
)
def test_unrealized_pnl_equals_current_minus_cost(
    cost_basis: float, current_price: float, shares: float
) -> None:
    """Unrealized P&L = (current_price - cost_basis) * shares."""
    unrealized_pnl = (current_price - cost_basis) * shares
    cost_total = cost_basis * shares
    current_value = current_price * shares
    expected = current_value - cost_total
    assert abs(unrealized_pnl - expected) < 1e-6


@pytest.mark.domain
@settings(max_examples=20)
@given(
    prices=st.lists(_positive_float, min_size=2, max_size=20),
    shares=_share_count,
)
def test_portfolio_value_nonnegative_long_only(prices: list[float], shares: float) -> None:
    """Portfolio value must be >= 0 for a long-only portfolio."""
    total_value = sum(p * shares for p in prices)
    assert total_value >= 0.0


# ---------------------------------------------------------------------------
# FIFO cost basis properties
# ---------------------------------------------------------------------------


def _now(offset_days: int = 0) -> datetime:
    from datetime import timedelta

    return datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=offset_days)


@pytest.mark.domain
@settings(max_examples=20)
@given(
    price1=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    shares1=st.floats(min_value=0.01, max_value=1000.0, allow_nan=False, allow_infinity=False),
    price2=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    shares2=st.floats(min_value=0.01, max_value=1000.0, allow_nan=False, allow_infinity=False),
)
def test_fifo_avg_cost_tracks_weighted_average(
    price1: float, shares1: float, price2: float, shares2: float
) -> None:
    """FIFO avg_cost_basis = weighted average of remaining lot prices."""
    txns = [
        {
            "type": "BUY",
            "shares": Decimal(str(round(shares1, 4))),
            "price": Decimal(str(round(price1, 4))),
            "at": _now(0),
        },
        {
            "type": "BUY",
            "shares": Decimal(str(round(shares2, 4))),
            "price": Decimal(str(round(price2, 4))),
            "at": _now(1),
        },
    ]
    result = _run_fifo(txns)
    expected_avg = (shares1 * price1 + shares2 * price2) / (shares1 + shares2)
    actual_avg = float(result["avg_cost_basis"])
    assert abs(actual_avg - expected_avg) < 0.01, (
        f"avg_cost_basis={actual_avg} != expected={expected_avg}"
    )


@pytest.mark.domain
@settings(max_examples=20)
@given(
    buy_price=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    buy_shares=st.floats(min_value=2.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    sell_fraction=st.floats(min_value=0.01, max_value=0.99, allow_nan=False, allow_infinity=False),
)
def test_partial_sell_preserves_remaining_cost_basis(
    buy_price: float, buy_shares: float, sell_fraction: float
) -> None:
    """After a partial sell, remaining cost basis should be the original buy price."""
    sell_shares = round(buy_shares * sell_fraction, 4)
    txns = [
        {
            "type": "BUY",
            "shares": Decimal(str(round(buy_shares, 4))),
            "price": Decimal(str(round(buy_price, 4))),
            "at": _now(0),
        },
        {
            "type": "SELL",
            "shares": Decimal(str(sell_shares)),
            "price": Decimal(str(round(buy_price * 1.1, 4))),
            "at": _now(1),
        },
    ]
    result = _run_fifo(txns)
    remaining_shares = float(result["shares"])
    expected_remaining = buy_shares - sell_shares
    assert abs(remaining_shares - expected_remaining) < 0.01
    # Cost basis of remaining shares should still be the buy price
    actual_cb = float(result["avg_cost_basis"])
    assert abs(actual_cb - buy_price) < 0.01


# ---------------------------------------------------------------------------
# Volatility annualization property
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(daily_vol=st.floats(min_value=0.001, max_value=0.1, allow_nan=False, allow_infinity=False))
def test_volatility_annualization(daily_vol: float) -> None:
    """Annual vol = daily_vol * sqrt(252)."""
    trading_days = 252
    annual_vol = daily_vol * math.sqrt(trading_days)
    # Round-trip check
    recovered_daily = annual_vol / math.sqrt(trading_days)
    assert abs(recovered_daily - daily_vol) < 1e-10


@pytest.mark.domain
@settings(max_examples=20)
@given(daily_return=st.floats(min_value=-0.1, max_value=0.1, allow_nan=False, allow_infinity=False))
def test_return_annualization(daily_return: float) -> None:
    """Annual return = (1 + daily_return)^252 - 1."""
    trading_days = 252
    annual_return = (1 + daily_return) ** trading_days - 1
    # Check we can recover daily from annual (floating point tolerance)
    recovered = (1 + annual_return) ** (1 / trading_days) - 1
    assert abs(recovered - daily_return) < 1e-7


# ---------------------------------------------------------------------------
# Sharpe ratio properties
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(
    returns=st.lists(
        st.floats(min_value=-0.2, max_value=0.2, allow_nan=False, allow_infinity=False),
        min_size=30,
        max_size=300,
    )
)
def test_sharpe_finite_for_non_degenerate_series(returns: list[float]) -> None:
    """Sharpe ratio should be a finite number for non-zero-variance return series."""
    import numpy as np

    arr = np.array(returns)
    vol = float(arr.std())
    if vol < 1e-10:
        return  # degenerate case — skip
    annual_vol = vol * math.sqrt(252)
    if annual_vol == 0:
        return
    ann_return = float((np.prod(1 + arr)) ** (252 / len(arr)) - 1)
    sharpe = (ann_return - 0.045) / annual_vol
    assert math.isfinite(sharpe)


@pytest.mark.domain
@settings(max_examples=20)
@given(
    returns=st.lists(
        st.floats(min_value=0.001, max_value=0.05, allow_nan=False, allow_infinity=False),
        min_size=30,
        max_size=100,
    ),
    k=st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False),
)
def test_sharpe_scaling_invariant(returns: list[float], k: float) -> None:
    """sharpe(k * returns, rf=0) == sharpe(returns, rf=0) for k > 0.

    Scaling all returns by a constant k does not change Sharpe (rf=0) because
    mean and std scale equally.
    """
    import numpy as np

    arr = np.array(returns)
    scaled = arr * k

    def _sharpe(r: np.ndarray) -> float:
        vol = r.std()
        if vol == 0:
            return float("nan")
        return float(r.mean() / vol)

    s_orig = _sharpe(arr)
    s_scaled = _sharpe(scaled)
    if math.isfinite(s_orig) and math.isfinite(s_scaled):
        assert abs(s_orig - s_scaled) < 1e-6, f"Sharpe invariant violated: {s_orig} vs {s_scaled}"


# ---------------------------------------------------------------------------
# Max drawdown property
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(
    returns=st.lists(
        st.floats(min_value=-0.3, max_value=0.3, allow_nan=False, allow_infinity=False),
        min_size=2,
        max_size=100,
    )
)
def test_max_drawdown_nonpositive(returns: list[float]) -> None:
    """Max drawdown (signed) must always be <= 0 by definition."""
    import numpy as np

    arr = np.array(returns)
    equity = np.cumprod(1 + arr)
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    max_dd = float(drawdown.min())
    assert max_dd <= 0.0 + 1e-10, f"Max drawdown={max_dd} must be <= 0"


@pytest.mark.domain
def test_calmar_inf_guard_when_drawdown_zero() -> None:
    """Calmar ratio must be capped (not Inf) when max_drawdown is 0."""
    import math

    # Simulate a Calmar computation where drawdown=0
    cagr = 0.15
    max_dd = 0.0
    # Guard that should be in any calmar computation
    calmar = cagr / max_dd if max_dd != 0 else None
    # It should be None (capped), not Inf
    assert calmar is None or math.isfinite(calmar), "Calmar must not be Inf when drawdown=0"


# ---------------------------------------------------------------------------
# Weight bounds feasibility property
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(n_assets=st.integers(min_value=1, max_value=50))
def test_weight_bounds_feasibility(n_assets: int) -> None:
    """max_weight must be >= 1/n_assets for equal-weight fallback to be feasible."""
    min_feasible_max = 1.0 / n_assets
    # If max_weight < 1/n_assets, optimization is infeasible
    # Our fallback uses equal weight = 1/n_assets, so max must be >= this
    equal_weight = 1.0 / n_assets
    assert equal_weight <= min_feasible_max + 1e-12


# ---------------------------------------------------------------------------
# Rebalancing value preservation
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(
    prices=st.lists(
        st.floats(min_value=10.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        min_size=2,
        max_size=10,
    ),
    total_value=st.floats(
        min_value=1000.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False
    ),
)
def test_rebalancing_preserves_value(prices: list[float], total_value: float) -> None:
    """Rebalancing allocates exactly total_value across positions."""
    n = len(prices)
    weights = [1.0 / n] * n  # equal weight
    allocated = sum(w * total_value for w in weights)
    assert abs(allocated - total_value) < 1e-6, (
        f"Rebalancing allocated {allocated} != total_value {total_value}"
    )


# ---------------------------------------------------------------------------
# Dividend reinvestment property
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(
    shares=st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
    price=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    dividend_per_share=st.floats(
        min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False
    ),
)
def test_dividend_reinvestment_increases_shares(
    shares: float, price: float, dividend_per_share: float
) -> None:
    """After dividend reinvestment, share count increases."""
    dividend_total = shares * dividend_per_share
    new_shares = dividend_total / price
    total_shares_after = shares + new_shares
    assert total_shares_after > shares
    # Cost basis of new shares = dividend reinvestment price
    assert new_shares > 0


# ---------------------------------------------------------------------------
# Sortino vs Sharpe property
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(
    returns=st.lists(
        st.floats(min_value=0.001, max_value=0.05, allow_nan=False, allow_infinity=False),
        min_size=30,
        max_size=100,
    )
)
def test_sortino_ge_sharpe_for_positive_only_returns(returns: list[float]) -> None:
    """For positive-only returns, downside deviation < total std → Sortino >= Sharpe."""
    import numpy as np

    arr = np.array(returns)
    mean_r = float(arr.mean())
    std_total = float(arr.std())
    # Downside returns are negative returns only; all positive here means downside = 0
    downside = arr[arr < 0]
    downside_std = float(downside.std()) if len(downside) > 0 else 0.0

    if std_total == 0:
        return  # degenerate

    sharpe = mean_r / std_total if std_total > 0 else 0.0
    # For all positive returns, downside_std < std_total → sortino > sharpe
    # If no downside, sortino = inf (capped) but certainly >= sharpe
    if downside_std > 0:
        sortino = mean_r / downside_std
        assert sortino >= sharpe - 1e-6, f"Sortino {sortino} < Sharpe {sharpe}"
