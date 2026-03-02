"""RecommendationSnapshot model — TimescaleDB hypertable."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class RecommendationSnapshot(Base):
    """Daily recommendation for a stock — stored as a TimescaleDB hypertable."""

    __tablename__ = "recommendation_snapshots"

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
    )
    ticker: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("stocks.ticker", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY, SELL, HOLD, WATCH
    confidence: Mapped[str] = mapped_column(String(10), nullable=False)  # HIGH, MEDIUM, LOW
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    price_at_recommendation: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    portfolio_weight_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_weight_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    suggested_amount_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    macro_regime: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reasoning: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_actionable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
