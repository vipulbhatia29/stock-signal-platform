"""HistoricalFeature model — training dataset for forecast ensemble."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class HistoricalFeature(Base):
    """Per-ticker-per-day feature vector for ML training.

    Backfilled from stock_prices using vectorized pandas-ta.
    Separate from signal_snapshots (different column set, no side effects).
    TimescaleDB hypertable partitioned by date.

    Float (not Numeric) is intentional — ML features don't need exact decimal
    precision, and double precision is standard for gradient boosting inputs.

    IMPORTANT for PR1 training queries: rows where forward_return_60d or
    forward_return_90d is NULL must be filtered out before training. Use
    WHERE forward_return_Xd IS NOT NULL in the training data query.

    No updated_at column: this table uses ON CONFLICT DO UPDATE upsert
    semantics, so created_at reflects the last write time. A separate
    updated_at would be redundant and is omitted intentionally.
    """

    __tablename__ = "historical_features"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    ticker: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("stocks.ticker", ondelete="CASCADE"),
        primary_key=True,
    )

    # Technical features (11 columns — all from price math)
    momentum_21d: Mapped[float] = mapped_column(Float, nullable=False)
    momentum_63d: Mapped[float] = mapped_column(Float, nullable=False)
    momentum_126d: Mapped[float] = mapped_column(Float, nullable=False)
    rsi_value: Mapped[float] = mapped_column(Float, nullable=False)
    macd_histogram: Mapped[float] = mapped_column(Float, nullable=False)
    # sma_cross: 0=BELOW_BOTH, 1=ABOVE_50_ONLY, 2=ABOVE_BOTH
    sma_cross: Mapped[int] = mapped_column(Integer, nullable=False)
    # bb_position: 0=LOWER, 1=MIDDLE, 2=UPPER
    bb_position: Mapped[int] = mapped_column(Integer, nullable=False)
    volatility: Mapped[float] = mapped_column(Float, nullable=False)
    sharpe_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    vix_level: Mapped[float] = mapped_column(Float, nullable=False)
    spy_momentum_21d: Mapped[float] = mapped_column(Float, nullable=False)

    # Gate indicators (confirmation-gate scoring v2)
    adx_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    obv_slope: Mapped[float | None] = mapped_column(Float, nullable=True)
    mfi_value: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Sentiment features (NaN for historical rows — model handles missing natively)
    stock_sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)
    sector_sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)
    macro_sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Convergence features (NaN for backfill — Phase 3 addition, avoids future migration)
    signals_aligned: Mapped[int | None] = mapped_column(Integer, nullable=True)
    convergence_label: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Forward return targets (log returns — NaN for last 90 days)
    forward_return_60d: Mapped[float | None] = mapped_column(Float, nullable=True)
    forward_return_90d: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<HistoricalFeature {self.ticker} {self.date}>"
