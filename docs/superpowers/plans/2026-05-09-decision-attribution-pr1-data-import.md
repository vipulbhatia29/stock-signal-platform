# Decision Attribution PR1: Data Foundation + CSV Import

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add position snapshot storage, CSV diff engine, and Fidelity CSV import endpoint so users can upload portfolio CSVs and the system detects what changed.

**Architecture:** Three new tables (`position_snapshots`, `position_changes`, `decision_attributions`) added via Alembic migration. A Fidelity CSV parser with fuzzy column matching and silent fixes handles messy broker exports. A snapshot import service stores raw state, diffs against previous snapshot, and syncs positions. The import endpoint accepts file uploads and returns a structured result with warnings.

**Tech Stack:** SQLAlchemy 2.0, TimescaleDB (hypertable for snapshots), FastAPI UploadFile, Python csv module, hashlib SHA-256.

**Spec:** `docs/superpowers/specs/2026-05-09-decision-attribution-hit-rate.md`

---

## File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `backend/models/attribution.py` | SQLAlchemy models: PositionSnapshot, PositionChange, DecisionAttribution |
| Modify | `backend/models/__init__.py` | Register new models for Alembic discovery |
| Create | `backend/migrations/versions/*_046_decision_attribution_tables.py` | Migration: 3 tables + hypertable + indexes |
| Create | `backend/services/portfolio/csv_parser.py` | Fidelity CSV parsing, validation, fuzzy column matching |
| Create | `backend/services/portfolio/snapshot_import.py` | Snapshot storage, diff engine, Position sync, Watchlist sync |
| Create | `backend/schemas/attribution.py` | Pydantic schemas: ImportResult, SnapshotRow, validation errors |
| Modify | `backend/routers/portfolio.py` | New `POST /portfolio/import-snapshot` endpoint |
| Modify | `backend/services/portfolio/__init__.py` | Re-export new service functions |
| Create | `tests/unit/services/test_csv_parser.py` | CSV parser unit tests |
| Create | `tests/unit/services/test_snapshot_import.py` | Snapshot import service unit tests |
| Create | `tests/unit/routers/test_import_snapshot.py` | Endpoint unit tests |

---

### Task 1: Pydantic Schemas

**Files:**
- Create: `backend/schemas/attribution.py`

- [ ] **Step 1: Create schema file**

```python
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
    """Fatal validation error — user must fix their CSV."""

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
```

- [ ] **Step 2: Verify import works**

Run: `uv run python -c "from backend.schemas.attribution import ImportResult; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/schemas/attribution.py
git commit -m "feat(attribution): add Pydantic schemas for CSV import"
```

---

### Task 2: SQLAlchemy Models

**Files:**
- Create: `backend/models/attribution.py`
- Modify: `backend/models/__init__.py`

- [ ] **Step 1: Create the models file**

```python
"""Position snapshot, change tracking, and decision attribution models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PositionSnapshot(UUIDPrimaryKeyMixin, Base):
    """Raw position state from a single CSV import.

    One row per ticker per import. TimescaleDB hypertable on imported_at.
    Source of truth for attribution diffs — NOT the Position table.
    """

    __tablename__ = "position_snapshots"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(
        sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"),
        nullable=False,
    )
    imported_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    shares: Mapped[Decimal] = mapped_column(sa.Numeric(12, 4), nullable=False)
    avg_cost_basis: Mapped[Decimal] = mapped_column(sa.Numeric(12, 4), nullable=False)
    market_value: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2), nullable=True)
    current_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 4), nullable=True)
    asset_type: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    csv_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    is_baseline: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)

    __table_args__ = (
        sa.UniqueConstraint(
            "portfolio_id", "ticker", "imported_at",
            name="uq_position_snapshots_portfolio_ticker_imported",
        ),
        sa.Index(
            "ix_position_snapshots_portfolio_imported",
            "portfolio_id", sa.desc("imported_at"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PositionSnapshot ticker={self.ticker} shares={self.shares} "
            f"imported_at={self.imported_at}>"
        )


class PositionChange(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Detected delta between consecutive CSV snapshots.

    One row per ticker that changed. Drives the attribution matcher.
    """

    __tablename__ = "position_changes"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(
        sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"),
        nullable=False,
    )
    detected_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    snapshot_before_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("position_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    snapshot_after_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("position_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    prev_shares: Mapped[Decimal] = mapped_column(
        sa.Numeric(12, 4), nullable=False, default=0,
    )
    new_shares: Mapped[Decimal] = mapped_column(sa.Numeric(12, 4), nullable=False)
    delta_shares: Mapped[Decimal] = mapped_column(sa.Numeric(12, 4), nullable=False)
    prev_avg_cost_basis: Mapped[Decimal] = mapped_column(
        sa.Numeric(12, 4), nullable=False, default=0,
    )
    new_avg_cost_basis: Mapped[Decimal] = mapped_column(sa.Numeric(12, 4), nullable=False)
    implied_action: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    attribution_status: Mapped[str] = mapped_column(
        sa.String(10), nullable=False, default="pending",
    )

    __table_args__ = (
        sa.Index(
            "ix_position_changes_portfolio_detected",
            "portfolio_id", sa.desc("detected_at"),
        ),
        sa.Index(
            "ix_position_changes_portfolio_ticker",
            "portfolio_id", "ticker",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PositionChange ticker={self.ticker} {self.implied_action} "
            f"delta={self.delta_shares}>"
        )


class DecisionAttribution(UUIDPrimaryKeyMixin, Base):
    """Links a position change to a candidate recommendation.

    Multiple candidates per change (scored and ranked). One marked is_primary.
    No hard FK to recommendation_snapshots (hypertable composite PK) —
    key fields are denormalized.
    """

    __tablename__ = "decision_attributions"

    position_change_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("position_changes.id", ondelete="CASCADE"),
        nullable=False,
    )
    rec_generated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False,
    )
    rec_ticker: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    rec_user_id: Mapped[uuid.UUID] = mapped_column(sa.UUID(), nullable=False)
    rec_action: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    rec_confidence: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    match_score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    match_reason: Mapped[str] = mapped_column(sa.Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)
    user_verdict: Mapped[str | None] = mapped_column(sa.String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        sa.Index("ix_decision_attributions_change_id", "position_change_id"),
        sa.Index(
            "ix_decision_attributions_primary",
            "is_primary",
            postgresql_where=sa.text("is_primary = true"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<DecisionAttribution change={self.position_change_id} "
            f"rec={self.rec_action} score={self.match_score}>"
        )
```

