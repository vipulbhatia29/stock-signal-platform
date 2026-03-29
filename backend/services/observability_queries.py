"""Shared observability query service.

Used by both user-facing /observability endpoints and admin endpoints.
All functions accept an optional user_id to scope queries to a single user.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.assessment import AssessmentRun
from backend.models.chat import ChatMessage, ChatSession
from backend.models.logs import LLMCallLog, ToolExecutionLog

_EXTERNAL_TOOLS = {"web_search", "get_geopolitical_events"}


async def get_kpis(
    db: AsyncSession,
    user_id: uuid.UUID | None = None,
) -> dict:
    """Return top-level KPI metrics for the observability dashboard.

    Args:
        db: Async database session.
        user_id: If set, scope to this user's queries only.

    Returns:
        Dict with queries_today, avg_latency_ms, avg_cost_per_query,
        pass_rate, fallback_rate_pct.
    """
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # Base query — distinct query_ids today
    llm_base = select(LLMCallLog).where(LLMCallLog.created_at >= today_start)
    if user_id:
        llm_base = llm_base.join(ChatSession, LLMCallLog.session_id == ChatSession.id).where(
            ChatSession.user_id == user_id
        )

    # Queries today (distinct query_id)
    queries_stmt = select(func.count(func.distinct(LLMCallLog.query_id))).select_from(
        llm_base.subquery()
    )
    queries_today = (await db.execute(queries_stmt)).scalar() or 0

    # Avg cost per query
    cost_stmt = select(
        func.sum(LLMCallLog.cost_usd).label("total_cost"),
    ).select_from(llm_base.subquery())
    total_cost = (await db.execute(cost_stmt)).scalar() or 0
    avg_cost = float(total_cost) / queries_today if queries_today > 0 else 0.0

    # Avg latency from tool execution log
    tool_base = select(ToolExecutionLog).where(ToolExecutionLog.created_at >= today_start)
    if user_id:
        tool_base = tool_base.join(
            ChatSession, ToolExecutionLog.session_id == ChatSession.id
        ).where(ChatSession.user_id == user_id)
    latency_stmt = select(func.avg(ToolExecutionLog.latency_ms)).select_from(tool_base.subquery())
    avg_latency = (await db.execute(latency_stmt)).scalar() or 0.0

    # Latest pass rate from eval_runs
    pass_stmt = select(AssessmentRun.pass_rate).order_by(AssessmentRun.completed_at.desc()).limit(1)
    pass_rate = (await db.execute(pass_stmt)).scalar()

    # Fallback rate (last 60s)
    cutoff_60s = text("now() - interval '60 seconds'")
    fb_stmt = select(
        func.count().label("total"),
        func.count().filter(LLMCallLog.error.is_not(None)).label("failures"),
    ).where(LLMCallLog.created_at >= cutoff_60s)
    fb_row = (await db.execute(fb_stmt)).one()
    fb_total = fb_row.total or 0
    fallback_rate = ((fb_row.failures or 0) / fb_total * 100) if fb_total > 0 else 0.0

    return {
        "queries_today": queries_today,
        "avg_latency_ms": round(float(avg_latency), 1),
        "avg_cost_per_query": round(avg_cost, 6),
        "pass_rate": float(pass_rate) if pass_rate is not None else None,
        "fallback_rate_pct": round(fallback_rate, 1),
    }


async def get_query_list(
    db: AsyncSession,
    user_id: uuid.UUID | None = None,
    page: int = 1,
    size: int = 25,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    agent_type: str | None = None,
) -> dict:
    """Return paginated list of queries grouped by query_id.

    Args:
        db: Async database session.
        user_id: Scope to user's queries.
        page: Page number (1-based).
        size: Items per page.
        date_from: Filter from this datetime.
        date_to: Filter to this datetime.
        agent_type: Filter by agent type.

    Returns:
        Dict with items (list of QueryRow-shaped dicts), total, page, size.
    """
    # Get distinct query_ids with aggregation from llm_call_log
    base = select(
        LLMCallLog.query_id,
        func.min(LLMCallLog.created_at).label("timestamp"),
        func.array_agg(func.distinct(LLMCallLog.model)).label("llm_models"),
        func.count().label("llm_calls"),
        func.sum(LLMCallLog.cost_usd).label("total_cost_usd"),
        func.max(LLMCallLog.agent_type).label("agent_type"),
    ).where(LLMCallLog.query_id.is_not(None))

    if user_id:
        base = base.join(ChatSession, LLMCallLog.session_id == ChatSession.id).where(
            ChatSession.user_id == user_id
        )
    if date_from:
        base = base.where(LLMCallLog.created_at >= date_from)
    if date_to:
        base = base.where(LLMCallLog.created_at <= date_to)
    if agent_type:
        base = base.where(LLMCallLog.agent_type == agent_type)

    base = base.group_by(LLMCallLog.query_id)

    # Count total
    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # Paginate
    offset = (page - 1) * size
    rows_stmt = base.order_by(text("timestamp DESC")).limit(size).offset(offset)
    rows = (await db.execute(rows_stmt)).all()

    items = []
    for row in rows:
        qid = row.query_id

        # Get tool calls for this query
        tool_stmt = (
            select(
                ToolExecutionLog.tool_name,
                func.count().label("cnt"),
                func.sum(ToolExecutionLog.latency_ms).label("total_latency"),
            )
            .where(ToolExecutionLog.query_id == qid)
            .group_by(ToolExecutionLog.tool_name)
        )
        tool_rows = (await db.execute(tool_stmt)).all()

        tools_used = [t.tool_name for t in tool_rows]
        db_calls = sum(t.cnt for t in tool_rows if t.tool_name not in _EXTERNAL_TOOLS)
        external_calls = sum(t.cnt for t in tool_rows if t.tool_name in _EXTERNAL_TOOLS)
        external_sources = [t.tool_name for t in tool_rows if t.tool_name in _EXTERNAL_TOOLS]
        tool_latency = sum(t.total_latency or 0 for t in tool_rows)

        # Get query text from chat_messages
        msg_stmt = (
            select(ChatMessage.content)
            .join(ChatSession, ChatMessage.session_id == ChatSession.id)
            .join(LLMCallLog, LLMCallLog.session_id == ChatSession.id)
            .where(LLMCallLog.query_id == qid, ChatMessage.role == "user")
            .order_by(ChatMessage.created_at.desc())
            .limit(1)
        )
        query_text = (await db.execute(msg_stmt)).scalar() or ""

        items.append(
            {
                "query_id": qid,
                "timestamp": row.timestamp,
                "query_text": query_text[:200] if query_text else "",
                "agent_type": row.agent_type or "react_v2",
                "tools_used": tools_used,
                "llm_calls": row.llm_calls,
                "llm_models": row.llm_models or [],
                "db_calls": db_calls,
                "external_calls": external_calls,
                "external_sources": external_sources,
                "total_cost_usd": round(float(row.total_cost_usd or 0), 6),
                "duration_ms": tool_latency,
                "score": None,
                "status": "completed",
            }
        )

    return {"items": items, "total": total, "page": page, "size": size}


async def get_query_detail(
    db: AsyncSession,
    query_id: uuid.UUID,
) -> dict | None:
    """Return step-by-step detail for a single query.

    Args:
        db: Async database session.
        query_id: The query UUID.

    Returns:
        Dict with query_id, query_text, steps, langfuse_trace_url, or None if not found.
    """
    # LLM calls
    llm_stmt = (
        select(LLMCallLog).where(LLMCallLog.query_id == query_id).order_by(LLMCallLog.created_at)
    )
    llm_rows = (await db.execute(llm_stmt)).scalars().all()

    # Tool calls
    tool_stmt = (
        select(ToolExecutionLog)
        .where(ToolExecutionLog.query_id == query_id)
        .order_by(ToolExecutionLog.created_at)
    )
    tool_rows = (await db.execute(tool_stmt)).scalars().all()

    if not llm_rows and not tool_rows:
        return None

    # Get query text
    if llm_rows and llm_rows[0].session_id:
        msg_stmt = (
            select(ChatMessage.content)
            .where(
                ChatMessage.session_id == llm_rows[0].session_id,
                ChatMessage.role == "user",
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(1)
        )
        query_text = (await db.execute(msg_stmt)).scalar() or ""
    else:
        query_text = ""

    # Merge and sort all events by timestamp
    events: list[tuple[datetime, dict]] = []

    for row in llm_rows:
        events.append(
            (
                row.created_at,
                {
                    "action": f"llm.{row.provider}.{row.model}",
                    "type_tag": "llm",
                    "model_name": row.model,
                    "latency_ms": row.latency_ms,
                    "cost_usd": float(row.cost_usd) if row.cost_usd else None,
                    "cache_hit": False,
                },
            )
        )

    for row in tool_rows:
        type_tag = "external" if row.tool_name in _EXTERNAL_TOOLS else "db"
        events.append(
            (
                row.created_at,
                {
                    "action": f"tool.{row.tool_name}",
                    "type_tag": type_tag,
                    "model_name": None,
                    "latency_ms": row.latency_ms,
                    "cost_usd": None,
                    "cache_hit": row.cache_hit,
                },
            )
        )

    events.sort(key=lambda e: e[0])

    steps = []
    for i, (_, event) in enumerate(events, 1):
        steps.append(
            {
                "step_number": i,
                **event,
                "input_summary": None,
                "output_summary": None,
            }
        )

    return {
        "query_id": query_id,
        "query_text": query_text,
        "steps": steps,
        "langfuse_trace_url": None,
    }


async def get_latest_assessment(db: AsyncSession) -> dict | None:
    """Return the most recent assessment run summary.

    Returns:
        Dict with assessment run fields, or None if no runs exist.
    """
    stmt = select(AssessmentRun).order_by(AssessmentRun.completed_at.desc()).limit(1)
    run = (await db.execute(stmt)).scalar_one_or_none()
    if not run:
        return None

    return {
        "id": run.id,
        "trigger": run.trigger,
        "total_queries": run.total_queries,
        "passed_queries": run.passed_queries,
        "pass_rate": run.pass_rate,
        "total_cost_usd": run.total_cost_usd,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
    }


async def get_assessment_history(
    db: AsyncSession,
    limit: int = 20,
) -> list[dict]:
    """Return historical assessment runs.

    Args:
        db: Async database session.
        limit: Max number of runs to return.

    Returns:
        List of assessment run dicts ordered by completed_at DESC.
    """
    stmt = select(AssessmentRun).order_by(AssessmentRun.completed_at.desc()).limit(limit)
    runs = (await db.execute(stmt)).scalars().all()

    return [
        {
            "id": run.id,
            "trigger": run.trigger,
            "total_queries": run.total_queries,
            "passed_queries": run.passed_queries,
            "pass_rate": run.pass_rate,
            "total_cost_usd": run.total_cost_usd,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
        }
        for run in runs
    ]
