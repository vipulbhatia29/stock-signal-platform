"""SQLAlchemy model for observability.auth_event_log.

Records every auth lifecycle event: JWT failures, token refresh, logout,
email verification, password reset, session revocation, and account deletion.
Low-volume table — regular (non-hypertable) with row-level DELETE retention.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class AuthEventLog(Base):
    """Row-per-auth-event log in the observability schema.

    Not a TimescaleDB hypertable — auth events are low volume and do not
    require time-series partitioning. Retention is enforced via row-level
    DELETE by a Celery Beat task (90-day window).

    Attributes:
        id: Surrogate primary key (UUID, server-generated).
        ts: Wall-clock timestamp of the event (with timezone).
        trace_id: Distributed trace ID from TraceIdMiddleware.
        span_id: Span ID for this event.
        user_id: Authenticated user who triggered the event, if known.
        event_type: Auth event subtype (AuthEventType enum value).
        outcome: "success" or "failure".
        failure_reason: Structured failure reason string, if applicable.
        ip_address: Client IP address, if available.
        user_agent: User-Agent header, if available.
        method: HTTP method of the triggering request, if available.
        path: Normalized request path, if available.
        extra_data: Additional structured context (JSONB).
        env: Deployment environment ("dev", "staging", "prod").
        git_sha: Git commit SHA of the running binary.
    """

    __tablename__ = "auth_event_log"
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
    trace_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    span_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    method: Mapped[str | None] = mapped_column(Text, nullable=True)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    env: Mapped[str] = mapped_column(Text, nullable=False)
    git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
