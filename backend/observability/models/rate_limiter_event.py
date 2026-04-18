"""SQLAlchemy model for observability.rate_limiter_event.

Records every rate-limiter action (acquire, wait, fallback) emitted by the
platform's internal token-bucket and sliding-window rate limiters, providing
visibility into back-pressure, starvation, and fallback frequency.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class RateLimiterEvent(Base):
    """Row-per-rate-limiter-action stored as a TimescaleDB hypertable.

    The table lives in the ``observability`` schema and is partitioned by ``ts``
    (1-day chunks). Rows are dropped after 30 days via a retention policy.

    Attributes:
        id: Surrogate primary key (UUID, server-generated).
        ts: Wall-clock timestamp of the event (with timezone). Hypertable partition key.
        trace_id: Distributed trace ID for correlation with external API calls.
        span_id: Span ID at the time the limiter was invoked.
        limiter_name: Logical name of the rate limiter (e.g. "yfinance", "openai_chat").
        action: Action taken: "acquired", "waited", "rejected", "fallback".
        wait_time_ms: How long the caller blocked waiting for a token (ms).
        tokens_remaining: Token bucket / window quota remaining after the action.
        reason_if_fallback: Human-readable reason when action == "fallback".
        env: Deployment environment ("dev", "staging", "prod").
        git_sha: Git commit SHA of the running binary.
    """

    __tablename__ = "rate_limiter_event"
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
    limiter_name: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    wait_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason_if_fallback: Mapped[str | None] = mapped_column(Text, nullable=True)
    env: Mapped[str] = mapped_column(Text, nullable=False)
    git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
