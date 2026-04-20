"""Persist anomaly findings to observability.finding_log with dedup."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

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
                    FindingLog.dedup_key  # nosemgrep
                    == finding.dedup_key,
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


# --- Auto-close threshold ---
AUTO_CLOSE_THRESHOLD = 3  # consecutive negative checks before auto-resolve


async def auto_close_findings(*, fired_dedup_keys: set[str]) -> tuple[int, int]:
    """Auto-close findings that have cleared for 3 consecutive scans.

    For each open/acknowledged finding:
    - If its dedup_key was fired in this scan → reset negative_check_count to 0
    - If NOT fired → increment negative_check_count
    - If negative_check_count reaches AUTO_CLOSE_THRESHOLD → resolve with auto tag

    Args:
        fired_dedup_keys: Set of dedup_keys that fired in the current scan.

    Returns:
        Tuple of (resolved_count, incremented_count).
    """
    from backend.observability.models.finding_log import FindingLog  # noqa: PLC0415

    async with async_session_factory() as session:
        result = await session.execute(
            select(FindingLog).where(
                FindingLog.status.in_(["open", "acknowledged"]),
            )
        )
        open_findings = result.scalars().all()

        if not open_findings:
            return 0, 0

        resolved = 0
        incremented = 0
        dirty = False

        for finding in open_findings:
            if finding.dedup_key in fired_dedup_keys:
                # Still firing — reset counter
                if finding.negative_check_count != 0:
                    finding.negative_check_count = 0
                    dirty = True
            else:
                # Not firing this scan — increment toward auto-close
                finding.negative_check_count += 1
                dirty = True
                if finding.negative_check_count >= AUTO_CLOSE_THRESHOLD:
                    finding.status = "resolved"
                    finding.resolved_at = datetime.now(timezone.utc)
                    resolved += 1
                else:
                    incremented += 1

        if dirty:
            from backend.observability.instrumentation.db import _in_obs_write  # noqa: PLC0415

            token = _in_obs_write.set(True)
            try:
                await session.commit()
            finally:
                _in_obs_write.reset(token)

    logger.info(
        "anomaly.auto_close",
        extra={"resolved": resolved, "incremented": incremented},
    )
    return resolved, incremented
