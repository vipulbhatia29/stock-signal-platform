"""Data-driven model cascade configuration loader."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelConfig:
    """Single model configuration from llm_model_config table."""

    id: int
    provider: str
    model_name: str
    tier: str
    priority: int
    is_enabled: bool
    tpm_limit: int | None
    rpm_limit: int | None
    tpd_limit: int | None
    rpd_limit: int | None
    cost_per_1k_input: float
    cost_per_1k_output: float


class ModelConfigLoader:
    """Reads llm_model_config from DB, caches in memory."""

    def __init__(self) -> None:
        self._cache: dict[str, list[ModelConfig]] = {}

    async def load(self, session: AsyncSession) -> dict[str, list[ModelConfig]]:
        """Load enabled models grouped by tier, ordered by priority."""
        from backend.models.llm_config import LLMModelConfig

        result = await session.execute(
            select(LLMModelConfig)
            .where(LLMModelConfig.is_enabled.is_(True))
            .order_by(LLMModelConfig.tier, LLMModelConfig.priority)
        )
        rows = result.scalars().all()

        grouped: dict[str, list[ModelConfig]] = {}
        for row in rows:
            mc = ModelConfig(
                id=row.id,
                provider=row.provider,
                model_name=row.model_name,
                tier=row.tier,
                priority=row.priority,
                is_enabled=row.is_enabled,
                tpm_limit=row.tpm_limit,
                rpm_limit=row.rpm_limit,
                tpd_limit=row.tpd_limit,
                rpd_limit=row.rpd_limit,
                cost_per_1k_input=float(row.cost_per_1k_input or 0),
                cost_per_1k_output=float(row.cost_per_1k_output or 0),
            )
            grouped.setdefault(mc.tier, []).append(mc)

        self._cache = grouped
        logger.info("Loaded %d model configs across %d tiers", len(rows), len(grouped))
        return grouped

    async def reload(self, session: AsyncSession) -> dict[str, list[ModelConfig]]:
        """Force re-read from DB. Called by admin reload endpoint."""
        logger.info("Reloading model config from DB")
        return await self.load(session)

    @property
    def cached(self) -> dict[str, list[ModelConfig]]:
        """Return the last-loaded config without hitting DB."""
        return self._cache
