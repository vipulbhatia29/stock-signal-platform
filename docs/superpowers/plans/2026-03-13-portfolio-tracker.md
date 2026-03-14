# Portfolio Tracker Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a manual-entry portfolio tracker with transaction log, FIFO positions, P&L, and sector allocation — exposed via 5 REST endpoints and a portfolio page in the Next.js frontend.

**Architecture:** Transactions are the append-only source of truth. `positions` is a DB table recomputed from the full transaction log via FIFO on every write. The portfolio page shows KPI row + positions table (3fr) + sector allocation pie (2fr) side-by-side.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Pydantic v2, Alembic, PostgreSQL, Next.js App Router, TanStack Query v5, Recharts, shadcn/ui

---

## File Map

### New files (create)
| File | Responsibility |
|---|---|
| `backend/models/portfolio.py` | Portfolio, Transaction, Position ORM models |
| `backend/schemas/portfolio.py` | Pydantic v2 request/response schemas |
| `backend/tools/portfolio.py` | FIFO engine, P&L computation, summary aggregation |
| `backend/routers/portfolio.py` | 5 REST endpoints, auth guard, FK error handling |
| `backend/migrations/versions/005_portfolio_tables.py` | Alembic migration — 3 new tables + indexes |
| `tests/unit/test_portfolio.py` | Unit tests for FIFO and P&L logic |
| `tests/api/test_portfolio.py` | API endpoint tests (auth, happy path, error) |
| `frontend/src/app/(authenticated)/portfolio/page.tsx` | Portfolio page (server component shell + client) |
| `frontend/src/app/(authenticated)/portfolio/portfolio-client.tsx` | Client component: KPI row + positions table + allocation chart |
| `frontend/src/components/log-transaction-dialog.tsx` | shadcn Dialog form for BUY/SELL entry |

### Modified files
| File | Change |
|---|---|
| `backend/models/__init__.py` | Import Portfolio, Transaction, Position so Base.metadata sees them |
| `backend/main.py` | Mount portfolio router at `/api/v1` |
| `tests/conftest.py` | Add PortfolioFactory, TransactionFactory |
| `frontend/src/types/api.ts` | Add Transaction, Position, SectorAllocation, PortfolioSummary types |
| `frontend/src/components/nav-bar.tsx` | Add "Portfolio" nav link |

---

## Chunk 1: Data Model + Migration

### Task 1: Portfolio, Transaction, Position models

**Files:**
- Create: `backend/models/portfolio.py`
- Modify: `backend/models/__init__.py`

- [ ] **Step 1: Write the model file**

```python
# backend/models/portfolio.py
"""Portfolio, Transaction, and Position ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.models.user import User


class Portfolio(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A user's investment portfolio (single account)."""

    __tablename__ = "portfolios"

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False, default="My Portfolio")
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    # Relationships
    user: Mapped[User] = relationship(back_populates="portfolio")
    transactions: Mapped[list[Transaction]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    positions: Mapped[list[Position]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Portfolio id={self.id} user_id={self.user_id} name={self.name!r}>"


class Transaction(UUIDPrimaryKeyMixin, Base):
    """An immutable BUY or SELL trade record (append-only ledger)."""

    __tablename__ = "transactions"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(
        sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"),
        nullable=False,
    )
    transaction_type: Mapped[str] = mapped_column(
        sa.Enum("BUY", "SELL", name="transaction_type_enum"),
        nullable=False,
    )
    shares: Mapped[Decimal] = mapped_column(sa.Numeric(12, 4), nullable=False)
    price_per_share: Mapped[Decimal] = mapped_column(sa.Numeric(12, 4), nullable=False)
    transacted_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        sa.CheckConstraint("shares > 0", name="ck_transactions_shares_positive"),
        sa.CheckConstraint("price_per_share > 0", name="ck_transactions_price_positive"),
    )

    # Relationships
    portfolio: Mapped[Portfolio] = relationship(back_populates="transactions")

    def __repr__(self) -> str:
        return (
            f"<Transaction id={self.id} {self.transaction_type} "
            f"{self.shares} {self.ticker} @ {self.price_per_share}>"
        )


class Position(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Current open position for a ticker — recomputed from transactions via FIFO."""

    __tablename__ = "positions"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(
        sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"),
        nullable=False,
    )
    shares: Mapped[Decimal] = mapped_column(sa.Numeric(12, 4), nullable=False)
    avg_cost_basis: Mapped[Decimal] = mapped_column(sa.Numeric(12, 4), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        sa.UniqueConstraint("portfolio_id", "ticker", name="uq_positions_portfolio_ticker"),
    )

    # Relationships
    portfolio: Mapped[Portfolio] = relationship(back_populates="positions")

    def __repr__(self) -> str:
        return f"<Position ticker={self.ticker} shares={self.shares} avg_cost={self.avg_cost_basis}>"
```

- [ ] **Step 2: Add `portfolio` relationship back-reference to User model**

In `backend/models/user.py`, find the existing `if TYPE_CHECKING:` block and add `Portfolio` to it (do NOT create a second `if TYPE_CHECKING:` block). Then add the relationship inside the `User` class after existing relationships:

```python
# Inside the existing if TYPE_CHECKING: block (add to it, don't create a new one):
from backend.models.portfolio import Portfolio

# Inside the User class body (after existing relationships):
portfolio: Mapped[Portfolio | None] = relationship(back_populates="user", uselist=False)
```

- [ ] **Step 3: Register models in `backend/models/__init__.py`**

Add import line and update `__all__` so `Base.metadata` includes the new tables:

```python
# Add import (alongside existing model imports):
from backend.models.portfolio import Portfolio, Position, Transaction  # noqa: F401

# Add to __all__ list:
"Portfolio",
"Position",
"Transaction",
```

- [ ] **Step 4: Verify import chain**

```bash
uv run python -c "from backend.models import Base; print([t.name for t in Base.metadata.sorted_tables])"
```

Expected: output includes `portfolios`, `transactions`, `positions`

---

### Task 2: Alembic migration 005

**Files:**
- Create: `backend/migrations/versions/005_portfolio_tables.py`

- [ ] **Step 1: Autogenerate migration**

```bash
uv run alembic revision --autogenerate -m "005_portfolio_tables"
```

- [ ] **Step 2: Review generated migration**

Open the generated file. Remove any spurious `op.drop_index()` lines for TimescaleDB-managed indexes (common autogenerate false positive — check against existing migrations for the pattern).

- [ ] **Step 3: Ensure check constraints and indexes are present**

The migration must contain:
- `op.create_check_constraint("ck_transactions_shares_positive", "transactions", "shares > 0")`
- `op.create_check_constraint("ck_transactions_price_positive", "transactions", "price_per_share > 0")`
- `op.create_index("ix_transactions_portfolio_ticker_date", "transactions", ["portfolio_id", "ticker", "transacted_at"])`
- `op.create_index("ix_positions_portfolio_ticker", "positions", ["portfolio_id", "ticker"])`

