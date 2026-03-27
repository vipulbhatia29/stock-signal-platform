"""Admin router — superuser-only endpoints for LLM model config management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.llm_config import LLMModelConfig
from backend.models.logs import LLMCallLog, ToolExecutionLog
from backend.models.user import User, UserRole
from backend.schemas.llm_config import (
    LLMModelConfigResponse,
    LLMModelConfigUpdate,
    TierToggleRequest,
)

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


@router.get(
    "/llm-metrics",
    summary="Get LLM cascade metrics",
    description="Returns real-time in-memory LLM request and cascade statistics.",
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Not admin"}},
)
async def get_llm_metrics(
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    """Get real-time LLM metrics from the ObservabilityCollector."""
    _require_admin(user)
    collector = getattr(request.app.state, "collector", None)
    if collector is None:
        return {
            "requests_by_model": {},
            "cascade_count": 0,
            "cascades_by_model": {},
            "rpm_by_model": {},
            "cascade_log": [],
            "fallback_rate_60s": 0.0,
        }
    stats = collector.get_stats()
    stats["fallback_rate_60s"] = collector.fallback_rate_last_60s()
    return stats


@router.get(
    "/tier-health",
    summary="Get tier health status",
    description="Returns per-model health classification with latency stats.",
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Not admin"}},
)
async def get_tier_health(
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    """Get per-model health classification."""
    _require_admin(user)
    collector = getattr(request.app.state, "collector", None)
    if collector is None:
        return {
            "tiers": [],
            "summary": {"total": 0, "healthy": 0, "degraded": 0, "down": 0, "disabled": 0},
        }
    return collector.get_tier_health()


@router.post(
    "/tier-toggle",
    summary="Enable/disable a model",
    description="Toggle a model on or off at runtime without a redeploy.",
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Not admin"}},
)
async def tier_toggle(
    body: TierToggleRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    """Toggle a model on/off at runtime."""
    _require_admin(user)
    collector = getattr(request.app.state, "collector", None)
    if collector is None:
        raise HTTPException(status_code=503, detail="Observability not initialized")
    collector.toggle_model(body.model, enabled=body.enabled)
    logger.info("Toggled model %s → enabled=%s", body.model, body.enabled)
    return {"status": "ok", "model": body.model, "enabled": body.enabled}


@router.get(
    "/llm-usage",
    summary="Get LLM usage stats (30-day)",
    description="Aggregated LLM usage from the database: cost, latency, escalation rate.",
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Not admin"}},
)
async def get_llm_usage(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Get 30-day LLM usage from llm_call_log table."""
    _require_admin(user)

    cutoff = text("now() - interval '30 days'")

    stmt = select(
        func.count().label("total_requests"),
        func.coalesce(func.sum(LLMCallLog.cost_usd), 0).label("total_cost_usd"),
        func.coalesce(func.avg(LLMCallLog.latency_ms), 0).label("avg_latency_ms"),
    ).where(
        LLMCallLog.created_at >= cutoff,
        LLMCallLog.error.is_(None),
    )
    result = await db.execute(stmt)
    row = result.one()

    model_stmt = (
        select(
            LLMCallLog.model,
            LLMCallLog.provider,
            func.count().label("request_count"),
            func.coalesce(func.sum(LLMCallLog.cost_usd), 0).label("cost_usd"),
        )
        .where(
            LLMCallLog.created_at >= cutoff,
            LLMCallLog.error.is_(None),
        )
        .group_by(LLMCallLog.model, LLMCallLog.provider)
    )
    model_result = await db.execute(model_stmt)
    models = [
        {
            "model": r.model,
            "provider": r.provider,
            "request_count": r.request_count,
            "cost_usd": float(r.cost_usd),
        }
        for r in model_result.all()
    ]

    total = row.total_requests or 0
    if total > 0:
        anthropic_stmt = select(func.count()).where(
            LLMCallLog.created_at >= cutoff,
            LLMCallLog.error.is_(None),
            LLMCallLog.provider == "anthropic",
        )
        anthropic_result = await db.execute(anthropic_stmt)
        anthropic_count = anthropic_result.scalar() or 0
        escalation_rate = round(anthropic_count / total, 4)
    else:
        escalation_rate = 0.0

    return {
        "total_requests": total,
        "total_cost_usd": float(row.total_cost_usd),
        "avg_latency_ms": round(float(row.avg_latency_ms)),
        "models": models,
        "escalation_rate": escalation_rate,
    }


@router.get(
    "/observability/query/{query_id}/cost",
    summary="Get per-query cost breakdown",
    description="Returns LLM cost and tool call stats for a specific query.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not admin"},
        404: {"description": "No data found for query"},
    },
)
async def get_query_cost(
    query_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Get per-query cost breakdown with LLM and tool call details."""
    import uuid as uuid_mod

    _require_admin(user)

    try:
        qid = uuid_mod.UUID(query_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid query_id format")

    # LLM calls for this query
    llm_result = await db.execute(select(LLMCallLog).where(LLMCallLog.query_id == qid))
    llm_rows = llm_result.scalars().all()

    # Tool calls for this query
    tool_result = await db.execute(select(ToolExecutionLog).where(ToolExecutionLog.query_id == qid))
    tool_rows = tool_result.scalars().all()

    if not llm_rows and not tool_rows:
        raise HTTPException(status_code=404, detail="No data found for query")

    # Build LLM breakdown
    llm_calls = []
    total_cost = 0.0
    total_prompt = 0
    total_completion = 0
    for row in llm_rows:
        cost = float(row.cost_usd) if row.cost_usd else 0.0
        total_cost += cost
        total_prompt += row.prompt_tokens or 0
        total_completion += row.completion_tokens or 0
        llm_calls.append(
            {
                "model": row.model,
                "provider": row.provider,
                "prompt_tokens": row.prompt_tokens or 0,
                "completion_tokens": row.completion_tokens or 0,
                "cost_usd": cost,
                "latency_ms": row.latency_ms,
                "agent_type": row.agent_type,
            }
        )

    # Build tool breakdown
    tool_total = len(tool_rows)
    cache_hits = sum(1 for r in tool_rows if r.cache_hit)
    tool_latency = sum(r.latency_ms or 0 for r in tool_rows)
    by_tool: dict[str, dict] = {}
    for row in tool_rows:
        entry = by_tool.setdefault(row.tool_name, {"count": 0, "cache_hits": 0})
        entry["count"] += 1
        if row.cache_hit:
            entry["cache_hits"] += 1

    return {
        "query_id": str(qid),
        "total_cost_usd": round(total_cost, 6),
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "llm_calls": llm_calls,
        "tool_calls": {
            "total": tool_total,
            "cache_hits": cache_hits,
            "cache_hit_rate": round(cache_hits / tool_total, 2) if tool_total else 0.0,
            "total_latency_ms": tool_latency,
            "by_tool": [{"tool_name": name, **stats} for name, stats in by_tool.items()],
        },
    }
