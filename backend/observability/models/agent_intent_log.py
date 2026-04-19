"""SQLAlchemy model for observability.agent_intent_log.

Records intent classification results. Regular table (low volume).
Retention enforced by Celery row-level DELETE task (30 days).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class AgentIntentLog(Base):
    """Per-intent-classification row in observability schema."""

    __tablename__ = "agent_intent_log"
    __table_args__ = (
        Index("ix_agent_intent_log_query_id", "query_id"),
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
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    session_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    query_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)

    intent: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    out_of_scope: Mapped[bool] = mapped_column(Boolean, nullable=False)
    decline_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    query_text_hash: Mapped[str] = mapped_column(Text, nullable=False)

    env: Mapped[str] = mapped_column(Text, nullable=False)
    git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
