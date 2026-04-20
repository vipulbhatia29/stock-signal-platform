"""Anomaly rule: Data quality critical findings detected.

Fires when any ``dq_check_history.severity = 'critical'`` row exists in
the last scan window (5 minutes).  DQ checks run nightly at 04:00 ET, so
this rule catches the latest critical findings on each anomaly scan cycle.

NOTE: DqCheckHistory lives in the ``public`` schema, not ``observability``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.database import async_session_factory
from backend.models.dq_check_history import DqCheckHistory
from backend.observability.anomaly.base import AnomalyRule, Finding

logger = logging.getLogger(__name__)

# --- Thresholds ---
LOOKBACK_MINUTES = 60  # DQ runs once per night; check last hour to catch it


class DqCriticalFindingsRule(AnomalyRule):
    """Fire a finding for each critical DQ check result in the last hour.

    Deduplicates per ``check_name`` — one finding per distinct failing check.
    """

    @property
    def name(self) -> str:
        """Unique rule identifier."""
        return "dq_critical"

    async def evaluate(self) -> list[Finding]:
        """Run the rule and return findings for critical DQ checks.

        Returns:
            List of Finding instances, one per distinct critical check_name.
        """
        since = datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MINUTES)

        stmt = (
            select(DqCheckHistory)
            .where(
                DqCheckHistory.severity == "critical",
                DqCheckHistory.detected_at >= since,
            )
            .order_by(DqCheckHistory.detected_at.desc())
        )

        async with async_session_factory() as session:
            result = await session.execute(stmt)
            rows = result.scalars().all()

        if not rows:
            return []

        # Deduplicate by check_name — one finding per check
        seen: set[str] = set()
        findings: list[Finding] = []
        for row in rows:
            check: str = row.check_name
            if check in seen:
                continue
            seen.add(check)

            findings.append(
                Finding(
                    kind="dq_critical",
                    attribution_layer="data_quality",
                    severity="critical",
                    title=f"Critical data quality finding: '{check}'",
                    evidence={
                        "check_name": check,
                        "ticker": row.ticker,
                        "message": row.message,
                        "detected_at": row.detected_at.isoformat(),
                        "lookback_minutes": LOOKBACK_MINUTES,
                    },
                    dedup_key=f"dq_critical:data_quality:{check}",
                    remediation_hint=(
                        f"DQ check '{check}' reported a critical finding. "
                        "Inspect the data pipeline for the affected ticker and "
                        "verify upstream data source health."
                    ),
                )
            )

        return findings
