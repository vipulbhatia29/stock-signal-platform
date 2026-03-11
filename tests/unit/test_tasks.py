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
