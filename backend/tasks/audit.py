"""Audit trail maintenance tasks."""

from __future__ import annotations

import asyncio
import logging

from backend.tasks import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="backend.tasks.audit.purge_login_attempts_task")
def purge_login_attempts_task() -> None:
    """Delete login attempts older than 90 days.

    Batch delete to avoid lock contention. CCPA/GDPR compliant retention.
    """
    asyncio.run(_purge_login_attempts_async())


async def _purge_login_attempts_async() -> None:
    """Async implementation of login attempt purge."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete

    from backend.database import async_session_factory
    from backend.models.login_attempt import LoginAttempt

    cutoff = datetime.now(timezone.utc) - timedelta(days=90)

    async with async_session_factory() as session:
        result = await session.execute(delete(LoginAttempt).where(LoginAttempt.timestamp < cutoff))
        await session.commit()
        if result.rowcount and result.rowcount > 0:
            logger.info("Purged %d login attempts older than 90 days", result.rowcount)
