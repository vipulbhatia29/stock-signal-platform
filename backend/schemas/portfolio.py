"""Pydantic v2 schemas for portfolio endpoints."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class TransactionCreate(BaseModel):
    """Request body for logging a BUY or SELL transaction."""

    ticker: str = Field(..., min_length=1, max_length=10)
    transaction_type: str = Field(..., pattern="^(BUY|SELL)$")
    shares: Decimal = Field(..., gt=0, decimal_places=4)
    price_per_share: Decimal = Field(..., gt=0, decimal_places=4)
    transacted_at: datetime
    notes: str | None = None

    model_config = {"str_strip_whitespace": True}

    @field_validator("ticker", mode="before")
    @classmethod
    def normalise_ticker(cls, v: str) -> str:
        """Normalise ticker to uppercase and strip whitespace."""
        return v.upper().strip()


class TransactionResponse(BaseModel):
    """Response schema for a single transaction."""

    id: UUID
    portfolio_id: UUID
    ticker: str
    transaction_type: str
    shares: float
    price_per_share: float
    transacted_at: datetime
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionListResponse(BaseModel):
    """Paginated transaction list."""

    transactions: list[TransactionResponse]
    total: int


class PositionResponse(BaseModel):
    """Current position with live P&L fields."""

    ticker: str
    shares: float
    avg_cost_basis: float
    current_price: float | None
    market_value: float | None
    unrealized_pnl: float | None
    unrealized_pnl_pct: float | None
    allocation_pct: float | None
    sector: str | None = None

    model_config = {"from_attributes": True}


class SectorAllocation(BaseModel):
    """Sector breakdown entry for the allocation panel."""

    sector: str
    market_value: float
    pct: float
    over_limit: bool  # True if pct exceeds user's max_sector_pct


class PortfolioSummaryResponse(BaseModel):
    """Portfolio KPI totals + sector breakdown."""

    total_value: float
    total_cost_basis: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    position_count: int
    sectors: list[SectorAllocation]


class PortfolioSnapshotResponse(BaseModel):
    """A single daily portfolio value snapshot."""

    snapshot_date: datetime
    total_value: float
    total_cost_basis: float
    unrealized_pnl: float
    position_count: int

    model_config = {"from_attributes": True}


class DividendResponse(BaseModel):
    """A single dividend payment record."""

    ticker: str
    ex_date: datetime
    amount: float

    model_config = {"from_attributes": True}


class DividendSummaryResponse(BaseModel):
    """Dividend summary for a ticker: history + aggregated stats."""

    ticker: str
    total_received: float
    annual_dividends: float
    dividend_yield: float | None
    last_ex_date: datetime | None
    payment_count: int
    history: list[DividendResponse]


# ---------------------------------------------------------------------------
# Divestment rules
# ---------------------------------------------------------------------------

AlertRule = Literal[
    "stop_loss",
    "position_concentration",
    "sector_concentration",
    "weak_fundamentals",
]
AlertSeverity = Literal["critical", "warning"]


class DivestmentAlert(BaseModel):
    """A single divestment alert fired by the rules engine."""

    rule: AlertRule
    severity: AlertSeverity
    message: str
    value: float
    threshold: float


class PositionWithAlerts(PositionResponse):
    """Position response enriched with divestment alerts."""

    alerts: list[DivestmentAlert] = []


# ---------------------------------------------------------------------------
# User preferences
# ---------------------------------------------------------------------------


class UserPreferenceResponse(BaseModel):
    """Response schema for user investment preferences."""

    default_stop_loss_pct: float
    max_position_pct: float
    max_sector_pct: float
    min_cash_reserve_pct: float
    rebalancing_strategy: str | None = "min_volatility"

    model_config = {"from_attributes": True}


class UserPreferenceUpdate(BaseModel):
    """Partial update schema for user investment preferences."""

    default_stop_loss_pct: float | None = Field(None, gt=0, le=100)
    max_position_pct: float | None = Field(None, gt=0, le=100)
    max_sector_pct: float | None = Field(None, gt=0, le=100)
    min_cash_reserve_pct: float | None = Field(None, gt=0, le=100)
    rebalancing_strategy: Literal["min_volatility", "max_sharpe", "risk_parity"] | None = None


# ---------------------------------------------------------------------------
# Rebalancing
# ---------------------------------------------------------------------------


class RebalancingSuggestion(BaseModel):
    """Single rebalancing suggestion for one position."""

    ticker: str
    action: str  # "BUY_MORE" | "HOLD" | "AT_CAP"
    current_allocation_pct: float | None
    target_allocation_pct: float
    suggested_amount: float  # 0.0 means no action needed
    reason: str


class RebalancingResponse(BaseModel):
    """Full rebalancing output for the portfolio."""

    total_value: float
    available_cash: float
    num_positions: int
    suggestions: list[RebalancingSuggestion]


# ---------------------------------------------------------------------------
# Portfolio Analytics (QuantStats)
# ---------------------------------------------------------------------------


class PortfolioAnalyticsResponse(BaseModel):
    """QuantStats portfolio-level analytics from the latest portfolio snapshot."""

    sharpe: float | None = None
    sortino: float | None = None
    max_drawdown: float | None = None
    max_drawdown_duration: int | None = None
    calmar: float | None = None
    alpha: float | None = None
    beta: float | None = None
    var_95: float | None = None
    cagr: float | None = None
    data_days: int | None = None

    model_config = {"from_attributes": True}
