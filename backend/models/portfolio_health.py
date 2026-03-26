"""Daily portfolio health score snapshot — TimescaleDB hypertable."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class PortfolioHealthSnapshot(Base):
    """Daily portfolio health score snapshot — one row per portfolio per day."""

    __tablename__ = "portfolio_health_snapshots"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
        primary_key=True,
    )
    snapshot_date: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        primary_key=True,
    )
    health_score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    grade: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    diversification_score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    signal_quality_score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    risk_score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    income_score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    sector_balance_score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    hhi: Mapped[float] = mapped_column(sa.Float, nullable=False)
    weighted_beta: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    weighted_sharpe: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    weighted_yield: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    position_count: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<PortfolioHealthSnapshot {self.portfolio_id} "
            f"{self.snapshot_date} score={self.health_score}>"
        )
