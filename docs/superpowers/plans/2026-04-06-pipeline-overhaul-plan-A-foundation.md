# Spec A: Ingestion Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship per-ticker, per-stage freshness tracking (`ticker_ingestion_state`), staleness SLAs, a `@tracked_task` decorator, and a `task_tracer` helper as additive primitives with zero production call sites.

**Architecture:** A mutable current-state table keyed on `ticker` tracks last-updated timestamps for 9 pipeline stages. An async service computes green/yellow/red bucketing against SLA constants defined in `backend/config.py`. A `@tracked_task` decorator wraps async functions in the existing `PipelineRunner` lifecycle. A `trace_task` async context manager wraps `LangfuseService` + `ObservabilityCollector` for non-agent Celery code paths.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Postgres/TimescaleDB, Celery, pytest

**Spec:** `docs/superpowers/specs/2026-04-06-pipeline-overhaul-spec-A-foundation.md`

---

## File Structure

### Created
```
backend/migrations/versions/025_ticker_ingestion_state.py   # NEW — Alembic migration
backend/models/ticker_ingestion_state.py                    # NEW — SQLAlchemy model
backend/services/ticker_state.py                            # NEW — freshness service
backend/services/observability/__init__.py                  # NEW — sub-package marker
backend/services/observability/task_tracer.py               # NEW — trace_task + handle
tests/unit/services/test_ticker_state.py                    # NEW — service unit tests (no DB)
tests/unit/services/test_task_tracer.py                     # NEW — tracer unit tests (no DB)
tests/unit/tasks/test_pipeline_runner_decorator.py          # NEW — decorator unit tests (no DB)
tests/api/test_ingestion_health_state.py                    # NEW — real-DB integration
tests/api/test_tracked_task_error_redaction.py              # NEW — persisted error_summary audit
tests/unit/conftest.py                                      # MODIFY — extend xdist guardrail to db_session
```

### Modified
```
backend/config.py                                           # MODIFY — StalenessSLAs class + property
backend/models/__init__.py                                  # MODIFY — register TickerIngestionState
backend/tasks/pipeline.py                                   # MODIFY — append tracked_task decorator
```

---

## Task 1: Migration 025 + `TickerIngestionState` Model

**Files:**
- Create: `backend/migrations/versions/025_ticker_ingestion_state.py`
- Create: `backend/models/ticker_ingestion_state.py`
- Create: `tests/api/test_ingestion_health_state.py`

Spec section: A1 (Ticker ingestion state table).

- [ ] **Step 1: Verify current Alembic head is `b2351fa2d293`**

```bash
uv run alembic current
```

Expected output should include `b2351fa2d293 (head)`. If not, STOP and reconcile before proceeding.

- [ ] **Step 2: Write the failing integration test skeleton**

Create `tests/api/test_ingestion_health_state.py`:

```python
"""Integration tests for ticker_ingestion_state table and migration 025."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from backend.models.stock import Stock
from backend.models.ticker_ingestion_state import TickerIngestionState

pytestmark = pytest.mark.asyncio


async def test_ticker_ingestion_state_table_exists(db_session) -> None:
    """Migration 025 must create the ticker_ingestion_state table."""
    result = await db_session.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = 'ticker_ingestion_state'"
        )
    )
    assert result.scalar_one_or_none() == "ticker_ingestion_state"


async def test_ticker_ingestion_state_has_expected_columns(db_session) -> None:
    """Schema must match spec A1 exactly."""
    result = await db_session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'ticker_ingestion_state' ORDER BY column_name"
        )
    )
    cols = {row[0] for row in result.fetchall()}
    assert cols == {
        "ticker",
        "prices_updated_at",
        "signals_updated_at",
        "fundamentals_updated_at",
        "forecast_updated_at",
        "forecast_retrained_at",
        "news_updated_at",
        "sentiment_updated_at",
        "convergence_updated_at",
        "backtest_updated_at",
        "created_at",
        "updated_at",
    }


async def test_stocks_cascade_delete_removes_ingestion_state_row(db_session) -> None:
    """FK ON DELETE CASCADE must remove ticker_ingestion_state when stock deleted."""
    now = datetime.now(timezone.utc)
    stock = Stock(ticker="TSTA", name="Test A", sector="Tech", industry="Soft")
    db_session.add(stock)
    await db_session.flush()
    db_session.add(
        TickerIngestionState(
            ticker="TSTA",
            prices_updated_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    await db_session.commit()

    await db_session.delete(stock)
    await db_session.commit()

    result = await db_session.execute(
        text("SELECT ticker FROM ticker_ingestion_state WHERE ticker = 'TSTA'")
    )
    assert result.scalar_one_or_none() is None
```

- [ ] **Step 3: Run the failing test to confirm it fails**

```bash
uv run pytest tests/api/test_ingestion_health_state.py -q --tb=short
```

Expected: all three tests fail with `ModuleNotFoundError: backend.models.ticker_ingestion_state` (model file not yet created).

- [ ] **Step 4: Create `backend/models/ticker_ingestion_state.py`**

```python
"""Per-ticker, per-stage ingestion freshness tracking."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class TickerIngestionState(Base):
    """One row per ticker — freshness timestamps for each pipeline stage.

    Mutable current-state table (NOT time-series). History lives in
    pipeline_runs and the domain tables themselves.
    """

    __tablename__ = "ticker_ingestion_state"

    ticker: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("stocks.ticker", ondelete="CASCADE"),
        primary_key=True,
    )

    prices_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    signals_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    fundamentals_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    forecast_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    forecast_retrained_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    news_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sentiment_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    convergence_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    backtest_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    def __repr__(self) -> str:
        return f"<TickerIngestionState {self.ticker}>"
```

- [ ] **Step 5: Create migration 025**

Create `backend/migrations/versions/025_ticker_ingestion_state.py`. `down_revision` MUST be `"b2351fa2d293"` (024 forecast intelligence tables — current head per MEMORY.md).

