"""Backtest run results for Prophet model validation."""

import uuid as _uuid
from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin


class BacktestRun(TimestampMixin, Base):
    """Walk-forward backtest result for a single ticker+horizon+config."""

    __tablename__ = "backtest_runs"

    id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    ticker: Mapped[str] = mapped_column(String(10), ForeignKey("stocks.ticker"), nullable=False)
    model_version_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_versions.id"), nullable=False
    )
    config_label: Mapped[str] = mapped_column(String(30), nullable=False)
    train_start: Mapped[date] = mapped_column(Date, nullable=False)
    train_end: Mapped[date] = mapped_column(Date, nullable=False)
    test_start: Mapped[date] = mapped_column(Date, nullable=False)
    test_end: Mapped[date] = mapped_column(Date, nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    num_windows: Mapped[int] = mapped_column(Integer, nullable=False)
    mape: Mapped[float] = mapped_column(Float, nullable=False)
    mae: Mapped[float] = mapped_column(Float, nullable=False)
    rmse: Mapped[float] = mapped_column(Float, nullable=False)
    direction_accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    ci_containment: Mapped[float] = mapped_column(Float, nullable=False)
    market_regime: Mapped[str | None] = mapped_column(String(20), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    __table_args__ = (
        Index(
            "ix_backtest_runs_ticker_horizon",
            "ticker",
            "horizon_days",
            "created_at",
            postgresql_using="btree",
        ),
    )

    def __repr__(self) -> str:
        return f"<BacktestRun {self.ticker} h={self.horizon_days} mape={self.mape:.3f}>"
