"""Stock and Watchlist models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.models.user import User


class Stock(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Stock ticker in the universe."""

    __tablename__ = "stocks"

    ticker: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    exchange: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Profile (materialized from yfinance during ingestion)
    business_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    employees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Market data
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Growth & margins
    revenue_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_margins: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_margins: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_margins: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_on_equity: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Market risk & income (populated during ingestion from yfinance)
    beta: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    forward_pe: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Analyst targets
    analyst_target_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    analyst_target_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    analyst_target_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    analyst_buy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    analyst_hold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    analyst_sell: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ETF flag
    is_etf: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Watchlist(UUIDPrimaryKeyMixin, Base):
    """User's watchlist entry."""

    __tablename__ = "watchlist"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(
        ForeignKey("stocks.ticker", ondelete="CASCADE"),
        nullable=False,
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    price_acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # Relationships
    user: Mapped[User] = relationship(back_populates="watchlist_items")
    stock: Mapped[Stock] = relationship()