- [ ] **Step 2: Register models in `__init__.py`**

Add to `backend/models/__init__.py` after the existing portfolio imports (line 34):

```python
from backend.models.attribution import (  # noqa: F401
    DecisionAttribution,
    PositionChange,
    PositionSnapshot,
)
```

Add to the `__all__` list:

```python
"DecisionAttribution",
"PositionChange",
"PositionSnapshot",
```

- [ ] **Step 3: Verify import works**

Run: `uv run python -c "from backend.models.attribution import PositionSnapshot, PositionChange, DecisionAttribution; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/models/attribution.py backend/models/__init__.py
git commit -m "feat(attribution): add PositionSnapshot, PositionChange, DecisionAttribution models"
```

---

### Task 3: Alembic Migration

**Files:**
- Create: `backend/migrations/versions/*_046_decision_attribution_tables.py`

- [ ] **Step 1: Generate migration**

Run: `uv run alembic revision --autogenerate -m "046_decision_attribution_tables"`

- [ ] **Step 2: Edit the migration**

Open the generated file. Verify it creates the 3 tables. Then append the hypertable creation and manually clean any false TimescaleDB index drops:

After the `create_table('position_snapshots', ...)` call in `upgrade()`, add:

```python
op.execute(
    "SELECT create_hypertable('position_snapshots', 'imported_at', "
    "chunk_time_interval => INTERVAL '3 months', migrate_data => true)"
)
```

Verify `downgrade()` drops tables in correct order (attributions → changes → snapshots) and does NOT drop any existing TimescaleDB indexes.

- [ ] **Step 3: Apply migration**

Run: `uv run alembic upgrade head`
Expected: No errors, migration applied.

- [ ] **Step 4: Verify migration head**

Run: `uv run alembic current`
Expected: Shows new revision as head.

- [ ] **Step 5: Commit**

```bash
git add backend/migrations/versions/*046*
git commit -m "feat(attribution): migration 046 — position_snapshots, position_changes, decision_attributions"
```

---

### Task 4: CSV Parser

**Files:**
- Create: `backend/services/portfolio/csv_parser.py`
- Create: `tests/unit/services/test_csv_parser.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for Fidelity CSV parser."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.services.portfolio.csv_parser import parse_fidelity_csv

# --- Fixtures ---

VALID_CSV = (
    '"Positions for account Designated Bene Individual as of 02:41 AM ET, 2026/04/30"\n'
    "\n"
    '"Symbol","Description","Qty (Quantity)","Price","Cost Basis","Mkt Val (Market Value)","Asset Type"\n'
    '"AAPL","APPLE INC","27.4355","270.84","$2,989.79","$7,430.63","Equity"\n'
    '"MSFT","MICROSOFT CORP","10.0","420.50","$3,500.00","$4,205.00","Equity"\n'
)

DOLLAR_SIGNS_CSV = (
    '"Symbol","Description","Qty (Quantity)","Price","Cost Basis","Mkt Val (Market Value)","Asset Type"\n'
    '"AAPL","APPLE INC","27.4355","$270.84","$2,989.79","$7,430.63","Equity"\n'
)

MISSING_QTY_COLUMN_CSV = (
    '"Symbol","Description","Price","Cost Basis"\n'
    '"AAPL","APPLE INC","270.84","$2,989.79"\n'
)

EMPTY_SYMBOL_CSV = (
    '"Symbol","Description","Qty (Quantity)","Price","Cost Basis","Mkt Val (Market Value)","Asset Type"\n'
    '"","APPLE INC","27.4355","270.84","$2,989.79","$7,430.63","Equity"\n'
)

BAD_QTY_CSV = (
    '"Symbol","Description","Qty (Quantity)","Price","Cost Basis","Mkt Val (Market Value)","Asset Type"\n'
    '"AAPL","APPLE INC","--","270.84","$2,989.79","$7,430.63","Equity"\n'
)

CASH_ROW_CSV = (
    '"Symbol","Description","Qty (Quantity)","Price","Cost Basis","Mkt Val (Market Value)","Asset Type"\n'
    '"AAPL","APPLE INC","27.4355","270.84","$2,989.79","$7,430.63","Equity"\n'
    '"Cash & Cash Investments","","","","","$1,234.56","Cash and Money Market"\n'
    '"Positions Total","","","","","$8,665.19",""\n'
)

DUPLICATE_TICKER_CSV = (
    '"Symbol","Description","Qty (Quantity)","Price","Cost Basis","Mkt Val (Market Value)","Asset Type"\n'
    '"AAPL","APPLE INC","27.4355","270.84","$2,989.79","$7,430.63","Equity"\n'
    '"AAPL","APPLE INC","10.0","270.84","$2,708.40","$2,708.40","Equity"\n'
)

LOWERCASE_TICKER_CSV = (
    '"Symbol","Description","Qty (Quantity)","Price","Cost Basis","Mkt Val (Market Value)","Asset Type"\n'
    '"aapl","APPLE INC","27.4355","270.84","$2,989.79","$7,430.63","Equity"\n'
)

NO_HEADER_CSV = "just some random text\nwith no recognizable columns\n"

COST_BASIS_MISSING_CSV = (
    '"Symbol","Description","Qty (Quantity)","Price","Cost Basis","Mkt Val (Market Value)","Asset Type"\n'
    '"AAPL","APPLE INC","10.0","270.84","--","$2,708.40","Equity"\n'
)


# --- Tests ---


class TestParseFidelityCsv:
    """CSV parser tests."""

    def test_valid_csv_parses_correctly(self) -> None:
        rows, warnings, errors = parse_fidelity_csv(VALID_CSV)
        assert len(rows) == 2
        assert rows[0].ticker == "AAPL"
        assert rows[0].shares == Decimal("27.4355")
        assert rows[0].price == Decimal("270.84")
        assert rows[0].avg_cost_basis == Decimal("2989.79") / Decimal("27.4355")
        assert rows[1].ticker == "MSFT"
        assert len(errors) == 0

    def test_strips_dollar_signs_and_commas(self) -> None:
        rows, warnings, errors = parse_fidelity_csv(DOLLAR_SIGNS_CSV)
        assert len(rows) == 1
        assert rows[0].cost_basis == Decimal("2989.79")

    def test_missing_required_column_returns_error(self) -> None:
        rows, warnings, errors = parse_fidelity_csv(MISSING_QTY_COLUMN_CSV)
        assert len(rows) == 0
        assert len(errors) == 1
        assert "Qty" in errors[0].message

    def test_empty_symbol_skipped(self) -> None:
        rows, warnings, errors = parse_fidelity_csv(EMPTY_SYMBOL_CSV)
        assert len(rows) == 0

    def test_bad_qty_skipped_with_warning(self) -> None:
        rows, warnings, errors = parse_fidelity_csv(BAD_QTY_CSV)
        assert len(rows) == 0
        assert any("not a valid number" in w.message for w in warnings)

    def test_cash_and_summary_rows_skipped(self) -> None:
        rows, warnings, errors = parse_fidelity_csv(CASH_ROW_CSV)
        assert len(rows) == 1
        assert rows[0].ticker == "AAPL"

    def test_duplicate_ticker_warns(self) -> None:
        rows, warnings, errors = parse_fidelity_csv(DUPLICATE_TICKER_CSV)
        assert len(rows) == 1
        assert any("appears twice" in w.message for w in warnings)

    def test_lowercase_ticker_uppercased(self) -> None:
        rows, warnings, errors = parse_fidelity_csv(LOWERCASE_TICKER_CSV)
        assert len(rows) == 1
        assert rows[0].ticker == "AAPL"

    def test_no_header_returns_error(self) -> None:
        rows, warnings, errors = parse_fidelity_csv(NO_HEADER_CSV)
        assert len(rows) == 0
        assert len(errors) == 1
        assert "header" in errors[0].message.lower()

    def test_cost_basis_missing_derived_from_price(self) -> None:
        rows, warnings, errors = parse_fidelity_csv(COST_BASIS_MISSING_CSV)
        assert len(rows) == 1
        assert rows[0].cost_basis == Decimal("270.84") * Decimal("10.0")
        assert any("no cost basis" in w.message.lower() or "cost basis" in w.message.lower() for w in warnings)

    def test_empty_string_returns_error(self) -> None:
        rows, warnings, errors = parse_fidelity_csv("")
        assert len(rows) == 0
        assert len(errors) >= 1

    def test_header_on_different_row(self) -> None:
        """Header not on row 3 — parser scans first 10 rows."""
        csv_content = (
            "Account summary info\n"
            "More info\n"
            "Even more info\n"
            "And more\n"
            '"Symbol","Description","Qty (Quantity)","Price","Cost Basis","Mkt Val (Market Value)","Asset Type"\n'
            '"AAPL","APPLE INC","10.0","270.84","$2,708.40","$2,708.40","Equity"\n'
        )
        rows, warnings, errors = parse_fidelity_csv(csv_content)
        assert len(rows) == 1
        assert rows[0].ticker == "AAPL"

    def test_bom_stripped(self) -> None:
        csv_content = (
            '\ufeff"Symbol","Description","Qty (Quantity)","Price","Cost Basis","Mkt Val (Market Value)","Asset Type"\n'
            '"AAPL","APPLE INC","10.0","270.84","$2,708.40","$2,708.40","Equity"\n'
        )
        rows, warnings, errors = parse_fidelity_csv(csv_content)
        assert len(rows) == 1

    def test_percentage_signs_stripped(self) -> None:
        csv_content = (
            '"Symbol","Description","Qty (Quantity)","Price","Cost Basis","Mkt Val (Market Value)","Asset Type"\n'
            '"AAPL","APPLE INC","10.0","270.84%","$2,708.40","$2,708.40","Equity"\n'
        )
        rows, warnings, errors = parse_fidelity_csv(csv_content)
        assert len(rows) == 1
        assert rows[0].price == Decimal("270.84")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/services/test_csv_parser.py -v`
