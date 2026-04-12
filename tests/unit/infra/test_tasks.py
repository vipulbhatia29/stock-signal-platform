"""Unit tests for Celery tasks."""

from unittest.mock import patch

import pytest


def test_refresh_ticker_task_calls_ingest():
    """refresh_ticker_task delegates to _refresh_ticker_async via asyncio.run."""
    with patch("asyncio.run", return_value={"ticker": "AAPL", "status": "ok"}) as mock_run:
        from backend.tasks.market_data import refresh_ticker_task

        result = refresh_ticker_task.run("AAPL")
        mock_run.assert_called_once()
        assert result["ticker"] == "AAPL"
        assert result["status"] == "ok"


def test_refresh_ticker_task_retries_on_exception():
    """refresh_ticker_task re-raises when async helper raises an exception."""
    with patch("asyncio.run") as mock_run:
        mock_run.side_effect = Exception("yfinance rate limit")

        from backend.tasks.market_data import refresh_ticker_task

        with pytest.raises(Exception, match="yfinance rate limit"):
            refresh_ticker_task.run("AAPL")


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_intraday_refresh_all_task_dispatches_per_ticker():
    """intraday_refresh_all_task fans out one task per referenced ticker."""
    with (
        patch(
            "asyncio.run",
            return_value=["AAPL", "MSFT"],
        ) as mock_run,
        patch("backend.tasks.market_data.refresh_ticker_task") as mock_task,
    ):
        from backend.tasks.market_data import intraday_refresh_all_task

        result = intraday_refresh_all_task.run()

        mock_run.assert_called_once()
        assert mock_task.delay.call_count == 2
        mock_task.delay.assert_any_call("AAPL")
        mock_task.delay.assert_any_call("MSFT")
        assert result["dispatched"] == 2
        assert result["tickers"] == ["AAPL", "MSFT"]


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_intraday_refresh_all_task_handles_empty_universe():
    """intraday_refresh_all_task returns 0 dispatched when no tickers."""
    with (
        patch("asyncio.run", return_value=[]) as mock_run,
        patch("backend.tasks.market_data.refresh_ticker_task") as mock_task,
    ):
        from backend.tasks.market_data import intraday_refresh_all_task

        result = intraday_refresh_all_task.run()

        mock_run.assert_called_once()
        mock_task.delay.assert_not_called()
        assert result["dispatched"] == 0
        assert result["tickers"] == []


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_beat_schedule_contains_refresh_job():
    """Celery beat_schedule includes the 30-minute watchlist refresh job."""
    from backend.tasks import celery_app

    assert "intraday-refresh-all" in celery_app.conf.beat_schedule
    entry = celery_app.conf.beat_schedule["intraday-refresh-all"]
    assert entry["task"] == "backend.tasks.market_data.intraday_refresh_all_task"
    assert entry["schedule"] == 30 * 60


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_beat_schedule_contains_portfolio_snapshot_job():
    """Celery beat_schedule includes the daily portfolio snapshot job."""
    from backend.tasks import celery_app

    assert "snapshot-all-portfolios-daily" in celery_app.conf.beat_schedule
    entry = celery_app.conf.beat_schedule["snapshot-all-portfolios-daily"]
    assert entry["task"] == "backend.tasks.portfolio.snapshot_all_portfolios_task"


def test_snapshot_all_portfolios_task_calls_async():
    """snapshot_all_portfolios_task delegates to _snapshot_all_portfolios_async."""
    with patch("asyncio.run", return_value={"snapshotted": 2, "skipped": 0}) as mock_run:
        from backend.tasks.portfolio import snapshot_all_portfolios_task

        result = snapshot_all_portfolios_task.run()
        mock_run.assert_called_once()
        assert result["snapshotted"] == 2
        assert result["skipped"] == 0


def test_snapshot_all_portfolios_task_retries_on_exception():
    """snapshot_all_portfolios_task re-raises on failure."""
    with patch("asyncio.run") as mock_run:
        mock_run.side_effect = Exception("DB connection refused")

        from backend.tasks.portfolio import snapshot_all_portfolios_task

        with pytest.raises(Exception, match="DB connection refused"):
            snapshot_all_portfolios_task.run()
