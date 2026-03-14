"""Pydantic v2 schemas for portfolio endpoints."""

from datetime import datetime
from decimal import Decimal
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

    model_config = {"from_attributes": True}


class SectorAllocation(BaseModel):
    """Sector breakdown entry for the allocation panel."""

    sector: str
    market_value: float
    pct: float
    over_limit: bool  # True if pct > 30


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
