"""Pydantic v2 response schemas for forecast and scorecard endpoints."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class ForecastDriver(BaseModel):
    """Single feature driving a forecast."""

    feature: str
    label: str
    direction: str  # "bullish" | "bearish"
    importance: float = Field(ge=0.0, le=1.0)


class ForecastHorizon(BaseModel):
    """Forecast at a single horizon — return-based."""

    horizon_days: int
    expected_return_pct: float
    return_lower_pct: float
    return_upper_pct: float
    target_date: date
    direction: str  # "bullish" | "bearish" | "neutral"
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_level: str = "medium"
    drivers: list[ForecastDriver] | None = None
    implied_target_price: float | None = None
    forecast_signal: str | None = None


class ModelAccuracy(BaseModel):
    """Model performance metrics."""

    direction_hit_rate: float = Field(ge=0.0, le=1.0)
    avg_error_pct: float = Field(ge=0.0)
    ci_containment_rate: float = Field(ge=0.0, le=1.0)
    evaluated_count: int


class ForecastResponse(BaseModel):
    """Forecast data for a single ticker."""

    ticker: str
    current_price: float
    horizons: list[ForecastHorizon]
    model_type: str = "lightgbm"
    model_accuracy: ModelAccuracy | None = None
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


class ForecastEvaluation(BaseModel):
    """Single evaluated forecast with actual outcome."""

    forecast_date: date
    target_date: date
    horizon_days: int
    expected_return_pct: float
    return_lower_pct: float
    return_upper_pct: float
    actual_return_pct: float | None
    error_pct: float
    direction_correct: bool


class ForecastTrackRecordSummary(BaseModel):
    """Aggregate accuracy stats for a ticker's forecasts."""

    total_evaluated: int
    direction_hit_rate: float = Field(ge=0.0, le=1.0)
    avg_error_pct: float = Field(ge=0.0)
    ci_containment_rate: float = Field(ge=0.0, le=1.0)


class ForecastTrackRecordResponse(BaseModel):
    """Full track record for a ticker's forecast history."""

    ticker: str
    evaluations: list[ForecastEvaluation]
    summary: ForecastTrackRecordSummary
