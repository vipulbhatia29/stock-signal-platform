"""Pydantic schemas for backtest API."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class BacktestRunResponse(BaseModel):
    """Single backtest run result."""

    id: UUID
    ticker: str
    model_version_id: UUID
    config_label: str
    horizon_days: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    num_windows: int
    mape: float
    mae: float
    rmse: float
    direction_accuracy: float
    ci_containment: float
    market_regime: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class BacktestSummaryItem(BaseModel):
    """Per-ticker backtest summary (latest run per horizon)."""

    ticker: str
    horizon_days: int
    mape: float
    direction_accuracy: float
    ci_containment: float
    market_regime: str | None = None
    config_label: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BacktestSummaryResponse(BaseModel):
    """All tickers sorted by accuracy."""

    items: list[BacktestSummaryItem]
    total: int


class BacktestTriggerRequest(BaseModel):
    """Request to trigger a backtest run."""

    ticker: str | None = Field(None, description="Specific ticker, or None for all")
    horizon_days: int = Field(90, description="Forecast horizon to backtest")


class BacktestTriggerResponse(BaseModel):
    """Response after triggering a backtest."""

    task_id: str
    status: str = "queued"
