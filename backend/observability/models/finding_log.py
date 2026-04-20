"""SQLAlchemy model for observability.finding_log.

Stores anomaly engine findings with evidence, remediation hints, and
lifecycle tracking (open → acknowledged → resolved | suppressed).
Regular table (not hypertable) — moderate volume. Retention: 180 days.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class FindingLog(Base):
    """Anomaly finding row in observability schema."""

    __tablename__ = "finding_log"
    __table_args__ = (
        Index("ix_finding_log_status_severity_opened", "status", "severity", "opened_at"),
        Index("ix_finding_log_dedup_key_status", "dedup_key", "status"),
        Index("ix_finding_log_attribution_kind_opened", "attribution_layer", "kind", "opened_at"),
        {"schema": "observability"},
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    attribution_layer: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False)
    remediation_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_traces: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=False)), nullable=True)

    acknowledged_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suppressed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    suppression_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    dedup_key: Mapped[str] = mapped_column(Text, nullable=False)
    jira_ticket_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    negative_check_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    env: Mapped[str] = mapped_column(Text, nullable=False)
