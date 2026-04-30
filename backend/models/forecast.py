"""Forecast and recommendation evaluation models."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ModelVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tracks every trained forecast model for versioning, rollback, and accuracy."""

    __tablename__ = "model_versions"

    ticker: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("stocks.ticker", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_type: Mapped[str] = mapped_column(String(20), nullable=False, default="prophet")
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    training_data_start: Mapped[date] = mapped_column(Date, nullable=False)
    training_data_end: Mapped[date] = mapped_column(Date, nullable=False)
    data_points: Mapped[int] = mapped_column(Integer, nullable=False)
    hyperparameters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    artifact_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<ModelVersion {self.ticker} v{self.version} ({self.status})>"


class ForecastResult(Base):
    """One row per ticker per horizon per forecast date — TimescaleDB hypertable."""

    __tablename__ = "forecast_results"

    forecast_date: Mapped[date] = mapped_column(Date, primary_key=True)
    ticker: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("stocks.ticker", ondelete="CASCADE"),
        primary_key=True,
    )
    horizon_days: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    expected_return_pct: Mapped[float] = mapped_column(Float, nullable=False)
    return_lower_pct: Mapped[float] = mapped_column(Float, nullable=False)
    return_upper_pct: Mapped[float] = mapped_column(Float, nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    actual_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    drivers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    base_price: Mapped[float] = mapped_column(Float, nullable=False)
    forecast_signal: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<ForecastResult {self.ticker} {self.forecast_date} +{self.horizon_days}d>"


class RecommendationOutcome(UUIDPrimaryKeyMixin, Base):
    """Evaluation of past BUY/SELL recommendations at 30/90/180d horizons."""

    __tablename__ = "recommendation_outcomes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["rec_generated_at", "rec_ticker"],
            ["recommendation_snapshots.generated_at", "recommendation_snapshots.ticker"],
            ondelete="CASCADE",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    rec_generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rec_ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    price_at_recommendation: Mapped[float] = mapped_column(Float, nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual_price: Mapped[float] = mapped_column(Float, nullable=False)
    return_pct: Mapped[float] = mapped_column(Float, nullable=False)
    spy_return_pct: Mapped[float] = mapped_column(Float, nullable=False)
    alpha_pct: Mapped[float] = mapped_column(Float, nullable=False)
    action_was_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<RecommendationOutcome {self.rec_ticker} "
            f"{self.action} {self.horizon_days}d "
            f"correct={self.action_was_correct}>"
        )
