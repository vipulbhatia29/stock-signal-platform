"""Portfolio core — CRUD, snapshots, history, summary."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.portfolio import Portfolio, PortfolioSnapshot, Position
from backend.schemas.portfolio import PortfolioSummaryResponse, SectorAllocation
from backend.services.portfolio.fifo import get_positions_with_pnl

logger = logging.getLogger(__name__)


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
