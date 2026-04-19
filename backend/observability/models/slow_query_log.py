"""SQLAlchemy model for observability.slow_query_log.

Records SQL queries exceeding the slow query threshold (500ms) as a
TimescaleDB hypertable row in the observability schema. Partitioned by
ts (1-day chunks). Retention enforced by Celery drop_chunks task (30 days).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class SlowQueryLog(Base):
    """Per-slow-query row in observability schema.

    Attributes:
        id: Surrogate primary key (UUID, server-generated).
        ts: Wall-clock timestamp of the query (with timezone). Hypertable partition key.
        trace_id: Distributed trace ID from TraceIdMiddleware.
        span_id: Span ID for this query.
        user_id: Authenticated user, if known.
        session_id: Frontend session ID, if known.
        query_text: Normalized query with literals replaced by $N placeholders.
        query_hash: SHA256 hash of normalized query for grouping.
        duration_ms: Query execution time in milliseconds.
        rows_affected: Number of rows returned or affected.
        source_file: Python source file that initiated the query.
        source_line: Line number in source file.
        env: Deployment environment.
        git_sha: Git commit SHA of the running binary.
    """

    __tablename__ = "slow_query_log"
    __table_args__ = (
        Index("ix_slow_query_log_query_hash", "query_hash"),
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
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    session_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)

    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_hash: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_affected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_line: Mapped[int | None] = mapped_column(Integer, nullable=True)

    env: Mapped[str] = mapped_column(Text, nullable=False)
    git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
