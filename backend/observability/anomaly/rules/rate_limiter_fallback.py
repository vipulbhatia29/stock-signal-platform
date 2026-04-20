"""Anomaly rule: Rate limiter fallback — permissive bypass detected.

Any ``action = 'fallback_permissive'`` event in the last 5 minutes fires a finding.
Fallback-permissive events mean the rate limiter allowed requests through despite
quota exhaustion — a safety bypass that should never go unnoticed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.database import async_session_factory
from backend.observability.anomaly.base import AnomalyRule, Finding
from backend.observability.models.rate_limiter_event import RateLimiterEvent

logger = logging.getLogger(__name__)

# --- Thresholds ---
LOOKBACK_MINUTES = 5
FALLBACK_ACTION = "fallback_permissive"


class RateLimiterFallbackRule(AnomalyRule):
    """Fire a finding for every distinct limiter that entered fallback-permissive mode.

    Fallback-permissive allows requests through when the limiter cannot enforce
    limits (e.g. Redis unavailable). This rule fires once per distinct limiter_name
    to surface all affected rate limiters.
    """

    @property
    def name(self) -> str:
        """Unique rule identifier."""
        return "rate_limiter_fallback"

    async def evaluate(self) -> list[Finding]:
        """Run the rule and return findings for every limiter in fallback mode.

        Returns:
            List of Finding instances, one per distinct limiter_name with a fallback event.
        """
        since = datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MINUTES)

        stmt = (
            select(RateLimiterEvent)
            .where(
                RateLimiterEvent.action == FALLBACK_ACTION,
                RateLimiterEvent.ts >= since,
            )
            .order_by(RateLimiterEvent.ts.desc())
        )

        async with async_session_factory() as session:
            result = await session.execute(stmt)
            rows = result.scalars().all()

        if not rows:
            return []

        # Deduplicate by limiter_name — one finding per limiter
        seen: set[str] = set()
        findings: list[Finding] = []
        for row in rows:
            limiter_name: str = row.limiter_name
            if limiter_name in seen:
                continue
            seen.add(limiter_name)

            findings.append(
                Finding(
                    kind="rate_limiter_fallback",
                    attribution_layer="rate_limiter",
                    severity="warning",
                    title=f"Rate limiter '{limiter_name}' entered fallback-permissive mode",
                    evidence={
                        "limiter_name": limiter_name,
                        "latest_event_ts": row.ts.isoformat(),
                        "reason_if_fallback": row.reason_if_fallback,
                        "lookback_minutes": LOOKBACK_MINUTES,
                    },
                    dedup_key=f"rate_limiter_fallback:rate_limiter:{limiter_name}",
                    remediation_hint=(
                        f"Rate limiter '{limiter_name}' bypassed limits in permissive fallback. "
                        "Check Redis connectivity and rate limiter configuration. "
                        "Downstream providers may be over-called."
                    ),
                )
            )

        return findings
