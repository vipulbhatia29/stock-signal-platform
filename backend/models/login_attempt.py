"""Login attempt audit trail for security monitoring and compliance."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, UUIDPrimaryKeyMixin


class LoginAttempt(UUIDPrimaryKeyMixin, Base):
    """Audit log of login attempts for brute force detection and compliance.

    Retained for 90 days, then purged by a Celery Beat task.
    """

    __tablename__ = "login_attempts"

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    method: Mapped[str] = mapped_column(String(20), nullable=False, default="password")
    provider_sub: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        """Return debug representation."""
        return f"<LoginAttempt email={self.email!r} success={self.success}>"
