"""Anomaly rule: Slow query regression — p95 duration exceeds 2× 7-day baseline.

Groups by query_hash, compares last-1h p95 to 7-day baseline p95.
Fires only when there are at least MIN_OCCURRENCES in the last hour.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.database import async_session_factory
from backend.observability.anomaly.base import AnomalyRule, Finding
from backend.observability.models.slow_query_log import SlowQueryLog

logger = logging.getLogger(__name__)

# --- Thresholds ---
REGRESSION_MULTIPLIER = 2.0  # current p95 must be > 2× baseline p95 to fire
MIN_OCCURRENCES = 5  # minimum recent rows per hash to fire
RECENT_HOURS = 1
BASELINE_DAYS = 7


def _percentile(sorted_values: list[int], pct: float) -> float:
    """Compute a percentile from a sorted list of integers.

    Args:
        sorted_values: Sorted list of integer durations.
        pct: Percentile in range [0, 100].

    Returns:
        Interpolated percentile value.
    """
    if not sorted_values:
        return 0.0
    idx = (pct / 100.0) * (len(sorted_values) - 1)
    lower = int(idx)
    upper = min(lower + 1, len(sorted_values) - 1)
    frac = idx - lower
    return sorted_values[lower] * (1 - frac) + sorted_values[upper] * frac


class SlowQueryRegressionRule(AnomalyRule):
    """Detect query hashes whose p95 duration has regressed vs 7-day baseline.

    Fires one finding per regressing query hash when the hash has at least
    MIN_OCCURRENCES rows in the recent window.
    """

    @property
    def name(self) -> str:
        """Unique rule identifier."""
        return "slow_query_regression"

    async def evaluate(self) -> list[Finding]:
        """Run the rule and return findings for regressed query hashes.

        Returns:
            List of Finding instances, one per regressing query_hash.
        """
        now = datetime.now(timezone.utc)
        recent_since = now - timedelta(hours=RECENT_HOURS)
        baseline_since = now - timedelta(days=BASELINE_DAYS)

        # Fetch recent rows (last 1h)
        recent_stmt = select(SlowQueryLog.query_hash, SlowQueryLog.duration_ms).where(
            SlowQueryLog.ts >= recent_since
        )

        # Fetch baseline rows (last 7d, excluding last 1h to separate windows)
        baseline_stmt = select(SlowQueryLog.query_hash, SlowQueryLog.duration_ms).where(
            SlowQueryLog.ts >= baseline_since,
            SlowQueryLog.ts < recent_since,
        )

        async with async_session_factory() as session:
            recent_result = await session.execute(recent_stmt)
            recent_rows = recent_result.all()

            baseline_result = await session.execute(baseline_stmt)
            baseline_rows = baseline_result.all()

        # Group by query_hash
        recent_by_hash: dict[str, list[int]] = defaultdict(list)
        for row in recent_rows:
            recent_by_hash[row.query_hash].append(row.duration_ms)

        baseline_by_hash: dict[str, list[int]] = defaultdict(list)
        for row in baseline_rows:
            baseline_by_hash[row.query_hash].append(row.duration_ms)

        findings: list[Finding] = []
        for query_hash, durations in recent_by_hash.items():
            if len(durations) < MIN_OCCURRENCES:
                continue

            baseline_durations = baseline_by_hash.get(query_hash, [])
            if not baseline_durations:
                # No baseline — cannot determine regression
                continue

            recent_p95 = _percentile(sorted(durations), 95)
            baseline_p95 = _percentile(sorted(baseline_durations), 95)

            if baseline_p95 <= 0:
                continue

            ratio = recent_p95 / baseline_p95
            if ratio <= REGRESSION_MULTIPLIER:
                continue

            findings.append(
                Finding(
                    kind="slow_query_regression",
                    attribution_layer="db",
                    severity="warning",
                    title=f"Slow query regression detected for hash '{query_hash}'",
                    evidence={
                        "query_hash": query_hash,
                        "recent_p95_ms": round(recent_p95, 2),
                        "baseline_p95_ms": round(baseline_p95, 2),
                        "ratio": round(ratio, 2),
                        "regression_multiplier_threshold": REGRESSION_MULTIPLIER,
                        "recent_occurrence_count": len(durations),
                        "lookback_hours": RECENT_HOURS,
                        "baseline_days": BASELINE_DAYS,
                    },
                    dedup_key=f"slow_query_regression:db:{query_hash}",
                    remediation_hint=(
                        f"Query hash '{query_hash}' p95 has degraded {ratio:.1f}×. "
                        "Run EXPLAIN ANALYZE, check index usage, and review recent schema changes."
                    ),
                )
            )

        return findings