```python
"""025_ticker_ingestion_state

Revision ID: e1f2a3b4c5d6
Revises: b2351fa2d293
Create Date: 2026-04-06 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e1f2a3b4c5d6"
down_revision = "b2351fa2d293"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ticker_ingestion_state table + indexes + backfill from stocks."""
    op.create_table(
        "ticker_ingestion_state",
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column(
            "prices_updated_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "signals_updated_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "fundamentals_updated_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "forecast_updated_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "forecast_retrained_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("news_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "sentiment_updated_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "convergence_updated_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "backtest_updated_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["ticker"], ["stocks.ticker"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("ticker"),
    )
    op.create_index(
        "ix_ticker_ingestion_state_prices_updated_at",
        "ticker_ingestion_state",
        ["prices_updated_at"],
    )
    op.create_index(
        "ix_ticker_ingestion_state_signals_updated_at",
        "ticker_ingestion_state",
        ["signals_updated_at"],
    )
    op.create_index(
        "ix_ticker_ingestion_state_forecast_updated_at",
        "ticker_ingestion_state",
        ["forecast_updated_at"],
    )

    # Backfill prices_updated_at from stocks.last_fetched_at. Other columns
    # start NULL and populate organically as tasks run.
    op.execute(
        """
        INSERT INTO ticker_ingestion_state
            (ticker, prices_updated_at, created_at, updated_at)
        SELECT ticker, last_fetched_at, now(), now()
        FROM stocks
        """
    )


def downgrade() -> None:
    """Drop indexes and table (no data to preserve — additive only)."""
    op.drop_index(
        "ix_ticker_ingestion_state_forecast_updated_at",
        table_name="ticker_ingestion_state",
    )
    op.drop_index(
        "ix_ticker_ingestion_state_signals_updated_at",
        table_name="ticker_ingestion_state",
    )
    op.drop_index(
        "ix_ticker_ingestion_state_prices_updated_at",
        table_name="ticker_ingestion_state",
    )
    op.drop_table("ticker_ingestion_state")
```

- [ ] **Step 6: Apply the migration locally and verify head**

```bash
uv run alembic upgrade head && uv run alembic current
```

Expected: `e1f2a3b4c5d6 (head)`.

- [ ] **Step 7: Re-run the integration test to confirm pass**

```bash
uv run pytest tests/api/test_ingestion_health_state.py -q --tb=short
```

Expected: 3 passed.

- [ ] **Step 8: Lint**

```bash
uv run ruff check --fix backend/models/ticker_ingestion_state.py backend/migrations/versions/025_ticker_ingestion_state.py tests/api/test_ingestion_health_state.py && uv run ruff format backend/models/ticker_ingestion_state.py backend/migrations/versions/025_ticker_ingestion_state.py tests/api/test_ingestion_health_state.py
```

- [ ] **Step 9: Commit**

```bash
git add backend/migrations/versions/025_ticker_ingestion_state.py backend/models/ticker_ingestion_state.py tests/api/test_ingestion_health_state.py
git commit -m "feat(ingestion): add ticker_ingestion_state table (Spec A §A1)"
```

---

## Task 2: Register Model in `backend/models/__init__.py`

**Files:**
- Modify: `backend/models/__init__.py`

Spec section: A1 (model discovery).

- [ ] **Step 1: Add import + `__all__` entry**

In `backend/models/__init__.py`, add this import alphabetically (after `from backend.models.stock import ...`):

```python
from backend.models.ticker_ingestion_state import TickerIngestionState
```

And add `"TickerIngestionState",` to `__all__` in alphabetical order (between `"Stock",` and `"StockIndex",` — note: `"TickerIngestionState"` sorts after `"StockPrice"` and `"ToolExecutionLog"`; place it between `"ToolExecutionLog"` and `"Transaction"`).

- [ ] **Step 2: Verify the import resolves and Alembic still sees metadata**

```bash
uv run python -c "from backend.models import TickerIngestionState; print(TickerIngestionState.__tablename__)"
```

Expected output: `ticker_ingestion_state`.

- [ ] **Step 3: Run full unit suite to confirm no breakage**

```bash
uv run pytest tests/unit/ -q --tb=short -x
```

Expected: all pre-existing tests still pass (no regressions from the model registration).

- [ ] **Step 4: Lint**

```bash
uv run ruff check --fix backend/models/__init__.py && uv run ruff format backend/models/__init__.py
```

- [ ] **Step 5: Commit**

```bash
git add backend/models/__init__.py
git commit -m "feat(models): register TickerIngestionState for Alembic discovery (Spec A §A1)"
```

---

## Task 3: Staleness SLA Constants in `backend/config.py`

**Files:**
- Modify: `backend/config.py`
- Create: `tests/unit/services/test_ticker_state.py` (first test only — full suite lands in Task 4)

Spec section: A2 (Staleness SLA constants).

- [ ] **Step 1: Write the failing SLA value test**

Create `tests/unit/services/test_ticker_state.py` with just the SLA change-detector test:

```python
"""Unit tests for ticker_state service and staleness SLAs."""

from __future__ import annotations

from datetime import timedelta

import pytest

pytestmark = pytest.mark.asyncio


def test_staleness_slas_exact_values() -> None:
    """Change-detector: any SLA edit must be deliberate and reviewed.

    Spec A §A2 pins these values. Do not relax without a PR + PM approval.
    """
    from backend.config import StalenessSLAs

    sla = StalenessSLAs()
    assert sla.prices == timedelta(hours=4)
    assert sla.signals == timedelta(hours=4)
    assert sla.fundamentals == timedelta(hours=24)
    assert sla.forecast == timedelta(hours=24)
    assert sla.forecast_retrain == timedelta(days=14)
    assert sla.news == timedelta(hours=6)
    assert sla.sentiment == timedelta(hours=6)
    assert sla.convergence == timedelta(hours=24)
    assert sla.backtest == timedelta(days=7)


def test_settings_staleness_slas_property_returns_instance() -> None:
    """`settings.staleness_slas` must yield a StalenessSLAs instance."""
    from backend.config import StalenessSLAs, settings

    assert isinstance(settings.staleness_slas, StalenessSLAs)
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/unit/services/test_ticker_state.py -q --tb=short
```

Expected: `ImportError` / `AttributeError` — `StalenessSLAs` does not exist.

- [ ] **Step 3: Add `StalenessSLAs` + property to `backend/config.py`**

At the top of `backend/config.py`, ensure `from datetime import timedelta` is present (add it if missing, alphabetically in the stdlib block).

Immediately before the `class Settings(BaseSettings):` definition, add:

```python
class StalenessSLAs:
    """Green-threshold freshness SLAs per pipeline stage.

    Yellow = 2x green. Red = >2x green. See services/ticker_state.py for
    the bucketing logic.

    These are module-level constants (immutable) rather than a Pydantic
    settings class because they are a product decision, not an env knob.
    If a deployment wants tighter SLAs, bump the constants in a PR — don't
    flip them per-environment.
    """

    prices: timedelta = timedelta(hours=4)
    signals: timedelta = timedelta(hours=4)
    fundamentals: timedelta = timedelta(hours=24)
    forecast: timedelta = timedelta(hours=24)
    forecast_retrain: timedelta = timedelta(days=14)
    news: timedelta = timedelta(hours=6)
    sentiment: timedelta = timedelta(hours=6)
    convergence: timedelta = timedelta(hours=24)
    backtest: timedelta = timedelta(days=7)
```

Inside `class Settings(BaseSettings):`, add the property at the bottom of the class (before any trailing class-level config):

