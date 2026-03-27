"""Seed the 'reason' tier in llm_model_config.

Copies planner-tier model configurations to create the 'reason' tier
used by the ReAct agent loop. Safe to run multiple times (ON CONFLICT DO NOTHING).

Usage:
    uv run python scripts/seed_reason_tier.py
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from backend.database import async_session_factory

logger = logging.getLogger(__name__)


async def seed_reason_tier() -> None:
    """Copy planner tier rows to create reason tier."""
    async with async_session_factory() as db:
        result = await db.execute(
            text(
                """
                INSERT INTO llm_model_config (
                    provider, model_name, tier, priority,
                    is_enabled, tpm_limit, rpm_limit, tpd_limit, rpd_limit,
                    cost_per_1k_input, cost_per_1k_output,
                    notes, created_at, updated_at
                )
                SELECT
                    provider, model_name, 'reason', priority,
                    is_enabled, tpm_limit, rpm_limit, tpd_limit, rpd_limit,
                    cost_per_1k_input, cost_per_1k_output,
                    notes, NOW(), NOW()
                FROM llm_model_config
                WHERE tier = 'planner'
                ON CONFLICT DO NOTHING
                """
            )
        )
        await db.commit()
        logger.info("Seeded %d reason-tier rows", result.rowcount)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_reason_tier())
