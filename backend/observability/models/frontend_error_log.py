"""SQLAlchemy model for observability.frontend_error_log.

Records frontend JavaScript errors captured via the beacon API endpoint.
Regular table (not hypertable) — moderate volume with 30d retention.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class FrontendErrorLog(Base):
    """Row-per-error log for frontend JavaScript errors.

    Attributes:
        id: Surrogate primary key (UUID, server-generated).
        ts: Wall-clock timestamp of the error (with timezone).
        trace_id: Distributed trace ID from the last API response.
        user_id: Authenticated user, if known (pre-auth errors won't have this).
        error_type: Classification (unhandled_rejection, react_error_boundary, etc.).
        error_message: Human-readable error message (truncated 1KB).
        error_stack: Stack trace (truncated 5KB).
        page_route: URL pathname where the error occurred.
        component_name: React component name from error boundary info.
        user_agent: Browser User-Agent string.
        url: Full URL or script filename.
        frontend_metadata: Additional structured context (JSONB).
        env: Deployment environment.
        git_sha: Git commit SHA of the running backend.
    """

    __tablename__ = "frontend_error_log"
    __table_args__ = (
        Index("ix_frontend_error_log_trace_id", "trace_id"),
        Index("ix_frontend_error_log_ts", "ts"),
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
    parent_span_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    error_type: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_stack: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_route: Mapped[str | None] = mapped_column(Text, nullable=True)
    component_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    frontend_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    env: Mapped[str] = mapped_column(Text, nullable=False)
    git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
