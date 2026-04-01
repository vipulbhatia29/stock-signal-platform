"""SignalSnapshot model — TimescaleDB hypertable."""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class SignalSnapshot(Base):
    """Point-in-time technical signal computation — stored as a TimescaleDB hypertable."""

    __tablename__ = "signal_snapshots"

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
    )
    ticker: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("stocks.ticker", ondelete="CASCADE"),
        primary_key=True,
    )

    # RSI
    rsi_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    rsi_signal: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # MACD
    macd_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    macd_histogram: Mapped[float | None] = mapped_column(Float, nullable=True)
    macd_signal_label: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # SMA
    sma_50: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma_200: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma_signal: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Bollinger Bands
    bb_upper: Mapped[float | None] = mapped_column(Float, nullable=True)
    bb_lower: Mapped[float | None] = mapped_column(Float, nullable=True)
    bb_position: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Returns & Risk
    annual_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    volatility: Mapped[float | None] = mapped_column(Float, nullable=True)
    sharpe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)

    # QuantStats per-stock metrics (vs SPY benchmark)
    sortino: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)
    alpha: Mapped[float | None] = mapped_column(Float, nullable=True)
    beta: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Price
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Composite
    composite_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    composite_weights: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
