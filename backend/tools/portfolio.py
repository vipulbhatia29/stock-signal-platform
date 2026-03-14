"""Portfolio tool: FIFO cost basis, P&L, summary, position recompute."""

from __future__ import annotations

import logging
import uuid
from collections import deque
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.portfolio import Portfolio, Position, Transaction
from backend.models.price import StockPrice
from backend.models.stock import Stock
from backend.schemas.portfolio import PortfolioSummaryResponse, PositionResponse, SectorAllocation

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
) -> list[dict]:
    """Group positions by sector, compute %, flag concentration.

    Args:
        positions: List of dicts with keys: ticker, sector (str|None), market_value (float).
        total_value: Total portfolio market value (denominator for pct).

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
            {"sector": sector, "market_value": value, "pct": round(pct, 2), "over_limit": pct > 30}
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

    pnl_rows = []
    total_value = 0.0
    for pos in positions:
        price_result = await db.execute(
            select(StockPrice.adj_close)
            .where(StockPrice.ticker == pos.ticker)
            .order_by(StockPrice.time.desc())
            .limit(1)
        )
        current_price_raw = price_result.scalar_one_or_none()
        current_price = float(current_price_raw) if current_price_raw is not None else None

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
            )
        )
    return responses


async def get_portfolio_summary(
    portfolio_id: uuid.UUID, db: AsyncSession
) -> PortfolioSummaryResponse:
    """Aggregate KPI totals and sector allocation for the portfolio.

    Args:
        portfolio_id: The portfolio's UUID.
        db: Async SQLAlchemy session.

    Returns:
        PortfolioSummaryResponse with totals and sector breakdown.
    """
    positions_with_pnl = await get_positions_with_pnl(portfolio_id, db)

    total_value = sum(p.market_value or 0 for p in positions_with_pnl)
    total_cost = sum(p.shares * p.avg_cost_basis for p in positions_with_pnl)
    unrealized_pnl = total_value - total_cost
    unrealized_pnl_pct = (unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0

    # Fetch sector for each ticker
    tickers = [p.ticker for p in positions_with_pnl]
    sector_map: dict[str, str | None] = {}
    if tickers:
        result = await db.execute(
            select(Stock.ticker, Stock.sector).where(Stock.ticker.in_(tickers))
        )
        sector_map = {row.ticker: row.sector for row in result}

    pos_dicts = [
        {
            "ticker": p.ticker,
            "sector": sector_map.get(p.ticker),
            "market_value": p.market_value or 0,
        }
        for p in positions_with_pnl
    ]
    sector_data = _group_sectors(pos_dicts, total_value)
    sectors = [SectorAllocation(**s) for s in sector_data]

    return PortfolioSummaryResponse(
        total_value=total_value,
        total_cost_basis=total_cost,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=unrealized_pnl_pct,
        position_count=len(positions_with_pnl),
        sectors=sectors,
    )
