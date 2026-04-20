"""Anomaly rule: Agent decline rate elevated.

Fires when more than 10% of ``agent_intent_log`` queries in the last hour
have a non-null ``decline_reason``, indicating the agent is refusing too
many user queries.  Requires at least 20 queries for statistical significance.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from backend.database import async_session_factory
from backend.observability.anomaly.base import AnomalyRule, Finding
from backend.observability.models.agent_intent_log import AgentIntentLog

logger = logging.getLogger(__name__)

# --- Thresholds ---
DECLINE_RATE_THRESHOLD = 0.10  # 10 %
MIN_QUERY_COUNT = 20
LOOKBACK_HOURS = 1


class AgentDeclineRateRule(AnomalyRule):
    """Fire a finding when the agent decline rate exceeds 10% over the last hour.

    Uses a single aggregate query to count total queries and declined queries.
    Requires at least 20 queries to avoid false positives from low volume.
    """

    @property
    def name(self) -> str:
        """Unique rule identifier."""
        return "agent_decline_rate"

    async def evaluate(self) -> list[Finding]:
        """Run the rule and return a finding if decline rate exceeds threshold.

        Returns:
            List with one Finding if threshold exceeded, otherwise empty.
        """
        since = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)

        total_col = func.count(AgentIntentLog.id).label("total_queries")
        declined_col = (
            func.count(AgentIntentLog.id)
            .filter(AgentIntentLog.decline_reason.isnot(None))
            .label("declined_queries")
        )

        stmt = select(total_col, declined_col).where(AgentIntentLog.ts >= since)

        async with async_session_factory() as session:
            result = await session.execute(stmt)
            row = result.one()

        total: int = row.total_queries
        declined: int = row.declined_queries

        if total < MIN_QUERY_COUNT:
            return []

        decline_rate = declined / total
        if decline_rate <= DECLINE_RATE_THRESHOLD:
            return []

        return [
            Finding(
                kind="agent_decline_rate_elevated",
                attribution_layer="agent",
                severity="warning",
                title=(
                    f"Agent decline rate {decline_rate:.0%} ({declined}/{total} queries declined)"
                ),
                evidence={
                    "total_queries": total,
                    "declined_queries": declined,
                    "decline_rate_pct": round(decline_rate * 100, 2),
                    "threshold_pct": DECLINE_RATE_THRESHOLD * 100,
                    "lookback_hours": LOOKBACK_HOURS,
                    "min_query_count": MIN_QUERY_COUNT,
                },
                dedup_key="agent_decline_rate_elevated:agent:all",
                remediation_hint=(
                    f"Agent declined {declined}/{total} queries ({decline_rate:.0%}) in the last "
                    f"hour. Review decline_reason distribution in agent_intent_log. "
                    "Common causes: guardrail false positives, missing tool capabilities, "
                    "or misconfigured intent classifier thresholds."
                ),
            )
        ]
