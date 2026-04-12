"""Portfolio FIFO engine — cost basis, positions, transactions."""

from __future__ import annotations

import logging
import uuid
from collections import deque
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.portfolio import Position, Transaction
from backend.models.price import StockPrice
from backend.models.stock import Stock
from backend.schemas.portfolio import PositionResponse
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


# ---------------------------------------------------------------------------
# DB helpers — transactions, positions, FIFO recompute
# ---------------------------------------------------------------------------


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
