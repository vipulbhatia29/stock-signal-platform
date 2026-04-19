"""Anomaly engine orchestrator."""

from __future__ import annotations

import asyncio
import logging

from backend.observability.anomaly.base import AnomalyRule, Finding

logger = logging.getLogger(__name__)


async def run_anomaly_scan(
    *,
    rules: list[AnomalyRule],
    semaphore_limit: int = 4,
    rule_timeout_s: float = 30.0,
) -> list[Finding]:
    """Execute all anomaly rules in parallel and collect findings."""
    if not rules:
        return []

    sem = asyncio.Semaphore(semaphore_limit)

    async def _run_one(rule: AnomalyRule) -> list[Finding]:
        async with sem:
            try:
                return await asyncio.wait_for(rule.evaluate(), timeout=rule_timeout_s)
            except asyncio.TimeoutError:
                logger.warning("anomaly.rule.timeout", extra={"rule": rule.name})
                return []
            except Exception:
                logger.warning("anomaly.rule.failed", extra={"rule": rule.name}, exc_info=True)
                return []

    results = await asyncio.gather(*[_run_one(r) for r in rules])
    return [f for batch in results for f in batch]
