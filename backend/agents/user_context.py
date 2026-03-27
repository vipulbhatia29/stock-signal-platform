"""Build user context for the Agent V2 planner.

Queries portfolio, positions, preferences, and watchlist so the planner
can personalize its tool plan (e.g., include portfolio exposure for held stocks).

Preferences and watchlist queries run concurrently via asyncio.gather with
independent DB sessions, since AsyncSession is not safe for concurrent use.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def _fetch_preferences(user_id: uuid.UUID) -> dict[str, Any]:
    """Fetch user preferences using an independent DB session.

    Args:
        user_id: The authenticated user's UUID.

    Returns:
        Dict of preference fields, or empty dict if not found / on error.
    """
    from backend.database import async_session_factory
    from backend.models.user import UserPreference

    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(UserPreference).where(UserPreference.user_id == user_id)
            )
            pref = result.scalar_one_or_none()
            if pref is not None:
                return {
                    "max_position_pct": pref.max_position_pct,
                    "max_sector_pct": pref.max_sector_pct,
                    "default_stop_loss_pct": pref.default_stop_loss_pct,
                }
    except Exception:
        logger.warning("user_context_preferences_failed", extra={"user_id": str(user_id)})
    return {}


async def _fetch_watchlist(user_id: uuid.UUID) -> list[str]:
    """Fetch user watchlist tickers using an independent DB session.

    Args:
        user_id: The authenticated user's UUID.

    Returns:
        List of ticker strings, or empty list on error.
    """
    from backend.database import async_session_factory
    from backend.models.stock import Watchlist

    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Watchlist.ticker).where(Watchlist.user_id == user_id)
            )
            return [row[0] for row in result.all()]
    except Exception:
        logger.warning("user_context_watchlist_failed", extra={"user_id": str(user_id)})
    return []


async def build_user_context(user_id: uuid.UUID, db: AsyncSession) -> dict[str, Any]:
    """Build a context dict describing the user's portfolio state.

    Portfolio queries run on the caller's session (they use get_or_create which
    may write). Preferences and watchlist run concurrently on independent
    sessions via asyncio.gather for lower latency.

    Args:
        user_id: The authenticated user's UUID.
        db: Async database session (used for portfolio queries).

    Returns:
        Dict with keys: portfolio_id, positions, sector_allocation,
        preferences, watchlist. Empty/default values for new users.
    """
    from backend.services.portfolio import get_or_create_portfolio, get_positions_with_pnl

    context: dict[str, Any] = {
        "user_id": str(user_id),
        "portfolio_id": None,
        "positions": [],
        "held_tickers": [],
        "sector_allocation": {},
        "preferences": {},
        "watchlist": [],
    }

    # Launch preferences + watchlist concurrently (independent sessions)
    prefs_task = asyncio.create_task(_fetch_preferences(user_id))
    watchlist_task = asyncio.create_task(_fetch_watchlist(user_id))

    # Portfolio + positions (sequential — uses caller's session, may write)
    try:
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

    # Await concurrent results
    context["preferences"], context["watchlist"] = await asyncio.gather(prefs_task, watchlist_task)

    return context
