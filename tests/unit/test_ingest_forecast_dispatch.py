"""Tests for on-ingest forecast dispatch (KAN-404).

Verifies that ingest_ticker dispatches retrain_single_ticker_task after step 6,
and that a Celery/Redis failure does not break the ingest pipeline.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from backend.services.pipelines import ingest_ticker

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestIngestForecastDispatch:
    """Forecast dispatch fire-and-forget behaviour inside ingest_ticker."""

    @pytest.mark.asyncio
    @patch("backend.tasks.forecasting.retrain_single_ticker_task")
    @patch("backend.services.pipelines.update_last_fetched_at", new_callable=AsyncMock)
    @patch("backend.services.pipelines.persist_earnings_snapshots", new_callable=AsyncMock)
    @patch("backend.services.pipelines.persist_enriched_fundamentals", new_callable=AsyncMock)
    @patch("backend.services.pipelines.fetch_earnings_history", return_value=[])
    @patch("backend.services.pipelines.fetch_analyst_data", return_value=MagicMock())
    @patch(
        "backend.services.pipelines.fetch_fundamentals",
        return_value=MagicMock(piotroski_score=5),
    )
    @patch("backend.services.pipelines.load_prices_df")
    @patch("backend.services.pipelines.fetch_prices_delta", new_callable=AsyncMock)
    @patch("backend.services.pipelines.ensure_stock_exists", new_callable=AsyncMock)
    async def test_dispatches_forecast_training_on_ingest(
        self,
        mock_ensure: AsyncMock,
        mock_fetch_prices: AsyncMock,
        mock_load_df: MagicMock,
        mock_fundamentals: MagicMock,
        mock_analyst: MagicMock,
        mock_earnings: MagicMock,
        mock_persist_fundamentals: AsyncMock,
        mock_persist_earnings: AsyncMock,
        mock_update_fetched: AsyncMock,
        mock_retrain_task: MagicMock,
    ) -> None:
        """Successful ingest dispatches retrain_single_ticker_task.delay(ticker)."""
        mock_stock = MagicMock()
        mock_stock.name = "Ford Motor Co"
        mock_stock.last_fetched_at = None
        mock_ensure.return_value = mock_stock
        mock_fetch_prices.return_value = pd.DataFrame({"Close": [10.0]})
        mock_load_df.return_value = pd.DataFrame({"Close": [10.0, 11.0]})

        mock_db = AsyncMock()
        result = await ingest_ticker("FORD", mock_db)

        mock_retrain_task.delay.assert_called_once_with("FORD", priority=True)
        assert result["ticker"] == "FORD"

    @pytest.mark.asyncio
    @patch("backend.tasks.forecasting.retrain_single_ticker_task")
    @patch("backend.services.pipelines.update_last_fetched_at", new_callable=AsyncMock)
    @patch("backend.services.pipelines.persist_earnings_snapshots", new_callable=AsyncMock)
    @patch("backend.services.pipelines.persist_enriched_fundamentals", new_callable=AsyncMock)
    @patch("backend.services.pipelines.fetch_earnings_history", return_value=[])
    @patch("backend.services.pipelines.fetch_analyst_data", return_value=MagicMock())
    @patch(
        "backend.services.pipelines.fetch_fundamentals",
        return_value=MagicMock(piotroski_score=5),
    )
    @patch("backend.services.pipelines.load_prices_df")
    @patch("backend.services.pipelines.fetch_prices_delta", new_callable=AsyncMock)
    @patch("backend.services.pipelines.ensure_stock_exists", new_callable=AsyncMock)
    async def test_celery_failure_does_not_break_ingest(
        self,
        mock_ensure: AsyncMock,
        mock_fetch_prices: AsyncMock,
        mock_load_df: MagicMock,
        mock_fundamentals: MagicMock,
        mock_analyst: MagicMock,
        mock_earnings: MagicMock,
        mock_persist_fundamentals: AsyncMock,
        mock_persist_earnings: AsyncMock,
        mock_update_fetched: AsyncMock,
        mock_retrain_task: MagicMock,
    ) -> None:
        """Celery dispatch failure (ConnectionError) does not break ingest — result returned."""
        mock_stock = MagicMock()
        mock_stock.name = "Ford Motor Co"
        mock_stock.last_fetched_at = None
        mock_ensure.return_value = mock_stock
        mock_fetch_prices.return_value = pd.DataFrame({"Close": [10.0]})
        mock_load_df.return_value = pd.DataFrame({"Close": [10.0, 11.0]})
        mock_retrain_task.delay.side_effect = ConnectionError("Redis down")

        mock_db = AsyncMock()
        result = await ingest_ticker("FORD", mock_db)

        # Ingest still completes successfully despite the dispatch failure
        assert result["ticker"] == "FORD"
        assert result["stock_name"] == "Ford Motor Co"