```python
    @property
    def staleness_slas(self) -> StalenessSLAs:
        """Return the staleness SLA constants (see StalenessSLAs docstring)."""
        return StalenessSLAs()
```

- [ ] **Step 4: Run the SLA tests to verify pass**

```bash
uv run pytest tests/unit/services/test_ticker_state.py -q --tb=short
```

Expected: 2 passed.

- [ ] **Step 5: Lint**

```bash
uv run ruff check --fix backend/config.py tests/unit/services/test_ticker_state.py && uv run ruff format backend/config.py tests/unit/services/test_ticker_state.py
```

- [ ] **Step 6: Commit**

```bash
git add backend/config.py tests/unit/services/test_ticker_state.py
git commit -m "feat(config): add StalenessSLAs freshness constants (Spec A §A2)"
```

---

## Task 4: `backend/services/ticker_state.py` Service

**Files:**
- Create: `backend/services/ticker_state.py`
- Modify: `tests/unit/services/test_ticker_state.py` (append full suite)

Spec section: A1 (Service file).

- [ ] **Step 1: Append failing service tests**

Append to `tests/unit/services/test_ticker_state.py`:

```python
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from freezegun import freeze_time


def _make_state_row(**overrides):
    """Build a TickerIngestionState instance with sensible defaults."""
    from backend.models.ticker_ingestion_state import TickerIngestionState

    now = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)
    defaults = {
        "ticker": "AAPL",
        "prices_updated_at": None,
        "signals_updated_at": None,
        "fundamentals_updated_at": None,
        "forecast_updated_at": None,
        "forecast_retrained_at": None,
        "news_updated_at": None,
        "sentiment_updated_at": None,
        "convergence_updated_at": None,
        "backtest_updated_at": None,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return TickerIngestionState(**defaults)


@freeze_time("2026-04-06 12:00:00")
async def test_get_ticker_readiness_missing_row_returns_unknown() -> None:
    """Missing row → every stage is 'unknown', overall 'unknown'."""
    from backend.services import ticker_state

    fake_session = AsyncMock()
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = None
    fake_session.execute = AsyncMock(return_value=fake_result)

    with patch.object(
        ticker_state, "async_session_factory"
    ) as factory:
        factory.return_value.__aenter__.return_value = fake_session
        factory.return_value.__aexit__.return_value = None
        readiness = await ticker_state.get_ticker_readiness("ZZZZ")

    assert readiness.ticker == "ZZZZ"
    assert readiness.overall == "unknown"
    assert all(v == "unknown" for v in readiness.stages.values())


@freeze_time("2026-04-06 12:00:00")
async def test_get_ticker_readiness_green_when_fresh() -> None:
    """All stages fresh → green."""
    from backend.services import ticker_state

    now = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)
    row = _make_state_row(
        prices_updated_at=now,
        signals_updated_at=now,
        fundamentals_updated_at=now,
        forecast_updated_at=now,
        forecast_retrained_at=now,
        news_updated_at=now,
        sentiment_updated_at=now,
        convergence_updated_at=now,
        backtest_updated_at=now,
    )

    fake_session = AsyncMock()
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = row
    fake_session.execute = AsyncMock(return_value=fake_result)

    with patch.object(ticker_state, "async_session_factory") as factory:
        factory.return_value.__aenter__.return_value = fake_session
        factory.return_value.__aexit__.return_value = None
        readiness = await ticker_state.get_ticker_readiness("AAPL")

    assert readiness.overall == "green"
    assert all(v == "green" for v in readiness.stages.values())


@freeze_time("2026-04-06 12:00:00")
async def test_get_ticker_readiness_yellow_between_1x_and_2x_sla() -> None:
    """Aged 1.5× SLA → yellow."""
    from datetime import timedelta

    from backend.services import ticker_state

    aged = datetime(2026, 4, 6, 6, 0, tzinfo=timezone.utc)  # 6h old — prices SLA 4h
    row = _make_state_row(prices_updated_at=aged)

    fake_session = AsyncMock()
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = row
    fake_session.execute = AsyncMock(return_value=fake_result)

    with patch.object(ticker_state, "async_session_factory") as factory:
        factory.return_value.__aenter__.return_value = fake_session
        factory.return_value.__aexit__.return_value = None
        readiness = await ticker_state.get_ticker_readiness("AAPL")

    assert readiness.stages["prices"] == "yellow"
    # 6h < 2x4h=8h ⇒ yellow; sanity check the math
    assert (datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc) - aged) == timedelta(hours=6)


@freeze_time("2026-04-06 12:00:00")
async def test_get_ticker_readiness_red_beyond_2x_sla() -> None:
    """Aged >2× SLA → red."""
    from backend.services import ticker_state

    aged = datetime(2026, 4, 5, 20, 0, tzinfo=timezone.utc)  # 16h old — prices SLA 4h
    row = _make_state_row(prices_updated_at=aged)

    fake_session = AsyncMock()
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = row
    fake_session.execute = AsyncMock(return_value=fake_result)

    with patch.object(ticker_state, "async_session_factory") as factory:
        factory.return_value.__aenter__.return_value = fake_session
        factory.return_value.__aexit__.return_value = None
        readiness = await ticker_state.get_ticker_readiness("AAPL")

    assert readiness.stages["prices"] == "red"


@freeze_time("2026-04-06 12:00:00")
async def test_get_ticker_readiness_overall_is_worst_stage() -> None:
    """Overall is the minimum over (red<yellow<unknown<green)."""
    from backend.services import ticker_state

    now = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)
    aged_red = datetime(2026, 4, 5, 20, 0, tzinfo=timezone.utc)
    row = _make_state_row(
        prices_updated_at=now,  # green
        forecast_updated_at=aged_red,  # red (16h > 2*4h... wait forecast SLA is 24h)
    )
    # forecast SLA 24h. For red we need >48h. Adjust aged_red:
    row.forecast_updated_at = datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc)  # 72h

    fake_session = AsyncMock()
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = row
    fake_session.execute = AsyncMock(return_value=fake_result)

    with patch.object(ticker_state, "async_session_factory") as factory:
        factory.return_value.__aenter__.return_value = fake_session
        factory.return_value.__aexit__.return_value = None
        readiness = await ticker_state.get_ticker_readiness("AAPL")

    assert readiness.stages["prices"] == "green"
    assert readiness.stages["forecast"] == "red"
    assert readiness.overall == "red"


async def test_mark_stage_updated_swallows_db_error() -> None:
    """Fire-and-forget: DB errors must never propagate."""
    from backend.services import ticker_state

    with patch.object(
        ticker_state, "async_session_factory", side_effect=RuntimeError("db dead")
    ):
        # Must return None, not raise
        await ticker_state.mark_stage_updated("AAPL", "prices")


async def test_mark_stage_updated_forecast_vs_forecast_retrain() -> None:
    """'forecast' writes forecast_updated_at; 'forecast_retrain' writes forecast_retrained_at."""
    from backend.services import ticker_state

    captured_stmts: list = []

    async def fake_execute(stmt):
        captured_stmts.append(stmt)
        return MagicMock()

    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(side_effect=fake_execute)
    fake_session.commit = AsyncMock()

    with patch.object(ticker_state, "async_session_factory") as factory:
        factory.return_value.__aenter__.return_value = fake_session
        factory.return_value.__aexit__.return_value = None

        await ticker_state.mark_stage_updated("AAPL", "forecast")
        await ticker_state.mark_stage_updated("AAPL", "forecast_retrain")

    # Both statements should have been issued
    assert len(captured_stmts) == 2


@freeze_time("2026-04-06 12:00:00")
async def test_get_universe_health_orders_red_first() -> None:
    """Sort order: red, yellow, unknown, green then ticker."""
    from backend.services import ticker_state

    now = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)
    aged_red = datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc)  # 24h for prices (red)
    rows = [
        _make_state_row(ticker="GRN", prices_updated_at=now),
        _make_state_row(ticker="RED", prices_updated_at=aged_red),
        _make_state_row(ticker="UNK"),  # no timestamps
    ]

    fake_session = AsyncMock()
    fake_result = MagicMock()
    fake_result.scalars.return_value = rows
    fake_session.execute = AsyncMock(return_value=fake_result)

    with patch.object(ticker_state, "async_session_factory") as factory:
        factory.return_value.__aenter__.return_value = fake_session
        factory.return_value.__aexit__.return_value = None
        health = await ticker_state.get_universe_health()

    tickers_in_order = [r.ticker for r in health]
    # RED must come before UNK which must come before GRN
    assert tickers_in_order.index("RED") < tickers_in_order.index("UNK")
    assert tickers_in_order.index("UNK") < tickers_in_order.index("GRN")


async def test_get_universe_health_empty_table_returns_empty_list() -> None:
    """Empty table → empty list (not None, not error)."""
    from backend.services import ticker_state

    fake_session = AsyncMock()
    fake_result = MagicMock()
    fake_result.scalars.return_value = []
    fake_session.execute = AsyncMock(return_value=fake_result)

    with patch.object(ticker_state, "async_session_factory") as factory:
        factory.return_value.__aenter__.return_value = fake_session
        factory.return_value.__aexit__.return_value = None
        health = await ticker_state.get_universe_health()

    assert health == []
```

