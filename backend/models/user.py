"""User and UserPreference models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, time, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Time,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.models.stock import Watchlist


class UserRole(str, enum.Enum):
    """User role enum."""

    ADMIN = "admin"
    USER = "user"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Platform user."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda e: [m.value for m in e]),
        default=UserRole.USER,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    preference: Mapped[UserPreference | None] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    watchlist_items: Mapped[list[Watchlist]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserPreference(UUIDPrimaryKeyMixin, Base):
    """User-configurable preferences."""

    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    timezone: Mapped[str] = mapped_column(String(50), default="America/New_York", nullable=False)
    default_stop_loss_pct: Mapped[float] = mapped_column(Float, default=20.0, nullable=False)
    max_position_pct: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    max_sector_pct: Mapped[float] = mapped_column(Float, default=30.0, nullable=False)
    min_cash_reserve_pct: Mapped[float] = mapped_column(Float, default=10.0, nullable=False)
    notify_telegram: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notify_email: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quiet_hours_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    quiet_hours_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    composite_weights: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user: Mapped[User] = relationship(back_populates="preference")
