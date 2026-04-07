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