Expected: ImportError — module `csv_parser` does not exist.

- [ ] **Step 3: Implement the parser**

```python
"""Fidelity CSV parser with fuzzy column matching and silent fixes.

Accepts Fidelity-format position CSVs with messy formatting
(dollar signs, percentages, varied column names, summary rows)
and returns clean parsed rows with warnings for ambiguous cases.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from decimal import Decimal, InvalidOperation

from backend.schemas.attribution import CsvValidationError, ImportWarning, SnapshotRowSchema

logger = logging.getLogger(__name__)

# Column aliases — fuzzy matching against these after normalizing
_COLUMN_ALIASES: dict[str, list[str]] = {
    "symbol": ["symbol", "ticker"],
    "qty": ["qty", "quantity", "shares"],
    "price": ["price", "last price", "current price"],
    "cost_basis": ["cost basis", "cost", "total cost"],
    "asset_type": ["asset type", "type"],
    "description": ["description", "name"],
    "market_value": ["mkt val", "market value"],
}

_REQUIRED_COLUMNS = {"symbol", "qty", "price", "cost_basis"}

_SKIP_SYMBOLS = frozenset({
    "", "cash & cash investments", "positions total",
    "pending activity",
})

_SKIP_ASSET_TYPES = frozenset({"cash and money market", ""})


def _normalize_header(raw: str) -> str:
    """Strip parentheticals, whitespace, and lowercase."""
    cleaned = re.sub(r"\([^)]*\)", "", raw)
    return cleaned.strip().lower()


def _resolve_columns(headers: list[str]) -> dict[str, int] | None:
    """Map our canonical names to column indexes via fuzzy alias matching.

    Returns None if any required column is missing.
    """
    normalized = [_normalize_header(h) for h in headers]
    mapping: dict[str, int] = {}

    for canonical, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            for idx, norm in enumerate(normalized):
                if norm == alias:
                    mapping[canonical] = idx
                    break
            if canonical in mapping:
                break

    return mapping if _REQUIRED_COLUMNS.issubset(mapping) else None


def _parse_decimal(val: str) -> Decimal | None:
    """Parse a decimal value, stripping $, commas, %, whitespace."""
    if not val or val.strip() in ("--", "N/A", "Incomplete", ""):
        return None
    cleaned = val.replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _find_header_row(lines: list[str]) -> int | None:
    """Scan first 10 lines for one containing 'Symbol'."""
    for i, line in enumerate(lines[:10]):
        if "symbol" in line.lower():
            return i
    return None


def parse_fidelity_csv(
    content: str,
) -> tuple[list[SnapshotRowSchema], list[ImportWarning], list[CsvValidationError]]:
    """Parse a Fidelity positions CSV into validated snapshot rows.

    Args:
        content: UTF-8 CSV text (raw file content).

    Returns:
        Tuple of (valid_rows, warnings, errors).
        If errors is non-empty, the import should be rejected.
    """
    warnings: list[ImportWarning] = []
    errors: list[CsvValidationError] = []
    rows: list[SnapshotRowSchema] = []

    if not content or not content.strip():
        errors.append(CsvValidationError(message="File is empty."))
        return rows, warnings, errors

    # Strip BOM
    content = content.lstrip("\ufeff")

    lines = content.splitlines()
    header_idx = _find_header_row(lines)

    if header_idx is None:
        errors.append(CsvValidationError(
            message="Could not find header row. Expected columns: Symbol, Qty, Price, Cost Basis",
        ))
        return rows, warnings, errors

    # Parse from header row onward
    csv_content = "\n".join(lines[header_idx:])
    reader = csv.reader(io.StringIO(csv_content))

    try:
        raw_headers = next(reader)
    except StopIteration:
        errors.append(CsvValidationError(message="File has header but no data rows."))
        return rows, warnings, errors

    col_map = _resolve_columns(raw_headers)
    if col_map is None:
        missing = _REQUIRED_COLUMNS - set(
            k for k, aliases in _COLUMN_ALIASES.items()
            if any(
                _normalize_header(h) == a
                for h in raw_headers
                for a in aliases
            )
        )
        errors.append(CsvValidationError(
            message=f"Missing column(s): {', '.join(missing)}. "
            "Required: Symbol, Qty, Price, Cost Basis",
        ))
        return rows, warnings, errors

    seen_tickers: set[str] = set()

    for row_num, fields in enumerate(reader, start=header_idx + 2):
        if len(fields) <= max(col_map.values()):
            continue  # Short row — skip silently

        symbol = fields[col_map["symbol"]].strip().upper()

        # Skip cash, summary, and blank rows
        if symbol.lower() in _SKIP_SYMBOLS:
            continue

        asset_type = ""
        if "asset_type" in col_map:
            asset_type = fields[col_map["asset_type"]].strip()
        if asset_type.lower() in _SKIP_ASSET_TYPES:
            continue

        # Duplicate check
        if symbol in seen_tickers:
            warnings.append(ImportWarning(
                row=row_num, message=f"{symbol} appears twice — first row used",
            ))
            continue
        seen_tickers.add(symbol)

        # Parse numeric fields
        shares = _parse_decimal(fields[col_map["qty"]])
        if shares is None or shares < 0:
            warnings.append(ImportWarning(
                row=row_num,
                message=f"Qty '{fields[col_map['qty']].strip()}' is not a valid number",
            ))
            continue

        price = _parse_decimal(fields[col_map["price"]])
        if price is None:
            price = Decimal("0")
            warnings.append(ImportWarning(
                row=row_num,
                message=f"{symbol} has no price — P&L metrics will be incomplete",
            ))

        cost_basis = _parse_decimal(fields[col_map["cost_basis"]])
        if cost_basis is None or cost_basis <= 0:
            if price > 0 and shares > 0:
                cost_basis = price * shares
                warnings.append(ImportWarning(
                    row=row_num,
                    message=f"{symbol} has no cost basis — estimated from Price × Qty",
                ))
            else:
                cost_basis = Decimal("0")

        market_value = Decimal("0")
        if "market_value" in col_map:
            market_value = _parse_decimal(fields[col_map["market_value"]]) or Decimal("0")
        if market_value == 0 and price > 0 and shares > 0:
            market_value = price * shares

        description = ""
        if "description" in col_map:
            description = fields[col_map["description"]].strip()

        avg_cost = cost_basis / shares if shares > 0 else Decimal("0")

        rows.append(SnapshotRowSchema(
            ticker=symbol,
            description=description,
            shares=shares,
            price=price,
            cost_basis=cost_basis,
            market_value=market_value,
            asset_type=asset_type or "Equity",
            avg_cost_basis=avg_cost,
        ))

    if not rows and not errors:
        errors.append(CsvValidationError(message="No valid positions found in CSV."))

    return rows, warnings, errors
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/services/test_csv_parser.py -v`
Expected: All 14 tests pass.

