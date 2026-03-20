"""EarningsSnapshot model — quarterly EPS estimates, actuals, and surprise."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class EarningsSnapshot(Base):
    """Quarterly earnings data — materialized from yfinance during ingestion."""

    __tablename__ = "earnings_snapshots"

    ticker: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("stocks.ticker", ondelete="CASCADE"),
        primary_key=True,
    )
    quarter: Mapped[str] = mapped_column(
        String(10),
        primary_key=True,
    )  # e.g. "2025-12-31"

    eps_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_actual: Mapped[float | None] = mapped_column(Float, nullable=True)
    surprise_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        """Debug representation."""
        return f"<EarningsSnapshot {self.ticker} Q={self.quarter} EPS={self.eps_actual}>"
