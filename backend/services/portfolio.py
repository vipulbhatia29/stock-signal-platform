"""Portfolio service — FIFO cost basis, P&L, positions, snapshots, transactions.

Extracted from tools/portfolio.py and routers/portfolio.py so that routers,
tasks, and tool classes all share a single source of truth for DB-touching
business logic.  Every function preserves its original signature so existing
call-sites continue to work after re-export.
"""

from __future__ import annotations

import logging
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.portfolio import (
    Portfolio,
    PortfolioSnapshot,
    Position,
    RebalancingSuggestion,
    Transaction,
)
from backend.models.price import StockPrice
from backend.models.stock import Stock
from backend.schemas.portfolio import PortfolioSummaryResponse, PositionResponse, SectorAllocation
from backend.services.exceptions import PortfolioNotFoundError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure FIFO engine (no DB — testable without async)
# ---------------------------------------------------------------------------


def _run_fifo(
    transactions: list[dict],
) -> dict:
    """Run FIFO walk over a list of transaction dicts.

    Args:
        transactions: List of dicts with keys: type ("BUY"|"SELL"),
            shares (Decimal), price (Decimal), at (datetime).
            Order does not matter — sorted internally by `at`.

    Returns:
        Dict with keys: shares (Decimal), avg_cost_basis (Decimal),
        closed_at (datetime | None).

    Raises:
        ValueError: If any SELL exceeds available BUY lots.
    """
    sorted_txns = sorted(transactions, key=lambda t: t["at"])
    lot_queue: deque[tuple[Decimal, Decimal]] = deque()  # (shares, price)
    last_sell_at: datetime | None = None

    for txn in sorted_txns:
        if txn["type"] == "BUY":
            lot_queue.append((txn["shares"], txn["price"]))
        else:  # SELL
            remaining_to_sell = txn["shares"]
            while remaining_to_sell > 0:
                if not lot_queue:
                    raise ValueError(
                        f"Insufficient shares: tried to sell {txn['shares']} "
                        f"but ran out of BUY lots"
                    )
                lot_shares, lot_price = lot_queue[0]
                if lot_shares <= remaining_to_sell:
                    remaining_to_sell -= lot_shares
                    lot_queue.popleft()
                else:
                    lot_queue[0] = (lot_shares - remaining_to_sell, lot_price)
                    remaining_to_sell = Decimal("0")
            last_sell_at = txn["at"]

    total_shares = sum(s for s, _ in lot_queue)
    if total_shares == 0:
        return {"shares": Decimal("0"), "avg_cost_basis": Decimal("0"), "closed_at": last_sell_at}

    total_cost = sum(s * p for s, p in lot_queue)
    avg_cost = total_cost / total_shares
    return {"shares": total_shares, "avg_cost_basis": avg_cost, "closed_at": None}


def _group_sectors(
    positions: list[dict],
    total_value: float,
    max_sector_pct: float = 30.0,
) -> list[dict]:
    """Group positions by sector, compute %, flag concentration.

    Args:
        positions: List of dicts with keys: ticker, sector (str|None), market_value (float).
        total_value: Total portfolio market value (denominator for pct).
        max_sector_pct: User's sector concentration limit (default 30%).

    Returns:
        List of dicts: sector, market_value, pct, over_limit.
    """
    buckets: dict[str, float] = {}
    for pos in positions:
        sector = pos["sector"] or "Unknown"
        buckets[sector] = buckets.get(sector, 0.0) + pos["market_value"]

    result = []
    for sector, value in sorted(buckets.items(), key=lambda x: -x[1]):
        pct = (value / total_value * 100) if total_value > 0 else 0.0
        result.append(
            {
                "sector": sector,
                "market_value": value,
                "pct": round(pct, 2),
                "over_limit": pct > max_sector_pct,
            }
        )
    return result


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def get_or_create_portfolio(user_id: uuid.UUID, db: AsyncSession) -> Portfolio:
    """Get the user's portfolio, creating one if it doesn't exist.

    Args:
        user_id: The authenticated user's ID.
        db: Async SQLAlchemy session.

    Returns:
        The user's Portfolio row.
    """
    result = await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
    portfolio = result.scalar_one_or_none()
    if portfolio is None:
        portfolio = Portfolio(user_id=user_id, name="My Portfolio")
        db.add(portfolio)
        await db.flush()
        logger.info("Created portfolio for user %s", user_id)
    return portfolio


