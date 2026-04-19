"""SQLAlchemy model for observability.oauth_event_log.

Records every OAuth provider flow event: authorize start, code exchange,
token refresh, account link/unlink, and conflict detection.
Low-volume table — regular (non-hypertable) with row-level DELETE retention.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class OAuthEventLog(Base):
    """Row-per-OAuth-flow-event log in the observability schema.

    Not a TimescaleDB hypertable — OAuth events are low volume.
    Retention enforced via row-level DELETE (90-day window).

    Attributes:
        id: Surrogate primary key (UUID, server-generated).
        ts: Wall-clock timestamp of the event (with timezone).
        trace_id: Distributed trace ID, if available.
        user_id: Authenticated user, if known at time of event.
        provider: OAuth provider name (e.g. "google").
        action: OAuth flow step (OAuthAction enum value).
        status: "success" or "failure".
        error_reason: Structured error description on failure.
        attempt_number: Retry count (0 = first attempt).
        extra_data: Additional structured context (JSONB).
        env: Deployment environment ("dev", "staging", "prod").
        git_sha: Git commit SHA of the running binary.
    """

    __tablename__ = "oauth_event_log"
    __table_args__ = (
        Index("ix_oauth_event_log_trace_id", "trace_id"),
        Index("ix_oauth_event_log_ts", "ts"),
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
    trace_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    span_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    env: Mapped[str] = mapped_column(Text, nullable=False)
    git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
