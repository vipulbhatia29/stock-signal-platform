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


@celery_app.task(name="backend.tasks.audit.purge_deleted_accounts_task")
def purge_deleted_accounts_task() -> None:
    """Hard-delete users where deleted_at > 30 days ago.

    CASCADE foreign keys handle child record cleanup.
    Runs daily at 3:15 AM ET (after login attempt purge).
    """
    asyncio.run(_purge_deleted_accounts_async())


async def _purge_deleted_accounts_async() -> None:
    """Async implementation of deleted account purge."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from backend.database import async_session_factory
    from backend.models.user import User

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(
                User.deleted_at.isnot(None),
                User.deleted_at < cutoff,
            )
        )
        users = result.scalars().all()
        for user in users:
            logger.info(
                "Purging deleted user %s (deleted_at=%s)",
                user.id,
                user.deleted_at,
            )
            await session.delete(user)  # CASCADE handles child records
        await session.commit()
        if users:
            logger.info(
                "Purged %d deleted accounts past 30-day grace period",
                len(users),
            )
