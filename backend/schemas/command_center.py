"""Command Center API response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DatabaseHealth(BaseModel):
    """Database connection pool health."""

    healthy: bool
    latency_ms: float
    pool_active: int
    pool_size: int
    pool_overflow: int
    migration_head: str | None = None


class RedisHealth(BaseModel):
    """Redis connection health."""

    healthy: bool
    latency_ms: float
    memory_used_mb: float | None = None
    memory_max_mb: float | None = None
    total_keys: int | None = None


class McpHealth(BaseModel):
    """MCP subprocess health."""

    healthy: bool
    mode: str
    tool_count: int
    restarts: int
    uptime_seconds: int | None = None


class CeleryHealth(BaseModel):
    """Celery worker health."""

    workers: int | None = None
    queued: int | None = None
    beat_active: bool | None = None


class LangfuseHealth(BaseModel):
    """Langfuse tracing health."""

    connected: bool = False
    traces_today: int = 0
    spans_today: int = 0


class SystemHealthZone(BaseModel):
    """Zone 1: System health dashboard."""

    status: str  # "ok" | "degraded"
    database: DatabaseHealth
    redis: RedisHealth
    mcp: McpHealth
    celery: CeleryHealth
    langfuse: LangfuseHealth


class ApiTrafficZone(BaseModel):
    """Zone 2: HTTP API traffic metrics."""

    window_seconds: int = 300
    sample_count: int = 0
    rps_avg: float = 0
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    latency_p99_ms: float | None = None
    error_rate_pct: float | None = None
    total_requests_today: int = 0
    total_errors_today: int = 0
    top_endpoints: list[dict] = Field(default_factory=list)


class TierHealth(BaseModel):
    """LLM tier health status."""

    model: str
    status: str
    failures_5m: int = 0
    successes_5m: int = 0
    cascade_count: int = 0
    latency: dict = Field(default_factory=dict)


class TokenBudgetStatus(BaseModel):
    """Per-model token budget utilization."""

    model: str
    tpm_used_pct: float = 0
    rpm_used_pct: float = 0


class LlmOperationsZone(BaseModel):
    """Zone 3: LLM operations dashboard."""

    tiers: list[TierHealth] = Field(default_factory=list)
    cost_today_usd: float = 0
    cost_yesterday_usd: float = 0
    cost_week_usd: float = 0
    cascade_rate_pct: float = 0
    token_budgets: list[TokenBudgetStatus] = Field(default_factory=list)


class PipelineLastRun(BaseModel):
    """Latest pipeline run summary."""

    started_at: str
    status: str
    total_duration_seconds: float | None = None
    tickers_succeeded: int = 0
    tickers_failed: int = 0
    tickers_total: int = 0
    step_durations: dict | None = None


class PipelineWatermarkStatus(BaseModel):
    """Pipeline watermark status."""

    pipeline: str
    last_date: str
    status: str


class PipelineZone(BaseModel):
    """Zone 4: Pipeline status dashboard."""

    last_run: PipelineLastRun | None = None
    watermarks: list[PipelineWatermarkStatus] = Field(default_factory=list)
    next_run_at: str | None = None


class CommandCenterMeta(BaseModel):
    """Assembly metadata."""

    assembly_ms: int = 0
    degraded_zones: list[str] = Field(default_factory=list)


class CommandCenterResponse(BaseModel):
    """Full command center aggregate response."""

    timestamp: str
    meta: CommandCenterMeta = Field(default_factory=CommandCenterMeta)
    system_health: SystemHealthZone | dict | None = None
    api_traffic: ApiTrafficZone | dict | None = None
    llm_operations: LlmOperationsZone | dict | None = None
    pipeline: PipelineZone | dict | None = None
