"""Build user context for the Agent V2 planner.

Queries portfolio, positions, preferences, and watchlist so the planner
can personalize its tool plan (e.g., include portfolio exposure for held stocks).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def build_user_context(user_id: uuid.UUID, db: AsyncSession) -> dict[str, Any]:
    """Build a context dict describing the user's portfolio state.

    Args:
        user_id: The authenticated user's UUID.
        db: Async database session.

    Returns:
        Dict with keys: portfolio_id, positions, sector_allocation,
        preferences, watchlist. Empty/default values for new users.
    """
    from backend.models.stock import Watchlist
    from backend.models.user import UserPreference
    from backend.tools.portfolio import get_or_create_portfolio, get_positions_with_pnl

    context: dict[str, Any] = {
        "user_id": str(user_id),
        "portfolio_id": None,
        "positions": [],
        "held_tickers": [],
        "sector_allocation": {},
        "preferences": {},
        "watchlist": [],
    }

    try:
        # Portfolio + positions
        portfolio = await get_or_create_portfolio(user_id, db)
        context["portfolio_id"] = str(portfolio.id)

        positions = await get_positions_with_pnl(portfolio.id, db)
        context["positions"] = [
            {
                "ticker": p.ticker,
                "shares": float(p.shares),
                "avg_cost": float(p.avg_cost_basis),
                "allocation_pct": p.allocation_pct or 0.0,
            }
            for p in positions
        ]
        context["held_tickers"] = [p.ticker for p in positions]

        # Sector allocation from positions
        sector_map: dict[str, float] = {}
        for p in positions:
            sector = getattr(p, "sector", None) or "Unknown"
            sector_map[sector] = sector_map.get(sector, 0.0) + (p.allocation_pct or 0.0)
        context["sector_allocation"] = sector_map

    except Exception:
        logger.warning("user_context_portfolio_failed", extra={"user_id": str(user_id)})

    try:
        # User preferences
        result = await db.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        pref = result.scalar_one_or_none()
        if pref is not None:
            context["preferences"] = {
                "max_position_pct": pref.max_position_pct,
                "max_sector_pct": pref.max_sector_pct,
                "default_stop_loss_pct": pref.default_stop_loss_pct,
            }
    except Exception:
        logger.warning("user_context_preferences_failed", extra={"user_id": str(user_id)})

    try:
        # Watchlist
        result = await db.execute(
            select(Watchlist.ticker).where(Watchlist.user_id == user_id)
        )
        context["watchlist"] = [row[0] for row in result.all()]
    except Exception:
        logger.warning("user_context_watchlist_failed", extra={"user_id": str(user_id)})

    return context
