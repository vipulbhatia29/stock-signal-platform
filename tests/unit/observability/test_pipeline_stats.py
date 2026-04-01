"""Tests for pipeline run and watermark query service."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from backend.observability.metrics.pipeline_stats import (
    ET,
    NIGHTLY_HOUR,
    NIGHTLY_MINUTE,
    get_failed_tickers,
    get_latest_run,
    get_next_run_time,
    get_run_history,
    get_watermarks,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ET_TZ = ZoneInfo("America/New_York")


def _make_run(
    *,
    status: str = "completed",
    tickers_total: int = 50,
    tickers_succeeded: int = 48,
    tickers_failed: int = 2,
    duration_minutes: int = 5,
    error_summary: dict | None = None,
) -> MagicMock:
    """Build a mock PipelineRun object."""
    run = MagicMock()
    run.id = uuid.uuid4()
    run.pipeline_name = "nightly_ingest"
    run.status = status
    now = datetime.now(tz=ET_TZ)
    run.started_at = now - timedelta(minutes=duration_minutes)
    run.completed_at = now
    run.tickers_total = tickers_total
    run.tickers_succeeded = tickers_succeeded
    run.tickers_failed = tickers_failed
    run.trigger = "scheduled"
    run.retry_count = 0
    run.error_summary = error_summary
    return run


def _make_watermark(
    *,
    pipeline_name: str = "nightly_ingest",
    days_ago: int = 0,
    status: str = "ok",
) -> MagicMock:
    """Build a mock PipelineWatermark object."""
    wm = MagicMock()
    wm.pipeline_name = pipeline_name
    wm.last_completed_date = date.today() - timedelta(days=days_ago)
    wm.last_completed_at = datetime.now(tz=ET_TZ) - timedelta(days=days_ago)
    wm.status = status
    return wm


def _mock_session_returning(
    scalars: list | None = None,
    scalar_one: object | None = None,
) -> AsyncMock:
    """Create an AsyncSession mock that returns the given results."""
    session = AsyncMock()
    result_mock = MagicMock()

    if scalar_one is not None:
        result_mock.scalar_one_or_none.return_value = scalar_one
    else:
        result_mock.scalar_one_or_none.return_value = None

    if scalars is not None:
        result_mock.scalars.return_value.all.return_value = scalars
    else:
        result_mock.scalars.return_value.all.return_value = []

    session.execute.return_value = result_mock
    return session


# ---------------------------------------------------------------------------
# get_latest_run
# ---------------------------------------------------------------------------


class TestGetLatestRun:
    """Tests for get_latest_run."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_runs(self) -> None:
        """Returns None when database has no pipeline runs."""
        db = _mock_session_returning(scalar_one=None)
        result = await get_latest_run(db)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_dict_when_run_exists(self) -> None:
        """Returns a dict with expected keys for an existing run."""
        run = _make_run()
        db = _mock_session_returning(scalar_one=run)
        result = await get_latest_run(db)

        assert result is not None
        assert result["id"] == str(run.id)
        assert result["status"] == "completed"
        assert result["tickers_total"] == 50
        assert result["tickers_succeeded"] == 48
        assert result["tickers_failed"] == 2
        assert result["total_duration_seconds"] is not None
        assert result["total_duration_seconds"] > 0
        assert result["trigger"] == "scheduled"

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(self) -> None:
        """Returns None when database query raises."""
        db = AsyncMock()
        db.execute.side_effect = RuntimeError("connection lost")
        result = await get_latest_run(db)
        assert result is None


# ---------------------------------------------------------------------------
# get_watermarks
# ---------------------------------------------------------------------------


class TestGetWatermarks:
    """Tests for get_watermarks."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_watermarks(self) -> None:
        """Returns empty list when no watermarks exist."""
        db = _mock_session_returning(scalars=[])
        result = await get_watermarks(db)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_populated_list(self) -> None:
        """Returns watermarks with gap detection fields."""
        wm = _make_watermark(days_ago=0)
        db = _mock_session_returning(scalars=[wm])
        result = await get_watermarks(db)

        assert len(result) == 1
        assert result[0]["pipeline_name"] == "nightly_ingest"
        assert result[0]["status"] == "ok"
        assert result[0]["days_since_last"] == 0
        assert result[0]["has_gap"] is False

    @pytest.mark.asyncio
    async def test_detects_gap(self) -> None:
        """Flags has_gap=True when last_completed_date is >1 day ago."""
        wm = _make_watermark(days_ago=3)
        db = _mock_session_returning(scalars=[wm])
        result = await get_watermarks(db)

        assert result[0]["days_since_last"] == 3
        assert result[0]["has_gap"] is True

    @pytest.mark.asyncio
    async def test_returns_empty_on_db_error(self) -> None:
        """Returns empty list when database query raises."""
        db = AsyncMock()
        db.execute.side_effect = RuntimeError("connection lost")
        result = await get_watermarks(db)
        assert result == []


# ---------------------------------------------------------------------------
# get_next_run_time
# ---------------------------------------------------------------------------


class TestGetNextRunTime:
    """Tests for get_next_run_time."""

    def test_returns_iso_string(self) -> None:
        """Returns a valid ISO format datetime string."""
        result = get_next_run_time()
        # Should parse without error
        parsed = datetime.fromisoformat(result)
        assert parsed.hour == NIGHTLY_HOUR
        assert parsed.minute == NIGHTLY_MINUTE

    def test_next_run_is_future(self) -> None:
        """Next run time is always in the future or within today."""
        result = get_next_run_time()
        parsed = datetime.fromisoformat(result)
        now = datetime.now(tz=ET)
        # The result should be >= now (or very close, within a second)
        assert parsed >= now - timedelta(seconds=2)


# ---------------------------------------------------------------------------
# get_run_history
# ---------------------------------------------------------------------------


class TestGetRunHistory:
    """Tests for get_run_history."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_history(self) -> None:
        """Returns empty list when no runs in time window."""
        db = _mock_session_returning(scalars=[])
        result = await get_run_history(db, days=7)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_list_of_run_dicts(self) -> None:
        """Returns run dicts with expected fields."""
        run = _make_run()
        db = _mock_session_returning(scalars=[run])
        result = await get_run_history(db, days=7)

        assert len(result) == 1
        assert result[0]["id"] == str(run.id)
        assert result[0]["status"] == "completed"
        assert result[0]["total_duration_seconds"] is not None

    @pytest.mark.asyncio
    async def test_returns_empty_on_db_error(self) -> None:
        """Returns empty list when database query raises."""
        db = AsyncMock()
        db.execute.side_effect = RuntimeError("connection lost")
        result = await get_run_history(db)
        assert result == []


# ---------------------------------------------------------------------------
# get_failed_tickers
# ---------------------------------------------------------------------------


class TestGetFailedTickers:
    """Tests for get_failed_tickers."""

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        """Returns None when run_id does not exist."""
        db = _mock_session_returning(scalar_one=None)
        result = await get_failed_tickers(db, str(uuid.uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_error_details(self) -> None:
        """Returns error summary for a failed run."""
        errors = {"AAPL": "timeout", "TSLA": "rate_limited"}
        run = _make_run(status="failed", error_summary=errors)
        db = _mock_session_returning(scalar_one=run)
        result = await get_failed_tickers(db, str(run.id))

        assert result is not None
        assert result["status"] == "failed"
        assert result["error_summary"] == errors
        assert result["tickers_failed"] == 2

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(self) -> None:
        """Returns None when database query raises."""
        db = AsyncMock()
        db.execute.side_effect = RuntimeError("connection lost")
        result = await get_failed_tickers(db, str(uuid.uuid4()))
        assert result is None
