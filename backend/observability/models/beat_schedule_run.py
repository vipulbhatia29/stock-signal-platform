"""SQLAlchemy model for observability.beat_schedule_run.

Records beat schedule dispatch events. Regular table (not a hypertable) —
low volume. Retention enforced by Celery row-level DELETE task (90 days).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class BeatScheduleRun(Base):
    """Per-beat-dispatch row in observability schema.

    Attributes:
        id: Surrogate primary key (UUID, server-generated).
        ts: Event timestamp.
        trace_id: Distributed trace ID.
        span_id: Span ID for this event.
        task_name: Fully qualified Celery task name.
        scheduled_time: When the task was expected to run.
        actual_start_time: When the task was actually dispatched.
        drift_seconds: Difference between actual and scheduled.
        outcome: Dispatch outcome (dispatched, skipped, error).
        error_reason: Error message if outcome is error.
        env: Deployment environment.
        git_sha: Git commit SHA.
    """

    __tablename__ = "beat_schedule_run"
    __table_args__ = {"schema": "observability"}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    trace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    span_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)

    task_name: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual_start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    drift_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    env: Mapped[str] = mapped_column(Text, nullable=False)
    git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
