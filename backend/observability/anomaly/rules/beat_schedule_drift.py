"""Anomaly rule: Beat schedule drift exceeded.

Fires when any ``beat_schedule_run.drift_seconds > 300`` in the last hour.
Drift indicates the task ran significantly later than scheduled, possibly
due to worker overload or scheduler congestion.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.database import async_session_factory
from backend.observability.anomaly.base import AnomalyRule, Finding
from backend.observability.models.beat_schedule_run import BeatScheduleRun

logger = logging.getLogger(__name__)

# --- Thresholds ---
DRIFT_THRESHOLD_SECONDS = 300.0
LOOKBACK_HOURS = 1


class BeatScheduleDriftRule(AnomalyRule):
    """Fire a finding for every beat task that drifted more than 300s in the last hour.

    Deduplicates per task_name so each drifting task produces only one finding.
    """

    @property
    def name(self) -> str:
        """Unique rule identifier."""
        return "beat_schedule_drift"

    async def evaluate(self) -> list[Finding]:
        """Run the rule and return findings for drifting beat schedule runs.

        Returns:
            List of Finding instances, one per drifting task_name.
        """
        since = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)

        stmt = (
            select(BeatScheduleRun)
            .where(
                BeatScheduleRun.ts >= since,
                BeatScheduleRun.drift_seconds > DRIFT_THRESHOLD_SECONDS,
            )
            .order_by(BeatScheduleRun.ts.desc())
        )

        async with async_session_factory() as session:
            result = await session.execute(stmt)
            rows = result.scalars().all()

        if not rows:
            return []

        # Deduplicate by task_name — report the worst drift per task
        seen: set[str] = set()
        findings: list[Finding] = []
        for row in rows:
            task: str = row.task_name
            if task in seen:
                continue
            seen.add(task)

            findings.append(
                Finding(
                    kind="beat_schedule_drift",
                    attribution_layer="celery",
                    severity="warning",
                    title=f"Beat schedule drift {row.drift_seconds:.0f}s for '{task}'",
                    evidence={
                        "task_name": task,
                        "drift_seconds": row.drift_seconds,
                        "ts": row.ts.isoformat(),
                        "outcome": row.outcome,
                        "threshold_seconds": DRIFT_THRESHOLD_SECONDS,
                        "lookback_hours": LOOKBACK_HOURS,
                    },
                    dedup_key=f"beat_schedule_drift:celery:{task}",
                    remediation_hint=(
                        f"Task '{task}' drifted {row.drift_seconds:.0f}s from its schedule. "
                        "Check worker CPU/memory pressure, pending task queue depth, "
                        "and whether other long-running tasks are blocking the scheduler."
                    ),
                )
            )

        return findings
