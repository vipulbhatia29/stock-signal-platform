"""SQLAlchemy model for observability.request_log.

Records every HTTP request as a TimescaleDB hypertable row in the
observability schema. Partitioned by ts (1-day chunks). Retention enforced
by Celery drop_chunks task (30 days).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class RequestLog(Base):
    """Per-HTTP-request row in observability schema.

    Attributes:
        id: Surrogate primary key (UUID, server-generated).
        ts: Wall-clock timestamp of the request (with timezone). Hypertable partition key.
        trace_id: Distributed trace ID from TraceIdMiddleware.
        span_id: Span ID for this request.
        user_id: Authenticated user, if known.
        session_id: Frontend session ID, if known.
        method: HTTP verb (GET, POST, …).
        path: Normalized path (UUIDs → {id}, tickers → {param}).
        raw_path: Original path for debugging.
        status_code: HTTP response status code.
        latency_ms: Round-trip latency in milliseconds.
        request_bytes: Content-Length of request body, if present.
        response_bytes: Content-Length of response body, if present.
        ip_address: Client IP address.
        user_agent: User-Agent header, truncated to 500 chars.
        referer: Referer header.
        environment_snapshot: Feature flags and obs config at request time.
        env: Deployment environment ("dev", "staging", "prod").
        git_sha: Git commit SHA of the running binary.
    """

    __tablename__ = "request_log"
    __table_args__ = (
        Index("ix_request_log_trace_id", "trace_id"),
        {"schema": "observability"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
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

    method: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    raw_path: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    request_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    referer: Mapped[str | None] = mapped_column(Text, nullable=True)

    environment_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    env: Mapped[str] = mapped_column(Text, nullable=False)
    git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
