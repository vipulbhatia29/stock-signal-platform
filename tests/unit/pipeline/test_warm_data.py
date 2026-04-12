"""Tests for warm data Celery tasks."""

import uuid
from unittest.mock import AsyncMock, patch

from tests.unit.tasks._tracked_helper_bypass import bypass_tracked


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
    import asyncio

    from backend.tasks.warm_data import _sync_analyst_consensus_async

    with patch(
        "backend.tasks.warm_data._fetch_and_cache_analyst",
        new_callable=AsyncMock,
    ) as mock_fetch:
        tickers = ["AAPL", "MSFT"]
        r = object()  # unused — helper is patched
        asyncio.run(bypass_tracked(_sync_analyst_consensus_async)(tickers, r, run_id=uuid.uuid4()))
        assert mock_fetch.await_count == 2


def test_fred_indicators_task_calls_fred():
    """sync_fred_indicators_task invokes the FRED adapter."""
    import asyncio

    from backend.tasks.warm_data import _sync_fred_indicators_async

    with patch(
        "backend.tasks.warm_data._fetch_and_cache_fred",
        new_callable=AsyncMock,
    ) as mock_fetch:
        r = object()  # unused — helper is patched
        asyncio.run(bypass_tracked(_sync_fred_indicators_async)(r, run_id=uuid.uuid4()))
        assert mock_fetch.await_count == 1


def test_institutional_holders_task_calls_edgar():
    """sync_institutional_holders_task invokes the Edgar adapter."""
    import asyncio

    from backend.tasks.warm_data import _sync_institutional_holders_async

    with patch(
        "backend.tasks.warm_data._fetch_and_cache_holders",
        new_callable=AsyncMock,
    ) as mock_fetch:
        tickers = ["AAPL"]
        r = object()  # unused — helper is patched
        asyncio.run(
            bypass_tracked(_sync_institutional_holders_async)(tickers, r, run_id=uuid.uuid4())
        )
        assert mock_fetch.await_count == 1
