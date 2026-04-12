"""Portfolio analytics — QuantStats, rebalancing, optimization."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.portfolio import Portfolio, PortfolioSnapshot, RebalancingSuggestion
from backend.models.price import StockPrice
from backend.services.portfolio.fifo import get_positions_with_pnl

logger = logging.getLogger(__name__)

VALID_STRATEGIES = ("min_volatility", "max_sharpe", "risk_parity")


async def compute_quantstats_portfolio(
    portfolio_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """Compute portfolio-level QuantStats metrics from snapshot history.

    Args:
        portfolio_id: The portfolio to analyze.
        db: Async database session.

    Returns:
        Dict with sharpe, sortino, max_drawdown, max_drawdown_duration,
        calmar, alpha, beta, var_95, cagr, data_days. All None when < 30 days.
    """
    import pandas as pd
    import quantstats as qs

    null_result = {
        "sharpe": None,
        "sortino": None,
        "max_drawdown": None,
        "max_drawdown_duration": None,
        "calmar": None,
        "alpha": None,
        "beta": None,
        "var_95": None,
        "cagr": None,
        "data_days": 0,
    }

    # Fetch portfolio snapshots ordered by date
    snap_result = await db.execute(
        select(PortfolioSnapshot.snapshot_date, PortfolioSnapshot.total_value)
        .where(PortfolioSnapshot.portfolio_id == portfolio_id)
        .order_by(PortfolioSnapshot.snapshot_date.asc())
    )
    rows = snap_result.all()

    if len(rows) < 2:
        null_result["data_days"] = len(rows)
        return null_result

    dates = [r.snapshot_date for r in rows]
    values = [float(r.total_value) for r in rows]
    # Normalize to tz-naive for QuantStats compatibility
    idx = pd.DatetimeIndex(dates)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    value_series = pd.Series(values, index=idx)
    returns = value_series.pct_change().dropna()

    null_result["data_days"] = len(returns)

    if len(returns) < 30:
        return null_result

    from backend.services.signals import DEFAULT_RISK_FREE_RATE

    rf = DEFAULT_RISK_FREE_RATE

    try:
        import math

        def _safe_round(val: float, digits: int = 4) -> float | None:
            """Round a float, returning None for NaN/Inf."""
            f = float(val)
            return round(f, digits) if math.isfinite(f) else None

        metrics: dict = {
            "sharpe": _safe_round(qs.stats.sharpe(returns, rf=rf)),
            "sortino": _safe_round(qs.stats.sortino(returns, rf=rf)),
            "max_drawdown": _safe_round(abs(qs.stats.max_drawdown(returns))),
            "max_drawdown_duration": None,
            "calmar": None,
            "alpha": None,
            "beta": None,
            "var_95": _safe_round(abs(qs.stats.var(returns, confidence=0.95))),
            "cagr": _safe_round(qs.stats.cagr(returns)),
            "data_days": len(returns),
        }

        # Calmar can be inf when max_drawdown is 0 — isolate it
        try:
            calmar_val = float(qs.stats.calmar(returns))
            metrics["calmar"] = round(calmar_val, 4) if math.isfinite(calmar_val) else None
        except (ValueError, ZeroDivisionError, ArithmeticError):
            pass

        # Max drawdown duration
        try:
            dd_details = qs.stats.drawdown_details(returns)
            if dd_details is not None and not dd_details.empty and "days" in dd_details.columns:
                metrics["max_drawdown_duration"] = int(dd_details["days"].max())
        except (ValueError, TypeError, AttributeError):
            pass

        # Alpha/beta from SPY benchmark
        spy_result = await db.execute(
            select(StockPrice.time, StockPrice.adj_close)
            .where(
                StockPrice.ticker == "SPY",
                StockPrice.time >= dates[0],
                StockPrice.time <= dates[-1],
            )
            .order_by(StockPrice.time.asc())
        )
        spy_rows = spy_result.all()

        if spy_rows:
            spy_dates = [r.time for r in spy_rows]
            spy_prices = [float(r.adj_close) for r in spy_rows]
            spy_idx = pd.DatetimeIndex(spy_dates)
            if spy_idx.tz is not None:
                spy_idx = spy_idx.tz_localize(None)
            spy_series = pd.Series(spy_prices, index=spy_idx)
            spy_returns = spy_series.pct_change().dropna()
            common = returns.index.intersection(spy_returns.index)
            if len(common) >= 30:
                greeks = qs.stats.greeks(returns[common], spy_returns[common])
                greeks_dict = greeks.to_dict() if hasattr(greeks, "to_dict") else {}
                metrics["alpha"] = round(float(greeks_dict.get("alpha", 0.0)), 4)
                metrics["beta"] = round(float(greeks_dict.get("beta", 0.0)), 4)

        return metrics
    except Exception:
        logger.warning("QuantStats portfolio computation failed", exc_info=True)
        return null_result


async def compute_rebalancing(
    portfolio_id: uuid.UUID,
    strategy: str,
    db: AsyncSession,
    max_position_pct: float = 5.0,
) -> list[dict]:
    """Compute optimized rebalancing suggestions using PyPortfolioOpt.

    Args:
        portfolio_id: The portfolio to rebalance.
        strategy: One of min_volatility, max_sharpe, risk_parity.
        db: Async database session.

    Returns:
        List of dicts with ticker, target_weight, current_weight,
        delta_shares, delta_dollars, action, strategy.
        Falls back to equal-weight on insufficient data or solver failure.
    """
    import pandas as pd

    # Get open positions
    positions = await get_positions_with_pnl(portfolio_id, db)
    if not positions or len(positions) < 2:
        return _equal_weight_fallback(positions, strategy)

    tickers = [p.ticker for p in positions]
    total_value = sum(float(p.market_value or 0) for p in positions)
    if total_value <= 0:
        return []

    # Fetch 1y daily closes for all position tickers
    one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)
    result = await db.execute(
        select(StockPrice.time, StockPrice.ticker, StockPrice.close)
        .where(
            StockPrice.ticker.in_(tickers),
            StockPrice.time >= one_year_ago,
        )
        .order_by(StockPrice.time.asc())
    )
    rows = result.all()

    if not rows:
        return _equal_weight_fallback(positions, strategy)

    # Build price matrix (date × ticker)
    data: dict[str, dict] = {}
    for r in rows:
        dt = r.time
        if dt not in data:
            data[dt] = {}
        data[dt][r.ticker] = float(r.close)

    prices_df = pd.DataFrame.from_dict(data, orient="index").sort_index()
    prices_df = prices_df.dropna(axis=1, how="all").dropna()

    if len(prices_df) < 30 or len(prices_df.columns) < 2:
        return _equal_weight_fallback(positions, strategy)

    try:
        weights = _optimize(prices_df, strategy, max_position_pct=max_position_pct)
    except Exception:
        logger.warning(
            "PyPortfolioOpt optimization failed for strategy=%s, falling back",
            strategy,
            exc_info=True,
        )
        return _equal_weight_fallback(positions, strategy)

    # Compute deltas
    current_weights = {}
    shares_map = {}
    price_map = {}
    for p in positions:
        mv = float(p.market_value or 0)
        current_weights[p.ticker] = mv / total_value if total_value > 0 else 0
        shares_map[p.ticker] = float(p.shares)
        price_map[p.ticker] = mv / float(p.shares) if float(p.shares) > 0 else 0

    suggestions = []
    for ticker, target_w in weights.items():
        current_w = current_weights.get(ticker, 0)
        delta_dollars = (target_w - current_w) * total_value
        price = price_map.get(ticker, 0)
        delta_shares = delta_dollars / price if price > 0 else 0

        if abs(delta_dollars) < 1.0:
            action = "HOLD"
        elif delta_dollars > 0:
            action = "BUY_MORE"
        else:
            action = "REDUCE"

        suggestions.append(
            {
                "ticker": ticker,
                "strategy": strategy,
                "target_weight": round(target_w, 4),
                "current_weight": round(current_w, 4),
                "delta_shares": round(delta_shares, 4),
                "delta_dollars": round(delta_dollars, 2),
                "action": action,
            }
        )

    return suggestions


def _optimize(
    prices_df: "pd.DataFrame",
    strategy: str,
    max_position_pct: float = 5.0,
) -> dict[str, float]:
    """Run PyPortfolioOpt optimization for the given strategy.

    Args:
        prices_df: DataFrame of daily prices (date × ticker).
        strategy: One of min_volatility, max_sharpe, risk_parity.
        max_position_pct: Maximum weight per position (from UserPreference).

    Returns:
        Dict mapping ticker → optimal weight (0-1).
    """
    from pypfopt import (
        EfficientFrontier,
        HRPOpt,
        expected_returns,
        risk_models,
    )

    n_assets = len(prices_df.columns)
    # Ensure cap is at least 1/n so the problem is feasible
    max_w = max(max_position_pct / 100.0, 1.0 / n_assets)

    if strategy == "risk_parity":
        returns_df = prices_df.pct_change().dropna()
        hrp = HRPOpt(returns_df)
        hrp.optimize()
        return hrp.clean_weights(cutoff=0.001)

    mu = expected_returns.mean_historical_return(prices_df)
    s = risk_models.sample_cov(prices_df)
    ef = EfficientFrontier(mu, s, weight_bounds=(0, max_w))

    if strategy == "max_sharpe":
        ef.max_sharpe()
    else:  # min_volatility (default)
        ef.min_volatility()

    return ef.clean_weights(cutoff=0.001)


def _equal_weight_fallback(
    positions: list,
    strategy: str,
) -> list[dict]:
    """Fall back to equal-weight when optimization is not possible."""
    if not positions:
        return []

    n = len(positions)
    target_w = 1.0 / n
    total_value = sum(float(p.market_value or 0) for p in positions)

    suggestions = []
    for p in positions:
        mv = float(p.market_value or 0)
        current_w = mv / total_value if total_value > 0 else 0
        delta_dollars = (target_w - current_w) * total_value
        price = mv / float(p.shares) if float(p.shares) > 0 else 0
        delta_shares = delta_dollars / price if price > 0 else 0

        if abs(delta_dollars) < 1.0:
            action = "HOLD"
        elif delta_dollars > 0:
            action = "BUY_MORE"
        else:
            action = "REDUCE"

        suggestions.append(
            {
                "ticker": p.ticker,
                "strategy": strategy,
                "target_weight": round(target_w, 4),
                "current_weight": round(current_w, 4),
                "delta_shares": round(delta_shares, 4),
                "delta_dollars": round(delta_dollars, 2),
                "action": action,
            }
        )

    return suggestions


async def materialize_rebalancing(
    portfolio_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """Compute and store rebalancing suggestions for a portfolio.

    Reads the user's preferred strategy from UserPreference,
    computes suggestions, then replaces existing rows for this
    portfolio+strategy combination.

    Args:
        portfolio_id: The portfolio to rebalance.
        db: Async database session.
    """
    from backend.models.user import UserPreference

    # Get portfolio's user and their preference
    port_result = await db.execute(select(Portfolio.user_id).where(Portfolio.id == portfolio_id))
    user_id = port_result.scalar_one_or_none()
    if user_id is None:
        return

    pref_result = await db.execute(select(UserPreference).where(UserPreference.user_id == user_id))
    pref = pref_result.scalar_one_or_none()
    strategy = (
        pref.rebalancing_strategy
        if pref and pref.rebalancing_strategy in VALID_STRATEGIES
        else "min_volatility"
    )

    max_pos = pref.max_position_pct if pref else 5.0
    suggestions = await compute_rebalancing(
        portfolio_id,
        strategy,
        db,
        max_position_pct=max_pos,
    )
    if not suggestions:
        return

    # Delete existing suggestions for this portfolio+strategy
    from sqlalchemy import delete

    await db.execute(
        delete(RebalancingSuggestion).where(
            RebalancingSuggestion.portfolio_id == portfolio_id,
            RebalancingSuggestion.strategy == strategy,
        )
    )

    # Bulk insert new suggestions
    now = datetime.now(timezone.utc)
    for s in suggestions:
        db.add(
            RebalancingSuggestion(
                portfolio_id=portfolio_id,
                ticker=s["ticker"],
                strategy=s["strategy"],
                target_weight=s["target_weight"],
                current_weight=s["current_weight"],
                delta_shares=s["delta_shares"],
                delta_dollars=s["delta_dollars"],
                action=s["action"],
                computed_at=now,
            )
        )

    await db.commit()
    logger.info(
        "Materialized %d rebalancing suggestions for portfolio %s (strategy=%s)",
        len(suggestions),
        portfolio_id,
        strategy,
    )