- [ ] **Step 5: Lint**

Run: `uv run ruff check --fix backend/services/portfolio/csv_parser.py tests/unit/services/test_csv_parser.py && uv run ruff format backend/services/portfolio/csv_parser.py tests/unit/services/test_csv_parser.py`

- [ ] **Step 6: Commit**

```bash
git add backend/services/portfolio/csv_parser.py tests/unit/services/test_csv_parser.py
git commit -m "feat(attribution): Fidelity CSV parser with fuzzy column matching"
```

---

### Task 5: Snapshot Import Service

**Files:**
- Create: `backend/services/portfolio/snapshot_import.py`
- Create: `tests/unit/services/test_snapshot_import.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for snapshot import service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.schemas.attribution import SnapshotRowSchema
from backend.services.portfolio.snapshot_import import (
    _classify_action,
    _compute_diffs,
    import_portfolio_snapshot,
)


class TestClassifyAction:
    """Unit tests for action classification logic."""

    def test_open_new_position(self) -> None:
        assert _classify_action(prev=Decimal("0"), new=Decimal("10")) == "OPEN"

    def test_add_to_position(self) -> None:
        assert _classify_action(prev=Decimal("10"), new=Decimal("20")) == "ADD"

    def test_trim_position(self) -> None:
        assert _classify_action(prev=Decimal("20"), new=Decimal("10")) == "TRIM"

    def test_close_position(self) -> None:
        assert _classify_action(prev=Decimal("10"), new=Decimal("0")) == "CLOSE"

    def test_no_change_returns_none(self) -> None:
        assert _classify_action(prev=Decimal("10"), new=Decimal("10")) is None


class TestComputeDiffs:
    """Unit tests for diff computation between two snapshot sets."""

    def test_new_ticker_is_open(self) -> None:
        prev: dict[str, tuple[Decimal, Decimal]] = {}
        curr = {"AAPL": (Decimal("10"), Decimal("150.00"))}
        diffs = _compute_diffs(prev, curr)
        assert len(diffs) == 1
        assert diffs[0]["ticker"] == "AAPL"
        assert diffs[0]["implied_action"] == "OPEN"
        assert diffs[0]["prev_shares"] == Decimal("0")

    def test_removed_ticker_is_close(self) -> None:
        prev = {"AAPL": (Decimal("10"), Decimal("150.00"))}
        curr: dict[str, tuple[Decimal, Decimal]] = {}
        diffs = _compute_diffs(prev, curr)
        assert len(diffs) == 1
        assert diffs[0]["implied_action"] == "CLOSE"
        assert diffs[0]["new_shares"] == Decimal("0")

    def test_increased_shares_is_add(self) -> None:
        prev = {"AAPL": (Decimal("10"), Decimal("150.00"))}
        curr = {"AAPL": (Decimal("20"), Decimal("155.00"))}
        diffs = _compute_diffs(prev, curr)
        assert len(diffs) == 1
        assert diffs[0]["implied_action"] == "ADD"
        assert diffs[0]["delta_shares"] == Decimal("10")

    def test_decreased_shares_is_trim(self) -> None:
        prev = {"AAPL": (Decimal("20"), Decimal("150.00"))}
        curr = {"AAPL": (Decimal("10"), Decimal("150.00"))}
        diffs = _compute_diffs(prev, curr)
        assert len(diffs) == 1
        assert diffs[0]["implied_action"] == "TRIM"

    def test_unchanged_shares_no_diff(self) -> None:
        prev = {"AAPL": (Decimal("10"), Decimal("150.00"))}
        curr = {"AAPL": (Decimal("10"), Decimal("150.00"))}
        diffs = _compute_diffs(prev, curr)
        assert len(diffs) == 0

    def test_multiple_changes(self) -> None:
        prev = {
            "AAPL": (Decimal("10"), Decimal("150.00")),
            "MSFT": (Decimal("5"), Decimal("400.00")),
        }
        curr = {
            "AAPL": (Decimal("20"), Decimal("155.00")),
            "NVDA": (Decimal("3"), Decimal("900.00")),
        }
        diffs = _compute_diffs(prev, curr)
        tickers = {d["ticker"] for d in diffs}
        assert tickers == {"AAPL", "MSFT", "NVDA"}
        actions = {d["ticker"]: d["implied_action"] for d in diffs}
        assert actions["AAPL"] == "ADD"
        assert actions["MSFT"] == "CLOSE"
        assert actions["NVDA"] == "OPEN"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/services/test_snapshot_import.py -v`
