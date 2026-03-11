"""Stock index and index membership models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StockIndex(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A stock market index (e.g. S&P 500, NASDAQ-100, Dow 30)."""

    __tablename__ = "stock_indexes"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    memberships: Mapped[list[StockIndexMembership]] = relationship(
        back_populates="index", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """Return a string representation."""
        return f"<StockIndex(name={self.name!r}, slug={self.slug!r})>"


class StockIndexMembership(Base):
    """Association between a stock and an index."""

    __tablename__ = "stock_index_memberships"
    __table_args__ = (UniqueConstraint("ticker", "index_id", name="uq_ticker_index"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(
        ForeignKey("stocks.ticker", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    index_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stock_indexes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    removed_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    index: Mapped[StockIndex] = relationship(back_populates="memberships")

    def __repr__(self) -> str:
        """Return a string representation."""
        return f"<StockIndexMembership(ticker={self.ticker!r}, index_id={self.index_id!r})>"
