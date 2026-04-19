"""Anomaly rule: DB connection pool exhaustion detected.

Any ``pool_event_type = 'exhausted'`` event in the last 5 minutes is
immediately surfaced as a finding — pool exhaustion is always a critical signal.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.database import async_session_factory
from backend.observability.anomaly.base import AnomalyRule, Finding
from backend.observability.models.db_pool_event import DbPoolEvent

logger = logging.getLogger(__name__)

# --- Thresholds ---
LOOKBACK_MINUTES = 5
EXHAUSTED_EVENT_TYPE = "exhausted"


class DbPoolExhaustionRule(AnomalyRule):
    """Fire a finding any time pool exhaustion is recorded within the last 5 minutes.

    Pool exhaustion events indicate that all connections were checked out and
    requests had to wait or were rejected. Any occurrence warrants immediate attention.
    """

    @property
    def name(self) -> str:
        """Unique rule identifier."""
        return "db_pool_exhaustion"

    async def evaluate(self) -> list[Finding]:
        """Run the rule and return a finding if pool exhaustion occurred recently.

        Returns:
            List with one Finding if any exhaustion event is found, otherwise empty.
        """
        since = datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MINUTES)

        stmt = (
            select(DbPoolEvent)
            .where(
                DbPoolEvent.pool_event_type == EXHAUSTED_EVENT_TYPE,
                DbPoolEvent.ts >= since,
            )
            .limit(1)
        )

        async with async_session_factory() as session:
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

        if row is None:
            return []

        return [
            Finding(
                kind="db_pool_exhaustion",
                attribution_layer="db",
                severity="critical",
                title="Database connection pool exhaustion detected",
                evidence={
                    "event_id": str(row.id),
                    "ts": row.ts.isoformat(),
                    "pool_size": row.pool_size,
                    "checked_out": row.checked_out,
                    "overflow": row.overflow,
                    "lookback_minutes": LOOKBACK_MINUTES,
                },
                dedup_key="db_pool_exhaustion:db:pool",
                remediation_hint=(
                    "Connection pool is exhausted. Consider increasing pool_size, "
                    "reducing connection hold times, or investigating slow queries "
                    "that hold connections for extended periods."
                ),
            )
        ]