- [ ] **Step 2: Run to confirm all new tests fail**

```bash
uv run pytest tests/unit/services/test_ticker_state.py -q --tb=short
```

Expected: the 2 SLA tests from Task 3 still pass; all new tests fail with `ModuleNotFoundError: backend.services.ticker_state`.

- [ ] **Step 3: Create `backend/services/ticker_state.py`**

```python
"""Per-ticker, per-stage ingestion freshness service."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from backend.config import settings
from backend.database import async_session_factory
from backend.models.ticker_ingestion_state import TickerIngestionState

logger = logging.getLogger(__name__)

Stage = Literal[
    "prices",
    "signals",
    "fundamentals",
    "forecast",
    "forecast_retrain",
    "news",
    "sentiment",
    "convergence",
    "backtest",
]

StageStatus = Literal["green", "yellow", "red", "unknown"]

# Stage → column name. "forecast_retrain" targets forecast_retrained_at.
_STAGE_COLUMNS: dict[Stage, str] = {
    "prices": "prices_updated_at",
    "signals": "signals_updated_at",
    "fundamentals": "fundamentals_updated_at",
    "forecast": "forecast_updated_at",
    "forecast_retrain": "forecast_retrained_at",
    "news": "news_updated_at",
    "sentiment": "sentiment_updated_at",
    "convergence": "convergence_updated_at",
    "backtest": "backtest_updated_at",
}


@dataclass(frozen=True, slots=True)
class ReadinessState:
    """Per-ticker freshness snapshot with per-stage status buckets."""

    ticker: str
    stages: dict[Stage, StageStatus]
    timestamps: dict[Stage, datetime | None]
    overall: StageStatus  # worst-stage wins


@dataclass(frozen=True, slots=True)
class ReadinessRow:
    """Flat row for the universe health dashboard."""

    ticker: str
    prices: StageStatus
    signals: StageStatus
    fundamentals: StageStatus
    forecast: StageStatus
    news: StageStatus
    sentiment: StageStatus
    convergence: StageStatus
    backtest: StageStatus
    overall: StageStatus


async def mark_stage_updated(ticker: str, stage: Stage) -> None:
    """Idempotent upsert of the stage timestamp for a ticker.

    Safe to call concurrently — uses ON CONFLICT DO UPDATE. Fire-and-forget:
    errors are logged at warning but never propagated, so an observability
    write failure cannot kill an ingestion task.

    Args:
        ticker: Stock ticker symbol.
        stage: Which pipeline stage just completed.
    """
    now = datetime.now(timezone.utc)
    col = _STAGE_COLUMNS[stage]
    values = {
        "ticker": ticker,
        col: now,
        "created_at": now,
        "updated_at": now,
    }
    stmt = insert(TickerIngestionState).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker"],
        set_={col: now, "updated_at": now},
    )
    try:
        async with async_session_factory() as session:
            await session.execute(stmt)
            await session.commit()
    except Exception:
        logger.warning(
            "Failed to mark stage %s for ticker %s", stage, ticker, exc_info=True
        )


async def get_ticker_readiness(ticker: str) -> ReadinessState:
    """Return freshness status for a single ticker across all stages.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        ReadinessState with per-stage status and the worst-stage overall.
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(TickerIngestionState).where(
                TickerIngestionState.ticker == ticker
            )
        )
        row = result.scalar_one_or_none()

    return _compute_readiness(ticker, row)


async def get_universe_health() -> list[ReadinessRow]:
    """Return freshness status for every ticker in the universe.

    Returns:
        One ReadinessRow per ticker in ticker_ingestion_state, sorted by
        overall status (red first) then ticker ascending.
    """
    async with async_session_factory() as session:
        result = await session.execute(select(TickerIngestionState))
        rows = list(result.scalars())

    readiness = [_compute_readiness(r.ticker, r) for r in rows]
    priority = {"red": 0, "yellow": 1, "unknown": 2, "green": 3}
    ordered = sorted(
        readiness, key=lambda r: (priority[r.overall], r.ticker)
    )
    return [_to_row(r) for r in ordered]


def _compute_readiness(
    ticker: str, row: TickerIngestionState | None
) -> ReadinessState:
    """Compute per-stage status from a row (or absence thereof)."""
    sla = settings.staleness_slas
    now = datetime.now(timezone.utc)

    def status_for(
        ts: datetime | None, green: timedelta, yellow: timedelta
    ) -> StageStatus:
        if ts is None:
            return "unknown"
        age = now - ts
        if age <= green:
            return "green"
        if age <= yellow:
            return "yellow"
        return "red"

    timestamps: dict[Stage, datetime | None] = {
        "prices": row.prices_updated_at if row else None,
        "signals": row.signals_updated_at if row else None,
        "fundamentals": row.fundamentals_updated_at if row else None,
        "forecast": row.forecast_updated_at if row else None,
        "forecast_retrain": row.forecast_retrained_at if row else None,
        "news": row.news_updated_at if row else None,
        "sentiment": row.sentiment_updated_at if row else None,
        "convergence": row.convergence_updated_at if row else None,
        "backtest": row.backtest_updated_at if row else None,
    }

    stages: dict[Stage, StageStatus] = {
        "prices": status_for(
            timestamps["prices"], sla.prices, sla.prices * 2
        ),
        "signals": status_for(
            timestamps["signals"], sla.signals, sla.signals * 2
        ),
        "fundamentals": status_for(
            timestamps["fundamentals"], sla.fundamentals, sla.fundamentals * 2
        ),
        "forecast": status_for(
            timestamps["forecast"], sla.forecast, sla.forecast * 2
        ),
        "forecast_retrain": status_for(
            timestamps["forecast_retrain"],
            sla.forecast_retrain,
            sla.forecast_retrain * 2,
        ),
        "news": status_for(timestamps["news"], sla.news, sla.news * 2),
        "sentiment": status_for(
            timestamps["sentiment"], sla.sentiment, sla.sentiment * 2
        ),
        "convergence": status_for(
            timestamps["convergence"], sla.convergence, sla.convergence * 2
        ),
        "backtest": status_for(
            timestamps["backtest"], sla.backtest, sla.backtest * 2
        ),
    }

    overall = _worst(stages.values())
    return ReadinessState(
        ticker=ticker, stages=stages, timestamps=timestamps, overall=overall
    )


def _worst(values: Iterable[StageStatus]) -> StageStatus:
    """Return the worst stage status (red > yellow > unknown > green)."""
    priority = {"red": 0, "yellow": 1, "unknown": 2, "green": 3}
    return min(values, key=lambda s: priority[s], default="unknown")


def _to_row(r: ReadinessState) -> ReadinessRow:
    """Flatten a ReadinessState into a dashboard row (drops forecast_retrain)."""
    s = r.stages
    return ReadinessRow(
        ticker=r.ticker,
        prices=s["prices"],
        signals=s["signals"],
        fundamentals=s["fundamentals"],
        forecast=s["forecast"],
        news=s["news"],
        sentiment=s["sentiment"],
        convergence=s["convergence"],
        backtest=s["backtest"],
        overall=r.overall,
    )
```

