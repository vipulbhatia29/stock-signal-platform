"""Tests for warm data Celery tasks."""

from unittest.mock import AsyncMock, patch


def test_sync_analyst_consensus_task_exists():
    """Task is registered with Celery."""
    from backend.tasks.warm_data import sync_analyst_consensus_task

    assert sync_analyst_consensus_task.name


def test_sync_fred_indicators_task_exists():
    """Task is registered with Celery."""
    from backend.tasks.warm_data import sync_fred_indicators_task

    assert sync_fred_indicators_task.name


def test_sync_institutional_holders_task_exists():
    """Task is registered with Celery."""
    from backend.tasks.warm_data import sync_institutional_holders_task

    assert sync_institutional_holders_task.name


def test_analyst_consensus_task_calls_finnhub():
    """sync_analyst_consensus_task invokes the Finnhub adapter."""
    with (
        patch(
            "backend.tasks.warm_data._get_watched_tickers",
            return_value=["AAPL", "MSFT"],
        ),
        patch(
            "backend.tasks.warm_data._fetch_and_cache_analyst",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        from backend.tasks.warm_data import sync_analyst_consensus_task

        result = sync_analyst_consensus_task()
        assert result["tickers_processed"] == 2
        assert mock_fetch.await_count == 2


def test_fred_indicators_task_calls_fred():
    """sync_fred_indicators_task invokes the FRED adapter."""
    with patch(
        "backend.tasks.warm_data._fetch_and_cache_fred",
        new_callable=AsyncMock,
    ) as mock_fetch:
        from backend.tasks.warm_data import sync_fred_indicators_task

        result = sync_fred_indicators_task()
        assert result["status"] == "ok"
        assert mock_fetch.await_count == 1


def test_institutional_holders_task_calls_edgar():
    """sync_institutional_holders_task invokes the Edgar adapter."""
    with (
        patch(
            "backend.tasks.warm_data._get_watched_tickers",
            return_value=["AAPL"],
        ),
        patch(
            "backend.tasks.warm_data._fetch_and_cache_holders",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        from backend.tasks.warm_data import sync_institutional_holders_task

        result = sync_institutional_holders_task()
        assert result["tickers_processed"] == 1
        assert mock_fetch.await_count == 1
