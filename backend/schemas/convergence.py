"""Pydantic v2 schemas for signal convergence endpoints."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class DirectionEnum(str, Enum):
    """Signal direction classification."""

    bullish = "bullish"
    bearish = "bearish"
    neutral = "neutral"


class ConvergenceLabelEnum(str, Enum):
    """Convergence label for a set of signals."""

    strong_bull = "strong_bull"
    weak_bull = "weak_bull"
    mixed = "mixed"
    weak_bear = "weak_bear"
    strong_bear = "strong_bear"


class SignalDirectionDetail(BaseModel):
    """Direction classification for a single signal."""

    signal: str = Field(description="Signal name (rsi, macd, sma, piotroski, forecast, news)")
    direction: DirectionEnum
    value: float | None = Field(
        default=None,
        description="Raw signal value (e.g. RSI=42, MACD histogram=0.03)",
    )


class DivergenceAlert(BaseModel):
    """Alert when forecast direction disagrees with technical majority."""

    is_divergent: bool = Field(
        description="True when forecast disagrees with the technical majority"
    )
    forecast_direction: DirectionEnum | None = Field(
        default=None,
        description="Direction the forecast predicts (when divergent)",
    )
    technical_majority: DirectionEnum | None = Field(
        default=None,
        description="Direction the majority of technicals indicate (when divergent)",
    )
    historical_hit_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="How often the forecast was right in similar past divergences (0-1)",
    )
    sample_count: int | None = Field(
        default=None,
        description="Number of historical cases used to compute the hit rate",
    )


class ConvergenceResponse(BaseModel):
    """Full convergence data for a single ticker."""

    ticker: str
    date: date
    signals: list[SignalDirectionDetail]
    signals_aligned: int = Field(
        ge=0, le=6, description="Count of signals in the majority direction"
    )
    convergence_label: ConvergenceLabelEnum
    composite_score: float | None = Field(default=None, description="Composite signal score (0-10)")
    divergence: DivergenceAlert
    rationale: str | None = Field(
        default=None,
        description="Human-readable explanation of the convergence state",
    )


class PortfolioPositionConvergence(BaseModel):
    """Convergence summary for a single portfolio position."""

    ticker: str
    weight: float = Field(description="Position weight in portfolio (0-1)")
    convergence_label: ConvergenceLabelEnum
    signals_aligned: int = Field(ge=0, le=6)
    divergence: DivergenceAlert


class PortfolioConvergenceResponse(BaseModel):
    """Convergence summary for an entire portfolio."""

    portfolio_id: str
    date: date
    positions: list[PortfolioPositionConvergence]
    bullish_pct: float = Field(
        ge=0.0,
        le=1.0,
        description="Weight-adjusted % of portfolio that is bullish-aligned",
    )
    bearish_pct: float = Field(
        ge=0.0,
        le=1.0,
        description="Weight-adjusted % of portfolio that is bearish-aligned",
    )
    mixed_pct: float = Field(
        ge=0.0,
        le=1.0,
        description="Weight-adjusted % of portfolio that is mixed",
    )
    divergent_positions: list[str] = Field(
        default_factory=list,
        description="Tickers where forecast diverges from technical majority",
    )


class ConvergenceHistoryRow(BaseModel):
    """Single row of convergence history."""

    date: date
    convergence_label: ConvergenceLabelEnum
    signals_aligned: int = Field(ge=0, le=6)
    composite_score: float | None = None
    actual_return_90d: float | None = None
    actual_return_180d: float | None = None


class ConvergenceHistoryResponse(BaseModel):
    """Convergence history for a ticker over time."""

    ticker: str
    data: list[ConvergenceHistoryRow]
    total: int
    limit: int
    offset: int


class SectorTickerConvergence(BaseModel):
    """Convergence summary for a single ticker within a sector."""

    ticker: str
    convergence_label: ConvergenceLabelEnum
    signals_aligned: int = Field(ge=0, le=6)


class SectorConvergenceResponse(BaseModel):
    """Equal-weight aggregated convergence for a sector."""

    sector: str
    date: date
    tickers: list[SectorTickerConvergence]
    bullish_pct: float = Field(ge=0.0, le=1.0)
    bearish_pct: float = Field(ge=0.0, le=1.0)
    mixed_pct: float = Field(ge=0.0, le=1.0)
    ticker_count: int
