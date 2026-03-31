"""Shared observability query service.

Used by both user-facing /observability endpoints and admin endpoints.
All functions accept an optional user_id to scope queries to a single user.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Float, case, func, literal_column, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models.assessment import AssessmentResult, AssessmentRun
from backend.models.chat import ChatMessage, ChatSession
from backend.models.logs import LLMCallLog, ToolExecutionLog
from backend.models.user import User

# Status derivation: worst status wins (highest code)
STATUS_MAP = {3: "error", 2: "declined", 1: "timeout", 0: "completed"}
STATUS_MAP_REVERSE = {v: k for k, v in STATUS_MAP.items()}

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
    sort_by: str = "timestamp",
    sort_order: str = "desc",
    status: str | None = None,
    cost_min: float | None = None,
    cost_max: float | None = None,
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
        sort_by: Column to sort by (timestamp, total_cost_usd, llm_calls,
            duration_ms, score).
        sort_order: Sort direction (asc, desc).
        status: Filter by derived worst-status (error, declined, timeout,
            completed).
        cost_min: Minimum total cost filter (HAVING).
        cost_max: Maximum total cost filter (HAVING).

    Returns:
        Dict with items (list of QueryRow-shaped dicts), total, page, size.
    """
    # Correlated subquery for tool duration
    duration_sq = (
        select(func.coalesce(func.sum(ToolExecutionLog.latency_ms), 0))
        .where(ToolExecutionLog.query_id == LLMCallLog.query_id)
        .correlate(LLMCallLog)
        .scalar_subquery()
    )

    # Eval score subquery (LEFT JOIN target) — aggregated to prevent row fan-out
    # when a query_id appears in multiple assessment runs
    eval_sq = (
        select(
            AssessmentResult.query_id,
            func.avg(
                case(
                    (
                        AssessmentResult.reasoning_coherence_score.is_not(None),
                        (
                            AssessmentResult.grounding_score
                            + AssessmentResult.reasoning_coherence_score
                        )
                        / 2,
                    ),
                    else_=AssessmentResult.grounding_score,
                )
            ).label("eval_score"),
        )
        .where(AssessmentResult.query_id.is_not(None))
        .group_by(AssessmentResult.query_id)
        .subquery()
    )

    # Derived worst-status column
    status_col = func.max(
        case(
            (LLMCallLog.status == "error", 3),
            (LLMCallLog.status == "declined", 2),
            (LLMCallLog.status == "timeout", 1),
            else_=0,
        )
    ).label("status_code")

    # Get distinct query_ids with aggregation from llm_call_log
    base = (
        select(
            LLMCallLog.query_id,
            func.min(LLMCallLog.created_at).label("timestamp"),
            func.array_agg(func.distinct(LLMCallLog.model)).label("llm_models"),
            func.count().label("llm_calls"),
            func.sum(LLMCallLog.cost_usd).label("total_cost_usd"),
            func.max(LLMCallLog.agent_type).label("agent_type"),
            duration_sq.label("duration_ms"),
            status_col,
            eval_sq.c.eval_score,
        )
        .outerjoin(eval_sq, eval_sq.c.query_id == LLMCallLog.query_id)
        .where(LLMCallLog.query_id.is_not(None))
    )

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

    # HAVING filters (must be applied BEFORE count subquery)
    if status is not None and status in STATUS_MAP_REVERSE:
        base = base.having(
            func.max(
                case(
                    (LLMCallLog.status == "error", 3),
                    (LLMCallLog.status == "declined", 2),
                    (LLMCallLog.status == "timeout", 1),
                    else_=0,
                )
            )
            == STATUS_MAP_REVERSE[status]
        )
    if cost_min is not None:
        base = base.having(func.sum(LLMCallLog.cost_usd) >= cost_min)
    if cost_max is not None:
        base = base.having(func.sum(LLMCallLog.cost_usd) <= cost_max)

    # Count total (after HAVING filters)
    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # Sort map — literal_column supports .asc()/.desc()/.nulls_last()
    sort_map = {
        "timestamp": literal_column("timestamp"),
        "total_cost_usd": literal_column("total_cost_usd"),
        "llm_calls": literal_column("llm_calls"),
        "duration_ms": literal_column("duration_ms"),
        "score": eval_sq.c.eval_score,
    }
    sort_col = sort_map.get(sort_by, literal_column("timestamp"))

    if sort_order == "asc":
        order_clause = sort_col.asc()
    else:
        order_clause = sort_col.desc()

    # NULLS LAST for score sorting
    if sort_by == "score":
        order_clause = order_clause.nulls_last()

    # Paginate
    offset = (page - 1) * size
    rows_stmt = base.order_by(order_clause).limit(size).offset(offset)
    rows = (await db.execute(rows_stmt)).all()

    qids = [row.query_id for row in rows]

    # Batch: tool calls for all query_ids on this page
    tool_by_qid: dict[uuid.UUID, list] = {qid: [] for qid in qids}
    if qids:
        tool_stmt = (
            select(
                ToolExecutionLog.query_id,
                ToolExecutionLog.tool_name,
                func.count().label("cnt"),
                func.sum(ToolExecutionLog.latency_ms).label("total_latency"),
            )
            .where(ToolExecutionLog.query_id.in_(qids))
            .group_by(ToolExecutionLog.query_id, ToolExecutionLog.tool_name)
        )
        for t in (await db.execute(tool_stmt)).all():
            tool_by_qid[t.query_id].append(t)

    # Batch: query text for all query_ids on this page
    # Use a subquery to get latest user message per session
    text_by_qid: dict[uuid.UUID, str] = {}
    if qids:
        msg_stmt = (
            select(
                LLMCallLog.query_id,
                func.max(ChatMessage.content).label("content"),
            )
            .join(ChatSession, LLMCallLog.session_id == ChatSession.id)
            .join(ChatMessage, ChatMessage.session_id == ChatSession.id)
            .where(LLMCallLog.query_id.in_(qids), ChatMessage.role == "user")
            .group_by(LLMCallLog.query_id)
        )
        for m in (await db.execute(msg_stmt)).all():
            text_by_qid[m.query_id] = m.content or ""

    items = []
    for row in rows:
        qid = row.query_id
        tool_rows = tool_by_qid.get(qid, [])

        tools_used = [t.tool_name for t in tool_rows]
        db_calls = sum(t.cnt for t in tool_rows if t.tool_name not in _EXTERNAL_TOOLS)
        external_calls = sum(t.cnt for t in tool_rows if t.tool_name in _EXTERNAL_TOOLS)
        external_sources = [t.tool_name for t in tool_rows if t.tool_name in _EXTERNAL_TOOLS]
        tool_latency = sum(t.total_latency or 0 for t in tool_rows)
        query_text = text_by_qid.get(qid, "")

        # Derive status string from status_code
        derived_status = STATUS_MAP.get(row.status_code, "completed")

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
                "score": float(row.eval_score) if row.eval_score is not None else None,
                "status": derived_status,
            }
        )

    return {"items": items, "total": total, "page": page, "size": size}


