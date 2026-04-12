"""Celery & background jobs hardening tests — tasks, beat schedule, asyncio bridge."""

from unittest.mock import patch

import pytest

# ===========================================================================
# Beat schedule verification
# ===========================================================================


class TestBeatSchedule:
    """Verify Celery beat schedule is properly configured."""

    def test_beat_schedule_has_intraday_refresh(self):
        """Beat schedule includes 30-minute intraday refresh job."""
        from backend.tasks import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "intraday-refresh-all" in schedule
        entry = schedule["intraday-refresh-all"]
        assert entry["task"] == "backend.tasks.market_data.intraday_refresh_all_task"
        assert entry["schedule"] == 30 * 60

    def test_beat_schedule_has_portfolio_snapshot(self):
        """Beat schedule includes daily portfolio snapshot job."""
        from backend.tasks import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "snapshot-all-portfolios-daily" in schedule
        entry = schedule["snapshot-all-portfolios-daily"]
        assert entry["task"] == "backend.tasks.portfolio.snapshot_all_portfolios_task"

    def test_beat_schedule_has_analyst_sync(self):
        """Beat schedule includes analyst consensus sync job."""
        from backend.tasks import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "sync-analyst-consensus" in schedule

    def test_beat_schedule_has_fred_sync(self):
        """Beat schedule includes FRED indicators sync job."""
        from backend.tasks import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "sync-fred-indicators" in schedule

    def test_beat_schedule_has_institutional_holders(self):
        """Beat schedule includes institutional holders sync job."""
        from backend.tasks import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "sync-institutional-holders" in schedule


# ===========================================================================
# refresh_ticker_task
# ===========================================================================


class TestRefreshTickerTask:
    """Test refresh_ticker_task behavior."""

    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    def test_refresh_ticker_delegates_to_async(self):
        """refresh_ticker_task calls asyncio.run with _refresh_ticker_async."""
        with patch(
            "backend.tasks.market_data.asyncio.run",
            return_value={"ticker": "AAPL", "status": "ok"},
        ) as mock_run:
            from backend.tasks.market_data import refresh_ticker_task

            result = refresh_ticker_task.run("AAPL")
            mock_run.assert_called_once()
            assert result["ticker"] == "AAPL"
            assert result["status"] == "ok"

    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    def test_refresh_ticker_has_retry_config(self):
        """refresh_ticker_task is configured with retries."""
        from backend.tasks.market_data import refresh_ticker_task

        assert refresh_ticker_task.max_retries == 4


# ===========================================================================
# intraday_refresh_all_task (fan-out, renamed from refresh_all_watchlist_tickers_task)
# ===========================================================================


class TestIntradayRefreshAllTask:
    """Test intraday fan-out task."""

    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    def test_fan_out_dispatches_per_ticker(self):
        """Fan-out task dispatches one refresh_ticker_task per referenced ticker."""
        with (
            patch(
                "backend.tasks.market_data.asyncio.run",
                return_value=["AAPL", "MSFT", "GOOG"],
            ),
            patch("backend.tasks.market_data.refresh_ticker_task") as mock_task,
        ):
            from backend.tasks.market_data import intraday_refresh_all_task

            result = intraday_refresh_all_task.run()
            assert mock_task.delay.call_count == 3
            assert result["dispatched"] == 3

    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    def test_fan_out_empty_universe(self):
        """Empty universe dispatches zero tasks."""
        with (
            patch("backend.tasks.market_data.asyncio.run", return_value=[]),
            patch("backend.tasks.market_data.refresh_ticker_task") as mock_task,
        ):
            from backend.tasks.market_data import intraday_refresh_all_task

            result = intraday_refresh_all_task.run()
            mock_task.delay.assert_not_called()
            assert result["dispatched"] == 0


# ===========================================================================
# snapshot_all_portfolios_task
# ===========================================================================


class TestSnapshotTask:
    """Test portfolio snapshot task."""

    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    def test_snapshot_task_delegates_to_async(self):
        """snapshot_all_portfolios_task calls asyncio.run."""
        with patch(
            "backend.tasks.portfolio.asyncio.run",
            return_value={"snapshotted": 3, "skipped": 1},
        ) as mock_run:
            from backend.tasks.portfolio import snapshot_all_portfolios_task

            result = snapshot_all_portfolios_task.run()
            mock_run.assert_called_once()
            assert result["snapshotted"] == 3

    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    def test_snapshot_task_has_retry_config(self):
        """snapshot_all_portfolios_task has retry configuration."""
        from backend.tasks.portfolio import snapshot_all_portfolios_task

        assert snapshot_all_portfolios_task.max_retries == 2


# ===========================================================================
# Warm data tasks
# ===========================================================================


class TestWarmDataTasks:
    """Test cache warming tasks."""

    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    def test_fred_indicators_task_returns_series(self):
        """FRED indicators task returns series list."""
        with (
            patch("backend.tasks.warm_data._get_redis_client"),
            patch("backend.tasks.warm_data.asyncio.run", return_value=None),
        ):
            from backend.tasks.warm_data import sync_fred_indicators_task

            result = sync_fred_indicators_task.run()
            assert result["status"] == "ok"
            assert isinstance(result["series"], list)
