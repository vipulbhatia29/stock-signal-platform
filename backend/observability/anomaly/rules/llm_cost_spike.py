"""Anomaly rule: LLM cost spike — today's cost exceeds 3× the 7-day daily median.

Queries the public-schema llm_call_log table (not observability schema).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select

from backend.database import async_session_factory
from backend.models.logs import LLMCallLog
from backend.observability.anomaly.base import AnomalyRule, Finding

logger = logging.getLogger(__name__)

# --- Thresholds ---
SPIKE_MULTIPLIER = 3.0  # today's cost must be > 3× median to fire
BASELINE_DAYS = 7


class LlmCostSpikeRule(AnomalyRule):
    """Detect today's LLM spending exceeding 3× the 7-day daily median.

    Compares today's total ``cost_usd`` to the median of the previous
    7 calendar days. Fires a single finding when the threshold is breached.
    """

    @property
    def name(self) -> str:
        """Unique rule identifier."""
        return "llm_cost_spike"

    async def evaluate(self) -> list[Finding]:
        """Run the rule and return a finding if today's cost is a spike.

        Returns:
            List with one Finding if a spike is detected, otherwise empty.
        """
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        baseline_start = today_start - timedelta(days=BASELINE_DAYS)

        # Today's total cost
        today_stmt = select(func.coalesce(func.sum(LLMCallLog.cost_usd), Decimal("0"))).where(
            LLMCallLog.created_at >= today_start
        )

        # Per-day totals for the last 7 days (to compute median client-side)
        # Using cast to date for grouping
        from sqlalchemy import cast
        from sqlalchemy.dialects.postgresql import DATE

        daily_stmt = (
            select(
                cast(LLMCallLog.created_at, DATE).label("day"),
                func.coalesce(func.sum(LLMCallLog.cost_usd), Decimal("0")).label("daily_cost"),
            )
            .where(
                LLMCallLog.created_at >= baseline_start,
                LLMCallLog.created_at < today_start,
            )
            .group_by(cast(LLMCallLog.created_at, DATE))
        )

        async with async_session_factory() as session:
            today_result = await session.execute(today_stmt)
            today_cost: Decimal = today_result.scalar_one()

            daily_result = await session.execute(daily_stmt)
            daily_rows = daily_result.all()

        if not daily_rows:
            # No baseline data — cannot determine spike
            logger.debug("llm_cost_spike: no baseline data, skipping")
            return []

        daily_costs = sorted(float(row.daily_cost) for row in daily_rows)
        n = len(daily_costs)
        if n % 2 == 1:
            median_cost = daily_costs[n // 2]
        else:
            median_cost = (daily_costs[n // 2 - 1] + daily_costs[n // 2]) / 2.0

        today_float = float(today_cost)

        if median_cost <= 0.0:
            # Avoid division by zero; if median is 0 and today > 0 it's always a spike
            if today_float > 0.0:
                ratio = float("inf")
            else:
                return []
        else:
            ratio = today_float / median_cost

        if ratio <= SPIKE_MULTIPLIER:
            return []

        return [
            Finding(
                kind="llm_cost_spike",
                attribution_layer="llm",
                severity="warning",
                title="LLM cost spike detected — today's spend exceeds 3× 7-day median",
                evidence={
                    "today_cost_usd": today_float,
                    "seven_day_median_usd": median_cost,
                    "ratio": round(ratio, 2),
                    "spike_multiplier_threshold": SPIKE_MULTIPLIER,
                    "baseline_days": BASELINE_DAYS,
                },
                dedup_key="llm_cost_spike:llm:daily",
                remediation_hint=(
                    "Review LLM usage for runaway loops, missing early-exit conditions, "
                    "or sudden traffic spikes. Check llm_call_log for high-token sessions."
                ),
            )
        ]
