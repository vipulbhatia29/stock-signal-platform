"""Daily signal convergence snapshot — tracks alignment of all indicators."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin


class SignalConvergenceDaily(TimestampMixin, Base):
    """Pre-computed daily convergence state per ticker.

    Powers historical pattern analysis: "when this divergence pattern
    happened before, the forecast was right X% of the time."
    """

    __tablename__ = "signal_convergence_daily"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), primary_key=True)
    rsi_direction: Mapped[str] = mapped_column(String(10), nullable=False)
    macd_direction: Mapped[str] = mapped_column(String(10), nullable=False)
    sma_direction: Mapped[str] = mapped_column(String(10), nullable=False)
    piotroski_direction: Mapped[str] = mapped_column(String(10), nullable=False)
    forecast_direction: Mapped[str] = mapped_column(String(10), nullable=False)
    news_sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)
    signals_aligned: Mapped[int] = mapped_column(Integer, nullable=False)
    convergence_label: Mapped[str] = mapped_column(String(20), nullable=False)
    composite_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_return_90d: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_return_180d: Mapped[float | None] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<SignalConvergenceDaily {self.ticker} {self.date} {self.convergence_label}>"