If autogenerate missed any, add them manually.

- [ ] **Step 4: Apply migration**

```bash
uv run alembic upgrade head
uv run alembic current
```

Expected: shows `005_portfolio_tables (head)`

- [ ] **Step 5: Commit**

```bash
git add backend/models/portfolio.py backend/models/__init__.py backend/models/user.py backend/migrations/versions/005_portfolio_tables.py
git commit -m "feat: portfolio, transaction, position models + migration 005"
```

---

## Chunk 2: Schemas + FIFO Tool

### Task 3: Pydantic schemas

**Files:**
- Create: `backend/schemas/portfolio.py`

- [ ] **Step 1: Write the schemas file**

```python
# backend/schemas/portfolio.py
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
```

- [ ] **Step 2: Verify import**

```bash
uv run python -c "from backend.schemas.portfolio import TransactionCreate, PortfolioSummaryResponse; print('OK')"
```

Expected: `OK`

---

### Task 4: FIFO portfolio tool

**Files:**
- Create: `backend/tools/portfolio.py`

- [ ] **Step 1: Write failing unit tests first** (TDD)

Create `tests/unit/test_portfolio.py`:

```python
# tests/unit/test_portfolio.py
"""Unit tests for FIFO cost basis and portfolio P&L computation."""

from collections import deque
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.tools.portfolio import _run_fifo


def _dt(day: int) -> datetime:
    """Helper: create a UTC datetime at day N of 2026."""
    return datetime(2026, 1, day, tzinfo=timezone.utc)


def test_fifo_single_buy_no_sells():
    """Single BUY with no SELLs → full shares at cost."""
    txns = [
        {"type": "BUY", "shares": Decimal("10"), "price": Decimal("100"), "at": _dt(1)},
    ]
    result = _run_fifo(txns)
    assert result["shares"] == Decimal("10")
    assert result["avg_cost_basis"] == Decimal("100")
    assert result["closed_at"] is None


def test_fifo_multiple_buys_weighted_average():
    """Multiple BUYs → weighted average cost of remaining lots."""
    txns = [
        {"type": "BUY", "shares": Decimal("10"), "price": Decimal("100"), "at": _dt(1)},
        {"type": "BUY", "shares": Decimal("10"), "price": Decimal("200"), "at": _dt(2)},
    ]
    result = _run_fifo(txns)
    assert result["shares"] == Decimal("20")
    assert result["avg_cost_basis"] == Decimal("150")  # (10*100 + 10*200) / 20


def test_fifo_partial_sell_consumes_oldest_lots():
    """SELL of 5 shares against 10-share BUY lot → 5 shares remain."""
    txns = [
        {"type": "BUY", "shares": Decimal("10"), "price": Decimal("100"), "at": _dt(1)},
        {"type": "SELL", "shares": Decimal("5"), "price": Decimal("150"), "at": _dt(2)},
    ]
    result = _run_fifo(txns)
    assert result["shares"] == Decimal("5")
    assert result["avg_cost_basis"] == Decimal("100")


def test_fifo_full_sell_closes_position():
    """SELL of all shares → shares=0, closed_at set."""
    txns = [
        {"type": "BUY", "shares": Decimal("10"), "price": Decimal("100"), "at": _dt(1)},
        {"type": "SELL", "shares": Decimal("10"), "price": Decimal("150"), "at": _dt(2)},
    ]
    result = _run_fifo(txns)
    assert result["shares"] == Decimal("0")
    assert result["closed_at"] == _dt(2)


def test_fifo_oversell_raises():
    """SELL exceeding available shares raises ValueError."""
    txns = [
        {"type": "BUY", "shares": Decimal("5"), "price": Decimal("100"), "at": _dt(1)},
        {"type": "SELL", "shares": Decimal("10"), "price": Decimal("150"), "at": _dt(2)},
    ]
    with pytest.raises(ValueError, match="Insufficient shares"):
        _run_fifo(txns)


def test_fifo_multiple_tickers_isolated():
    """FIFO for one ticker does not affect another."""
    aapl_txns = [
        {"type": "BUY", "shares": Decimal("10"), "price": Decimal("100"), "at": _dt(1)},
        {"type": "SELL", "shares": Decimal("10"), "price": Decimal("150"), "at": _dt(2)},
    ]
    msft_txns = [
        {"type": "BUY", "shares": Decimal("5"), "price": Decimal("300"), "at": _dt(1)},
    ]
    aapl = _run_fifo(aapl_txns)
    msft = _run_fifo(msft_txns)
    assert aapl["shares"] == Decimal("0")
    assert msft["shares"] == Decimal("5")


def test_fifo_out_of_order_entry_reorders():
    """BUY entered with a past date is sorted into correct FIFO order."""
    txns = [
        # SELL logged first in list but FIFO sorts by transacted_at
        {"type": "SELL", "shares": Decimal("5"), "price": Decimal("150"), "at": _dt(3)},
        # This BUY happened before the SELL — FIFO should consume it
        {"type": "BUY", "shares": Decimal("10"), "price": Decimal("100"), "at": _dt(1)},
    ]
    result = _run_fifo(txns)
    assert result["shares"] == Decimal("5")


def test_fifo_delete_simulation_raises_on_invalid():
    """Simulating removal of a BUY that underlies a SELL should raise ValueError."""
    all_txns = [
        {"type": "BUY", "shares": Decimal("10"), "price": Decimal("100"), "at": _dt(1)},
        {"type": "SELL", "shares": Decimal("10"), "price": Decimal("150"), "at": _dt(2)},
    ]
    # Simulate removing the BUY
    remaining = [t for t in all_txns if not (t["type"] == "BUY" and t["at"] == _dt(1))]
    with pytest.raises(ValueError, match="Insufficient shares"):
        _run_fifo(remaining)


def test_fifo_null_sector_grouped_as_unknown():
    """Null sector on a stock is bucketed as 'Unknown' (tested via summary helper)."""
    # This is a property of get_portfolio_summary; tested here via sector grouping util
    from backend.tools.portfolio import _group_sectors

    positions = [
        {"ticker": "AAPL", "sector": None, "market_value": 1000.0},
        {"ticker": "MSFT", "sector": "Technology", "market_value": 2000.0},
    ]
    result = _group_sectors(positions, total_value=3000.0)
    sectors = {s["sector"]: s for s in result}
    assert "Unknown" in sectors
    assert sectors["Unknown"]["pct"] == pytest.approx(33.33, abs=0.01)
    assert "Technology" in sectors
    assert sectors["Technology"]["over_limit"] is False
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/unit/test_portfolio.py -v
```

