"""Pydantic v2 response schemas for forecast and scorecard endpoints."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class ForecastHorizon(BaseModel):
    """Forecast at a single horizon."""

    horizon_days: int
    predicted_price: float = Field(ge=0.01)
    predicted_lower: float = Field(ge=0.01)
    predicted_upper: float = Field(ge=0.01)
    target_date: date
    confidence_level: str = "medium"
    sharpe_direction: str = "flat"


class ForecastResponse(BaseModel):
    """Forecast data for a single ticker."""

    ticker: str
    horizons: list[ForecastHorizon]
    model_mape: float | None = None
    model_status: str = "active"


class PortfolioForecastHorizon(BaseModel):
    """Portfolio-level forecast at a single horizon."""

    horizon_days: int
    expected_return_pct: float
    lower_pct: float
    upper_pct: float
    diversification_ratio: float = 1.0
    confidence_level: str = "medium"


class PortfolioForecastResponse(BaseModel):
    """Aggregated portfolio forecast."""

    horizons: list[PortfolioForecastHorizon]
    ticker_count: int
    vix_regime: str = "normal"
    missing_tickers: list[str] = Field(default_factory=list)


class SectorForecastResponse(BaseModel):
    """Forecast for a sector via its ETF proxy."""

    sector: str
    etf_ticker: str
    horizons: list[ForecastHorizon]
    user_exposure_pct: float = 0.0
    user_tickers_in_sector: list[str] = Field(default_factory=list)


class HorizonBreakdownResponse(BaseModel):
    """Scorecard breakdown for a single horizon."""

    horizon_days: int
    total: int
    correct: int
    hit_rate: float
    avg_alpha: float


class ScorecardResponse(BaseModel):
    """Recommendation performance scorecard."""

    total_outcomes: int
    overall_hit_rate: float
    avg_alpha: float
    buy_hit_rate: float
    sell_hit_rate: float
    worst_miss_pct: float
    worst_miss_ticker: str
    by_horizon: list[HorizonBreakdownResponse] = Field(default_factory=list)