async def get_query_detail(
    db: AsyncSession,
    query_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> dict | None:
    """Return step-by-step detail for a single query.

    Args:
        db: Async database session.
        query_id: The query UUID.
        user_id: If set, verify query belongs to this user. None = admin (no filter).

    Returns:
        Dict with query_id, query_text, steps, langfuse_trace_url, or None if not found.
    """
    # LLM calls
    llm_stmt = select(LLMCallLog).where(LLMCallLog.query_id == query_id)
    if user_id:
        llm_stmt = llm_stmt.join(ChatSession, LLMCallLog.session_id == ChatSession.id).where(
            ChatSession.user_id == user_id
        )
    llm_stmt = llm_stmt.order_by(LLMCallLog.created_at)
    llm_rows = (await db.execute(llm_stmt)).scalars().all()

    # Tool calls
    tool_stmt = select(ToolExecutionLog).where(ToolExecutionLog.query_id == query_id)
    if user_id:
        tool_stmt = tool_stmt.join(
            ChatSession, ToolExecutionLog.session_id == ChatSession.id
        ).where(ChatSession.user_id == user_id)
    tool_stmt = tool_stmt.order_by(ToolExecutionLog.created_at)
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
                    "input_summary": f"→ {row.provider}/{row.model}",
                    "output_summary": (
                        f"{row.completion_tokens or 0} tokens, "
                        f"{row.latency_ms or 0}ms, "
                        f"${float(row.cost_usd or 0):.4f}"
                    ),
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
                    "input_summary": row.input_summary,
                    "output_summary": row.output_summary,
                    "latency_ms": row.latency_ms,
                    "cost_usd": None,
                    "cache_hit": row.cache_hit,
                },
            )
        )

    events.sort(key=lambda e: e[0])

    steps = []
    for i, (_, event) in enumerate(events, 1):
        steps.append({"step_number": i, **event})

    # Langfuse deep-link URL
    langfuse_trace_id = None
    for row in llm_rows:
        if row.langfuse_trace_id:
            langfuse_trace_id = row.langfuse_trace_id
            break

    langfuse_url = None
    if langfuse_trace_id and settings.LANGFUSE_SECRET_KEY and settings.LANGFUSE_BASEURL:
        langfuse_url = f"{settings.LANGFUSE_BASEURL}/trace/{langfuse_trace_id}"

    return {
        "query_id": query_id,
        "query_text": query_text,
        "steps": steps,
        "langfuse_trace_url": langfuse_url,
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


# ── Group-by dimension mapping ──────────────────────────────────────────────

_LLM_GROUP_COLS = {
    "agent_type": LLMCallLog.agent_type,
    "model": LLMCallLog.model,
    "status": LLMCallLog.status,
    "provider": LLMCallLog.provider,
    "tier": LLMCallLog.tier,
}

_VALID_BUCKETS = {"day", "week", "month"}


async def get_query_groups(
    db: AsyncSession,
    group_by: str,
    user_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    bucket: str = "day",
) -> dict:
    """Return aggregated query groups by the specified dimension.

    Args:
        db: Async database session.
        group_by: Grouping dimension (agent_type, date, model, status,
            provider, tier, tool_name, user, intent_category).
        user_id: Scope to user's queries (None = admin, sees all).
        date_from: Filter window start.
        date_to: Filter window end.
        bucket: Date bucketing granularity (day/week/month). Only used
            when group_by=date.

    Returns:
        Dict with group_by, bucket (optional), groups (list of GroupRow
        dicts), total_queries.
    """
    if group_by == "tool_name":
        rows = await _groups_tool_name(db, user_id, date_from, date_to)
    elif group_by == "user":
        rows = await _groups_user(db, date_from, date_to)
    elif group_by == "intent_category":
        rows = await _groups_intent_category(db, date_from, date_to)
    else:
        rows = await _groups_llm(db, group_by, user_id, date_from, date_to, bucket)

    groups = []
    for row in rows:
        key = row.key
        if hasattr(key, "isoformat"):
            key = key.isoformat()
        else:
            key = str(key) if not isinstance(key, str) else key

        groups.append(
            {
                "key": key,
                "query_count": row.query_count,
                "total_cost_usd": round(float(row.total_cost or 0), 6),
                "avg_cost_usd": round(float(row.total_cost or 0) / max(row.query_count, 1), 6),
                "avg_latency_ms": round(float(row.avg_latency or 0), 1),
                "error_rate": round(float(row.error_rate or 0), 4),
            }
        )

    return {
        "group_by": group_by,
        "bucket": bucket if group_by == "date" else None,
        "groups": groups,
        "total_queries": sum(g["query_count"] for g in groups),
    }


async def _groups_llm(
    db: AsyncSession,
    group_by: str,
    user_id: uuid.UUID | None,
    date_from: datetime | None,
    date_to: datetime | None,
    bucket: str,
) -> list:
    """Build grouped query from llm_call_log for LLM-based dimensions."""
    if group_by == "date":
        safe_bucket = bucket if bucket in _VALID_BUCKETS else "day"
        group_col = func.date_trunc(safe_bucket, LLMCallLog.created_at)
    else:
        group_col = _LLM_GROUP_COLS[group_by]

    error_rate_col = (
        func.sum(case((LLMCallLog.status == "error", 1), else_=0)).cast(Float) / func.count()
    )

    base = (
        select(
            group_col.label("key"),
            func.count(func.distinct(LLMCallLog.query_id)).label("query_count"),
            func.coalesce(func.sum(LLMCallLog.cost_usd), 0).label("total_cost"),
            func.coalesce(func.avg(LLMCallLog.latency_ms), 0).label("avg_latency"),
            error_rate_col.label("error_rate"),
        )
        .where(LLMCallLog.query_id.is_not(None))
        .group_by(group_col)
    )

    if user_id:
        base = base.join(ChatSession, LLMCallLog.session_id == ChatSession.id).where(
            ChatSession.user_id == user_id
        )
    if date_from:
        base = base.where(LLMCallLog.created_at >= date_from)
    if date_to:
        base = base.where(LLMCallLog.created_at <= date_to)

    return (await db.execute(base)).all()


async def _groups_tool_name(
    db: AsyncSession,
    user_id: uuid.UUID | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> list:
    """Build grouped query from tool_execution_log by tool_name."""
    error_rate_col = (
        func.sum(case((ToolExecutionLog.status != "ok", 1), else_=0)).cast(Float) / func.count()
    )

    base = (
        select(
            ToolExecutionLog.tool_name.label("key"),
            func.count(func.distinct(ToolExecutionLog.query_id)).label("query_count"),
            literal_column("0").label("total_cost"),
            func.coalesce(func.avg(ToolExecutionLog.latency_ms), 0).label("avg_latency"),
            error_rate_col.label("error_rate"),
        )
        .where(ToolExecutionLog.query_id.is_not(None))
        .group_by(ToolExecutionLog.tool_name)
    )

    if user_id:
        base = base.join(ChatSession, ToolExecutionLog.session_id == ChatSession.id).where(
            ChatSession.user_id == user_id
        )
    if date_from:
        base = base.where(ToolExecutionLog.created_at >= date_from)
    if date_to:
        base = base.where(ToolExecutionLog.created_at <= date_to)

    return (await db.execute(base)).all()


async def _groups_user(
    db: AsyncSession,
    date_from: datetime | None,
    date_to: datetime | None,
) -> list:
    """Build grouped query joining llm_call_log -> chat_session -> users."""
    error_rate_col = (
        func.sum(case((LLMCallLog.status == "error", 1), else_=0)).cast(Float) / func.count()
    )

    base = (
        select(
            User.email.label("key"),
            func.count(func.distinct(LLMCallLog.query_id)).label("query_count"),
            func.coalesce(func.sum(LLMCallLog.cost_usd), 0).label("total_cost"),
            func.coalesce(func.avg(LLMCallLog.latency_ms), 0).label("avg_latency"),
            error_rate_col.label("error_rate"),
        )
        .join(ChatSession, LLMCallLog.session_id == ChatSession.id)
        .join(User, ChatSession.user_id == User.id)
        .where(LLMCallLog.query_id.is_not(None))
        .group_by(User.email)
    )

    if date_from:
        base = base.where(LLMCallLog.created_at >= date_from)
    if date_to:
        base = base.where(LLMCallLog.created_at <= date_to)

    return (await db.execute(base)).all()


async def _groups_intent_category(
    db: AsyncSession,
    date_from: datetime | None,
    date_to: datetime | None,
) -> list:
    """Build grouped query from eval_results by intent_category."""
    base = select(
        AssessmentResult.intent_category.label("key"),
        func.count().label("query_count"),
        func.coalesce(func.sum(AssessmentResult.total_cost_usd), 0).label("total_cost"),
        func.coalesce(func.avg(AssessmentResult.total_duration_ms), 0).label("avg_latency"),
        literal_column("0").label("error_rate"),
    ).group_by(AssessmentResult.intent_category)

    if date_from:
        base = base.where(AssessmentResult.created_at >= date_from)
    if date_to:
        base = base.where(AssessmentResult.created_at <= date_to)

    return (await db.execute(base)).all()