async def _get_transactions_for_ticker(
    portfolio_id: uuid.UUID, ticker: str, db: AsyncSession
) -> list[dict]:
    """Load all transactions for a ticker as plain dicts for FIFO walk.

    Args:
        portfolio_id: The portfolio's UUID.
        ticker: The stock ticker.
        db: Async SQLAlchemy session.

    Returns:
        List of transaction dicts suitable for _run_fifo().
    """
    result = await db.execute(
        select(Transaction)
        .where(Transaction.portfolio_id == portfolio_id, Transaction.ticker == ticker)
        .order_by(Transaction.transacted_at)
    )
    txns = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "type": t.transaction_type,
            "shares": t.shares,
            "price": t.price_per_share,
            "at": t.transacted_at,
        }
        for t in txns
    ]


async def recompute_position(portfolio_id: uuid.UUID, ticker: str, db: AsyncSession) -> None:
    """Run FIFO walk and upsert the position row for one ticker.

    Args:
        portfolio_id: The portfolio's UUID.
        ticker: The stock ticker to recompute.
        db: Async SQLAlchemy session.
    """
    txn_dicts = await _get_transactions_for_ticker(portfolio_id, ticker, db)
    if not txn_dicts:
        # All transactions deleted — remove position row if it exists
        result = await db.execute(
            select(Position).where(Position.portfolio_id == portfolio_id, Position.ticker == ticker)
        )
        pos = result.scalar_one_or_none()
        if pos:
            await db.delete(pos)
        return

    fifo = _run_fifo(txn_dicts)
    opened_at = min(t["at"] for t in txn_dicts if t["type"] == "BUY")

    # Check if position row already exists (to preserve opened_at)
    result = await db.execute(
        select(Position).where(Position.portfolio_id == portfolio_id, Position.ticker == ticker)
    )
    existing = result.scalar_one_or_none()

    if existing is None:
        pos = Position(
            portfolio_id=portfolio_id,
            ticker=ticker,
            shares=fifo["shares"],
            avg_cost_basis=fifo["avg_cost_basis"],
            opened_at=opened_at,
            closed_at=fifo["closed_at"],
        )
        db.add(pos)
    else:
        # Update but NEVER overwrite opened_at
        existing.shares = fifo["shares"]
        existing.avg_cost_basis = fifo["avg_cost_basis"]
        existing.closed_at = fifo["closed_at"]

    logger.info("Recomputed position for %s: shares=%s", ticker, fifo["shares"])


async def get_positions_with_pnl(
    portfolio_id: uuid.UUID, db: AsyncSession
) -> list[PositionResponse]:
    """Get all open positions with current price and unrealized P&L.

    Args:
        portfolio_id: The portfolio's UUID.
        db: Async SQLAlchemy session.

    Returns:
        List of PositionResponse with live P&L fields.
    """
    result = await db.execute(
        select(Position).where(
            Position.portfolio_id == portfolio_id,
            Position.closed_at.is_(None),
        )
    )
    positions = result.scalars().all()

    # Bulk-fetch sector for all held tickers
    tickers = [pos.ticker for pos in positions]
    sector_map: dict[str, str | None] = {}
    if tickers:
        sector_result = await db.execute(
            select(Stock.ticker, Stock.sector).where(Stock.ticker.in_(tickers))
        )
        sector_map = {row.ticker: row.sector for row in sector_result}

    # Batch-fetch latest prices for all position tickers (fixes N+1 query)
    price_map: dict[str, float] = {}
    if tickers:
        price_result = await db.execute(
            select(StockPrice.ticker, StockPrice.adj_close)
            .distinct(StockPrice.ticker)
            .where(StockPrice.ticker.in_(tickers))
            .order_by(StockPrice.ticker, StockPrice.time.desc())
        )
        price_map = {row.ticker: float(row.adj_close) for row in price_result}

    pnl_rows = []
    total_value = 0.0
    for pos in positions:
        current_price = price_map.get(pos.ticker)

        shares = float(pos.shares)
        avg_cost = float(pos.avg_cost_basis)
        market_value = shares * current_price if current_price is not None else None
        if market_value:
            total_value += market_value

        pnl_rows.append(
            {
                "ticker": pos.ticker,
                "shares": shares,
                "avg_cost_basis": avg_cost,
                "current_price": current_price,
                "market_value": market_value,
                "sector": sector_map.get(pos.ticker),
                "_cost_basis_total": shares * avg_cost,
            }
        )

    responses = []
    for row in pnl_rows:
        mv = row["market_value"]
        cost = row["_cost_basis_total"]
        unrealized_pnl = (mv - cost) if mv is not None else None
        unrealized_pnl_pct = (
            (unrealized_pnl / cost * 100) if (unrealized_pnl is not None and cost > 0) else None
        )
        allocation_pct = (mv / total_value * 100) if (mv is not None and total_value > 0) else None
        responses.append(
            PositionResponse(
                ticker=row["ticker"],
                shares=row["shares"],
                avg_cost_basis=row["avg_cost_basis"],
                current_price=row["current_price"],
                market_value=mv,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=unrealized_pnl_pct,
                allocation_pct=allocation_pct,
                sector=row["sector"],
            )
        )
    return responses


