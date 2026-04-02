"""Admin audit logging for pipeline and cache operations."""

import uuid as _uuid

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin


class AdminAuditLog(TimestampMixin, Base):
    """Tracks admin actions: pipeline triggers, cache clears, etc."""

    __tablename__ = "admin_audit_log"

    id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    user_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    target: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    __table_args__ = (Index("ix_audit_user_created", "user_id", "created_at"),)

    def __repr__(self) -> str:
        return f"<AdminAuditLog {self.action} target={self.target}>"
