"""SQLAlchemy connection pool statistics collector."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


async def get_pool_stats(engine: AsyncEngine) -> dict:
    """Read current pool statistics from SQLAlchemy engine.

    Returns:
        Dict with pool_size, checked_out, overflow, checked_in, pool_status.
        On failure, returns a dict with status=unavailable.
    """
    try:
        pool = engine.pool
        return {
            "pool_size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "checked_in": pool.checkedin(),
            "pool_status": str(pool.status()),
        }
    except Exception:
        logger.warning("Failed to read DB pool stats", exc_info=True)
        return {"status": "unavailable", "error": "Pool stats unavailable"}
