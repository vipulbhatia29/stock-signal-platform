"""Unit tests for pipeline infrastructure — PipelineRunner, gap detection, retry."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.pipeline import PipelineRun, PipelineWatermark
from backend.tasks.pipeline import (
    PipelineRunner,
    detect_gap,
    with_retry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session_factory():
    """Create a mock async session context manager."""
    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm, mock_session


def _make_run(
    run_id: uuid.UUID | None = None,
    status: str = "running",
    tickers_total: int = 10,
    tickers_succeeded: int = 0,
    tickers_failed: int = 0,
    error_summary: dict | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    pipeline_name: str = "price_refresh",
) -> PipelineRun:
    """Create a PipelineRun instance for testing."""
    return PipelineRun(
        id=run_id or uuid.uuid4(),
        pipeline_name=pipeline_name,
        started_at=started_at or datetime.now(timezone.utc),
        completed_at=completed_at,
        status=status,
        tickers_total=tickers_total,
        tickers_succeeded=tickers_succeeded,
        tickers_failed=tickers_failed,
        error_summary=error_summary,
        trigger="scheduled",
    )


# ---------------------------------------------------------------------------
# PipelineRunner.start_run
# ---------------------------------------------------------------------------


class TestPipelineRunnerStartRun:
    """Tests for PipelineRunner.start_run."""

    @pytest.mark.asyncio
    @patch("backend.tasks.pipeline.async_session_factory")
    async def test_start_run_creates_row(self, mock_factory: MagicMock) -> None:
        """start_run should create a PipelineRun row and return its UUID."""
        mock_cm, mock_session = _mock_session_factory()
        mock_factory.return_value = mock_cm

        runner = PipelineRunner()
        run_id = await runner.start_run("price_refresh", "scheduled", 50)

        assert isinstance(run_id, uuid.UUID)
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

        added_run = mock_session.add.call_args[0][0]
        assert added_run.pipeline_name == "price_refresh"
        assert added_run.tickers_total == 50
        assert added_run.status == "running"


# ---------------------------------------------------------------------------
# PipelineRunner.record_ticker_success / failure
# ---------------------------------------------------------------------------


class TestPipelineRunnerRecordTicker:
    """Tests for record_ticker_success and record_ticker_failure."""

    @pytest.mark.asyncio
    @patch("backend.tasks.pipeline.async_session_factory")
    async def test_record_success_increments(self, mock_factory: MagicMock) -> None:
        """record_ticker_success should increment tickers_succeeded."""
        mock_cm, mock_session = _mock_session_factory()
        mock_factory.return_value = mock_cm

        run = _make_run(tickers_succeeded=5)
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = run
        mock_session.execute.return_value = mock_result

        runner = PipelineRunner()
        await runner.record_ticker_success(run.id, "AAPL")

        assert run.tickers_succeeded == 6
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.tasks.pipeline.async_session_factory")
    async def test_record_failure_increments_and_logs_error(self, mock_factory: MagicMock) -> None:
        """record_ticker_failure should increment tickers_failed and add to error_summary."""
        mock_cm, mock_session = _mock_session_factory()
        mock_factory.return_value = mock_cm

        run = _make_run(tickers_failed=1, error_summary={"GME": "timeout"})
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = run
        mock_session.execute.return_value = mock_result

        runner = PipelineRunner()
        await runner.record_ticker_failure(run.id, "TSLA", "rate_limit")

        assert run.tickers_failed == 2
        assert run.error_summary["TSLA"] == "rate_limit"
        assert run.error_summary["GME"] == "timeout"

    @pytest.mark.asyncio
    @patch("backend.tasks.pipeline.async_session_factory")
    async def test_record_failure_initializes_error_summary(self, mock_factory: MagicMock) -> None:
        """record_ticker_failure should initialize error_summary if None."""
        mock_cm, mock_session = _mock_session_factory()
        mock_factory.return_value = mock_cm

        run = _make_run(error_summary=None)
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = run
        mock_session.execute.return_value = mock_result

        runner = PipelineRunner()
        await runner.record_ticker_failure(run.id, "AAPL", "404")

        assert run.error_summary == {"AAPL": "404"}


# ---------------------------------------------------------------------------
# PipelineRunner.complete_run
# ---------------------------------------------------------------------------


class TestPipelineRunnerCompleteRun:
    """Tests for PipelineRunner.complete_run."""

    @pytest.mark.asyncio
    @patch("backend.tasks.pipeline.async_session_factory")
    async def test_all_success(self, mock_factory: MagicMock) -> None:
        """complete_run with 0 failures should set status to 'success'."""
        mock_cm, mock_session = _mock_session_factory()
        mock_factory.return_value = mock_cm

        run = _make_run(tickers_total=10, tickers_succeeded=10, tickers_failed=0)
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = run
        mock_session.execute.return_value = mock_result

        runner = PipelineRunner()
        status = await runner.complete_run(run.id)

        assert status == "success"
        assert run.completed_at is not None

    @pytest.mark.asyncio
    @patch("backend.tasks.pipeline.async_session_factory")
    async def test_partial_success(self, mock_factory: MagicMock) -> None:
        """complete_run with some failures should set status to 'partial'."""
        mock_cm, mock_session = _mock_session_factory()
        mock_factory.return_value = mock_cm

        run = _make_run(tickers_total=10, tickers_succeeded=7, tickers_failed=3)
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = run
        mock_session.execute.return_value = mock_result

        runner = PipelineRunner()
        status = await runner.complete_run(run.id)

        assert status == "partial"

    @pytest.mark.asyncio
    @patch("backend.tasks.pipeline.async_session_factory")
    async def test_all_failed(self, mock_factory: MagicMock) -> None:
        """complete_run with 0 successes should set status to 'failed'."""
        mock_cm, mock_session = _mock_session_factory()
        mock_factory.return_value = mock_cm

        run = _make_run(tickers_total=10, tickers_succeeded=0, tickers_failed=10)
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = run
        mock_session.execute.return_value = mock_result

        runner = PipelineRunner()
        status = await runner.complete_run(run.id)

        assert status == "failed"


# ---------------------------------------------------------------------------
# PipelineRunner.update_watermark
# ---------------------------------------------------------------------------


class TestPipelineRunnerWatermark:
    """Tests for PipelineRunner.update_watermark."""

    @pytest.mark.asyncio
    @patch("backend.tasks.pipeline.async_session_factory")
    async def test_creates_watermark_if_none(self, mock_factory: MagicMock) -> None:
        """update_watermark should create a new watermark if none exists."""
        mock_cm, mock_session = _mock_session_factory()
        mock_factory.return_value = mock_cm

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        runner = PipelineRunner()
        await runner.update_watermark("price_refresh", date(2026, 3, 21))

        mock_session.add.assert_called_once()
        added = mock_session.add.call_args[0][0]
        assert added.pipeline_name == "price_refresh"
        assert added.last_completed_date == date(2026, 3, 21)
        assert added.status == "ok"

    @pytest.mark.asyncio
    @patch("backend.tasks.pipeline.async_session_factory")
    async def test_updates_existing_watermark(self, mock_factory: MagicMock) -> None:
        """update_watermark should update an existing watermark."""
        mock_cm, mock_session = _mock_session_factory()
        mock_factory.return_value = mock_cm

        existing = PipelineWatermark(
            pipeline_name="price_refresh",
            last_completed_date=date(2026, 3, 20),
            last_completed_at=datetime.now(timezone.utc),
            status="backfilling",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_session.execute.return_value = mock_result

        runner = PipelineRunner()
        await runner.update_watermark("price_refresh", date(2026, 3, 21))

        assert existing.last_completed_date == date(2026, 3, 21)
        assert existing.status == "ok"


# ---------------------------------------------------------------------------
# PipelineRunner.detect_stale_runs
# ---------------------------------------------------------------------------


class TestPipelineRunnerStaleRuns:
    """Tests for PipelineRunner.detect_stale_runs."""

    @pytest.mark.asyncio
    @patch("backend.tasks.pipeline.async_session_factory")
    async def test_detects_stale_run(self, mock_factory: MagicMock) -> None:
        """detect_stale_runs should find runs stuck running for > 1 hour."""
        mock_cm, mock_session = _mock_session_factory()
        mock_factory.return_value = mock_cm

        stale_run = _make_run(
            started_at=datetime.now(timezone.utc) - timedelta(hours=2),
            status="running",
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [stale_run]
        mock_session.execute.return_value = mock_result

        runner = PipelineRunner()
        stale_ids = await runner.detect_stale_runs()

        assert len(stale_ids) == 1
        assert stale_run.status == "failed"
        assert stale_run.completed_at is not None
        assert stale_run.error_summary["_stale"] == "Run exceeded 1-hour threshold"

    @pytest.mark.asyncio
    @patch("backend.tasks.pipeline.async_session_factory")
    async def test_no_stale_runs(self, mock_factory: MagicMock) -> None:
        """detect_stale_runs should return empty list when no stale runs exist."""
        mock_cm, mock_session = _mock_session_factory()
        mock_factory.return_value = mock_cm

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        runner = PipelineRunner()
        stale_ids = await runner.detect_stale_runs()

        assert stale_ids == []


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------


class TestDetectGap:
    """Tests for detect_gap function."""

    @pytest.mark.asyncio
    @patch("backend.tasks.pipeline.async_session_factory")
    async def test_gap_detected_3_days(self, mock_factory: MagicMock) -> None:
        """detect_gap should return 3 missing business days."""
        mock_cm, mock_session = _mock_session_factory()
        mock_factory.return_value = mock_cm

        # Watermark was last completed on a Monday, today is Friday (4 bdays gap)
        # Use a fixed date that's a Monday
        last_date = date(2026, 3, 16)  # Monday
        watermark = PipelineWatermark(
            pipeline_name="price_refresh",
            last_completed_date=last_date,
            last_completed_at=datetime.now(timezone.utc),
            status="ok",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = watermark
        mock_session.execute.return_value = mock_result

        fake_now = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)  # Friday
        with patch("backend.tasks.pipeline.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            missing = await detect_gap("price_refresh")

        # Should have Tue, Wed, Thu = 3 business days
        assert len(missing) == 3
        assert missing[0] == date(2026, 3, 17)  # Tuesday
        assert missing[-1] == date(2026, 3, 19)  # Thursday

    @pytest.mark.asyncio
    @patch("backend.tasks.pipeline.async_session_factory")
    async def test_no_gap_when_current(self, mock_factory: MagicMock) -> None:
        """detect_gap should return empty list when watermark is current."""
        mock_cm, mock_session = _mock_session_factory()
        mock_factory.return_value = mock_cm

        today = date(2026, 3, 20)
        yesterday = today - timedelta(days=1)
        watermark = PipelineWatermark(
            pipeline_name="price_refresh",
            last_completed_date=yesterday,
            last_completed_at=datetime.now(timezone.utc),
            status="ok",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = watermark
        mock_session.execute.return_value = mock_result

        fake_now = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)
        with patch("backend.tasks.pipeline.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            missing = await detect_gap("price_refresh")

        assert missing == []

    @pytest.mark.asyncio
    @patch("backend.tasks.pipeline.async_session_factory")
    async def test_no_watermark_returns_empty(self, mock_factory: MagicMock) -> None:
        """detect_gap should return empty list when no watermark exists."""
        mock_cm, mock_session = _mock_session_factory()
        mock_factory.return_value = mock_cm

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        missing = await detect_gap("price_refresh")
        assert missing == []


# ---------------------------------------------------------------------------
# Exponential backoff retry
# ---------------------------------------------------------------------------


class TestWithRetry:
    """Tests for with_retry exponential backoff helper."""

    @pytest.mark.asyncio
    async def test_succeeds_first_try(self) -> None:
        """with_retry should return immediately on first success."""
        result = await with_retry(lambda: _async_return(42), max_retries=3)
        assert result == 42

    @pytest.mark.asyncio
    @patch("backend.tasks.pipeline.asyncio.sleep", new_callable=AsyncMock)
    async def test_retries_then_succeeds(self, mock_sleep: AsyncMock) -> None:
        """with_retry should retry on failure and succeed on later attempt."""
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("transient")
            return "ok"

        result = await with_retry(flaky, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert call_count == 3
        assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    @patch("backend.tasks.pipeline.asyncio.sleep", new_callable=AsyncMock)
    async def test_exhausts_retries(self, mock_sleep: AsyncMock) -> None:
        """with_retry should raise the last exception when all retries fail."""

        async def always_fail():
            raise ConnectionError("db down")

        with pytest.raises(ConnectionError, match="db down"):
            await with_retry(always_fail, max_retries=2, base_delay=0.01)

        # 3 total attempts (initial + 2 retries), 2 sleeps
        assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    @patch("backend.tasks.pipeline.asyncio.sleep", new_callable=AsyncMock)
    async def test_exponential_delays(self, mock_sleep: AsyncMock) -> None:
        """with_retry should use exponential backoff: base, base*2, base*4..."""

        async def always_fail():
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            await with_retry(always_fail, max_retries=3, base_delay=1.0)

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == [1.0, 2.0, 4.0]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _async_return(value):
    """Helper: return a value asynchronously."""
    return value