Expected: ImportError — module does not exist.

- [ ] **Step 3: Implement the service**

```python
"""Snapshot import service — store CSV snapshots, diff, sync positions.

Core flow:
1. Dedup check (csv_hash)
2. Baseline bootstrap (first import)
3. Store snapshot rows
4. Compute diffs against previous snapshot
5. Best-effort Position table sync
6. Watchlist sync
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.attribution import PositionChange, PositionSnapshot
from backend.models.portfolio import Portfolio, Position
from backend.models.stock import Watchlist
from backend.schemas.attribution import ImportResult, ImportWarning, SnapshotRowSchema
from backend.services.stock_data import ensure_stock_exists

logger = logging.getLogger(__name__)


def compute_csv_hash(content: str) -> str:
    """SHA-256 hash of raw CSV content for dedup."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _classify_action(*, prev: Decimal, new: Decimal) -> str | None:
    """Derive implied action from share delta.

    Returns None if shares are unchanged.
    """
    if prev == 0 and new > 0:
        return "OPEN"
    if prev > 0 and new > prev:
        return "ADD"
    if prev > 0 and new < prev and new > 0:
        return "TRIM"
    if prev > 0 and new == 0:
        return "CLOSE"
    return None


def _compute_diffs(
    prev: dict[str, tuple[Decimal, Decimal]],
    curr: dict[str, tuple[Decimal, Decimal]],
) -> list[dict]:
    """Compute position diffs between two snapshot states.

    Args:
        prev: {ticker: (shares, avg_cost)} from previous snapshot.
        curr: {ticker: (shares, avg_cost)} from current snapshot.

    Returns:
        List of diff dicts with keys: ticker, prev_shares, new_shares,
        delta_shares, prev_avg_cost_basis, new_avg_cost_basis, implied_action.
    """
    diffs: list[dict] = []
    all_tickers = set(prev) | set(curr)

    for ticker in sorted(all_tickers):
        prev_shares, prev_cost = prev.get(ticker, (Decimal("0"), Decimal("0")))
        new_shares, new_cost = curr.get(ticker, (Decimal("0"), Decimal("0")))

        action = _classify_action(prev=prev_shares, new=new_shares)
        if action is None:
            continue

        diffs.append({
            "ticker": ticker,
            "prev_shares": prev_shares,
            "new_shares": new_shares,
            "delta_shares": new_shares - prev_shares,
            "prev_avg_cost_basis": prev_cost,
            "new_avg_cost_basis": new_cost,
            "implied_action": action,
        })

    return diffs


async def _get_previous_snapshot(
    portfolio_id: uuid.UUID, db: AsyncSession,
) -> dict[str, tuple[Decimal, Decimal, uuid.UUID]]:
    """Load most recent snapshot for each ticker.

    Returns: {ticker: (shares, avg_cost, snapshot_id)}
    """
    # Find the most recent imported_at for this portfolio
    latest_q = (
        select(PositionSnapshot.imported_at)
        .where(PositionSnapshot.portfolio_id == portfolio_id)
        .order_by(PositionSnapshot.imported_at.desc())
        .limit(1)
    )
    latest_result = await db.execute(latest_q)
    latest_at = latest_result.scalar_one_or_none()

    if latest_at is None:
        return {}

    rows_q = (
        select(PositionSnapshot)
        .where(
            PositionSnapshot.portfolio_id == portfolio_id,
            PositionSnapshot.imported_at == latest_at,
        )
    )
    rows_result = await db.execute(rows_q)
    rows = rows_result.scalars().all()

    return {
        r.ticker: (r.shares, r.avg_cost_basis, r.id)
        for r in rows
    }


async def _create_baseline_from_positions(
    portfolio_id: uuid.UUID,
    csv_hash: str,
    db: AsyncSession,
) -> bool:
    """Generate baseline snapshot from existing Position table state.

    Called on first import when positions already exist (from seed).
    Returns True if baseline was created.
    """
    result = await db.execute(
        select(Position).where(
            Position.portfolio_id == portfolio_id,
            Position.shares > 0,
        )
    )
    positions = result.scalars().all()

    if not positions:
        return False

    now = datetime.now(timezone.utc)
    for pos in positions:
        snap = PositionSnapshot(
            portfolio_id=portfolio_id,
            ticker=pos.ticker,
            imported_at=now,
            shares=pos.shares,
            avg_cost_basis=pos.avg_cost_basis,
            csv_hash=f"baseline_{csv_hash}",
            is_baseline=True,
        )
        db.add(snap)

    await db.flush()
    logger.info(
        "Created baseline snapshot from %d existing positions for portfolio %s",
        len(positions), portfolio_id,
    )
    return True


async def _sync_positions(
    portfolio_id: uuid.UUID,
    rows: list[SnapshotRowSchema],
    db: AsyncSession,
) -> None:
    """Best-effort Position table sync from CSV state.

    Upserts positions to match CSV. This is a display convenience —
    attribution uses position_snapshots as source of truth.
    """
    now = datetime.now(timezone.utc)
    current_tickers = {r.ticker for r in rows}

    for row in rows:
        stmt = pg_insert(Position.__table__).values(
            id=uuid.uuid4(),
            portfolio_id=portfolio_id,
            ticker=row.ticker,
            shares=row.shares,
            avg_cost_basis=row.avg_cost_basis,
            opened_at=now,
            created_at=now,
            updated_at=now,
        ).on_conflict_on_constraint("uq_positions_portfolio_ticker").do_update(
            set_={
                "shares": row.shares,
                "avg_cost_basis": row.avg_cost_basis,
                "updated_at": now,
                "closed_at": None,
            }
        )
        await db.execute(stmt)

    # Close positions not in CSV
    close_result = await db.execute(
        select(Position).where(
            Position.portfolio_id == portfolio_id,
            Position.ticker.notin_(current_tickers),
            Position.closed_at.is_(None),
        )
    )
    for pos in close_result.scalars().all():
        pos.closed_at = now
        pos.shares = Decimal("0")

    await db.flush()


async def _sync_watchlist(
    user_id: uuid.UUID,
    tickers: set[str],
    db: AsyncSession,
) -> None:
    """Add imported tickers to user's watchlist. Skip existing."""
    result = await db.execute(
        select(Watchlist.ticker).where(Watchlist.user_id == user_id)
    )
    existing = {row[0] for row in result.all()}

    for ticker in tickers - existing:
        db.add(Watchlist(user_id=user_id, ticker=ticker))

    await db.flush()


async def import_portfolio_snapshot(
    portfolio_id: uuid.UUID,
    user_id: uuid.UUID,
    rows: list[SnapshotRowSchema],
    csv_hash: str,
    db: AsyncSession,
) -> ImportResult:
    """Import a parsed CSV snapshot into the database.

    Stores snapshot rows, computes diffs against previous snapshot,
    syncs Position table, and syncs watchlist.

    Args:
        portfolio_id: The user's portfolio ID.
        user_id: The authenticated user's ID.
        rows: Parsed and validated snapshot rows.
        csv_hash: SHA-256 of raw CSV content for dedup.
        db: Async SQLAlchemy session.

    Returns:
        ImportResult with counts and warnings.
    """
    warnings: list[ImportWarning] = []

    # 1. Dedup check
    existing = await db.execute(
        select(PositionSnapshot.imported_at)
        .where(
            PositionSnapshot.portfolio_id == portfolio_id,
            PositionSnapshot.csv_hash == csv_hash,
        )
        .limit(1)
    )
    dup_date = existing.scalar_one_or_none()
    if dup_date is not None:
        return ImportResult(
            imported=0,
            is_duplicate=True,
        )

    # 2. Baseline check
    prev_snapshot = await _get_previous_snapshot(portfolio_id, db)
    is_baseline = False

    if not prev_snapshot:
        # No prior snapshots — check if positions exist from seed
        created = await _create_baseline_from_positions(portfolio_id, csv_hash, db)
        if created:
            # Re-load the baseline we just created
            prev_snapshot = await _get_previous_snapshot(portfolio_id, db)
        else:
            is_baseline = True

    # 3. Auto-create stocks for unknown tickers
    # NOTE: ensure_stock_exists() calls db.commit() internally, which
    # breaks our transaction boundary. We run it as a pre-pass so that
    # stock creation commits are isolated. If a later step fails, we
    # have phantom stocks (harmless) but no phantom snapshots.
    failed_tickers: set[str] = set()
    for row in rows:
        try:
            await ensure_stock_exists(row.ticker, db)
        except ValueError:
            failed_tickers.add(row.ticker)
            warnings.append(ImportWarning(
                message=f"{row.ticker} not found — skipped. Is this a mutual fund?",
            ))

    # Filter to tickers that have a valid stock record
    valid_rows = [r for r in rows if r.ticker not in failed_tickers]

    # 4. Store snapshot
    now = datetime.now(timezone.utc)
    snapshot_map: dict[str, uuid.UUID] = {}

    for row in valid_rows:
        snap_id = uuid.uuid4()
        snap = PositionSnapshot(
            id=snap_id,
            portfolio_id=portfolio_id,
            ticker=row.ticker,
            imported_at=now,
            shares=row.shares,
            avg_cost_basis=row.avg_cost_basis,
            market_value=row.market_value,
            current_price=row.price,
            asset_type=row.asset_type,
            csv_hash=csv_hash,
            is_baseline=is_baseline,
        )
        db.add(snap)
        snapshot_map[row.ticker] = snap_id

    await db.flush()

    # 5. Compute diffs (skip if baseline)
    changes_detected = 0
    if not is_baseline and prev_snapshot:
        prev_state = {
            ticker: (shares, cost)
            for ticker, (shares, cost, _sid) in prev_snapshot.items()
        }
        curr_state = {
            row.ticker: (row.shares, row.avg_cost_basis)
            for row in valid_rows
        }
        diffs = _compute_diffs(prev_state, curr_state)

        for diff in diffs:
            ticker = diff["ticker"]
            before_id = prev_snapshot.get(ticker, (None, None, None))[2] if ticker in prev_snapshot else None
            after_id = snapshot_map.get(ticker)

            # For CLOSE, the ticker isn't in curr snapshot — no after_id
            # We still need to record the change, use prev snapshot's id as reference
            if after_id is None and diff["implied_action"] == "CLOSE":
                # Create a zero-share snapshot row for the close
                close_id = uuid.uuid4()
                close_snap = PositionSnapshot(
                    id=close_id,
                    portfolio_id=portfolio_id,
                    ticker=ticker,
                    imported_at=now,
                    shares=Decimal("0"),
                    avg_cost_basis=Decimal("0"),
                    csv_hash=csv_hash,
                    is_baseline=False,
                )
                db.add(close_snap)
                after_id = close_id

            if after_id is None:
                continue  # Unknown ticker — skip

            change = PositionChange(
                portfolio_id=portfolio_id,
                ticker=ticker,
                detected_at=now,
                snapshot_before_id=before_id,
                snapshot_after_id=after_id,
                prev_shares=diff["prev_shares"],
                new_shares=diff["new_shares"],
                delta_shares=diff["delta_shares"],
                prev_avg_cost_basis=diff["prev_avg_cost_basis"],
                new_avg_cost_basis=diff["new_avg_cost_basis"],
                implied_action=diff["implied_action"],
                attribution_status="pending",
            )
            db.add(change)
            changes_detected += 1

        await db.flush()

    # 6. Sync Position table
    await _sync_positions(portfolio_id, valid_rows, db)

    # 7. Sync Watchlist
    await _sync_watchlist(user_id, {r.ticker for r in valid_rows}, db)

    await db.commit()

    logger.info(
        "Imported %d positions for portfolio %s (%d changes detected, baseline=%s)",
        len(valid_rows), portfolio_id, changes_detected, is_baseline,
    )

    return ImportResult(
        imported=len(valid_rows),
        warnings=warnings,
        changes_detected=changes_detected,
        is_baseline=is_baseline,
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/services/test_snapshot_import.py -v`
Expected: All 11 tests pass (pure function tests — no DB mocking needed).

