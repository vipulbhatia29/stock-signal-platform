"""Anomaly rule: External API error rate elevated above threshold.

Fires when a provider's error rate exceeds 10% of calls in the last hour,
provided that at least 10 calls have been made (to avoid noise from low volume).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from backend.database import async_session_factory
from backend.observability.anomaly.base import AnomalyRule, Finding
from backend.observability.models.external_api_call import ExternalApiCallLog

logger = logging.getLogger(__name__)

# --- Thresholds ---
ERROR_RATE_THRESHOLD = 0.10  # 10 %
MIN_CALL_COUNT = 10  # minimum calls to fire
LOOKBACK_HOURS = 1


class ExternalApiErrorRateRule(AnomalyRule):
    """Detect providers with elevated error rates in the last hour.

    Groups calls by provider and fires a finding for any provider whose
    error rate is >= 10% with at least 10 total calls.
    """

    @property
    def name(self) -> str:
        """Unique rule identifier."""
        return "external_api_error_rate"

    async def evaluate(self) -> list[Finding]:
        """Run the rule and return findings for providers with elevated error rates.

        Returns:
            List of Finding instances, one per offending provider.
        """
        since = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)

        total_col = func.count(ExternalApiCallLog.id).label("total_calls")
        error_col = (
            func.count(ExternalApiCallLog.id)
            .filter(ExternalApiCallLog.error_reason.isnot(None))
            .label("error_calls")
        )

        stmt = (
            select(
                ExternalApiCallLog.provider,
                total_col,
                error_col,
            )
            .where(ExternalApiCallLog.ts >= since)
            .group_by(ExternalApiCallLog.provider)
        )

        async with async_session_factory() as session:
            result = await session.execute(stmt)
            rows = result.all()

        findings: list[Finding] = []
        for row in rows:
            provider: str = row.provider
            total: int = row.total_calls
            errors: int = row.error_calls

            if total < MIN_CALL_COUNT:
                continue

            error_rate = errors / total
            if error_rate >= ERROR_RATE_THRESHOLD:
                findings.append(
                    Finding(
                        kind="external_api_error_rate_elevated",
                        attribution_layer="external_api",
                        severity="warning",
                        title=f"External API error rate elevated for provider '{provider}'",
                        evidence={
                            "provider": provider,
                            "total_calls": total,
                            "error_calls": errors,
                            "error_rate_pct": round(error_rate * 100, 2),
                            "threshold_pct": ERROR_RATE_THRESHOLD * 100,
                            "lookback_hours": LOOKBACK_HOURS,
                        },
                        dedup_key=f"external_api_error_rate_elevated:external_api:{provider}",
                        remediation_hint=(
                            f"Check provider '{provider}' health dashboard and recent "
                            "API key rotation. Review error_reason distribution."
                        ),
                    )
                )

        return findings
