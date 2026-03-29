"""Agent quality assessment models — periodic quality scoring."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class AssessmentRun(Base):
    """One row per assessment execution (weekly CI or on-demand)."""

    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4, primary_key=True)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    total_queries: Mapped[int] = mapped_column(Integer, nullable=False)
    passed_queries: Mapped[int] = mapped_column(Integer, nullable=False)
    pass_rate: Mapped[float] = mapped_column(Float, nullable=False)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<AssessmentRun {self.trigger} pass_rate={self.pass_rate:.0%}>"


class AssessmentResult(Base):
    """One row per golden query in an assessment run."""

    __tablename__ = "eval_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4, primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, name="eval_run_id"
    )
    query_index: Mapped[int] = mapped_column(Integer, nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    intent_category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False, default="react_v2")
    # Scores
    tool_selection_pass: Mapped[bool] = mapped_column(Boolean, nullable=False)
    grounding_score: Mapped[float] = mapped_column(Float, nullable=False)
    termination_pass: Mapped[bool] = mapped_column(Boolean, nullable=False)
    external_resilience_pass: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reasoning_coherence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Metadata
    tools_called: Mapped[dict] = mapped_column(JSONB, nullable=False)
    iteration_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    total_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    langfuse_trace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<AssessmentResult q{self.query_index} {self.intent_category}>"
