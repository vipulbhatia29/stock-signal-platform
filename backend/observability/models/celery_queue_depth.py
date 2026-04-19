"""SQLAlchemy model for observability.celery_queue_depth.

Records periodic queue depth snapshots as a TimescaleDB hypertable in
the observability schema. Partitioned by ts (1-hour chunks). Retention
enforced by Celery drop_chunks task (7 days).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class CeleryQueueDepth(Base):
    """Per-queue-depth-snapshot row in observability schema.

    Attributes:
        id: Surrogate primary key (UUID, server-generated).
        ts: Snapshot timestamp. Hypertable partition key.
        trace_id: Distributed trace ID.
        span_id: Span ID for this snapshot.
        queue_name: Name of the Redis queue (e.g. "celery").
        depth: Number of pending tasks in the queue.
        env: Deployment environment.
        git_sha: Git commit SHA.
    """

    __tablename__ = "celery_queue_depth"
    __table_args__ = (
        Index("ix_celery_queue_depth_queue_name", "queue_name"),
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

    queue_name: Mapped[str] = mapped_column(Text, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)

    env: Mapped[str] = mapped_column(Text, nullable=False)
    git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