Expected: All tests fail with `ModuleNotFoundError` or `ImportError` — confirms tests are real.

- [ ] **Step 3: Implement `backend/tools/portfolio.py`**

```python
# backend/tools/portfolio.py
"""Portfolio tool: FIFO cost basis, P&L, summary, position recompute."""

from __future__ import annotations

import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.portfolio import Portfolio, Position, Transaction
from backend.models.price import StockPrice
from backend.models.stock import Stock
from backend.schemas.portfolio import PositionResponse, PortfolioSummaryResponse, SectorAllocation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure FIFO engine (no DB — testable without async)
# ---------------------------------------------------------------------------

def _run_fifo(
    transactions: list[dict],
) -> dict:
    """Run FIFO walk over a list of transaction dicts.

    Args:
        transactions: List of dicts with keys: type ("BUY"|"SELL"),
            shares (Decimal), price (Decimal), at (datetime).
            Order does not matter — sorted internally by `at`.

    Returns:
        Dict with keys: shares (Decimal), avg_cost_basis (Decimal),
        closed_at (datetime | None).

    Raises:
        ValueError: If any SELL exceeds available BUY lots.
    """
    sorted_txns = sorted(transactions, key=lambda t: t["at"])
    lot_queue: deque[tuple[Decimal, Decimal]] = deque()  # (shares, price)
    last_sell_at: datetime | None = None

    for txn in sorted_txns:
        if txn["type"] == "BUY":
            lot_queue.append((txn["shares"], txn["price"]))
        else:  # SELL
            remaining_to_sell = txn["shares"]
            while remaining_to_sell > 0:
                if not lot_queue:
                    raise ValueError(
                        f"Insufficient shares: tried to sell {txn['shares']} "
                        f"but ran out of BUY lots"
                    )
                lot_shares, lot_price = lot_queue[0]
                if lot_shares <= remaining_to_sell:
                    remaining_to_sell -= lot_shares
                    lot_queue.popleft()
                else:
                    lot_queue[0] = (lot_shares - remaining_to_sell, lot_price)
                    remaining_to_sell = Decimal("0")
            last_sell_at = txn["at"]

    total_shares = sum(s for s, _ in lot_queue)
    if total_shares == 0:
        return {"shares": Decimal("0"), "avg_cost_basis": Decimal("0"), "closed_at": last_sell_at}

    total_cost = sum(s * p for s, p in lot_queue)
    avg_cost = total_cost / total_shares
    return {"shares": total_shares, "avg_cost_basis": avg_cost, "closed_at": None}


def _group_sectors(
    positions: list[dict],
    total_value: float,
) -> list[dict]:
    """Group positions by sector, compute %, flag concentration.

    Args:
        positions: List of dicts with keys: ticker, sector (str|None), market_value (float).
        total_value: Total portfolio market value (denominator for pct).

    Returns:
        List of dicts: sector, market_value, pct, over_limit.
    """
    buckets: dict[str, float] = {}
    for pos in positions:
        sector = pos["sector"] or "Unknown"
        buckets[sector] = buckets.get(sector, 0.0) + pos["market_value"]

    result = []
    for sector, value in sorted(buckets.items(), key=lambda x: -x[1]):
        pct = (value / total_value * 100) if total_value > 0 else 0.0
        result.append(
            {"sector": sector, "market_value": value, "pct": round(pct, 2), "over_limit": pct > 30}
        )
    return result


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def get_or_create_portfolio(user_id: uuid.UUID, db: AsyncSession) -> Portfolio:
    """Get the user's portfolio, creating one if it doesn't exist.

    Args:
        user_id: The authenticated user's ID.
        db: Async SQLAlchemy session.

    Returns:
        The user's Portfolio row.
    """
    result = await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
    portfolio = result.scalar_one_or_none()
    if portfolio is None:
        portfolio = Portfolio(user_id=user_id, name="My Portfolio")
        db.add(portfolio)
        await db.flush()
        logger.info("Created portfolio for user %s", user_id)
    return portfolio


async def _get_transactions_for_ticker(
    portfolio_id: uuid.UUID, ticker: str, db: AsyncSession
) -> list[dict]:
    """Load all transactions for a ticker as plain dicts for FIFO walk.

    Args:
        portfolio_id: The portfolio's UUID.
        ticker: The stock ticker.
        db: Async SQLAlchemy session.

    Returns:
        List of transaction dicts suitable for _run_fifo().
    """
    result = await db.execute(
        select(Transaction)
        .where(Transaction.portfolio_id == portfolio_id, Transaction.ticker == ticker)
        .order_by(Transaction.transacted_at)
    )
    txns = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "type": t.transaction_type,
            "shares": t.shares,
            "price": t.price_per_share,
            "at": t.transacted_at,
        }
        for t in txns
    ]


async def recompute_position(
    portfolio_id: uuid.UUID, ticker: str, db: AsyncSession
) -> None:
    """Run FIFO walk and upsert the position row for one ticker.

    Args:
        portfolio_id: The portfolio's UUID.
        ticker: The stock ticker to recompute.
        db: Async SQLAlchemy session.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    txn_dicts = await _get_transactions_for_ticker(portfolio_id, ticker, db)
    if not txn_dicts:
        # All transactions deleted — remove position row if it exists
        result = await db.execute(
            select(Position).where(
                Position.portfolio_id == portfolio_id, Position.ticker == ticker
            )
        )
        pos = result.scalar_one_or_none()
        if pos:
            await db.delete(pos)
        return

    fifo = _run_fifo(txn_dicts)
    opened_at = min(t["at"] for t in txn_dicts if t["type"] == "BUY")

    # Check if position row already exists (to preserve opened_at)
    result = await db.execute(
        select(Position).where(
            Position.portfolio_id == portfolio_id, Position.ticker == ticker
        )
    )
    existing = result.scalar_one_or_none()

    if existing is None:
        pos = Position(
            portfolio_id=portfolio_id,
            ticker=ticker,
            shares=fifo["shares"],
            avg_cost_basis=fifo["avg_cost_basis"],
            opened_at=opened_at,
            closed_at=fifo["closed_at"],
        )
        db.add(pos)
    else:
        # Update but NEVER overwrite opened_at
        existing.shares = fifo["shares"]
        existing.avg_cost_basis = fifo["avg_cost_basis"]
        existing.closed_at = fifo["closed_at"]

    logger.info("Recomputed position for %s: shares=%s", ticker, fifo["shares"])


async def get_positions_with_pnl(
    portfolio_id: uuid.UUID, db: AsyncSession
) -> list[PositionResponse]:
    """Get all open positions with current price and unrealized P&L.

    Args:
        portfolio_id: The portfolio's UUID.
        db: Async SQLAlchemy session.

    Returns:
        List of PositionResponse with live P&L fields.
    """
    result = await db.execute(
        select(Position).where(
            Position.portfolio_id == portfolio_id,
            Position.closed_at.is_(None),
        )
    )
    positions = result.scalars().all()

    # Compute total market value for allocation %
    pnl_rows = []
    total_value = 0.0
    for pos in positions:
        # Get latest price
        price_result = await db.execute(
            select(StockPrice.adj_close)
            .where(StockPrice.ticker == pos.ticker)
            .order_by(StockPrice.time.desc())
            .limit(1)
        )
        current_price_raw = price_result.scalar_one_or_none()
        current_price = float(current_price_raw) if current_price_raw is not None else None

        shares = float(pos.shares)
        avg_cost = float(pos.avg_cost_basis)
        market_value = shares * current_price if current_price is not None else None
        if market_value:
            total_value += market_value

        pnl_rows.append(
            {
                "ticker": pos.ticker,
                "shares": shares,
                "avg_cost_basis": avg_cost,
                "current_price": current_price,
                "market_value": market_value,
                "_cost_basis_total": shares * avg_cost,
            }
        )

    responses = []
    for row in pnl_rows:
        mv = row["market_value"]
        cost = row["_cost_basis_total"]
        unrealized_pnl = (mv - cost) if mv is not None else None
        unrealized_pnl_pct = (unrealized_pnl / cost * 100) if (unrealized_pnl is not None and cost > 0) else None
        allocation_pct = (mv / total_value * 100) if (mv is not None and total_value > 0) else None
        responses.append(
            PositionResponse(
                ticker=row["ticker"],
                shares=row["shares"],
                avg_cost_basis=row["avg_cost_basis"],
                current_price=row["current_price"],
                market_value=mv,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=unrealized_pnl_pct,
                allocation_pct=allocation_pct,
            )
        )
    return responses


async def get_portfolio_summary(
    portfolio_id: uuid.UUID, db: AsyncSession
) -> PortfolioSummaryResponse:
    """Aggregate KPI totals and sector allocation for the portfolio.

    Args:
        portfolio_id: The portfolio's UUID.
        db: Async SQLAlchemy session.

    Returns:
        PortfolioSummaryResponse with totals and sector breakdown.
    """
    positions_with_pnl = await get_positions_with_pnl(portfolio_id, db)

    total_value = sum(p.market_value or 0 for p in positions_with_pnl)
    total_cost = sum(p.shares * p.avg_cost_basis for p in positions_with_pnl)
    unrealized_pnl = total_value - total_cost
    unrealized_pnl_pct = (unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0

    # Fetch sector for each ticker
    tickers = [p.ticker for p in positions_with_pnl]
    sector_map: dict[str, str | None] = {}
    if tickers:
        result = await db.execute(
            select(Stock.ticker, Stock.sector).where(Stock.ticker.in_(tickers))
        )
        sector_map = {row.ticker: row.sector for row in result}

    pos_dicts = [
        {
            "ticker": p.ticker,
            "sector": sector_map.get(p.ticker),
            "market_value": p.market_value or 0,
        }
        for p in positions_with_pnl
    ]
    sector_data = _group_sectors(pos_dicts, total_value)
    sectors = [SectorAllocation(**s) for s in sector_data]

    return PortfolioSummaryResponse(
        total_value=total_value,
        total_cost_basis=total_cost,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=unrealized_pnl_pct,
        position_count=len(positions_with_pnl),
        sectors=sectors,
    )
```