- [ ] **Step 4: Run unit tests to confirm pass**

```bash
uv run pytest tests/unit/services/test_ticker_state.py -q --tb=short
```

Expected: all ticker_state tests pass.

- [ ] **Step 5: Lint**

```bash
uv run ruff check --fix backend/services/ticker_state.py tests/unit/services/test_ticker_state.py && uv run ruff format backend/services/ticker_state.py tests/unit/services/test_ticker_state.py
```

- [ ] **Step 6: Commit**

```bash
git add backend/services/ticker_state.py tests/unit/services/test_ticker_state.py
git commit -m "feat(services): add ticker_state freshness service (Spec A §A1)"
```

---

## Task 5: `@tracked_task` Decorator in `backend/tasks/pipeline.py`

**Files:**
- Modify: `backend/tasks/pipeline.py`
- Create: `tests/unit/tasks/test_pipeline_runner_decorator.py`

Spec section: A3 (PipelineRunner unified contract).

- [ ] **Step 1: Write failing decorator tests**

Create `tests/unit/tasks/test_pipeline_runner_decorator.py`:

```python
"""Unit tests for the @tracked_task decorator on PipelineRunner."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio


async def test_tracked_task_happy_path_calls_start_and_complete() -> None:
    """Decorator runs start_run → fn → complete_run on success."""
    from backend.tasks import pipeline

    run_id = uuid.uuid4()

    with patch.object(
        pipeline.PipelineRunner, "start_run", new=AsyncMock(return_value=run_id)
    ) as start_mock, patch.object(
        pipeline.PipelineRunner, "complete_run", new=AsyncMock()
    ) as complete_mock:

        @pipeline.tracked_task("unit_test_pipeline")
        async def inner(*, run_id: uuid.UUID) -> dict[str, bool]:
            assert isinstance(run_id, uuid.UUID)
            return {"ok": True}

        result = await inner()

    assert result == {"ok": True}
    start_mock.assert_awaited_once()
    complete_mock.assert_awaited_once_with(run_id)


async def test_tracked_task_injects_run_id_kwarg() -> None:
    """Inner fn must receive `run_id` as a kwarg."""
    from backend.tasks import pipeline

    run_id = uuid.uuid4()
    received: dict[str, uuid.UUID] = {}

    with patch.object(
        pipeline.PipelineRunner, "start_run", new=AsyncMock(return_value=run_id)
    ), patch.object(pipeline.PipelineRunner, "complete_run", new=AsyncMock()):

        @pipeline.tracked_task("p")
        async def inner(*, run_id: uuid.UUID) -> None:
            received["run_id"] = run_id

        await inner()

    assert received["run_id"] == run_id


async def test_tracked_task_forwards_tickers_total() -> None:
    """`tickers_total` is consumed by the decorator, not forwarded to inner."""
    from backend.tasks import pipeline

    run_id = uuid.uuid4()
    start_mock = AsyncMock(return_value=run_id)

    with patch.object(
        pipeline.PipelineRunner, "start_run", new=start_mock
    ), patch.object(pipeline.PipelineRunner, "complete_run", new=AsyncMock()):

        @pipeline.tracked_task("p")
        async def inner(*, run_id: uuid.UUID) -> None:
            # Would raise TypeError if tickers_total leaked through
            pass

        await inner(tickers_total=500)

    call_kwargs = start_mock.await_args.kwargs
    assert call_kwargs["tickers_total"] == 500
    assert call_kwargs["pipeline_name"] == "p"


async def test_tracked_task_marks_failed_on_exception() -> None:
    """Inner raises → complete_run called with status='failed'; exception re-raised."""
    from backend.tasks import pipeline

    run_id = uuid.uuid4()
    complete_mock = AsyncMock()

    with patch.object(
        pipeline.PipelineRunner, "start_run", new=AsyncMock(return_value=run_id)
    ), patch.object(
        pipeline.PipelineRunner, "complete_run", new=complete_mock
    ):

        @pipeline.tracked_task("p")
        async def inner(*, run_id: uuid.UUID) -> None:
            raise ValueError("secret db password hunter2")

        with pytest.raises(ValueError):
            await inner()

    complete_mock.assert_awaited_once()
    call_kwargs = complete_mock.await_args.kwargs
    assert call_kwargs.get("status") == "failed"
    # Hard Rule #10: `error_summary` never carries the raw exception string.
    summary = call_kwargs.get("error_summary") or {}
    assert "hunter2" not in str(summary)
    assert "secret db password" not in str(summary)


async def test_tracked_task_default_trigger_is_scheduled() -> None:
    """Default trigger is 'scheduled'."""
    from backend.tasks import pipeline

    run_id = uuid.uuid4()
    start_mock = AsyncMock(return_value=run_id)

    with patch.object(
        pipeline.PipelineRunner, "start_run", new=start_mock
    ), patch.object(pipeline.PipelineRunner, "complete_run", new=AsyncMock()):

        @pipeline.tracked_task("p")
        async def inner(*, run_id: uuid.UUID) -> None:
            pass

        await inner()

    assert start_mock.await_args.kwargs["trigger"] == "scheduled"


async def test_tracked_task_custom_trigger_passthrough() -> None:
    """Custom trigger flows through to start_run."""
    from backend.tasks import pipeline

    run_id = uuid.uuid4()
    start_mock = AsyncMock(return_value=run_id)

    with patch.object(
        pipeline.PipelineRunner, "start_run", new=start_mock
    ), patch.object(pipeline.PipelineRunner, "complete_run", new=AsyncMock()):

        @pipeline.tracked_task("p", trigger="manual")
        async def inner(*, run_id: uuid.UUID) -> None:
            pass

        await inner()

    assert start_mock.await_args.kwargs["trigger"] == "manual"
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/unit/tasks/test_pipeline_runner_decorator.py -q --tb=short
```

