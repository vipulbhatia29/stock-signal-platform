"""SQLAlchemy model for observability.email_send_log.

Records every email send attempt/outcome. Email addresses are SHA256-hashed
before storage for PII protection. Low-volume table — regular (non-hypertable)
with row-level DELETE retention.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class EmailSendLog(Base):
    """Row-per-email-send log in the observability schema.

    Email addresses are SHA256-hashed for PII protection (recipient_hash field).
    Not a TimescaleDB hypertable — email volume is low.
    Retention enforced via row-level DELETE (90-day window).

    Attributes:
        id: Surrogate primary key (UUID, server-generated).
        ts: Wall-clock timestamp of the send attempt (with timezone).
        trace_id: Distributed trace ID, if available.
        user_id: User who triggered the email send, if known.
        recipient_hash: SHA256 hex digest of the lowercased recipient email (64 chars).
        email_type: Email category (EmailType enum value).
        status: "sent", "failed", or "bounced".
        error_reason: Provider error description on failure.
        resend_message_id: Resend API message ID for delivery tracking.
        env: Deployment environment ("dev", "staging", "prod").
        git_sha: Git commit SHA of the running binary.
    """

    __tablename__ = "email_send_log"
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
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    recipient_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    email_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resend_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    env: Mapped[str] = mapped_column(Text, nullable=False)
    git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
