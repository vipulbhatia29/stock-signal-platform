"""Persist anomaly findings to observability.finding_log with dedup."""

from __future__ import annotations

import logging

from sqlalchemy import select

from backend.config import settings
from backend.database import async_session_factory
from backend.observability.anomaly.base import Finding

logger = logging.getLogger(__name__)


async def persist_findings(findings: list[Finding]) -> tuple[int, int]:
    """Write findings to finding_log, skipping duplicates.

    Dedup rule: skip if an open/acknowledged finding with same dedup_key exists.

    FindingLog is imported lazily to avoid registering the observability schema
    model in Base.metadata at module import time (schema only exists after migrations).

    Args:
        findings: List of Finding instances from the engine.

    Returns:
        Tuple of (inserted_count, skipped_count).
    """
    # Lazy import: keeps observability schema tables out of Base.metadata at
    # module load time — schema is created by migration DDL, not create_all().
    from backend.observability.models.finding_log import FindingLog  # noqa: PLC0415

    if not findings:
        return 0, 0

    inserted = 0
    skipped = 0

    async with async_session_factory() as session:
        for finding in findings:
            existing = await session.execute(
                select(FindingLog.id).where(
                    FindingLog.dedup_key == finding.dedup_key,
                    FindingLog.status.in_(["open", "acknowledged"]),
                )
            )
            if existing.scalar_one_or_none() is not None:
                skipped += 1
                continue

            session.add(
                FindingLog(
                    opened_at=finding.opened_at,
                    kind=finding.kind,
                    attribution_layer=finding.attribution_layer,
                    severity=finding.severity,
                    status="open",
                    title=finding.title,
                    evidence=finding.evidence,
                    remediation_hint=finding.remediation_hint,
                    related_traces=(
                        [str(t) for t in finding.related_traces] if finding.related_traces else None
                    ),
                    dedup_key=finding.dedup_key,
                    env=getattr(settings, "APP_ENV", "dev"),
                )
            )
            inserted += 1

        if inserted > 0:
            from backend.observability.instrumentation.db import _in_obs_write  # noqa: PLC0415

            token = _in_obs_write.set(True)
            try:
                await session.commit()
            finally:
                _in_obs_write.reset(token)

    logger.info("anomaly.persist", extra={"inserted": inserted, "skipped": skipped})
    return inserted, skipped
