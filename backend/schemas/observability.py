"""Pydantic schemas for observability API responses."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class KPIResponse(BaseModel):
    """Top-level observability KPI metrics."""

    queries_today: int
    avg_latency_ms: float
    avg_cost_per_query: float
    pass_rate: float | None
    fallback_rate_pct: float


class QueryRow(BaseModel):
    """Single row in the observability query list (L1 view)."""

    query_id: uuid.UUID
    timestamp: datetime
    query_text: str
    agent_type: str
    tools_used: list[str]
    llm_calls: int
    llm_models: list[str]
    db_calls: int
    external_calls: int
    external_sources: list[str]
    total_cost_usd: float
    duration_ms: int
    score: float | None
    status: str


class QueryListResponse(BaseModel):
    """Paginated list of observability queries."""

    items: list[QueryRow]
    total: int
    page: int
    size: int


class StepDetail(BaseModel):
    """Individual step within a query (L2 expansion view)."""

    step_number: int
    action: str
    type_tag: str
    model_name: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    latency_ms: int | None = None
    cost_usd: float | None = None
    cache_hit: bool = False


class QueryDetailResponse(BaseModel):
    """Detailed step-by-step view of a single query."""

    query_id: uuid.UUID
    query_text: str
    steps: list[StepDetail]
    langfuse_trace_url: str | None = None


class LangfuseURLResponse(BaseModel):
    """Deep link to Langfuse trace for a query."""

    url: str | None


class AssessmentRunSummary(BaseModel):
    """Summary of a single assessment run."""

    id: uuid.UUID
    trigger: str
    total_queries: int
    passed_queries: int
    pass_rate: float
    total_cost_usd: float
    started_at: datetime
    completed_at: datetime


class AssessmentHistoryResponse(BaseModel):
    """List of historical assessment runs."""

    items: list[AssessmentRunSummary]


class SortByEnum(str, Enum):
    """Sortable columns for query list."""

    timestamp = "timestamp"
    total_cost_usd = "total_cost_usd"
    duration_ms = "duration_ms"
    llm_calls = "llm_calls"
    score = "score"


class SortOrderEnum(str, Enum):
    """Sort direction."""

    asc = "asc"
    desc = "desc"


class StatusFilterEnum(str, Enum):
    """Query status filter values."""

    completed = "completed"
    error = "error"
    declined = "declined"
    timeout = "timeout"


class GroupByEnum(str, Enum):
    """Grouping dimensions for query aggregation."""

    agent_type = "agent_type"
    date = "date"
    model = "model"
    status = "status"
    provider = "provider"
    tier = "tier"
    tool_name = "tool_name"
    user = "user"
    intent_category = "intent_category"


class DateBucketEnum(str, Enum):
    """Date bucketing granularity."""

    day = "day"
    week = "week"
    month = "month"


class GroupRow(BaseModel):
    """Single row in a grouped aggregation result."""

    key: str
    query_count: int
    total_cost_usd: float
    avg_cost_usd: float
    avg_latency_ms: float
    error_rate: float


class GroupedResponse(BaseModel):
    """Response for grouped query aggregation."""

    group_by: str
    bucket: str | None = None
    groups: list[GroupRow]
    total_queries: int
