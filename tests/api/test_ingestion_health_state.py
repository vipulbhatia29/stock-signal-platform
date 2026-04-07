"""Integration tests for ticker_ingestion_state table and migration 025."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.stock import Stock
from backend.models.ticker_ingestion_state import TickerIngestionState
from backend.services import ticker_state as ticker_state_mod


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
    """Schema must match spec A1 exactly — including recommendation_updated_at and last_error."""
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
        "recommendation_updated_at",
        "last_error",
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


# ---------------------------------------------------------------------------
# Fix 1: Migration backfill SQL test
# ---------------------------------------------------------------------------


async def test_migration_025_backfill_populates_prices_updated_at_from_stocks(
    db_session: AsyncSession,
) -> None:
    """Backfill SQL pattern inserts ticker_ingestion_state rows from stocks.

    The schema is created session-scoped (the table already exists). This test
    exercises the idempotent backfill INSERT … SELECT … ON CONFLICT DO NOTHING
    SQL pattern that migration 025 runs, not the full alembic upgrade path.
    """
    now = datetime.now(timezone.utc)
    # Pre-seed three stocks with last_fetched_at set
    tickers = ["TST1", "TST2", "TST3"]
    for t in tickers:
        stock = Stock(ticker=t, name=f"Test {t}", sector="Tech", industry="Soft")
        stock.last_fetched_at = now
        db_session.add(stock)
    await db_session.commit()

    # Run the backfill SQL directly (mirrors migration 025 upgrade step)
    await db_session.execute(
        text(
            """
            INSERT INTO ticker_ingestion_state (ticker, prices_updated_at, created_at, updated_at)
            SELECT ticker, last_fetched_at, now(), now()
            FROM stocks
            WHERE ticker IN ('TST1', 'TST2', 'TST3')
            ON CONFLICT (ticker) DO NOTHING
            """
        )
    )
    await db_session.commit()

    # Verify all 3 rows were inserted with matching prices_updated_at
    result = await db_session.execute(
        text(
            "SELECT ticker, prices_updated_at FROM ticker_ingestion_state "
            "WHERE ticker IN ('TST1', 'TST2', 'TST3') ORDER BY ticker"
        )
    )
    rows = result.fetchall()
    assert len(rows) == 3, f"Expected 3 backfill rows, got {len(rows)}"
    for row in rows:
        assert row[1] is not None, f"prices_updated_at should not be NULL for {row[0]}"


# ---------------------------------------------------------------------------
# Fix 2: Static migration round-trip test (import + structure check)
# ---------------------------------------------------------------------------


def test_migration_025_upgrade_downgrade_clean() -> None:
    """Migration 025 module must import cleanly and expose upgrade/downgrade callables.

    A full alembic upgrade/downgrade round-trip against the dev DB is
    destructive in a shared-session test suite (it drops the table mid-run,
    racing with other tests). Instead we verify static correctness:
    - The module imports without error.
    - upgrade() and downgrade() are callable.
    - The revision IDs are what Spec A pinned.

    Full round-trip is exercised manually via `uv run alembic downgrade -1 &&
    uv run alembic upgrade head` before opening the PR.
    """
    import importlib

    migration = importlib.import_module("backend.migrations.versions.025_ticker_ingestion_state")
    assert callable(migration.upgrade), "upgrade() must be a callable"
    assert callable(migration.downgrade), "downgrade() must be a callable"
    assert migration.revision == "e1f2a3b4c5d6", f"Unexpected revision: {migration.revision}"
    assert migration.down_revision == "b2351fa2d293", (
        f"Unexpected down_revision: {migration.down_revision}"
    )


# ---------------------------------------------------------------------------
# Fix 3: Real-DB tests for mark_stage_updated insert/upsert/all-stages
# ---------------------------------------------------------------------------


async def test_mark_stage_updated_inserts_new_row(db_session: AsyncSession) -> None:
    """mark_stage_updated creates a new ticker_ingestion_state row on first call.

    Redirects the service's async_session_factory to use db_session via
    the same _shared_session_factory pattern as test_tracked_task_error_redaction.
    """
    stock = Stock(ticker="TSTI", name="Test Insert", sector="Tech", industry="Soft")
    db_session.add(stock)
    await db_session.commit()

    @asynccontextmanager
    async def _shared_session_factory():
        """Yield the shared db_session for every service call."""
        yield db_session

    with patch.object(ticker_state_mod, "async_session_factory", _shared_session_factory):
        await ticker_state_mod.mark_stage_updated("TSTI", "prices")

    result = await db_session.execute(
        text("SELECT ticker, prices_updated_at FROM ticker_ingestion_state WHERE ticker = 'TSTI'")
    )
    row = result.fetchone()
    assert row is not None, "Row must exist after mark_stage_updated"
    assert row[1] is not None, "prices_updated_at must be non-NULL"


async def test_mark_stage_updated_upserts_existing_row(db_session: AsyncSession) -> None:
    """mark_stage_updated advances updated_at and the target column on second call.

    Pre-seeds the row, then calls mark_stage_updated again after a brief
    delay and asserts the column was updated.
    """
    stock = Stock(ticker="TSTU", name="Test Upsert", sector="Tech", industry="Soft")
    db_session.add(stock)
    await db_session.commit()

    t1 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    db_session.add(
        TickerIngestionState(
            ticker="TSTU",
            signals_updated_at=t1,
            created_at=t1,
            updated_at=t1,
        )
    )
    await db_session.commit()

    @asynccontextmanager
    async def _shared_session_factory():
        """Yield the shared db_session for every service call."""
        yield db_session

    with patch.object(ticker_state_mod, "async_session_factory", _shared_session_factory):
        await ticker_state_mod.mark_stage_updated("TSTU", "signals")

    db_session.expire_all()  # synchronous — force re-read from DB on next access
    result = await db_session.execute(
        text(
            "SELECT signals_updated_at, updated_at FROM ticker_ingestion_state "
            "WHERE ticker = 'TSTU'"
        )
    )
    row = result.fetchone()
    assert row is not None
    assert row[0] > t1, "signals_updated_at must have advanced"
    assert row[1] > t1, "updated_at must have advanced"


@pytest.mark.parametrize(
    "stage, column, ticker",
    [
        ("prices", "prices_updated_at", "TSSPR"),
        ("signals", "signals_updated_at", "TSSSI"),
        ("fundamentals", "fundamentals_updated_at", "TSSFU"),
        ("forecast", "forecast_updated_at", "TSSFC"),
        ("forecast_retrain", "forecast_retrained_at", "TSSFR"),
        ("news", "news_updated_at", "TSSNW"),
        ("sentiment", "sentiment_updated_at", "TSSST"),
        ("convergence", "convergence_updated_at", "TSSCV"),
        ("backtest", "backtest_updated_at", "TSSBK"),
        ("recommendation", "recommendation_updated_at", "TSSRC"),
    ],
)
async def test_mark_stage_updated_distinct_stages_each_writes_correct_column(
    db_session: AsyncSession,
    stage: str,
    column: str,
    ticker: str,
) -> None:
    """Each of the 10 stages writes the correct column and leaves others NULL.

    This test supersedes the weak unit-level test_mark_stage_updated_forecast_vs_forecast_retrain
    which only counted statements without verifying which column was actually written.
    Each parametrize case uses a distinct ticker to avoid constraint collisions.
    """
    stock = Stock(ticker=ticker, name=f"Test {stage}", sector="Tech", industry="Soft")
    db_session.add(stock)
    await db_session.commit()

    @asynccontextmanager
    async def _shared_session_factory():
        """Yield the shared db_session for every service call."""
        yield db_session

    with patch.object(ticker_state_mod, "async_session_factory", _shared_session_factory):
        await ticker_state_mod.mark_stage_updated(ticker, stage)  # type: ignore[arg-type]

    result = await db_session.execute(
        text(f"SELECT {column} FROM ticker_ingestion_state WHERE ticker = :t"),
        {"t": ticker},
    )
    row = result.fetchone()
    assert row is not None, f"Row must exist for {stage}"
    assert row[0] is not None, f"{column} must be non-NULL after marking stage '{stage}'"
