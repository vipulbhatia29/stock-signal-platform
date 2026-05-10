"""Pydantic schemas for Decision Attribution (KAN-569)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class SnapshotRowSchema(BaseModel):
    """A single parsed row from a Fidelity CSV."""

    ticker: str
    description: str = ""
    shares: Decimal
    price: Decimal
    cost_basis: Decimal = Field(description="Total cost basis (not per-share)")
    market_value: Decimal
    asset_type: str = "Equity"
    avg_cost_basis: Decimal = Field(description="Computed: cost_basis / shares")


class ImportWarning(BaseModel):
    """Non-fatal issue found during CSV parsing."""

    row: int | None = None
    message: str


class CsvValidationError(BaseModel):
    """Fatal validation error - user must fix their CSV."""

    row: int | None = None
    message: str


class ImportResult(BaseModel):
    """Response from POST /portfolio/import-snapshot."""

    imported: int = Field(description="Number of positions stored")
    warnings: list[ImportWarning] = Field(default_factory=list)
    errors: list[CsvValidationError] = Field(default_factory=list)
    changes_detected: int = 0
    attributions_matched: int = 0
    is_baseline: bool = False
    is_duplicate: bool = False

    model_config = {"from_attributes": True}


class PositionChangeResponse(BaseModel):
    """A single detected position change from a CSV diff."""

    id: str
    ticker: str
    detected_at: datetime
    prev_shares: float
    new_shares: float
    delta_shares: float
    implied_action: str
    attribution_status: str

    model_config = {"from_attributes": True}
