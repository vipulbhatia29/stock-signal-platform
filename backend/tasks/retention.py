"""Nightly retention enforcement — purge old forecasts and news articles."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from backend.database import async_session_factory
from backend.models.forecast import ForecastResult
from backend.models.news_sentiment import NewsArticle
from backend.tasks import celery_app
from backend.tasks.pipeline import tracked_task

logger = logging.getLogger(__name__)

FORECAST_RETENTION_DAYS = 30
NEWS_RETENTION_DAYS = 90


@celery_app.task(name="backend.tasks.retention.purge_old_forecasts_task")
@tracked_task("forecast_retention", trigger="scheduled")
def purge_old_forecasts_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge forecast results older than 30 days."""
    return asyncio.run(_purge_old_forecasts_async())


async def _purge_old_forecasts_async() -> dict:
    """Keep last 30 days of forecasts; hard delete older rows."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=FORECAST_RETENTION_DAYS)
    async with async_session_factory() as db:
        result = await db.execute(delete(ForecastResult).where(ForecastResult.created_at < cutoff))
        await db.commit()
        deleted = result.rowcount or 0
    logger.info("Forecast retention: deleted %d rows older than %s", deleted, cutoff.date())
    return {"status": "ok", "deleted": deleted, "cutoff": cutoff.isoformat()}


@celery_app.task(name="backend.tasks.retention.purge_old_news_articles_task")
@tracked_task("news_retention", trigger="scheduled")
def purge_old_news_articles_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge news articles older than 90 days."""
    return asyncio.run(_purge_old_news_articles_async())


async def _purge_old_news_articles_async() -> dict:
    """Keep 90 days of raw news articles; daily aggregates retained forever."""
    # NewsArticle.published_at is naive (TIMESTAMP WITHOUT TIME ZONE)
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=NEWS_RETENTION_DAYS)
    async with async_session_factory() as db:
        result = await db.execute(delete(NewsArticle).where(NewsArticle.published_at < cutoff))
        await db.commit()
        deleted = result.rowcount or 0
    logger.info("News retention: deleted %d articles older than %s", deleted, cutoff.date())
    return {"status": "ok", "deleted": deleted, "cutoff": cutoff.isoformat()}
