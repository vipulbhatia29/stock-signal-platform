"""Pydantic v2 schemas for admin pipeline endpoints."""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class TaskDefinitionResponse(BaseModel):
    """Single task definition in a group."""

    name: str
    display_name: str
    group: str
    order: int
    is_seed: bool
    schedule: str
    estimated_duration: str
    idempotent: bool
    incremental: bool
    rationale: str
    depends_on: list[str]


class PipelineGroupResponse(BaseModel):
    """A task group with its tasks."""

    name: str
    tasks: list[TaskDefinitionResponse]
    execution_plan: list[list[str]]  # Phases of parallel task names


class PipelineGroupListResponse(BaseModel):
    """All pipeline groups."""

    groups: list[PipelineGroupResponse]


class PipelineRunResponse(BaseModel):
    """Status of a pipeline run."""

    run_id: str
    group: str
    status: str
    started_at: str
    completed_at: str | None = None
    task_names: list[str]
    completed: int
    failed: int
    total: int
    task_statuses: dict[str, str]
    errors: dict[str, str]


class TriggerGroupRequest(BaseModel):
    """Request to trigger a pipeline group run."""

    failure_mode: str = "stop_on_failure"

    @field_validator("failure_mode")
    @classmethod
    def validate_failure_mode(cls, v: str) -> str:
        """Ensure failure_mode is a known value."""
        valid = {"stop_on_failure", "continue"}
        if v in valid:
            return v
        if v.startswith("threshold:"):
            try:
                n = float(v.split(":", 1)[1])
                if not (0 <= n <= 100):
                    msg = "threshold:N requires N between 0 and 100"
                    raise ValueError(msg)
            except (ValueError, IndexError) as exc:
                msg = "threshold:N requires N to be a number between 0 and 100"
                raise ValueError(msg) from exc
            return v
        msg = f"failure_mode must be one of {valid} or 'threshold:N'"
        raise ValueError(msg)


class TriggerGroupResponse(BaseModel):
    """Response after triggering a group run."""

    group: str
    status: str
    message: str


class CacheClearRequest(BaseModel):
    """Request to clear cache by pattern."""

    pattern: str


class CacheClearResponse(BaseModel):
    """Response after clearing cache."""

    pattern: str
    keys_deleted: int
    message: str


class RunHistoryResponse(BaseModel):
    """Run history for a group."""

    group: str
    runs: list[PipelineRunResponse]


class TriggerTaskResponse(BaseModel):
    """Response after triggering a single task."""

    task_name: str
    status: str
    message: str


class StageStatus(BaseModel):
    """Stage readiness status for a single ticker."""

    ticker: str
    prices: str
    signals: str
    fundamentals: str
    forecast: str
    forecast_retrain: str
    news: str
    sentiment: str
    convergence: str
    backtest: str
    recommendation: str
    overall: str


class HealthResponse(BaseModel):
    """Ingestion health for all tickers in the universe."""

    total: int
    tickers: list[StageStatus]


class AuditLogEntry(BaseModel):
    """Single audit log entry."""

    id: str
    user_id: str
    action: str
    target: str | None = None
    metadata: dict | None = None
    created_at: str


class AuditLogResponse(BaseModel):
    """Paginated audit log listing."""

    total: int
    limit: int
    offset: int
    entries: list[AuditLogEntry]