- [ ] **Step 5: Lint**

Run: `uv run ruff check --fix backend/services/portfolio/snapshot_import.py tests/unit/services/test_snapshot_import.py && uv run ruff format backend/services/portfolio/snapshot_import.py tests/unit/services/test_snapshot_import.py`

- [ ] **Step 6: Commit**

```bash
git add backend/services/portfolio/snapshot_import.py tests/unit/services/test_snapshot_import.py
git commit -m "feat(attribution): snapshot import service with diff engine"
```

---

### Task 6: Import Endpoint

**Files:**
- Modify: `backend/routers/portfolio.py` (add new route)
- Create: `tests/unit/routers/test_import_snapshot.py`

- [ ] **Step 1: Write endpoint tests**

```python
"""Tests for POST /portfolio/import-snapshot endpoint."""

from __future__ import annotations

import io
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status

VALID_CSV_BYTES = (
    b'"Positions for account Designated Bene Individual as of 02:41 AM ET, 2026/04/30"\n'
    b"\n"
    b'"Symbol","Description","Qty (Quantity)","Price","Cost Basis","Mkt Val (Market Value)","Asset Type"\n'
    b'"AAPL","APPLE INC","27.4355","270.84","$2,989.79","$7,430.63","Equity"\n'
)

INVALID_CSV_BYTES = b"just some random text\nwith no recognizable columns\n"

MAX_FILE_SIZE = 512 * 1024  # 512KB


class TestImportSnapshotEndpoint:
    """Endpoint-level tests for CSV import."""

    def test_rejects_non_csv_content_type(self, client, auth_headers) -> None:
        """Non-CSV content type should be rejected."""
        response = client.post(
            "/api/v1/portfolio/import-snapshot",
            files={"file": ("test.json", io.BytesIO(b"{}"), "application/json")},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_oversized_file(self, client, auth_headers) -> None:
        """Files > 512KB should be rejected."""
        big_content = b"x" * (MAX_FILE_SIZE + 1)
        response = client.post(
            "/api/v1/portfolio/import-snapshot",
            files={"file": ("big.csv", io.BytesIO(big_content), "text/csv")},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_invalid_csv_format(self, client, auth_headers) -> None:
        """CSV with no recognizable header should return 422."""
        response = client.post(
            "/api/v1/portfolio/import-snapshot",
            files={"file": ("bad.csv", io.BytesIO(INVALID_CSV_BYTES), "text/csv")},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        body = response.json()
        assert "errors" in body

    def test_unauthenticated_returns_401(self, client) -> None:
        """No auth token should be rejected."""
        response = client.post(
            "/api/v1/portfolio/import-snapshot",
            files={"file": ("test.csv", io.BytesIO(VALID_CSV_BYTES), "text/csv")},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("backend.routers.portfolio.import_portfolio_snapshot")
    @patch("backend.routers.portfolio.parse_fidelity_csv")
    @patch("backend.routers.portfolio.get_or_create_portfolio")
    def test_successful_import_returns_201(
        self, mock_get_portfolio, mock_parse, mock_import, client, auth_headers,
    ) -> None:
        """Valid CSV should return 201 with ImportResult."""
        from backend.schemas.attribution import ImportResult, SnapshotRowSchema

        mock_get_portfolio.return_value = AsyncMock(id=uuid.uuid4())
        mock_parse.return_value = (
            [SnapshotRowSchema(
                ticker="AAPL", shares=10, price=270, cost_basis=2700,
                market_value=2700, avg_cost_basis=270,
            )],
            [],  # warnings
            [],  # errors
        )
        mock_import.return_value = ImportResult(imported=1, changes_detected=0, is_baseline=True)

        response = client.post(
            "/api/v1/portfolio/import-snapshot",
            files={"file": ("test.csv", io.BytesIO(VALID_CSV_BYTES), "text/csv")},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_201_CREATED
        body = response.json()
        assert body["imported"] == 1
        assert body["is_baseline"] is True

    @patch("backend.routers.portfolio.import_portfolio_snapshot")
    @patch("backend.routers.portfolio.parse_fidelity_csv")
    @patch("backend.routers.portfolio.get_or_create_portfolio")
    def test_duplicate_csv_returns_409(
        self, mock_get_portfolio, mock_parse, mock_import, client, auth_headers,
    ) -> None:
        """Same CSV uploaded twice should return 409."""
        from backend.schemas.attribution import ImportResult, SnapshotRowSchema

        mock_get_portfolio.return_value = AsyncMock(id=uuid.uuid4())
        mock_parse.return_value = (
            [SnapshotRowSchema(
                ticker="AAPL", shares=10, price=270, cost_basis=2700,
                market_value=2700, avg_cost_basis=270,
            )],
            [], [],
        )
        mock_import.return_value = ImportResult(imported=0, is_duplicate=True)

        response = client.post(
            "/api/v1/portfolio/import-snapshot",
            files={"file": ("test.csv", io.BytesIO(VALID_CSV_BYTES), "text/csv")},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_409_CONFLICT
```

