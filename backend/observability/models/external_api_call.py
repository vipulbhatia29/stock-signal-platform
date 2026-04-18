"""SQLAlchemy model for observability.external_api_call_log.

Records every outbound HTTP call made by the platform (yfinance, Finnhub, OpenAI, etc.)
with provider identity, latency, status, error classification, rate-limit metadata,
and an optional call-stack fingerprint for hot-path attribution.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CHAR, DateTime, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class ExternalApiCallLog(Base):
    """Row-per-outbound-HTTP-call log stored as a TimescaleDB hypertable.

    The table lives in the ``observability`` schema and is partitioned by ``ts``
    (1-day chunks). Compression is applied after 7 days; rows are dropped after
    30 days via a retention policy.

    Attributes:
        id: Surrogate primary key (UUID, server-generated).
        ts: Wall-clock timestamp of the call (with timezone). Hypertable partition key.
        trace_id: Distributed trace ID propagated from the incoming HTTP request.
        span_id: Span ID for this specific outbound call.
        parent_span_id: Parent span ID (None for root spans).
        user_id: Authenticated user who triggered the call, if known.
        provider: Provider name (e.g. "yfinance", "openai"). See ExternalProvider enum.
        endpoint: URL path or logical endpoint (e.g. "/v1/chat/completions").
        method: HTTP method (GET, POST, …).
        status_code: HTTP response status code. None on network/timeout errors.
        error_reason: Structured error classification. See ErrorReason enum.
        latency_ms: Round-trip latency in milliseconds (always recorded).
        request_bytes: Request body size in bytes.
        response_bytes: Response body size in bytes.
        retry_count: Number of retries attempted (0 = first attempt succeeded).
        cost_usd: Provider-reported or estimated cost in USD for this call.
        rate_limit_remaining: Remaining quota from provider response headers.
        rate_limit_reset_ts: Timestamp when the rate-limit quota resets.
        rate_limit_headers: Raw rate-limit headers as JSONB for full fidelity.
        stack_signature: Human-readable call-stack summary for attribution.
        stack_hash: SHA-256 hex digest of the normalised stack for grouping.
        env: Deployment environment ("dev", "staging", "prod").
        git_sha: Git commit SHA of the running binary.
    """

    __tablename__ = "external_api_call_log"
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
    trace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    span_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    parent_span_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    request_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default="0")
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    rate_limit_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_limit_reset_ts: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rate_limit_headers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    stack_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    stack_hash: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    env: Mapped[str] = mapped_column(Text, nullable=False)
    git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
