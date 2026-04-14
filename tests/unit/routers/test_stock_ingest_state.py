"""Unit tests for GET /stocks/{ticker}/ingest-state (Spec G.1)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from backend.models.user import User, UserRole
from backend.routers.stocks.data import get_ingest_state


@pytest.fixture
def user() -> User:
    """Provide a test user."""
    return User(
        id=uuid.uuid4(),
        email="test@test.com",
        hashed_password="hashed",
        role=UserRole.USER,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_row(fresh_stages: set[str] | None = None) -> MagicMock:
    """Build a mock TickerIngestionState with specified fresh stages."""
    now = datetime.now(timezone.utc)
    stale = now - timedelta(hours=100)
    all_stages = {
        "prices_updated_at",
        "signals_updated_at",
        "fundamentals_updated_at",
        "forecast_updated_at",
        "news_updated_at",
        "sentiment_updated_at",
        "convergence_updated_at",
    }
    fresh = fresh_stages or set()
    row = MagicMock()
    for col in all_stages:
        if col in fresh:
            setattr(row, col, now)
        else:
            setattr(row, col, stale)
    row.ticker = "AAPL"
    return row


class TestGetIngestState:
    """Tests for the ingest-state endpoint."""

    @pytest.mark.asyncio
    async def test_returns_all_7_stages_when_fresh(self, user: User) -> None:
        """Returns ready + 100% when all stages are fresh."""
        row = _make_row(
            {
                "prices_updated_at",
                "signals_updated_at",
                "fundamentals_updated_at",
                "forecast_updated_at",
                "news_updated_at",
                "sentiment_updated_at",
                "convergence_updated_at",
            }
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = row
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_ingest_state(ticker="AAPL", db=mock_db, current_user=user)

        assert result.ticker == "AAPL"
        assert result.overall_status == "ready"
        assert result.completion_pct == 100
        assert result.stages.prices.status.value == "fresh"

    @pytest.mark.asyncio
    async def test_returns_ingesting_when_missing_stages(self, user: User) -> None:
        """Returns ingesting when some stages have very old data."""
        row = _make_row({"prices_updated_at", "signals_updated_at"})
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = row
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_ingest_state(ticker="AAPL", db=mock_db, current_user=user)

        assert result.overall_status in ("ingesting", "stale")
        assert result.completion_pct < 100

    @pytest.mark.asyncio
    async def test_returns_404_for_unknown_ticker(self, user: User) -> None:
        """Returns 404 when ticker has no ingestion state row."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await get_ingest_state(ticker="NOPE", db=mock_db, current_user=user)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_updated_at_returns_missing_status(self, user: User) -> None:
        """Stages with None updated_at get status 'missing'."""
        row = MagicMock()
        for col in [
            "prices_updated_at",
            "signals_updated_at",
            "fundamentals_updated_at",
            "forecast_updated_at",
            "news_updated_at",
            "sentiment_updated_at",
            "convergence_updated_at",
        ]:
            setattr(row, col, None)
        row.ticker = "NEW"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = row
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_ingest_state(ticker="NEW", db=mock_db, current_user=user)

        assert result.overall_status == "ingesting"
        assert result.completion_pct == 0
        assert result.stages.prices.status.value == "missing"
