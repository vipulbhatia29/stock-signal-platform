"""In-app alert model for user-facing notifications."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, UUIDPrimaryKeyMixin


class InAppAlert(UUIDPrimaryKeyMixin, Base):
    """User-facing notification stored for the bell icon dropdown."""

    __tablename__ = "in_app_alerts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(30), server_default="info", nullable=False)
    title: Mapped[str] = mapped_column(String(200), server_default="", nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(10), nullable=True)
    dedup_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<InAppAlert {self.alert_type} user={self.user_id} read={self.is_read}>"