async def get_portfolio_summary(
    portfolio_id: uuid.UUID,
    db: AsyncSession,
    max_sector_pct: float = 30.0,
) -> PortfolioSummaryResponse:
    """Aggregate KPI totals and sector allocation for the portfolio.

    Args:
        portfolio_id: The portfolio's UUID.
        db: Async SQLAlchemy session.
        max_sector_pct: User's sector concentration limit for over_limit flag.

    Returns:
        PortfolioSummaryResponse with totals and sector breakdown.
    """
    positions_with_pnl = await get_positions_with_pnl(portfolio_id, db)

    total_value = sum(p.market_value or 0 for p in positions_with_pnl)
    total_cost = sum(p.shares * p.avg_cost_basis for p in positions_with_pnl)
    unrealized_pnl = total_value - total_cost
    unrealized_pnl_pct = (unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0

    # Sector data is already on positions (populated by get_positions_with_pnl)
    pos_dicts = [
        {
            "ticker": p.ticker,
            "sector": p.sector,
            "market_value": p.market_value or 0,
        }
        for p in positions_with_pnl
    ]
    sector_data = _group_sectors(pos_dicts, total_value, max_sector_pct=max_sector_pct)
    sectors = [SectorAllocation(**s) for s in sector_data]

    return PortfolioSummaryResponse(
        portfolio_id=str(portfolio_id),
        total_value=total_value,
        total_cost_basis=total_cost,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=unrealized_pnl_pct,
        position_count=len(positions_with_pnl),
        sectors=sectors,
    )


# ---------------------------------------------------------------------------
# Portfolio snapshot (daily value history)
# ---------------------------------------------------------------------------


async def snapshot_portfolio_value(
    portfolio_id: uuid.UUID, db: AsyncSession
) -> PortfolioSnapshot | None:
    """Capture the current portfolio value as a daily snapshot.

    Computes the portfolio summary and inserts a PortfolioSnapshot row.
    Skips if the portfolio has no open positions (nothing to snapshot).
    Uses an upsert (ON CONFLICT ... DO UPDATE) so re-running the same day
    overwrites stale values instead of failing on the unique constraint.

    Args:
        portfolio_id: The portfolio's UUID.
        db: Async SQLAlchemy session.

    Returns:
        The inserted PortfolioSnapshot, or None if no positions.
    """
    summary = await get_portfolio_summary(portfolio_id, db)
    if summary.position_count == 0:
        logger.info("Portfolio %s has no positions — skipping snapshot", portfolio_id)
        return None

    now = datetime.now(timezone.utc)

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(PortfolioSnapshot).values(
        portfolio_id=portfolio_id,
        snapshot_date=now,
        total_value=Decimal(str(round(summary.total_value, 2))),
        total_cost_basis=Decimal(str(round(summary.total_cost_basis, 2))),
        unrealized_pnl=Decimal(str(round(summary.unrealized_pnl, 2))),
        position_count=summary.position_count,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="portfolio_snapshots_pkey",
        set_={
            "total_value": stmt.excluded.total_value,
            "total_cost_basis": stmt.excluded.total_cost_basis,
            "unrealized_pnl": stmt.excluded.unrealized_pnl,
            "position_count": stmt.excluded.position_count,
        },
    )
    await db.execute(stmt)
    await db.commit()

    logger.info(
        "Snapshot captured for portfolio %s: value=%.2f pnl=%.2f",
        portfolio_id,
        summary.total_value,
        summary.unrealized_pnl,
    )

    # Return the row we just inserted/updated
    result = await db.execute(
        select(PortfolioSnapshot).where(
            PortfolioSnapshot.portfolio_id == portfolio_id,
            PortfolioSnapshot.snapshot_date == now,
        )
    )
    return result.scalar_one_or_none()


async def get_portfolio_history(
    portfolio_id: uuid.UUID,
    db: AsyncSession,
    days: int = 365,
) -> list[PortfolioSnapshot]:
    """Fetch the portfolio value history over the last N days.

    Args:
        portfolio_id: The portfolio's UUID.
        db: Async SQLAlchemy session.
        days: Number of days of history to return (default 365).

    Returns:
        List of PortfolioSnapshot rows, ordered by snapshot_date ascending.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(PortfolioSnapshot)
        .where(
            PortfolioSnapshot.portfolio_id == portfolio_id,
            PortfolioSnapshot.snapshot_date >= cutoff,
        )
        .order_by(PortfolioSnapshot.snapshot_date.asc())
    )
    return list(result.scalars().all())


async def get_all_portfolio_ids(db: AsyncSession) -> list[uuid.UUID]:
    """Return all portfolio IDs that have at least one open position.

    Args:
        db: Async SQLAlchemy session.

    Returns:
        List of portfolio UUIDs with open positions.
    """
    result = await db.execute(select(Position.portfolio_id).where(Position.shares > 0).distinct())
    return [row[0] for row in result.all()]


# ---------------------------------------------------------------------------
# Transaction CRUD (extracted from routers/portfolio.py inline DB queries)
# ---------------------------------------------------------------------------


async def list_transactions(
    portfolio_id: uuid.UUID,
    db: AsyncSession,
    *,
    ticker: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Transaction], int]:
    """Return paginated transactions for a portfolio.

    Args:
        portfolio_id: The portfolio's UUID.
        db: Async SQLAlchemy session.
        ticker: Optional ticker filter.
        limit: Page size.
        offset: Offset for pagination.

    Returns:
        Tuple of (list of Transaction rows, total count).
    """
    base = select(Transaction).where(Transaction.portfolio_id == portfolio_id)
    if ticker:
        base = base.where(Transaction.ticker == ticker.upper().strip())

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar_one()

    stmt = base.order_by(Transaction.transacted_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    txns = list(result.scalars().all())

    return txns, total


async def delete_transaction(
    portfolio_id: uuid.UUID,
    transaction_id: uuid.UUID,
    db: AsyncSession,
) -> str:
    """Delete a transaction after validating FIFO consistency.

    Args:
        portfolio_id: The portfolio's UUID.
        transaction_id: The transaction to delete.
        db: Async SQLAlchemy session.

    Returns:
        The ticker of the deleted transaction (for recompute).

    Raises:
        PortfolioNotFoundError: If the transaction is not found in this portfolio.
        ValueError: If removing the transaction would break FIFO consistency.
    """
    result = await db.execute(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.portfolio_id == portfolio_id,
        )
    )
    txn = result.scalar_one_or_none()
    if txn is None:
        raise PortfolioNotFoundError(str(transaction_id))

    ticker = txn.ticker

    # Pre-delete simulation: run FIFO without this transaction
    all_txns = await _get_transactions_for_ticker(portfolio_id, ticker, db)
    remaining = [t for t in all_txns if t["id"] != str(txn.id)]
    _run_fifo(remaining)  # raises ValueError if FIFO breaks

    await db.delete(txn)
    await recompute_position(portfolio_id, ticker, db)

    return ticker


async def get_health_history(
    portfolio_id: uuid.UUID,
    db: AsyncSession,
    days: int = 90,
) -> list:
    """Get portfolio health score history for trend chart.

    Args:
        portfolio_id: The portfolio's UUID.
        db: Async SQLAlchemy session.
        days: Number of days of history (default 90).

    Returns:
        List of PortfolioHealthSnapshot rows ordered by date ascending.
    """
    from backend.models.portfolio_health import PortfolioHealthSnapshot

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(PortfolioHealthSnapshot)
        .where(
            PortfolioHealthSnapshot.portfolio_id == portfolio_id,
            PortfolioHealthSnapshot.snapshot_date >= cutoff,
        )
        .order_by(PortfolioHealthSnapshot.snapshot_date.asc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# QuantStats portfolio-level metrics
# ---------------------------------------------------------------------------


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
        except Exception:
            pass

        # Max drawdown duration
        try:
            dd_details = qs.stats.drawdown_details(returns)
            if dd_details is not None and not dd_details.empty and "days" in dd_details.columns:
                metrics["max_drawdown_duration"] = int(dd_details["days"].max())
        except Exception:
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


# ---------------------------------------------------------------------------
# PyPortfolioOpt rebalancing
# ---------------------------------------------------------------------------

VALID_STRATEGIES = ("min_volatility", "max_sharpe", "risk_parity")


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