Expected: `AttributeError: module 'backend.tasks.pipeline' has no attribute 'tracked_task'`.

- [ ] **Step 3: Append the `tracked_task` decorator to `backend/tasks/pipeline.py`**

At the top of `backend/tasks/pipeline.py`, ensure the following imports exist (add if missing):

```python
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from functools import wraps
from typing import ParamSpec, TypeVar

from sqlalchemy import update

from backend.database import async_session_factory
from backend.models.pipeline import PipelineRun
```

At the bottom of the module (after the existing `with_retry` helper), append:

```python
P = ParamSpec("P")
R = TypeVar("R")


def tracked_task(
    pipeline_name: str,
    *,
    trigger: str = "scheduled",
) -> Callable[[Callable[..., Awaitable[R]]], Callable[..., Awaitable[R]]]:
    """Decorate an async task function with the PipelineRunner lifecycle.

    The decorated function is called with ``run_id: uuid.UUID`` as an
    extra keyword argument. On success, the pipeline run is marked
    completed; on exception the run is marked failed (with a generic
    error_summary — never the raw exception text, per Hard Rule #10) and
    the exception re-raises so Celery retry policy still triggers.

    Callers may pass ``tickers_total`` as a kwarg — it is consumed by the
    decorator (not forwarded to the wrapped function) and recorded on the
    pipeline_runs row.

    Args:
        pipeline_name: Name recorded in pipeline_runs.pipeline_name.
        trigger: "scheduled" | "backfill" | "manual".

    Returns:
        A decorator that wraps an async function with the runner lifecycle.
    """

    def decorator(
        fn: Callable[..., Awaitable[R]],
    ) -> Callable[..., Awaitable[R]]:
        runner = PipelineRunner()

        @wraps(fn)
        async def wrapper(*args: object, **kwargs: object) -> R:
            tickers_total_raw = kwargs.pop("tickers_total", 0)
            tickers_total = int(tickers_total_raw)  # type: ignore[arg-type]
            run_id = await runner.start_run(
                pipeline_name=pipeline_name,
                trigger=trigger,
                tickers_total=tickers_total,
            )
            try:
                result = await fn(*args, run_id=run_id, **kwargs)
            except Exception:
                logger.exception(
                    "Tracked task %s crashed — marking run %s failed",
                    pipeline_name,
                    run_id,
                )
                try:
                    async with async_session_factory() as session:
                        stmt = (
                            update(PipelineRun)
                            .where(PipelineRun.id == run_id)
                            .values(
                                status="failed",
                                completed_at=datetime.now(timezone.utc),
                                error_summary={"_exception": "see logs"},
                            )
                        )
                        await session.execute(stmt)
                        await session.commit()
                except Exception:
                    logger.warning(
                        "Failed to mark run %s as failed", run_id, exc_info=True
                    )
                raise
            else:
                await runner.complete_run(run_id)
                return result

        return wrapper

    return decorator
```

- [ ] **Step 4: Run decorator tests**

```bash
uv run pytest tests/unit/tasks/test_pipeline_runner_decorator.py -q --tb=short
```

Expected: all 6 tests pass.

- [ ] **Step 5: Run full pipeline test module for regression check**

```bash
uv run pytest tests/unit/pipeline/ -q --tb=short
```

Expected: all existing PipelineRunner tests still pass.

- [ ] **Step 6: Lint**

```bash
uv run ruff check --fix backend/tasks/pipeline.py tests/unit/tasks/test_pipeline_runner_decorator.py && uv run ruff format backend/tasks/pipeline.py tests/unit/tasks/test_pipeline_runner_decorator.py
```

- [ ] **Step 7: Commit**

```bash
git add backend/tasks/pipeline.py tests/unit/tasks/test_pipeline_runner_decorator.py
git commit -m "feat(tasks): add @tracked_task decorator for PipelineRunner (Spec A §A3)"
```

---

## Task 6: `task_tracer` Helper + `observability` Sub-Package

**Files:**
- Create: `backend/services/observability/__init__.py`
- Create: `backend/services/observability/task_tracer.py`
- Create: `tests/unit/services/test_task_tracer.py`

Spec section: A4 (Task tracer helper).

- [ ] **Step 1: Write failing tracer tests**

Create `tests/unit/services/test_task_tracer.py`:

```python
"""Unit tests for trace_task async context manager."""

from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


def _make_langfuse(trace_obj=None):
    """Build a MagicMock LangfuseService. trace_obj=None simulates disabled."""
    svc = MagicMock()
    svc.create_trace = MagicMock(return_value=trace_obj)
    return svc


def _make_collector():
    collector = MagicMock()
    collector.record_request = AsyncMock()
    return collector


async def test_trace_task_creates_langfuse_trace_with_task_metadata() -> None:
    """create_trace called with metadata containing task name + extras."""
    from backend.services.observability.task_tracer import trace_task

    trace_obj = MagicMock()
    langfuse = _make_langfuse(trace_obj)
    collector = _make_collector()

    async with trace_task(
        "nightly_sentiment",
        langfuse=langfuse,
        collector=collector,
        metadata={"ticker_count": 500},
    ) as handle:
        assert handle.name == "nightly_sentiment"

    langfuse.create_trace.assert_called_once()
    call_kwargs = langfuse.create_trace.call_args.kwargs
    assert call_kwargs["metadata"]["task"] == "nightly_sentiment"
    assert call_kwargs["metadata"]["ticker_count"] == 500


async def test_trace_task_handles_disabled_langfuse() -> None:
    """Disabled Langfuse (create_trace → None) must not raise."""
    from backend.services.observability.task_tracer import trace_task

    langfuse = _make_langfuse(trace_obj=None)
    collector = _make_collector()

    async with trace_task(
        "x", langfuse=langfuse, collector=collector
    ) as handle:
        assert handle._trace is None


async def test_trace_task_records_llm_via_collector() -> None:
    """handle.record_llm delegates to collector.record_request."""
    from backend.services.observability.task_tracer import trace_task

    trace_obj = MagicMock()
    langfuse = _make_langfuse(trace_obj)
    collector = _make_collector()

    async with trace_task(
        "x", langfuse=langfuse, collector=collector
    ) as handle:
        await handle.record_llm(
            model="gpt-4o-mini",
            provider="openai",
            tier="cheap",
            latency_ms=450,
            prompt_tokens=300,
            completion_tokens=40,
            cost_usd=0.0012,
        )

    collector.record_request.assert_awaited_once()
    kwargs = collector.record_request.await_args.kwargs
    assert kwargs["model"] == "gpt-4o-mini"
    assert kwargs["langfuse_trace_id"] == handle.trace_id
    assert isinstance(handle.trace_id, uuid.UUID)


async def test_trace_task_exception_sets_error_status() -> None:
    """Exception inside context → status=error, re-raised."""
    from backend.services.observability.task_tracer import (
        TaskTraceHandle,
        trace_task,
    )

    trace_obj = MagicMock()
    langfuse = _make_langfuse(trace_obj)
    collector = _make_collector()
    captured: dict[str, TaskTraceHandle] = {}

    with pytest.raises(ValueError):
        async with trace_task(
            "x", langfuse=langfuse, collector=collector
        ) as handle:
            captured["handle"] = handle
            raise ValueError("boom")

    assert captured["handle"]._status == "error"
    assert captured["handle"]._error == "ValueError"


async def test_trace_task_measures_duration_ms() -> None:
    """Duration is measured in ms and non-negative."""
    from backend.services.observability.task_tracer import trace_task

    trace_obj = MagicMock()
    langfuse = _make_langfuse(trace_obj)
    collector = _make_collector()

    async with trace_task(
        "x", langfuse=langfuse, collector=collector
    ) as handle:
        time.sleep(0.01)

    assert handle._duration_ms >= 0


async def test_trace_task_finalize_swallows_langfuse_errors() -> None:
    """trace.update raising must not propagate out of the context manager."""
    from backend.services.observability.task_tracer import trace_task

    trace_obj = MagicMock()
    trace_obj.update = MagicMock(side_effect=RuntimeError("langfuse down"))
    langfuse = _make_langfuse(trace_obj)
    collector = _make_collector()

    # Must exit cleanly
    async with trace_task(
        "x", langfuse=langfuse, collector=collector
    ) as handle:
        handle.add_metadata(foo="bar")


async def test_trace_task_add_metadata_merges_into_final_update() -> None:
    """add_metadata values appear in the trace.update call on exit."""
    from backend.services.observability.task_tracer import trace_task

    trace_obj = MagicMock()
    langfuse = _make_langfuse(trace_obj)
    collector = _make_collector()

    async with trace_task(
        "x", langfuse=langfuse, collector=collector
    ) as handle:
        handle.add_metadata(articles=10)

    trace_obj.update.assert_called_once()
    metadata = trace_obj.update.call_args.kwargs["metadata"]
    assert metadata["articles"] == 10
    assert metadata["task"] == "x"
    assert metadata["status"] == "completed"
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/unit/services/test_task_tracer.py -q --tb=short
```

Expected: `ModuleNotFoundError: backend.services.observability.task_tracer`.

- [ ] **Step 3: Create `backend/services/observability/__init__.py`**

```python
"""Service-level observability helpers (non-agent task tracing)."""
```

- [ ] **Step 4: Create `backend/services/observability/task_tracer.py`**

```python
"""Task-level tracing helper for non-agent Celery code paths.

Wraps Langfuse trace creation + ObservabilityCollector recording so
nightly jobs (sentiment scoring, Prophet training, news ingestion,
convergence, backtest) get the same visibility agents get today.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from backend.observability.collector import ObservabilityCollector
from backend.observability.langfuse import LangfuseService

logger = logging.getLogger(__name__)


class TaskTraceHandle:
    """Handle yielded by :func:`trace_task` — exposes metadata and LLM recording."""

    def __init__(
        self,
        *,
        name: str,
        trace_id: uuid.UUID,
        trace: Any | None,
        langfuse: LangfuseService,
        collector: ObservabilityCollector,
    ) -> None:
        self.name = name
        self.trace_id = trace_id
        self._trace = trace
        self._langfuse = langfuse
        self._collector = collector
        self._metadata: dict[str, Any] = {}
        self._status: str = "completed"
        self._error: str | None = None
        self._duration_ms: int = 0

    def add_metadata(self, **kwargs: Any) -> None:
        """Attach metadata to the trace (flushed on exit)."""
        self._metadata.update(kwargs)

    async def record_llm(
        self,
        *,
        model: str,
        provider: str,
        tier: str,
        latency_ms: int,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float | None = None,
    ) -> None:
        """Record an LLM call made inside this task.

        Delegates to :meth:`ObservabilityCollector.record_request` with the
        current trace id so the DB row joins cleanly to agent observability.
        """
        await self._collector.record_request(
            model=model,
            provider=provider,
            tier=tier,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            status="completed",
            langfuse_trace_id=self.trace_id,
        )

    async def _finalize(self) -> None:
        """End the trace with final metadata (fire-and-forget)."""
        if self._trace is None:
            return
        try:
            self._trace.update(
                metadata={
                    "task": self.name,
                    "status": self._status,
                    "error": self._error,
                    "duration_ms": self._duration_ms,
                    **self._metadata,
                }
            )
        except Exception:
            logger.warning(
                "trace_task finalize failed for %s", self.name, exc_info=True
            )


@asynccontextmanager
async def trace_task(
    name: str,
    *,
    langfuse: LangfuseService,
    collector: ObservabilityCollector,
    metadata: dict[str, Any] | None = None,
) -> AsyncIterator[TaskTraceHandle]:
    """Trace a non-agent task block in Langfuse + the DB collector.

    Usage::

        async with trace_task(
            "nightly_sentiment_scoring",
            langfuse=langfuse_service,
            collector=observability_collector,
            metadata={"ticker_count": 500},
        ) as handle:
            await do_work()
            handle.add_metadata(articles_scored=1234)

    On exit, the trace is ended; on exception, status is set to "error"
    and the exception re-raises.

    Args:
        name: Human-readable task name (e.g. "nightly_sentiment_scoring").
        langfuse: The app-level LangfuseService (no-op safe when disabled).
        collector: The app-level ObservabilityCollector.
        metadata: Optional initial metadata dict.

    Yields:
        TaskTraceHandle — call add_metadata / record_llm inside the block.
    """
    trace_id = uuid.uuid4()
    trace = langfuse.create_trace(
        trace_id=trace_id,
        session_id=trace_id,
        user_id=trace_id,
        metadata={"task": name, **(metadata or {})},
    )
    handle = TaskTraceHandle(
        name=name,
        trace_id=trace_id,
        trace=trace,
        langfuse=langfuse,
        collector=collector,
    )
    started_at = time.perf_counter()
    try:
        yield handle
    except Exception as exc:
        handle._status = "error"
        handle._error = type(exc).__name__
        logger.warning(
            "trace_task %s failed: %s", name, type(exc).__name__
        )
        raise
    finally:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        handle._duration_ms = duration_ms
        await handle._finalize()
```

