"""Pydantic v2 schemas for portfolio forecast API responses."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class BLExpectedReturn(BaseModel):
    """Black-Litterman expected return for a single ticker."""

    ticker: str
    expected_return: float  # Annualized, as decimal (e.g., 0.12 = 12%)
    view_confidence: float | None  # 0.0 to 0.95, None if no Prophet view


class BLSummary(BaseModel):
    """Black-Litterman portfolio summary."""

    portfolio_expected_return: float
    risk_free_rate: float
    per_ticker: list[BLExpectedReturn]


class MonteCarloPercentileBands(BaseModel):
    """Monte Carlo simulation percentile bands (time series)."""

    p5: list[float]
    p25: list[float]
    p50: list[float]
    p75: list[float]
    p95: list[float]


class MonteCarloSummary(BaseModel):
    """Monte Carlo simulation summary."""

    simulation_days: int
    initial_value: float
    terminal_median: float
    terminal_p5: float
    terminal_p95: float
    bands: MonteCarloPercentileBands


class CVaRSummary(BaseModel):
    """Conditional Value at Risk summary."""

    cvar_95_pct: float  # e.g., -12.5 means "expected loss of 12.5% in worst 5%"
    cvar_99_pct: float
    var_95_pct: float
    var_99_pct: float
    description_95: str  # "In a bad month (1-in-20): -12.5%"
    description_99: str  # "In a very bad month (1-in-100): -18.3%"


class PortfolioForecastFullResponse(BaseModel):
    """Complete portfolio forecast response."""

    portfolio_id: str
    forecast_date: date
    horizon_days: int
    bl: BLSummary
    monte_carlo: MonteCarloSummary
    cvar: CVaRSummary


class TickerComponent(BaseModel):
    """Prophet forecast component breakdown for a ticker."""

    ticker: str
    trend_pct: float
    stock_sentiment_pct: float | None = None
    sector_sentiment_pct: float | None = None
    macro_sentiment_pct: float | None = None
    net_forecast_pct: float


class PortfolioForecastComponentsResponse(BaseModel):
    """Prophet component breakdown per ticker."""

    portfolio_id: str
    components: list[TickerComponent]
