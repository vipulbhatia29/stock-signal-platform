"""Celery tasks for portfolio snapshot operations."""

import logging
import uuid

from backend.database import async_session_factory
from backend.services.portfolio import (
    compute_quantstats_portfolio,
    get_all_portfolio_ids,
    materialize_rebalancing,
    snapshot_portfolio_value,
)
from backend.tasks import celery_app
from backend.tasks._asyncio_bridge import safe_asyncio_run
from backend.tasks.pipeline import tracked_task

logger = logging.getLogger(__name__)


@tracked_task("portfolio_snapshot")
async def _snapshot_all_portfolios_async(*, run_id: uuid.UUID) -> dict:
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
                # Update the just-created snapshot with QuantStats metrics
                try:
                    qs_metrics = await compute_quantstats_portfolio(pid, db)
                    if qs_metrics.get("sharpe") is not None:
                        from sqlalchemy import update

                        from backend.models.portfolio import PortfolioSnapshot

                        await db.execute(
                            update(PortfolioSnapshot)
                            .where(
                                PortfolioSnapshot.portfolio_id == pid,
                                PortfolioSnapshot.snapshot_date == result.snapshot_date,
                            )
                            .values(**{k: v for k, v in qs_metrics.items() if v is not None})
                        )
                        await db.commit()
                except Exception:
                    logger.warning(
                        "QuantStats computation failed for portfolio %s", pid, exc_info=True
                    )
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
        return safe_asyncio_run(_snapshot_all_portfolios_async())  # type: ignore[arg-type]
    except Exception:
        logger.exception(
            "snapshot_all_portfolios_task failed (attempt %d/%d)",
            self.request.retries + 1,
            self.max_retries + 1,
        )
        raise


@tracked_task("portfolio_health")
async def _snapshot_health_async(*, run_id: uuid.UUID) -> dict:
    """Compute and store health snapshots for all portfolios.

    Returns:
        Dict with computed and skipped counts.
    """
    from datetime import datetime, timezone

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from backend.models.portfolio_health import PortfolioHealthSnapshot
    from backend.tools.portfolio_health import compute_portfolio_health

    async with async_session_factory() as db:
        portfolio_ids = await get_all_portfolio_ids(db)

    computed = 0
    skipped = 0
    for pid in portfolio_ids:
        try:
            async with async_session_factory() as db:
                health = await compute_portfolio_health(pid, db)
                if health is None:
                    skipped += 1
                    continue

                now = datetime.now(timezone.utc)
                component_map = {c.name: c.score for c in health.components}

                stmt = (
                    pg_insert(PortfolioHealthSnapshot)
                    .values(
                        portfolio_id=pid,
                        snapshot_date=now,
                        health_score=health.health_score,
                        grade=health.grade,
                        diversification_score=component_map.get("diversification", 0),
                        signal_quality_score=component_map.get("signal_quality", 0),
                        risk_score=component_map.get("risk", 0),
                        income_score=component_map.get("income", 0),
                        sector_balance_score=component_map.get("sector_balance", 0),
                        hhi=health.metrics.get("hhi", 0),
                        weighted_beta=health.metrics.get("weighted_beta"),
                        weighted_sharpe=health.metrics.get("weighted_sharpe"),
                        weighted_yield=health.metrics.get("weighted_yield"),
                        position_count=len(health.position_details),
                    )
                    .on_conflict_do_update(
                        constraint="portfolio_health_snapshots_pkey",
                        set_={
                            "health_score": health.health_score,
                            "grade": health.grade,
                            "diversification_score": component_map.get("diversification", 0),
                            "signal_quality_score": component_map.get("signal_quality", 0),
                            "risk_score": component_map.get("risk", 0),
                            "income_score": component_map.get("income", 0),
                            "sector_balance_score": component_map.get("sector_balance", 0),
                            "hhi": health.metrics.get("hhi", 0),
                            "weighted_beta": health.metrics.get("weighted_beta"),
                            "weighted_sharpe": health.metrics.get("weighted_sharpe"),
                            "weighted_yield": health.metrics.get("weighted_yield"),
                            "position_count": len(health.position_details),
                        },
                    )
                )
                await db.execute(stmt)
                await db.commit()
                computed += 1
        except Exception:
            logger.warning("Failed to snapshot health for portfolio %s", pid, exc_info=True)
            skipped += 1

    logger.info("Health snapshots: %d computed, %d skipped", computed, skipped)
    return {"computed": computed, "skipped": skipped}


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=True,
    name="backend.tasks.portfolio.snapshot_health_task",
)
def snapshot_health_task(self) -> dict:
    """Capture daily health score snapshots for all portfolios.

    Runs on Celery Beat schedule, 15 minutes after value snapshots.
    """
    logger.info("Starting health snapshots (attempt %d)", self.request.retries + 1)
    return safe_asyncio_run(_snapshot_health_async())  # type: ignore[arg-type]


@tracked_task("rebalancing")
async def _materialize_rebalancing_async(*, run_id: uuid.UUID) -> dict:
    """Compute and store rebalancing suggestions for all portfolios.

    Returns:
        Dict with computed and skipped counts.
    """
    async with async_session_factory() as db:
        portfolio_ids = await get_all_portfolio_ids(db)

    computed = 0
    skipped = 0
    for pid in portfolio_ids:
        try:
            async with async_session_factory() as db:
                await materialize_rebalancing(pid, db)
                computed += 1
        except Exception:
            logger.warning(
                "Rebalancing materialization failed for portfolio %s",
                pid,
                exc_info=True,
            )
            skipped += 1

    logger.info("Rebalancing: %d computed, %d skipped", computed, skipped)
    return {"computed": computed, "skipped": skipped}


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=True,
    name="backend.tasks.portfolio.materialize_rebalancing_task",
)
def materialize_rebalancing_task(self) -> dict:
    """Compute and store optimized rebalancing suggestions for all portfolios.

    Runs as part of the nightly pipeline Phase 4.
    """
    logger.info("Starting rebalancing materialization (attempt %d)", self.request.retries + 1)
    return safe_asyncio_run(_materialize_rebalancing_async())  # type: ignore[arg-type]