- [ ] **Step 4: Run unit tests — confirm they pass**

```bash
uv run pytest tests/unit/test_portfolio.py -v
```

Expected: All 9 tests pass.

- [ ] **Step 5: Lint**

```bash
uv run ruff check backend/tools/portfolio.py backend/schemas/portfolio.py --fix
uv run ruff format backend/tools/portfolio.py backend/schemas/portfolio.py
```

Expected: Zero errors.

- [ ] **Step 6: Commit**

```bash
git add backend/schemas/portfolio.py backend/tools/portfolio.py tests/unit/test_portfolio.py
git commit -m "feat: FIFO portfolio tool + schemas + unit tests"
```

---

## Chunk 3: Router + API Tests

### Task 5: Portfolio router

**Files:**
- Create: `backend/routers/portfolio.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Write the router**

```python
# backend/routers/portfolio.py
"""Portfolio API endpoints: transactions, positions, and summary."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.portfolio import Transaction
from backend.models.user import User
from backend.schemas.portfolio import (
    PortfolioSummaryResponse,
    PositionResponse,
    TransactionCreate,
    TransactionResponse,
)
from backend.tools.portfolio import (
    _get_transactions_for_ticker,
    _run_fifo,
    get_or_create_portfolio,
    get_portfolio_summary,
    get_positions_with_pnl,
    recompute_position,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.post(
    "/transactions",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log a BUY or SELL transaction",
)
async def create_transaction(
    body: TransactionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> TransactionResponse:
    """Log a BUY or SELL trade and recompute positions via FIFO.

    Returns the created transaction. Returns 422 if:
    - Ticker not found in stocks table
    - SELL exceeds available shares
    """
    portfolio = await get_or_create_portfolio(current_user.id, db)

    # Pre-validate SELL: check it won't exceed current open shares
    if body.transaction_type == "SELL":
        existing = await _get_transactions_for_ticker(portfolio.id, body.ticker, db)
        try:
            current = _run_fifo(existing)
        except ValueError:
            current = {"shares": 0}
        if float(body.shares) > float(current.get("shares", 0)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cannot sell {body.shares} shares of {body.ticker}: "
                f"only {current.get('shares', 0)} shares held.",
            )

    txn = Transaction(
        portfolio_id=portfolio.id,
        ticker=body.ticker,
        transaction_type=body.transaction_type,
        shares=body.shares,
        price_per_share=body.price_per_share,
        transacted_at=body.transacted_at,
        notes=body.notes,
    )
    db.add(txn)

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if "foreign key" in str(exc.orig).lower() and "ticker" in str(exc.orig).lower():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Ticker '{body.ticker}' not found. "
                    "Add it to your watchlist first to ingest it."
                ),
            ) from exc
        raise

    await recompute_position(portfolio.id, body.ticker, db)
    await db.commit()
    await db.refresh(txn)
    logger.info("Logged %s %s %s for user %s", body.transaction_type, body.shares, body.ticker, current_user.id)
    return TransactionResponse.model_validate(txn)


@router.get(
    "/transactions",
    response_model=list[TransactionResponse],
    summary="Get transaction history",
)
async def list_transactions(
    ticker: str | None = Query(None, description="Filter by ticker"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[TransactionResponse]:
    """Return all transactions sorted by date descending.

    Optionally filter by ticker symbol.
    """
    from sqlalchemy import select

    portfolio = await get_or_create_portfolio(current_user.id, db)

    stmt = (
        select(Transaction)
        .where(Transaction.portfolio_id == portfolio.id)
        .order_by(Transaction.transacted_at.desc())
    )
    if ticker:
        stmt = stmt.where(Transaction.ticker == ticker.upper().strip())

    result = await db.execute(stmt)
    txns = result.scalars().all()
    return [TransactionResponse.model_validate(t) for t in txns]


@router.delete(
    "/transactions/{transaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a transaction",
)
async def delete_transaction(
    transaction_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> None:
    """Remove a transaction after validating it won't strand a later SELL.

    Returns 422 if removing this transaction would leave any SELL
    without sufficient BUY lots.
    Returns 404 if transaction not found or belongs to another user.
    """
    from sqlalchemy import select

    portfolio = await get_or_create_portfolio(current_user.id, db)

    result = await db.execute(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.portfolio_id == portfolio.id,
        )
    )
    txn = result.scalar_one_or_none()
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")

    ticker = txn.ticker

    # Pre-delete simulation: run FIFO without this transaction (ID-based exclusion)
    all_txns = await _get_transactions_for_ticker(portfolio.id, ticker, db)
    remaining = [t for t in all_txns if t["id"] != str(txn.id)]
    try:
        _run_fifo(remaining)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot delete: removing this transaction would leave a later SELL without sufficient shares.",
        )

    await db.delete(txn)
    await recompute_position(portfolio.id, ticker, db)
    await db.commit()
    logger.info("Deleted transaction %s for user %s", transaction_id, current_user.id)


@router.get(
    "/positions",
    response_model=list[PositionResponse],
    summary="Get current positions with live P&L",
)
async def list_positions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[PositionResponse]:
    """Return all open positions with current price and unrealized P&L."""
    portfolio = await get_or_create_portfolio(current_user.id, db)
    return await get_positions_with_pnl(portfolio.id, db)


@router.get(
    "/summary",
    response_model=PortfolioSummaryResponse,
    summary="Get portfolio KPI totals and sector allocation",
)
async def get_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> PortfolioSummaryResponse:
    """Return total value, cost basis, unrealized P&L, and sector breakdown."""
    portfolio = await get_or_create_portfolio(current_user.id, db)
    return await get_portfolio_summary(portfolio.id, db)
```

- [ ] **Step 2: Mount router in `backend/main.py`**

Find the block where other routers are included (e.g. `app.include_router(stocks.router, ...)`) and add:

```python
from backend.routers import portfolio  # add to imports at top

app.include_router(portfolio.router, prefix="/api/v1")
```

- [ ] **Step 3: Verify app loads**

```bash
uv run python -c "from backend.main import app; print('OK')"
```

Expected: `OK` with no errors.

---

### Task 6: Add factories to conftest.py

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add PortfolioFactory and TransactionFactory**

Find the factories section in `tests/conftest.py` (after `StockFactory`) and add:

```python
from backend.models.portfolio import Portfolio, Transaction  # add to imports at top of file


class PortfolioFactory(factory.Factory):
    """Factory for Portfolio model instances."""

    class Meta:
        model = Portfolio

    id = factory.LazyFunction(uuid.uuid4)
    user_id = factory.LazyFunction(uuid.uuid4)
    name = "My Portfolio"
    description = None
    created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    updated_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))


class TransactionFactory(factory.Factory):
    """Factory for Transaction model instances."""

    class Meta:
        model = Transaction

    id = factory.LazyFunction(uuid.uuid4)
    portfolio_id = factory.LazyFunction(uuid.uuid4)
    ticker = "AAPL"
    transaction_type = "BUY"
    shares = Decimal("10")
    price_per_share = Decimal("150.00")
    transacted_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    notes = None
    created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
```

Also add `from decimal import Decimal` to the imports if not already present.

---

### Task 7: API tests

**Files:**
- Create: `tests/api/test_portfolio.py`

- [ ] **Step 1: Write the API tests**

```python
# tests/api/test_portfolio.py
"""API tests for portfolio endpoints."""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from tests.conftest import StockFactory, UserFactory


@pytest.mark.asyncio
class TestPortfolioAuth:
    """Unauthenticated requests return 401."""

    async def test_create_transaction_requires_auth(self, client: AsyncClient) -> None:
        """POST /portfolio/transactions without token returns 401."""
        resp = await client.post("/api/v1/portfolio/transactions", json={})
        assert resp.status_code == 401

    async def test_list_transactions_requires_auth(self, client: AsyncClient) -> None:
        """GET /portfolio/transactions without token returns 401."""
        resp = await client.get("/api/v1/portfolio/transactions")
        assert resp.status_code == 401

    async def test_positions_requires_auth(self, client: AsyncClient) -> None:
        """GET /portfolio/positions without token returns 401."""
        resp = await client.get("/api/v1/portfolio/positions")
        assert resp.status_code == 401

    async def test_summary_requires_auth(self, client: AsyncClient) -> None:
        """GET /portfolio/summary without token returns 401."""
        resp = await client.get("/api/v1/portfolio/summary")
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestCreateTransaction:
    """Tests for POST /api/v1/portfolio/transactions."""

    async def test_log_buy_returns_201(
        self, auth_client: AsyncClient, db_session
    ) -> None:
        """BUY transaction logged successfully returns 201 with transaction data."""
        # Create stock in DB first
        stock = StockFactory(ticker="AAPL", name="Apple Inc.")
        db_session.add(stock)
        await db_session.commit()

        resp = await auth_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "AAPL",
                "transaction_type": "BUY",
                "shares": "10",
                "price_per_share": "182.50",
                "transacted_at": "2026-01-15T00:00:00Z",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["ticker"] == "AAPL"
        assert data["transaction_type"] == "BUY"
        assert float(data["shares"]) == 10.0

    async def test_log_buy_unknown_ticker_returns_422(
        self, auth_client: AsyncClient
    ) -> None:
        """BUY for ticker not in stocks table returns 422 with clear message."""
        resp = await auth_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "ZZZZZ",
                "transaction_type": "BUY",
                "shares": "5",
                "price_per_share": "100.00",
                "transacted_at": "2026-01-15T00:00:00Z",
            },
        )
        assert resp.status_code == 422
        assert "not found" in resp.json()["detail"].lower()

    async def test_oversell_returns_422(
        self, auth_client: AsyncClient, db_session
    ) -> None:
        """SELL exceeding held shares returns 422."""
        stock = StockFactory(ticker="MSFT", name="Microsoft")
        db_session.add(stock)
        await db_session.commit()

        # Buy 5 shares first
        await auth_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "MSFT",
                "transaction_type": "BUY",
                "shares": "5",
                "price_per_share": "300.00",
                "transacted_at": "2026-01-15T00:00:00Z",
            },
        )

        # Try to sell 10
        resp = await auth_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "MSFT",
                "transaction_type": "SELL",
                "shares": "10",
                "price_per_share": "320.00",
                "transacted_at": "2026-01-20T00:00:00Z",
            },
        )
        assert resp.status_code == 422

    async def test_invalid_payload_returns_422(
        self, auth_client: AsyncClient
    ) -> None:
        """Missing required fields returns 422."""
        resp = await auth_client.post(
            "/api/v1/portfolio/transactions",
            json={"ticker": "AAPL"},
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestListTransactions:
    """Tests for GET /api/v1/portfolio/transactions."""

    async def test_empty_returns_empty_list(
        self, auth_client: AsyncClient
    ) -> None:
        """No transactions returns empty list."""
        resp = await auth_client.get("/api/v1/portfolio/transactions")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_filter_by_ticker(
        self, auth_client: AsyncClient, db_session
    ) -> None:
        """?ticker=AAPL filters to only AAPL transactions."""
        for ticker in ("AAPL", "MSFT"):
            stock = StockFactory(ticker=ticker, name=ticker)
            db_session.add(stock)
        await db_session.commit()

        for ticker in ("AAPL", "MSFT"):
            await auth_client.post(
                "/api/v1/portfolio/transactions",
                json={
                    "ticker": ticker,
                    "transaction_type": "BUY",
                    "shares": "5",
                    "price_per_share": "100.00",
                    "transacted_at": "2026-01-15T00:00:00Z",
                },
            )

        resp = await auth_client.get("/api/v1/portfolio/transactions?ticker=AAPL")
        assert resp.status_code == 200
        tickers = [t["ticker"] for t in resp.json()]
        assert all(t == "AAPL" for t in tickers)


@pytest.mark.asyncio
class TestDeleteTransaction:
    """Tests for DELETE /api/v1/portfolio/transactions/{id}."""

    async def test_delete_buy_with_no_sells_succeeds(
        self, auth_client: AsyncClient, db_session
    ) -> None:
        """DELETE a BUY with no associated SELLs returns 204."""
        stock = StockFactory(ticker="NVDA", name="NVIDIA")
        db_session.add(stock)
        await db_session.commit()

        create_resp = await auth_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "NVDA",
                "transaction_type": "BUY",
                "shares": "10",
                "price_per_share": "500.00",
                "transacted_at": "2026-01-15T00:00:00Z",
            },
        )
        txn_id = create_resp.json()["id"]

        resp = await auth_client.delete(f"/api/v1/portfolio/transactions/{txn_id}")
        assert resp.status_code == 204

    async def test_delete_buy_underlying_sell_returns_422(
        self, auth_client: AsyncClient, db_session
    ) -> None:
        """DELETE BUY that underlies a SELL returns 422."""
        stock = StockFactory(ticker="TSLA", name="Tesla")
        db_session.add(stock)
        await db_session.commit()

        buy_resp = await auth_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "TSLA",
                "transaction_type": "BUY",
                "shares": "10",
                "price_per_share": "200.00",
                "transacted_at": "2026-01-15T00:00:00Z",
            },
        )
        buy_id = buy_resp.json()["id"]

        await auth_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "TSLA",
                "transaction_type": "SELL",
                "shares": "10",
                "price_per_share": "250.00",
                "transacted_at": "2026-01-20T00:00:00Z",
            },
        )

        resp = await auth_client.delete(f"/api/v1/portfolio/transactions/{buy_id}")
        assert resp.status_code == 422

    async def test_delete_nonexistent_returns_404(
        self, auth_client: AsyncClient
    ) -> None:
        """DELETE unknown transaction ID returns 404."""
        import uuid
        resp = await auth_client.delete(f"/api/v1/portfolio/transactions/{uuid.uuid4()}")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestPositions:
    """Tests for GET /api/v1/portfolio/positions."""

    async def test_empty_portfolio_returns_empty_list(
        self, auth_client: AsyncClient
    ) -> None:
        """No transactions → empty positions list."""
        resp = await auth_client.get("/api/v1/portfolio/positions")
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.mark.asyncio
class TestSummary:
    """Tests for GET /api/v1/portfolio/summary."""

    async def test_empty_portfolio_returns_zero_kpis(
        self, auth_client: AsyncClient
    ) -> None:
        """Empty portfolio returns zero KPIs and empty sectors."""
        resp = await auth_client.get("/api/v1/portfolio/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_value"] == 0.0
        assert data["position_count"] == 0
        assert data["sectors"] == []
```

- [ ] **Step 2: Check that `auth_client` fixture exists**

Look in `tests/conftest.py` for `auth_client`. The existing fixture is named `authenticated_client`. Add a new `auth_client` fixture that matches the calling convention used in the portfolio tests. Note: `create_access_token` takes a `uuid.UUID` directly, not a dict:

```python
@pytest_asyncio.fixture
async def auth_client(client: AsyncClient, db_session) -> AsyncClient:
    """Authenticated AsyncClient with a valid JWT Bearer token."""
    user = UserFactory()
    db_session.add(user)
    await db_session.commit()
    token = create_access_token(user.id)  # takes uuid.UUID, not a dict
    client.headers["Authorization"] = f"Bearer {token}"
    return client
```

- [ ] **Step 3: Run API tests**

```bash
uv run pytest tests/api/test_portfolio.py -v
```

Expected: All tests pass.

- [ ] **Step 4: Run full test suite**

```bash
uv run pytest tests/unit/ tests/api/ -v --tb=short
```

Expected: All 163+ existing tests still pass + new portfolio tests pass.

- [ ] **Step 5: Lint**

```bash
uv run ruff check backend/routers/portfolio.py tests/api/test_portfolio.py tests/conftest.py --fix
uv run ruff format backend/routers/portfolio.py tests/api/test_portfolio.py tests/conftest.py
```

Expected: Zero errors.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/portfolio.py backend/main.py tests/api/test_portfolio.py tests/conftest.py
git commit -m "feat: portfolio router + API tests + factories"
```

---

## Chunk 4: Frontend — Portfolio Page

### Task 8: TypeScript types

**Files:**
- Modify: `frontend/src/types/api.ts`

- [ ] **Step 1: Add portfolio types**

Add to the bottom of `frontend/src/types/api.ts`:

```typescript
// Portfolio
export interface Transaction {
  id: string
  portfolio_id: string
  ticker: string
  transaction_type: "BUY" | "SELL"
  shares: number
  price_per_share: number
  transacted_at: string
  notes: string | null
  created_at: string
}

export interface TransactionCreate {
  ticker: string
  transaction_type: "BUY" | "SELL"
  shares: number
  price_per_share: number
  transacted_at: string
  notes?: string
}

export interface Position {
  ticker: string
  shares: number
  avg_cost_basis: number
  current_price: number | null
  market_value: number | null
  unrealized_pnl: number | null
  unrealized_pnl_pct: number | null
  allocation_pct: number | null
}

export interface SectorAllocation {
  sector: string
  market_value: number
  pct: number
  over_limit: boolean
}

export interface PortfolioSummary {
  total_value: number
  total_cost_basis: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  position_count: number
  sectors: SectorAllocation[]
}
```

---

### Task 9: Log Transaction Dialog

**Files:**
- Create: `frontend/src/components/log-transaction-dialog.tsx`

- [ ] **Step 1: Create the dialog component**

```typescript
// frontend/src/components/log-transaction-dialog.tsx
"use client"

import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { TransactionCreate } from "@/types/api"

export function LogTransactionDialog() {
  const [open, setOpen] = useState(false)
  const [type, setType] = useState<"BUY" | "SELL">("BUY")
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: (data: TransactionCreate) =>
      api<TransactionCreate>("/portfolio/transactions", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolio", "positions"] })
      queryClient.invalidateQueries({ queryKey: ["portfolio", "summary"] })
      queryClient.invalidateQueries({ queryKey: ["portfolio", "transactions"] })
      setOpen(false)
      toast.success("Transaction logged")
    },
    onError: (err: Error) => {
      toast.error(err.message ?? "Failed to log transaction")
    },
  })

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = new FormData(e.currentTarget)
    mutation.mutate({
      ticker: (form.get("ticker") as string).toUpperCase().trim(),
      transaction_type: type,
      shares: Number(form.get("shares")),
      price_per_share: Number(form.get("price_per_share")),
      transacted_at: new Date(form.get("transacted_at") as string).toISOString(),
      notes: (form.get("notes") as string) || undefined,
    })
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">+ Log Transaction</Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Log Transaction</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* BUY / SELL toggle */}
          <div className="flex gap-2">
            {(["BUY", "SELL"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setType(t)}
                className={`flex-1 rounded-md py-2 text-sm font-medium transition-colors ${
                  type === t
                    ? t === "BUY"
                      ? "bg-gain text-white"
                      : "bg-loss text-white"
                    : "bg-muted text-muted-foreground hover:bg-muted/80"
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          <div className="space-y-1">
            <Label htmlFor="ticker">Ticker</Label>
            <Input id="ticker" name="ticker" placeholder="AAPL" required className="uppercase" />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="shares">Shares</Label>
              <Input id="shares" name="shares" type="number" step="0.0001" min="0.0001" required />
            </div>
            <div className="space-y-1">
              <Label htmlFor="price_per_share">Price / Share ($)</Label>
              <Input id="price_per_share" name="price_per_share" type="number" step="0.01" min="0.01" required />
            </div>
          </div>

          <div className="space-y-1">
            <Label htmlFor="transacted_at">Date</Label>
            <Input
              id="transacted_at"
              name="transacted_at"
              type="date"
              defaultValue={new Date().toISOString().split("T")[0]}
              required
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="notes">Notes (optional)</Label>
            <Textarea id="notes" name="notes" rows={2} placeholder="e.g. Earnings play" />
          </div>

          <Button type="submit" className="w-full" disabled={mutation.isPending}>
            {mutation.isPending ? "Logging…" : `Log ${type}`}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
```

---

### Task 10: Portfolio client component

**Files:**
- Create: `frontend/src/app/(authenticated)/portfolio/portfolio-client.tsx`

- [ ] **Step 1: Create the client component**

```typescript
// frontend/src/app/(authenticated)/portfolio/portfolio-client.tsx
"use client"

import { useQuery } from "@tanstack/react-query"
import { Cell, Pie, PieChart, Tooltip } from "recharts"
import { api } from "@/lib/api"
import { ChangeIndicator } from "@/components/change-indicator"
import { MetricCard, MetricCardSkeleton } from "@/components/metric-card"
import { LogTransactionDialog } from "@/components/log-transaction-dialog"
import { useChartColors } from "@/lib/chart-theme"
import type { PortfolioSummary, Position } from "@/types/api"

const SECTOR_COLORS = [
  "#3b82f6", "#8b5cf6", "#22c55e", "#f59e0b",
  "#ef4444", "#06b6d4", "#ec4899", "#84cc16",
]

function KpiRow({ summary }: { summary: PortfolioSummary }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <MetricCard
        label="Total Value"
        value={`$${summary.total_value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
      />
      <MetricCard
        label="Cost Basis"
        value={`$${summary.total_cost_basis.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
      />
      <MetricCard
        label="Unrealized P&L"
        value={
          <ChangeIndicator
            value={summary.unrealized_pnl}
            pct={summary.unrealized_pnl_pct}
            size="lg"
          />
        }
      />
      <MetricCard label="Positions" value={String(summary.position_count)} />
    </div>
  )
}

function PositionsTable({ positions }: { positions: Position[] }) {
  return (
    <div className="rounded-lg border bg-card">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Positions
        </h2>
        <LogTransactionDialog />
      </div>
      {positions.length === 0 ? (
        <div className="px-4 py-12 text-center text-sm text-muted-foreground">
          No positions yet. Log your first transaction to get started.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-4 py-2 text-left">Ticker</th>
                <th className="px-4 py-2 text-right">Shares</th>
                <th className="px-4 py-2 text-right">Avg Cost</th>
                <th className="px-4 py-2 text-right">Current</th>
                <th className="px-4 py-2 text-right">Value</th>
                <th className="px-4 py-2 text-right">P&L</th>
                <th className="px-4 py-2 text-right">Alloc</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((pos) => (
                <tr key={pos.ticker} className="border-b last:border-0 hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3 font-mono font-semibold text-primary">{pos.ticker}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{pos.shares.toFixed(4)}</td>
                  <td className="px-4 py-3 text-right tabular-nums">${pos.avg_cost_basis.toFixed(2)}</td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {pos.current_price != null ? `$${pos.current_price.toFixed(2)}` : "—"}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {pos.market_value != null
                      ? `$${pos.market_value.toLocaleString("en-US", { minimumFractionDigits: 2 })}`
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {pos.unrealized_pnl != null ? (
                      <ChangeIndicator value={pos.unrealized_pnl} pct={pos.unrealized_pnl_pct ?? undefined} />
                    ) : "—"}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                    {pos.allocation_pct != null ? `${pos.allocation_pct.toFixed(1)}%` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function AllocationPanel({ summary }: { summary: PortfolioSummary }) {
  const chartData = summary.sectors.map((s) => ({ name: s.sector, value: s.market_value }))
  const overLimit = summary.sectors.filter((s) => s.over_limit)

  return (
    <div className="rounded-lg border bg-card">
      <div className="border-b px-4 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Allocation by Sector
        </h2>
      </div>
      {summary.sectors.length === 0 ? (
        <div className="px-4 py-12 text-center text-sm text-muted-foreground">No data</div>
      ) : (
        <div className="p-4">
          <div className="flex justify-center">
            <PieChart width={160} height={160}>
              <Pie data={chartData} dataKey="value" cx="50%" cy="50%" innerRadius={45} outerRadius={72}>
                {chartData.map((_, i) => (
                  <Cell key={i} fill={SECTOR_COLORS[i % SECTOR_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value: number) =>
                  `$${value.toLocaleString("en-US", { minimumFractionDigits: 0 })}`
                }
              />
            </PieChart>
          </div>
          <div className="mt-3 space-y-1">
            {summary.sectors.map((s, i) => (
              <div key={s.sector} className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-1.5">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-sm"
                    style={{ backgroundColor: SECTOR_COLORS[i % SECTOR_COLORS.length] }}
                  />
                  <span className="text-muted-foreground">{s.sector}</span>
                </span>
                <span className="tabular-nums font-medium">{s.pct.toFixed(1)}%</span>
              </div>
            ))}
          </div>
          {overLimit.length > 0 && (
            <div className="mt-3 rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
              ⚠️ {overLimit.map((s) => s.sector).join(", ")} over 30% concentration
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function PortfolioClient() {
  const { data: positions, isLoading: posLoading } = useQuery<Position[]>({
    queryKey: ["portfolio", "positions"],
    queryFn: () => api<Position[]>("/portfolio/positions"),
  })

  const { data: summary, isLoading: sumLoading } = useQuery<PortfolioSummary>({
    queryKey: ["portfolio", "summary"],
    queryFn: () => api<PortfolioSummary>("/portfolio/summary"),
  })

  if (posLoading || sumLoading || !summary) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[...Array(4)].map((_, i) => <MetricCardSkeleton key={i} />)}
        </div>
        <div className="h-64 animate-pulse rounded-lg bg-muted" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <KpiRow summary={summary} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[3fr_2fr]">
        <PositionsTable positions={positions ?? []} />
        <AllocationPanel summary={summary} />
      </div>
    </div>
  )
}
```

---

### Task 11: Portfolio page + nav link

**Files:**
- Create: `frontend/src/app/(authenticated)/portfolio/page.tsx`
- Modify: `frontend/src/components/nav-bar.tsx`

- [ ] **Step 1: Create the page**

```typescript
// frontend/src/app/(authenticated)/portfolio/page.tsx
import { PortfolioClient } from "./portfolio-client"

export const metadata = { title: "Portfolio" }

export default function PortfolioPage() {
  return (
    <div className="mx-auto max-w-7xl space-y-6 p-4 md:p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Portfolio</h1>
        <p className="text-sm text-muted-foreground">Your holdings, P&L, and sector allocation</p>
      </div>
      <PortfolioClient />
    </div>
  )
}
```

- [ ] **Step 2: Add Portfolio to the nav bar**

In `frontend/src/components/nav-bar.tsx`, find the nav links array (Dashboard, Screener) and add:

```typescript
{ href: "/portfolio", label: "Portfolio" },
```

in the same position/pattern as the existing links.

- [ ] **Step 3: Verify build**

```bash
cd frontend && npm run build
```

Expected: Zero errors, all routes compiled.

- [ ] **Step 4: Lint**

```bash
cd frontend && npm run lint
```

Expected: Zero errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/
git commit -m "feat: portfolio page — KPI row, positions table, allocation pie, log transaction dialog"
```

---

## Chunk 5: Doc Updates + Session Close

### Task 12: Update all docs and memories

**Files:**
- Modify: `PROGRESS.md`
- Modify: `project-plan.md`
- Modify: `docs/FSD.md`
- Modify: `docs/TDD.md`
- Modify: `docs/data-architecture.md`
- Update Serena memories: `project_overview`, `style_and_conventions`

- [ ] **Step 1: Add session entry to PROGRESS.md** covering:
  - What was built (models, migration 005, tool, router, 5 endpoints, frontend page)
  - Test count (163 → N)
  - Key decisions: FIFO as pure function, positions as DB table not view, opened_at preservation
  - Alembic head: `005_portfolio_tables`
  - Deferred items logged: value history, dividends, alerts, recs upgrade, Schwab OAuth
  - Next: fundamentals engine or agent/chat interface

- [ ] **Step 2: Update `project-plan.md`**
  - Mark Phase 3 portfolio deliverables 1-5 as complete
  - Add note: deferred portfolio features (value history, dividends, alerts) → Phase 3.5
  - Add Schwab OAuth as Phase 4 sub-item

- [ ] **Step 3: Update `docs/FSD.md`**
  - Add FR entries for: transaction log, FIFO positions, allocation view, 5 endpoints
  - Update Feature × Phase Matrix to mark portfolio tracker as implemented

- [ ] **Step 4: Update `docs/TDD.md`**
  - Add Section: Portfolio API contracts (all 5 endpoints with request/response shapes)
  - Add `backend/tools/portfolio.py` to tool registry section

- [ ] **Step 5: Update `docs/data-architecture.md`**
  - Add `portfolios`, `transactions`, `positions` to entity model
  - Note: transactions is append-only ledger; positions is recomputed materialized table

- [ ] **Step 6: Update Serena memories**
  - `project_overview` — update Current State: portfolio tracker complete, new test count, new Alembic head, next feature
  - `style_and_conventions` — add gotchas: `opened_at` preservation on upsert, FIFO as pure `_run_fifo()` function, ticker FK → 422 not 500

- [ ] **Step 7: Final commit**

```bash
git add PROGRESS.md project-plan.md docs/FSD.md docs/TDD.md docs/data-architecture.md
git commit -m "docs: portfolio tracker session complete — progress, plan, FSD, TDD, data-arch updated"
```

---

## Verification Checklist

Before marking this plan complete, confirm:

- [ ] `uv run alembic current` shows `005_portfolio_tables (head)`
- [ ] `uv run pytest tests/unit/test_portfolio.py -v` — all unit tests pass
- [ ] `uv run pytest tests/api/test_portfolio.py -v` — all API tests pass
- [ ] `uv run pytest tests/ -v` — full suite passes (no regressions)
- [ ] `uv run ruff check backend/ --fix && uv run ruff format backend/` — zero errors
- [ ] `cd frontend && npm run build` — zero errors
- [ ] `cd frontend && npm run lint` — zero errors
- [ ] `grep -r "is_in_universe" backend/` — zero results (sanity check)
