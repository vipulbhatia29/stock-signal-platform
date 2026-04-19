"""SQLAlchemy model for observability.db_pool_event.

Records database connection pool state changes (exhaustion, recovery,
slow checkouts, connection errors). Regular table (not a hypertable) —
low volume. Retention enforced by Celery row-level DELETE task (90 days).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class DbPoolEvent(Base):
    """Per-pool-event row in observability schema.

    Attributes:
        id: Surrogate primary key (UUID, server-generated).
        ts: Wall-clock timestamp of the event (with timezone).
        trace_id: Distributed trace ID.
        span_id: Span ID for this event.
        user_id: Authenticated user, if known.
        session_id: Frontend session ID, if known.
        pool_event_type: Type of pool event (exhausted, recovered, etc.).
        pool_size: Configured pool size.
        checked_out: Number of currently checked-out connections.
        overflow: Number of overflow connections in use.
        duration_ms: Duration of checkout wait (for slow_checkout events).
        env: Deployment environment.
        git_sha: Git commit SHA of the running binary.
    """

    __tablename__ = "db_pool_event"
    __table_args__ = (
        Index("ix_db_pool_event_trace_id", "trace_id"),
        Index("ix_db_pool_event_ts", "ts"),
        {"schema": "observability"},
    )

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
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    session_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)

    pool_event_type: Mapped[str] = mapped_column(Text, nullable=False)
    pool_size: Mapped[int] = mapped_column(Integer, nullable=False)
    checked_out: Mapped[int] = mapped_column(Integer, nullable=False)
    overflow: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    env: Mapped[str] = mapped_column(Text, nullable=False)
    git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
