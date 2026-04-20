"""Anomaly rule: Worker heartbeat missing.

Fires when no ``celery_worker_heartbeat`` row exists from a known worker
for more than 90 seconds.  Workers are discovered from heartbeats in the
last 24 hours — a worker that hasn't heartbeated at all is not tracked.

Workers whose most recent heartbeat has ``status='shutdown'`` are excluded —
graceful shutdowns are expected and should not fire findings.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.database import async_session_factory
from backend.observability.anomaly.base import AnomalyRule, Finding
from backend.observability.models.celery_worker_heartbeat import CeleryWorkerHeartbeat

logger = logging.getLogger(__name__)

# --- Thresholds ---
STALE_SECONDS = 90
DISCOVERY_HOURS = 24
SHUTDOWN_STATUS = "shutdown"


class WorkerHeartbeatMissingRule(AnomalyRule):
    """Fire a finding for every worker whose last heartbeat is older than 90s.

    Workers are discovered from heartbeats in the last 24 hours.  If a worker
    was active recently but hasn't heartbeated for >90s, it may be crashed or
    network-partitioned.  Workers that gracefully shut down (status='shutdown')
    are excluded.
    """

    @property
    def name(self) -> str:
        """Unique rule identifier."""
        return "worker_heartbeat_missing"

    async def evaluate(self) -> list[Finding]:
        """Run the rule and return findings for workers with stale heartbeats.

        Uses PostgreSQL DISTINCT ON to get the latest heartbeat row per worker,
        including status — so we can skip workers that gracefully shut down.

        Returns:
            List of Finding instances, one per worker with a missing heartbeat.
        """
        now = datetime.now(timezone.utc)
        discovery_since = now - timedelta(hours=DISCOVERY_HOURS)

        # DISTINCT ON (worker_name) + ORDER BY ts DESC → latest row per worker
        stmt = (
            select(
                CeleryWorkerHeartbeat.worker_name,
                CeleryWorkerHeartbeat.ts.label("latest_ts"),
                CeleryWorkerHeartbeat.status,
            )
            .where(CeleryWorkerHeartbeat.ts >= discovery_since)
            .distinct(CeleryWorkerHeartbeat.worker_name)
            .order_by(
                CeleryWorkerHeartbeat.worker_name,
                CeleryWorkerHeartbeat.ts.desc(),
            )
        )

        async with async_session_factory() as session:
            result = await session.execute(stmt)
            rows = result.all()

        findings: list[Finding] = []
        stale_threshold = now - timedelta(seconds=STALE_SECONDS)

        for row in rows:
            worker: str = row.worker_name
            latest: datetime = row.latest_ts

            # Skip workers that gracefully shut down — expected, not an anomaly
            if row.status == SHUTDOWN_STATUS:
                continue

            if latest < stale_threshold:
                gap_seconds = int((now - latest).total_seconds())
                findings.append(
                    Finding(
                        kind="worker_heartbeat_missing",
                        attribution_layer="celery",
                        severity="error",
                        title=f"Worker '{worker}' heartbeat missing for {gap_seconds}s",
                        evidence={
                            "worker_name": worker,
                            "last_heartbeat": latest.isoformat(),
                            "gap_seconds": gap_seconds,
                            "threshold_seconds": STALE_SECONDS,
                        },
                        dedup_key=f"worker_heartbeat_missing:celery:{worker}",
                        remediation_hint=(
                            f"Worker '{worker}' has not sent a heartbeat for {gap_seconds}s "
                            f"(threshold: {STALE_SECONDS}s). Check if the worker process is "
                            "alive, inspect logs for OOM kills, and verify network connectivity."
                        ),
                    )
                )

        return findings
