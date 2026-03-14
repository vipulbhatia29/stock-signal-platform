"""Celery tasks for portfolio snapshot operations."""

import asyncio
import logging

from backend.database import async_session_factory
from backend.tasks import celery_app
from backend.tools.portfolio import get_all_portfolio_ids, snapshot_portfolio_value

logger = logging.getLogger(__name__)


async def _snapshot_all_portfolios_async() -> dict:
    """Async implementation: snapshot every portfolio with open positions.

    Returns:
        A dict with count of snapshots created and skipped.
    """
    async with async_session_factory() as db:
        portfolio_ids = await get_all_portfolio_ids(db)

    snapshotted = 0
    skipped = 0
    for pid in portfolio_ids:
        async with async_session_factory() as db:
            result = await snapshot_portfolio_value(pid, db)
            if result:
                snapshotted += 1
            else:
                skipped += 1

    logger.info(
        "Portfolio snapshots complete: %d captured, %d skipped",
        snapshotted,
        skipped,
    )
    return {"snapshotted": snapshotted, "skipped": skipped}


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=True,
    retry_backoff_max=120,
    name="backend.tasks.portfolio.snapshot_all_portfolios_task",
)
def snapshot_all_portfolios_task(self) -> dict:
    """Capture daily value snapshots for all portfolios with positions.

    Runs on the Celery Beat schedule (daily at market close).
    Iterates over all portfolios that have open positions, computes
    summary, and inserts a PortfolioSnapshot row.

    Returns:
        A dict with count of snapshots created and skipped.

    Raises:
        Exception: Re-raised after max_retries exhausted.
    """
    try:
        logger.info("Starting daily portfolio snapshots (attempt %d)", self.request.retries + 1)
        return asyncio.run(_snapshot_all_portfolios_async())
    except Exception:
        logger.exception(
            "snapshot_all_portfolios_task failed (attempt %d/%d)",
            self.request.retries + 1,
            self.max_retries + 1,
        )
        raise