- [ ] **Step 2: Add endpoint to portfolio router**

Add these imports to the top of `backend/routers/portfolio.py`:

```python
from backend.schemas.attribution import CsvValidationError, ImportResult
from backend.services.portfolio.csv_parser import parse_fidelity_csv
from backend.services.portfolio.snapshot_import import (
    compute_csv_hash,
    import_portfolio_snapshot,
)
```

Add the endpoint (at the end of the file, before any trailing comments):

```python
_SNAPSHOT_MAX_FILE_SIZE = 512 * 1024  # 512KB


@router.post(
    "/import-snapshot",
    response_model=ImportResult,
    status_code=status.HTTP_201_CREATED,
    summary="Import portfolio positions from Fidelity CSV",
)
@limiter.limit("10/hour")
async def import_snapshot(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> ImportResult:
    """Upload a Fidelity-format positions CSV to snapshot portfolio state.

    The system stores a point-in-time snapshot, computes diffs against
    the previous import, and detects position changes (OPEN/ADD/TRIM/CLOSE).

    Args:
        request: FastAPI request (for rate limiter + cache).
        file: Uploaded CSV file.
        current_user: Authenticated user.
        db: Async database session.

    Returns:
        ImportResult with counts, warnings, and detected changes.
    """
    require_verified_email(current_user)

    # Content-type check
    if file.content_type not in ("text/csv", "application/csv", "text/plain",
                                  "application/vnd.ms-excel"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV",
        )

    # Size check
    content_bytes = await file.read()
    if len(content_bytes) > _SNAPSHOT_MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum 512KB.",
        )

    # Encoding
    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be UTF-8 encoded",
        )

    # Parse CSV
    rows, warnings, errors = parse_fidelity_csv(content)

    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"errors": [e.model_dump() for e in errors]},
        )

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"errors": [{"message": "No valid positions found in CSV"}]},
        )

    # Get or create portfolio
    portfolio = await get_or_create_portfolio(current_user.id, db)

    # Compute hash for dedup
    csv_hash = compute_csv_hash(content)

    # Import snapshot
    result = await import_portfolio_snapshot(
        portfolio_id=portfolio.id,
        user_id=current_user.id,
        rows=rows,
        csv_hash=csv_hash,
        db=db,
    )

    # Dedup rejection
    if result.is_duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This CSV was already imported.",
        )

    # Cache invalidation
    cache = getattr(request.app.state, "cache", None)
    if cache:
        await cache.invalidate_user(str(current_user.id))

    # Merge parser warnings into result
    result.warnings = warnings + result.warnings

    return result
```

