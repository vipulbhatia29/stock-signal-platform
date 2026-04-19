"""SQLAlchemy model for observability.celery_worker_heartbeat.

Records Celery worker heartbeats as a TimescaleDB hypertable in the
observability schema. Partitioned by ts (1-hour chunks). Retention
enforced by Celery drop_chunks task (7 days).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class CeleryWorkerHeartbeat(Base):
    """Per-heartbeat row in observability schema.

    Attributes:
        id: Surrogate primary key (UUID, server-generated).
        ts: Heartbeat timestamp. Hypertable partition key.
        trace_id: Distributed trace ID.
        span_id: Span ID for this heartbeat.
        worker_name: Celery worker name (e.g. "celery@hostname").
        hostname: Machine hostname.
        status: Worker lifecycle status (alive, draining, shutdown).
        tasks_in_flight: Number of currently executing tasks.
        queue_names: List of queues consumed by this worker.
        uptime_seconds: Worker uptime in seconds.
        env: Deployment environment.
        git_sha: Git commit SHA of the running binary.
    """

    __tablename__ = "celery_worker_heartbeat"
    __table_args__ = (
        Index("ix_celery_worker_heartbeat_worker_name", "worker_name"),
        {"schema": "observability"},
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        server_default=func.now(),
    )
    trace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    span_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)

    worker_name: Mapped[str] = mapped_column(Text, nullable=False)
    hostname: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    tasks_in_flight: Mapped[int] = mapped_column(Integer, nullable=False)
    queue_names: Mapped[list] = mapped_column(JSONB, nullable=False)
    uptime_seconds: Mapped[int] = mapped_column(Integer, nullable=False)

    env: Mapped[str] = mapped_column(Text, nullable=False)
    git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
