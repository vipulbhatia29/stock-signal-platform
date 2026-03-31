"""Observability API — user-facing query analytics and assessment results."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_async_session
from backend.dependencies import get_current_user, require_admin
from backend.models.user import User, UserRole
from backend.schemas.observability import (
    AssessmentHistoryResponse,
    AssessmentRunSummary,
    DateBucketEnum,
    GroupByEnum,
    GroupedResponse,
    KPIResponse,
    LangfuseURLResponse,
    QueryDetailResponse,
    QueryListResponse,
    SortByEnum,
    SortOrderEnum,
    StatusFilterEnum,
)
from backend.services.observability_queries import (
    get_assessment_history,
    get_kpis,
    get_latest_assessment,
    get_query_detail,
    get_query_groups,
    get_query_list,
)

router = APIRouter(prefix="/observability", tags=["observability"])


def _user_scope(user: User) -> uuid.UUID | None:
    """Return user_id for scoping, or None if admin (sees all)."""
    if user.role == UserRole.ADMIN:
        return None
    return user.id


@router.get(
    "/kpis",
    response_model=KPIResponse,
    summary="Get observability KPI metrics",
    description="Returns queries today, avg latency/cost, pass rate, fallback rate. "
    "Regular users see their own data; admins see all.",
)
async def kpis(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> KPIResponse:
    """Return top-level observability KPIs."""
    result = await get_kpis(db, user_id=_user_scope(user))
    return KPIResponse(**result)


@router.get(
    "/queries",
    response_model=QueryListResponse,
    summary="List queries with analytics",
    description="Paginated, filterable list of queries grouped by query_id.",
)
async def queries(
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    agent_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort_by: SortByEnum = SortByEnum.timestamp,
    sort_order: SortOrderEnum = SortOrderEnum.desc,
    status: StatusFilterEnum | None = None,
    cost_min: float | None = Query(None, ge=0),
    cost_max: float | None = Query(None, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> QueryListResponse:
    """Return paginated query list."""
    if cost_min is not None and cost_max is not None and cost_min > cost_max:
        raise HTTPException(status_code=422, detail="cost_min must be <= cost_max")

    result = await get_query_list(
        db,
        user_id=_user_scope(user),
        page=page,
        size=size,
        agent_type=agent_type,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by.value,
        sort_order=sort_order.value,
        status=status.value if status else None,
        cost_min=cost_min,
        cost_max=cost_max,
    )
    return QueryListResponse(**result)


@router.get(
    "/queries/grouped",
    response_model=GroupedResponse,
    summary="Aggregate queries by dimension",
    description="Returns grouped aggregation (count, cost, latency, error rate) "
    "by the specified dimension.",
)
async def grouped_queries(
    group_by: GroupByEnum = Query(..., description="Grouping dimension"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    bucket: DateBucketEnum = DateBucketEnum.day,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> GroupedResponse:
    """Return grouped query aggregation."""
    if group_by == GroupByEnum.user:
        require_admin(user)

    result = await get_query_groups(
        db,
        group_by=group_by.value,
        user_id=_user_scope(user) if group_by != GroupByEnum.intent_category else None,
        date_from=date_from,
        date_to=date_to,
        bucket=bucket.value,
    )
    return GroupedResponse(**result)


@router.get(
    "/queries/{query_id}",
    response_model=QueryDetailResponse,
    summary="Get query step-by-step detail",
    description="Returns all LLM calls, tool calls, and metadata for a query.",
    responses={404: {"description": "No data found for query"}},
)
async def query_detail(
    query_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> QueryDetailResponse:
    """Return step-by-step detail for a single query."""
    result = await get_query_detail(db, query_id, user_id=_user_scope(user))
    if result is None:
        raise HTTPException(status_code=404, detail="No data found for this query")
    return QueryDetailResponse(**result)


@router.get(
    "/queries/{query_id}/langfuse-url",
    response_model=LangfuseURLResponse,
    summary="Get Langfuse trace deep link",
    description="Returns URL to view this query's trace in Langfuse.",
)
async def langfuse_url(
    query_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> LangfuseURLResponse:
    """Return deep link to Langfuse trace for this query."""
    if not settings.LANGFUSE_SECRET_KEY:
        return LangfuseURLResponse(url=None)
    # Verify ownership — non-admins can only see their own queries
    result = await get_query_detail(db, query_id, user_id=_user_scope(user))
    if result is None:
        raise HTTPException(status_code=404, detail="No data found for this query")
    url = f"{settings.LANGFUSE_BASEURL}/trace/{query_id}"
    return LangfuseURLResponse(url=url)


@router.get(
    "/assessment/latest",
    response_model=AssessmentRunSummary | None,
    summary="Get latest assessment run",
    description="Returns the most recent agent quality assessment results.",
)
async def assessment_latest(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> AssessmentRunSummary | None:
    """Return latest assessment run summary."""
    result = await get_latest_assessment(db)
    if result is None:
        return None
    return AssessmentRunSummary(**result)


@router.get(
    "/assessment/history",
    response_model=AssessmentHistoryResponse,
    summary="Get assessment run history (admin only)",
    description="Returns historical assessment runs. Admin access required.",
    responses={403: {"description": "Not admin"}},
)
async def assessment_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> AssessmentHistoryResponse:
    """Return assessment run history (admin only)."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    runs = await get_assessment_history(db)
    return AssessmentHistoryResponse(items=[AssessmentRunSummary(**r) for r in runs])
