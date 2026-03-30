"""Admin router — superuser-only endpoints for LLM model config management and chat audit."""

from __future__ import annotations

import logging
import uuid as uuid_mod

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user, require_admin
from backend.models.chat import ChatMessage, ChatSession
from backend.models.llm_config import LLMModelConfig
from backend.models.logs import LLMCallLog, ToolExecutionLog
from backend.models.user import User
from backend.schemas.chat import (
    AdminChatSessionListResponse,
    AdminChatSessionSummary,
    AdminChatStatsResponse,
    AdminChatTranscriptResponse,
    ChatMessageResponse,
)
from backend.schemas.llm_config import (
    LLMModelConfigResponse,
    LLMModelConfigUpdate,
    TierToggleRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


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
    require_admin(user)
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
    require_admin(user)
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
    require_admin(user)

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
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Get LLM metrics from the llm_call_log table."""
    require_admin(user)
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
    stats = await collector.get_stats(db)
    stats["fallback_rate_60s"] = await collector.fallback_rate_last_60s(db)
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
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Get per-model health classification from the DB."""
    require_admin(user)
    collector = getattr(request.app.state, "collector", None)
    if collector is None:
        return {
            "tiers": [],
            "summary": {"total": 0, "healthy": 0, "degraded": 0, "down": 0, "disabled": 0},
        }
    return await collector.get_tier_health(db)


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
    require_admin(user)
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
    require_admin(user)

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
    require_admin(user)

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


# ── Chat audit trail endpoints ──────────────────────────────────────────────


@router.get(
    "/chat/sessions",
    response_model=AdminChatSessionListResponse,
    summary="List all chat sessions",
    description="Paginated list of chat sessions. Filterable by user and agent type.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not admin"},
    },
)
async def list_chat_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
    user_id: uuid_mod.UUID | None = Query(default=None, description="Filter by user ID"),
    agent_type: str | None = Query(default=None, description="Filter by agent type"),
    limit: int = Query(default=50, ge=1, le=100, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
) -> AdminChatSessionListResponse:
    """List all chat sessions with user email and message count."""
    require_admin(user)

    # Base query with join to users for email and subquery for message count
    msg_count_sq = (
        select(
            ChatMessage.session_id,
            func.count().label("message_count"),
        )
        .group_by(ChatMessage.session_id)
        .subquery()
    )

    base = (
        select(
            ChatSession,
            User.email.label("user_email"),
            func.coalesce(msg_count_sq.c.message_count, 0).label("message_count"),
        )
        .join(User, ChatSession.user_id == User.id)
        .outerjoin(msg_count_sq, ChatSession.id == msg_count_sq.c.session_id)
    )

    if user_id is not None:
        base = base.where(ChatSession.user_id == user_id)
    if agent_type is not None:
        base = base.where(ChatSession.agent_type == agent_type)

    # Total count
    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # Paginated results
    rows_stmt = base.order_by(ChatSession.last_active_at.desc()).limit(limit).offset(offset)
    result = await db.execute(rows_stmt)
    rows = result.all()

    sessions = [
        AdminChatSessionSummary(
            id=row.ChatSession.id,
            agent_type=row.ChatSession.agent_type,
            title=row.ChatSession.title,
            is_active=row.ChatSession.is_active,
            decline_count=row.ChatSession.decline_count,
            user_email=row.user_email,
            message_count=row.message_count,
            created_at=row.ChatSession.created_at,
            last_active_at=row.ChatSession.last_active_at,
        )
        for row in rows
    ]

    return AdminChatSessionListResponse(total=total, sessions=sessions)


@router.get(
    "/chat/sessions/{session_id}/transcript",
    response_model=AdminChatTranscriptResponse,
    summary="Get session transcript",
    description="Full message transcript for a specific chat session.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not admin"},
        404: {"description": "Session not found"},
    },
)
async def get_chat_transcript(
    session_id: uuid_mod.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> AdminChatTranscriptResponse:
    """Get the full transcript of a chat session."""
    require_admin(user)

    # Fetch session with user email and message count
    msg_count_sq = (
        select(
            ChatMessage.session_id,
            func.count().label("message_count"),
        )
        .where(ChatMessage.session_id == session_id)
        .group_by(ChatMessage.session_id)
        .subquery()
    )

    session_stmt = (
        select(
            ChatSession,
            User.email.label("user_email"),
            func.coalesce(msg_count_sq.c.message_count, 0).label("message_count"),
        )
        .join(User, ChatSession.user_id == User.id)
        .outerjoin(msg_count_sq, ChatSession.id == msg_count_sq.c.session_id)
        .where(ChatSession.id == session_id)
    )
    result = await db.execute(session_stmt)
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    session_summary = AdminChatSessionSummary(
        id=row.ChatSession.id,
        agent_type=row.ChatSession.agent_type,
        title=row.ChatSession.title,
        is_active=row.ChatSession.is_active,
        decline_count=row.ChatSession.decline_count,
        user_email=row.user_email,
        message_count=row.message_count,
        created_at=row.ChatSession.created_at,
        last_active_at=row.ChatSession.last_active_at,
    )

    # Fetch messages ordered by creation time
    msg_stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    msg_result = await db.execute(msg_stmt)
    messages = [ChatMessageResponse.model_validate(m) for m in msg_result.scalars().all()]

    return AdminChatTranscriptResponse(session=session_summary, messages=messages)


@router.get(
    "/chat/stats",
    response_model=AdminChatStatsResponse,
    summary="Get chat statistics",
    description="Aggregate counts for chat sessions, messages, and feedback.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not admin"},
    },
)
async def get_chat_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> AdminChatStatsResponse:
    """Get aggregate chat statistics."""
    require_admin(user)

    total_sessions = (await db.execute(select(func.count(ChatSession.id)))).scalar() or 0
    total_messages = (await db.execute(select(func.count(ChatMessage.id)))).scalar() or 0
    active_sessions = (
        await db.execute(select(func.count(ChatSession.id)).where(ChatSession.is_active.is_(True)))
    ).scalar() or 0
    feedback_up = (
        await db.execute(select(func.count(ChatMessage.id)).where(ChatMessage.feedback == "up"))
    ).scalar() or 0
    feedback_down = (
        await db.execute(select(func.count(ChatMessage.id)).where(ChatMessage.feedback == "down"))
    ).scalar() or 0

    return AdminChatStatsResponse(
        total_sessions=total_sessions,
        total_messages=total_messages,
        active_sessions=active_sessions,
        feedback_up=feedback_up,
        feedback_down=feedback_down,
    )