- [ ] **Step 3: Run existing portfolio tests to verify no regression**

Run: `uv run pytest tests/unit/routers/test_portfolio_ingest.py tests/api/test_portfolio.py -v --tb=short -q`
Expected: All existing tests pass.

- [ ] **Step 4: Run full unit test suite**

Run: `uv run pytest tests/unit/ -q --tb=short -x`
Expected: All tests pass, zero failures.

- [ ] **Step 5: Lint entire backend**

Run: `uv run ruff check --fix backend/ tests/ && uv run ruff format backend/ tests/`
Expected: Zero errors.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/portfolio.py tests/unit/routers/test_import_snapshot.py
git commit -m "feat(attribution): POST /portfolio/import-snapshot endpoint"
```

---

### Task 7: Integration Smoke Test

**Files:**
- No new files — manual verification.

- [ ] **Step 1: Run full unit tests**

Run: `uv run pytest tests/unit/ -q --tb=short`
Expected: All pass, zero failures. Note the count.

- [ ] **Step 2: Run ruff check on full codebase**

Run: `uv run ruff check backend/ tests/ scripts/`
Expected: Zero errors.

- [ ] **Step 3: Run ruff format check**

Run: `uv run ruff format --check backend/ tests/ scripts/`
Expected: Zero reformatted files. If any, run `uv run ruff format backend/ tests/ scripts/` and commit.

- [ ] **Step 4: Verify Alembic migration is clean**

Run: `uv run alembic current && uv run alembic check`
Expected: Current head is the new 046 revision. No pending changes detected.

- [ ] **Step 5: Verify all imports resolve**

Run: `uv run python -c "from backend.models.attribution import PositionSnapshot, PositionChange, DecisionAttribution; from backend.services.portfolio.csv_parser import parse_fidelity_csv; from backend.services.portfolio.snapshot_import import import_portfolio_snapshot; from backend.schemas.attribution import ImportResult; print('All imports OK')"`
Expected: `All imports OK`

---

## Hard Constraints (from spec)

1. **No str(e)** — all error messages are hardcoded strings, not exception stringification.
2. **Async by default** — all service functions and endpoint handlers are async.
3. **No mutable module state** — only constants at module level.
4. **uv only** — all commands use `uv run`.
5. **Position table is NOT source of truth for attribution** — `position_snapshots` is.
6. **FIFO untouched** — `recompute_position()` is never called from import path.
7. **Existing endpoints untouched** — no changes to `/transactions`, `/bulk-upload`, etc.
8. **Cache invalidation** — import endpoint MUST call `cache.invalidate_user()`.
