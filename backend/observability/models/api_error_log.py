"""SQLAlchemy model for observability.api_error_log.

Records every 4xx/5xx HTTP error as a TimescaleDB hypertable row in the
observability schema. Partitioned by ts (1-day chunks). Retention enforced
by Celery drop_chunks task (90 days).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class ApiErrorLog(Base):
    """HTTP error row (4xx + 5xx) in observability schema.

    Attributes:
        id: Surrogate primary key (UUID, server-generated).
        ts: Wall-clock timestamp of the error (with timezone). Hypertable partition key.
        trace_id: Distributed trace ID for correlation with request_log.
        span_id: Span ID at the time of the error.
        user_id: Authenticated user, if known.
        status_code: HTTP response status code.
        error_type: Structured error classification (auth, not_found, etc.).
        error_reason: Optional sub-reason for the error.
        error_message: PII-redacted error message (via redact_message()).
        stack_signature: Human-readable call-stack summary for attribution.
        stack_hash: SHA-256 hex digest of stack for grouping (64 chars).
        stack_trace: Full stack trace (5xx only, capped at 5KB).
        exception_class: Fully-qualified exception class name.
        env: Deployment environment ("dev", "staging", "prod").
        git_sha: Git commit SHA of the running binary.
    """

    __tablename__ = "api_error_log"
    __table_args__ = (
        Index("ix_api_error_log_trace_id", "trace_id"),
        Index("ix_api_error_log_stack_hash", "stack_hash"),
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

    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    error_type: Mapped[str] = mapped_column(Text, nullable=False)
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stack_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    stack_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    exception_class: Mapped[str | None] = mapped_column(Text, nullable=True)

    env: Mapped[str] = mapped_column(Text, nullable=False)
    git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
