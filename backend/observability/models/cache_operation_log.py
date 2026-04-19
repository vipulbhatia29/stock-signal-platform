"""SQLAlchemy model for observability.cache_operation_log.

Records Redis cache operations (1% sampled for non-errors, 100% for errors)
as a TimescaleDB hypertable in the observability schema. Partitioned by ts
(6-hour chunks). Retention enforced by Celery drop_chunks task (7 days).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class CacheOperationLog(Base):
    """Per-cache-operation row in observability schema.

    Attributes:
        id: Surrogate primary key (UUID, server-generated).
        ts: Wall-clock timestamp of the operation (with timezone). Hypertable partition key.
        trace_id: Distributed trace ID.
        span_id: Span ID for this operation.
        user_id: Authenticated user, if known.
        session_id: Frontend session ID, if known.
        operation: Cache operation type (get, set, delete, mget).
        key_pattern: Redacted cache key (UUIDs/IDs replaced with *).
        hit: Whether the cache operation was a hit (for get operations).
        latency_ms: Operation latency in milliseconds.
        value_bytes: Size of the cached value in bytes (for set operations).
        ttl_seconds: TTL set on the key (for set operations).
        error_reason: Error classification if the operation failed.
        env: Deployment environment.
        git_sha: Git commit SHA of the running binary.
    """

    __tablename__ = "cache_operation_log"
    __table_args__ = (
        Index("ix_cache_operation_log_operation", "operation"),
        Index("ix_cache_operation_log_trace_id", "trace_id"),
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

    operation: Mapped[str] = mapped_column(Text, nullable=False)
    key_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    value_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ttl_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    env: Mapped[str] = mapped_column(Text, nullable=False)
    git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
