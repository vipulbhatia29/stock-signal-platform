"""SQLAlchemy model for observability.agent_reasoning_log.

Records per-iteration reasoning snapshots from the ReAct loop.
Regular table (low volume). Retention enforced by Celery DELETE task (30 days).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class AgentReasoningLog(Base):
    """Per-ReAct-iteration row in observability schema."""

    __tablename__ = "agent_reasoning_log"
    __table_args__ = (
        Index("ix_agent_reasoning_log_query_id_step", "query_id", "loop_step"),
        Index("ix_agent_reasoning_log_trace_id", "trace_id"),
        Index("ix_agent_reasoning_log_ts", "ts"),
        {"schema": "observability"},
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    trace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    span_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    parent_span_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    session_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    query_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)

    loop_step: Mapped[int] = mapped_column(Integer, nullable=False)
    reasoning_type: Mapped[str] = mapped_column(Text, nullable=False)
    content_summary: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls_proposed: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    termination_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    env: Mapped[str] = mapped_column(Text, nullable=False)
    git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
