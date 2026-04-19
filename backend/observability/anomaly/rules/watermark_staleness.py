"""Anomaly rule: Pipeline watermark staleness.

Compares ``last_completed_at`` on each known pipeline to a configurable cadence.
Fires when the watermark is older than 2× the expected cadence.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from backend.database import async_session_factory
from backend.models.pipeline import PipelineWatermark
from backend.observability.anomaly.base import AnomalyRule, Finding

logger = logging.getLogger(__name__)

# --- Cadence map (seconds) ---
# Expected interval between successful completions.  Staleness threshold = cadence × 2.
PIPELINE_CADENCE_SECONDS: dict[str, int] = {
    "nightly_price_refresh": 86_400,  # 24 h
    "news_ingest": 21_600,  # 6 h
    "model_retrain": 604_800,  # 7 days
}

STALENESS_MULTIPLIER = 2


class WatermarkStalenessRule(AnomalyRule):
    """Fire a finding for each pipeline whose watermark exceeds 2× its cadence.

    Only pipelines listed in PIPELINE_CADENCE_SECONDS are checked. Unknown
    pipelines are silently skipped so that adding new pipelines doesn't
    immediately trigger false positives.
    """

    @property
    def name(self) -> str:
        """Unique rule identifier."""
        return "watermark_staleness"

    async def evaluate(self) -> list[Finding]:
        """Run the rule and return findings for stale pipeline watermarks.

        Returns:
            List of Finding instances, one per stale pipeline.
        """
        now = datetime.now(timezone.utc)

        stmt = select(PipelineWatermark).where(
            PipelineWatermark.pipeline_name.in_(list(PIPELINE_CADENCE_SECONDS.keys()))
        )

        async with async_session_factory() as session:
            result = await session.execute(stmt)
            watermarks = result.scalars().all()

        findings: list[Finding] = []
        for wm in watermarks:
            cadence_s = PIPELINE_CADENCE_SECONDS.get(wm.pipeline_name)
            if cadence_s is None:
                continue

            # last_completed_at may be tz-naive from DB; normalise to UTC
            last_completed_at = wm.last_completed_at
            if last_completed_at.tzinfo is None:
                last_completed_at = last_completed_at.replace(tzinfo=timezone.utc)

            age_seconds = (now - last_completed_at).total_seconds()
            threshold_seconds = cadence_s * STALENESS_MULTIPLIER

            if age_seconds <= threshold_seconds:
                continue

            findings.append(
                Finding(
                    kind="watermark_stale",
                    attribution_layer="pipeline",
                    severity="warning",
                    title=f"Pipeline '{wm.pipeline_name}' watermark is stale",
                    evidence={
                        "pipeline_name": wm.pipeline_name,
                        "last_completed_at": last_completed_at.isoformat(),
                        "age_seconds": round(age_seconds),
                        "threshold_seconds": threshold_seconds,
                        "cadence_seconds": cadence_s,
                        "staleness_multiplier": STALENESS_MULTIPLIER,
                        "pipeline_status": wm.status,
                    },
                    dedup_key=f"watermark_stale:pipeline:{wm.pipeline_name}",
                    remediation_hint=(
                        f"Pipeline '{wm.pipeline_name}' has not completed in "
                        f"{round(age_seconds / 3600, 1)} hours "
                        f"(expected every {cadence_s // 3600}h). "
                        "Check Celery beat schedule, worker health, and recent run logs."
                    ),
                )
            )

        return findings
