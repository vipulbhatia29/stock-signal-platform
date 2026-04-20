"""Anomaly rule: Frontend error burst detected.

Fires when more than 20 ``frontend_error_log`` rows of the same ``error_type``
appear in the last 5 minutes, indicating a systematic frontend failure.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from backend.database import async_session_factory
from backend.observability.anomaly.base import AnomalyRule, Finding
from backend.observability.models.frontend_error_log import FrontendErrorLog

logger = logging.getLogger(__name__)

# --- Thresholds ---
COUNT_THRESHOLD = 20
LOOKBACK_MINUTES = 5


class FrontendErrorBurstRule(AnomalyRule):
    """Fire a finding for each error_type that exceeds the burst threshold.

    Groups frontend errors by ``error_type`` and fires a finding for any
    type that has more than 20 occurrences in 5 minutes.
    """

    @property
    def name(self) -> str:
        """Unique rule identifier."""
        return "frontend_error_burst"

    async def evaluate(self) -> list[Finding]:
        """Run the rule and return findings for error types exceeding threshold.

        Returns:
            List of Finding instances, one per offending error_type.
        """
        since = datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MINUTES)

        count_col = func.count(FrontendErrorLog.id).label("error_count")

        stmt = (
            select(FrontendErrorLog.error_type, count_col)
            .where(FrontendErrorLog.ts >= since)
            .group_by(FrontendErrorLog.error_type)
        )

        async with async_session_factory() as session:
            result = await session.execute(stmt)
            rows = result.all()

        findings: list[Finding] = []
        for row in rows:
            error_type: str = row.error_type
            count: int = row.error_count

            if count > COUNT_THRESHOLD:
                findings.append(
                    Finding(
                        kind="frontend_error_burst",
                        attribution_layer="frontend",
                        severity="warning",
                        title=(
                            f"Frontend error burst: {count} '{error_type}'"
                            f" errors in {LOOKBACK_MINUTES}min"
                        ),
                        evidence={
                            "error_type": error_type,
                            "count": count,
                            "threshold": COUNT_THRESHOLD,
                            "lookback_minutes": LOOKBACK_MINUTES,
                        },
                        dedup_key=f"frontend_error_burst:frontend:{error_type}",
                        remediation_hint=(
                            f"Frontend is generating {count} '{error_type}' errors in "
                            f"{LOOKBACK_MINUTES} minutes. Check recent deployments, "
                            "inspect browser console logs, and review error boundary captures."
                        ),
                    )
                )

        return findings
