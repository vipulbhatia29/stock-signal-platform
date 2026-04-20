"""Anomaly rule: 5xx error rate elevated.

Fires when the ``api_error_log`` contains more than 5 rows with
``status_code >= 500`` in the last 5 minutes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from backend.database import async_session_factory
from backend.observability.anomaly.base import AnomalyRule, Finding
from backend.observability.models.api_error_log import ApiErrorLog

logger = logging.getLogger(__name__)

# --- Thresholds ---
COUNT_THRESHOLD = 5
LOOKBACK_MINUTES = 5


class Http5xxElevatedRule(AnomalyRule):
    """Fire a single finding when 5xx errors exceed the threshold in 5 minutes.

    All 5xx errors are aggregated regardless of endpoint — a single finding
    represents the overall 5xx health of the API.
    """

    @property
    def name(self) -> str:
        """Unique rule identifier."""
        return "http_5xx_elevated"

    async def evaluate(self) -> list[Finding]:
        """Run the rule and return a finding if 5xx count exceeds threshold.

        Returns:
            List with one Finding if threshold exceeded, otherwise empty.
        """
        since = datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MINUTES)

        stmt = select(func.count(ApiErrorLog.id)).where(
            ApiErrorLog.ts >= since,
            ApiErrorLog.status_code >= 500,
        )

        async with async_session_factory() as session:
            result = await session.execute(stmt)
            count_5xx: int = result.scalar_one()

        if count_5xx <= COUNT_THRESHOLD:
            return []

        return [
            Finding(
                kind="http_5xx_elevated",
                attribution_layer="api",
                severity="error",
                title=f"{count_5xx} server errors (5xx) in the last {LOOKBACK_MINUTES} minutes",
                evidence={
                    "count_5xx": count_5xx,
                    "threshold": COUNT_THRESHOLD,
                    "lookback_minutes": LOOKBACK_MINUTES,
                },
                dedup_key="http_5xx_elevated:api:all",
                remediation_hint=(
                    f"Detected {count_5xx} 5xx errors in {LOOKBACK_MINUTES} minutes. "
                    "Check recent deployments, database connectivity, and external "
                    "API provider status. Inspect api_error_log for stack traces."
                ),
            )
        ]
