"""Admin router — superuser-only endpoints for LLM model config management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.llm_config import LLMModelConfig
from backend.models.user import User, UserRole
from backend.schemas.llm_config import LLMModelConfigResponse, LLMModelConfigUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(user: User) -> User:
    """Raise 403 if user is not an admin."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get(
    "/llm-models",
    response_model=list[LLMModelConfigResponse],
    summary="List all LLM model configs",
    description="Returns all LLM model configurations including disabled ones.",
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Not admin"}},
)
async def list_llm_models(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[LLMModelConfigResponse]:
    """List all LLM model cascade configurations."""
    _require_admin(user)
    result = await db.execute(
        select(LLMModelConfig).order_by(LLMModelConfig.tier, LLMModelConfig.priority)
    )
    return [LLMModelConfigResponse.model_validate(row) for row in result.scalars().all()]


@router.patch(
    "/llm-models/{model_id}",
    response_model=LLMModelConfigResponse,
    summary="Update an LLM model config",
    description="Partially update an LLM model config (priority, enabled, limits, etc.).",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not admin"},
        404: {"description": "Model config not found"},
    },
)
async def update_llm_model(
    model_id: int,
    body: LLMModelConfigUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> LLMModelConfigResponse:
    """Update an LLM model config by ID."""
    _require_admin(user)
    result = await db.execute(select(LLMModelConfig).where(LLMModelConfig.id == model_id))
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=404, detail="Model config not found")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(config, key, value)

    db.add(config)
    await db.commit()
    await db.refresh(config)

    logger.info("Updated LLM model config id=%d: %s", model_id, update_data)
    return LLMModelConfigResponse.model_validate(config)


@router.post(
    "/llm-models/reload",
    summary="Reload LLM model configs from DB",
    description="Force-reload model configs into the running cascade. Takes effect immediately.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not admin"},
    },
)
async def reload_llm_models(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Reload model configs from DB into running app state."""
    _require_admin(user)

    from backend.agents.model_config import ModelConfigLoader

    loader = ModelConfigLoader()
    configs = await loader.reload(db)
    total = sum(len(models) for models in configs.values())
    logger.info("Reloaded %d model configs across %d tiers", total, len(configs))
    return {"status": "ok", "tiers": len(configs), "models": total}