- [ ] **Step 5: Run tracer tests**

```bash
uv run pytest tests/unit/services/test_task_tracer.py -q --tb=short
```

Expected: all 7 tests pass.

- [ ] **Step 6: Lint**

```bash
uv run ruff check --fix backend/services/observability/ tests/unit/services/test_task_tracer.py && uv run ruff format backend/services/observability/ tests/unit/services/test_task_tracer.py
```

- [ ] **Step 7: Commit**

```bash
git add backend/services/observability/__init__.py backend/services/observability/task_tracer.py tests/unit/services/test_task_tracer.py
git commit -m "feat(observability): add trace_task helper for non-agent tasks (Spec A §A4)"
```

---

## Task 7: Final Verification — Lint + Full Test Run

**Files:** (none modified — verification only)

- [ ] **Step 1: Run ruff over the full backend + tests tree**

```bash
uv run ruff check backend/ tests/ scripts/
```

Expected: zero errors. If anything flags, fix it and re-run before proceeding.

- [ ] **Step 2: Run ruff format in check mode**

```bash
uv run ruff format --check backend/ tests/ scripts/
```

Expected: zero diffs.

- [ ] **Step 3: Run the full unit test suite**

```bash
uv run pytest tests/unit/ -q --tb=short
```

Expected: all tests pass including the 9 new ticker_state tests, 6 new decorator tests, 7 new tracer tests, and every pre-existing unit test.

- [ ] **Step 4: Run the API test suite (real Postgres via testcontainers)**

```bash
uv run pytest tests/api/test_ingestion_health_state.py -q --tb=short
```

Expected: 3 passed (table exists, expected columns, cascade delete works).

- [ ] **Step 5: Confirm Alembic head is the new revision**

```bash
uv run alembic current
```

Expected: `e1f2a3b4c5d6 (head)`.

- [ ] **Step 6: Confirm no uncommitted changes**

```bash
git status
```

Expected: clean working tree, 6 commits ahead of `develop`.

---

## Task 7: Test guardrails + real-DB error redaction audit (review-required)

**Files:**
- Modify: `tests/unit/conftest.py`
- Create: `tests/api/test_tracked_task_error_redaction.py`

- [ ] **Step 1: Extend the xdist guardrail to `db_session`**

Append to `tests/unit/conftest.py` alongside the existing `client` /
`authenticated_client` guards:

```python
@pytest.fixture
def db_session():
    """Guardrail — DB-hitting db_session is banned under tests/unit/.

    tests/unit/ runs with pytest-xdist -n auto. Multiple workers share
    one Postgres instance; per-test TRUNCATE teardown races with sibling
    workers still running tests. Tests that need a real DB belong in
    tests/api/ (sequential).
    """
    pytest.fail(
        "The `db_session` fixture hits the real database and races with "
        "sibling xdist workers under tests/unit/. Move this test to "
        "tests/api/ where tests run sequentially."
    )
```

- [ ] **Step 2: Create `tests/api/test_tracked_task_error_redaction.py`**

This is the real teeth behind Hard Rule #10: assert the persisted
`pipeline_runs.error_summary` row never contains raw exception text.

```python
"""Spec A — @tracked_task must never persist str(exception) (Hard Rule #10)."""

import uuid

import pytest
from sqlalchemy import select

from backend.models.pipeline import PipelineRun
from backend.tasks import pipeline as pipeline_mod


@pytest.mark.asyncio
async def test_tracked_task_error_summary_does_not_leak_exception_string(db_session) -> None:
    @pipeline_mod.tracked_task("redaction_audit")
    async def inner(*, run_id: uuid.UUID) -> None:
        raise RuntimeError("db password hunter2 leaked")

    with pytest.raises(RuntimeError):
        await inner()

    # The decorator opens its own session, so query the real table.
    row = (
        await db_session.execute(
            select(PipelineRun)
            .where(PipelineRun.pipeline_name == "redaction_audit")
            .order_by(PipelineRun.started_at.desc())
            .limit(1)
        )
    ).scalar_one()
    assert row.status == "failed"
    joined = str(row.error_summary or {})
    assert "hunter2" not in joined
    assert "db password" not in joined
    assert "RuntimeError" not in joined or "see logs" in joined
```

- [ ] **Step 3: Run + commit**

```bash
uv run pytest tests/api/test_tracked_task_error_redaction.py -q
git add tests/unit/conftest.py tests/api/test_tracked_task_error_redaction.py
git commit -m "test(a): db_session guardrail + real-DB error redaction audit (Spec A)"
```

---

## Completion Checklist

- [ ] Migration 025 applied locally (head = `e1f2a3b4c5d6`)
- [ ] `TickerIngestionState` model registered in `backend/models/__init__.py`
- [ ] `StalenessSLAs` constants pinned in `backend/config.py`
- [ ] `backend/services/ticker_state.py` service with `mark_stage_updated`, `get_ticker_readiness`, `get_universe_health`
- [ ] `@tracked_task` decorator appended to `backend/tasks/pipeline.py` with no call-site adoption
- [ ] `backend/services/observability/task_tracer.py` + `TaskTraceHandle`
- [ ] All new tests green; zero pre-existing regressions
- [ ] Ruff clean across backend/ tests/ scripts/
- [ ] 6 commits, each referencing the Spec A section number
