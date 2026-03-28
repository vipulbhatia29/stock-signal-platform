"""Tests for on-demand data ingestion endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
from httpx import AsyncClient


class TestIngestTicker:
    """Tests for POST /api/v1/stocks/{ticker}/ingest."""

    async def test_ingest_requires_auth(self, client: AsyncClient) -> None:
        """Unauthenticated request returns 401."""
        response = await client.post("/api/v1/stocks/AAPL/ingest")
        assert response.status_code == 401

    async def test_ingest_invalid_ticker_format(self, authenticated_client: AsyncClient) -> None:
        """Invalid ticker format returns 422 (path param validation)."""
        response = await authenticated_client.post("/api/v1/stocks/$INVALID!/ingest")
        assert response.status_code == 422

    @patch("backend.services.pipelines.store_signal_snapshot", new_callable=AsyncMock)
    @patch("backend.services.pipelines.compute_signals")
    @patch("backend.services.pipelines.persist_earnings_snapshots", new_callable=AsyncMock)
    @patch("backend.services.pipelines.fetch_earnings_history", return_value=[])
    @patch("backend.services.pipelines.persist_enriched_fundamentals", new_callable=AsyncMock)
    @patch("backend.services.pipelines.fetch_analyst_data", return_value={})
    @patch("backend.services.pipelines.fetch_fundamentals")
    @patch("backend.services.pipelines.update_last_fetched_at", new_callable=AsyncMock)
    @patch("backend.services.pipelines.load_prices_df", new_callable=AsyncMock)
    @patch("backend.services.pipelines.fetch_prices_delta", new_callable=AsyncMock)
    @patch("backend.services.pipelines.ensure_stock_exists", new_callable=AsyncMock)
    async def test_ingest_new_ticker_success(
        self,
        mock_ensure: AsyncMock,
        mock_fetch: AsyncMock,
        mock_load: AsyncMock,
        mock_update: AsyncMock,
        mock_fundamentals: MagicMock,
        _mock_analyst: MagicMock,
        _mock_persist: AsyncMock,
        _mock_earnings: MagicMock,
        _mock_persist_earnings: AsyncMock,
        mock_compute: MagicMock,
        mock_store_signal: AsyncMock,
        authenticated_client: AsyncClient,
    ) -> None:
        """Ingesting a new ticker fetches data and computes signals."""
        mock_stock = MagicMock()
        mock_stock.name = "Apple Inc"
        mock_stock.last_fetched_at = None
        mock_ensure.return_value = mock_stock

        delta_df = pd.DataFrame({"Close": [150.0, 151.0]})
        mock_fetch.return_value = delta_df

        full_df = pd.DataFrame({"Close": [148.0, 149.0, 150.0, 151.0]})
        mock_load.return_value = full_df

        mock_fund_result = MagicMock()
        mock_fund_result.piotroski_score = 7
        mock_fundamentals.return_value = mock_fund_result

        mock_result = MagicMock()
        mock_result.composite_score = 7.5
        mock_compute.return_value = mock_result

        response = await authenticated_client.post("/api/v1/stocks/AAPL/ingest")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert data["name"] == "Apple Inc"
        assert data["rows_fetched"] == 2
        assert data["composite_score"] == 7.5

        # Verify compute_signals was called with piotroski_score
        mock_compute.assert_called_once()
        call_kwargs = mock_compute.call_args
        assert call_kwargs.kwargs.get("piotroski_score") == 7

    @patch("backend.services.pipelines.store_signal_snapshot", new_callable=AsyncMock)
    @patch("backend.services.pipelines.compute_signals")
    @patch("backend.services.pipelines.persist_earnings_snapshots", new_callable=AsyncMock)
    @patch("backend.services.pipelines.fetch_earnings_history", return_value=[])
    @patch("backend.services.pipelines.persist_enriched_fundamentals", new_callable=AsyncMock)
    @patch("backend.services.pipelines.fetch_analyst_data", return_value={})
    @patch("backend.services.pipelines.fetch_fundamentals")
    @patch("backend.services.pipelines.update_last_fetched_at", new_callable=AsyncMock)
    @patch("backend.services.pipelines.load_prices_df", new_callable=AsyncMock)
    @patch("backend.services.pipelines.fetch_prices_delta", new_callable=AsyncMock)
    @patch("backend.services.pipelines.ensure_stock_exists", new_callable=AsyncMock)
    async def test_ingest_passes_none_piotroski_when_fundamentals_unavailable(
        self,
        mock_ensure: AsyncMock,
        mock_fetch: AsyncMock,
        mock_load: AsyncMock,
        mock_update: AsyncMock,
        mock_fundamentals: MagicMock,
        _mock_analyst: MagicMock,
        _mock_persist: AsyncMock,
        _mock_earnings: MagicMock,
        _mock_persist_earnings: AsyncMock,
        mock_compute: MagicMock,
        mock_store_signal: AsyncMock,
        authenticated_client: AsyncClient,
    ) -> None:
        """When fundamentals return no Piotroski, composite uses 100% technical."""
        mock_stock = MagicMock()
        mock_stock.name = "SPDR ETF"
        mock_stock.last_fetched_at = None
        mock_ensure.return_value = mock_stock

        mock_fetch.return_value = pd.DataFrame({"Close": [400.0, 401.0]})
        mock_load.return_value = pd.DataFrame({"Close": [398.0, 399.0, 400.0, 401.0]})

        mock_fund_result = MagicMock()
        mock_fund_result.piotroski_score = None
        mock_fundamentals.return_value = mock_fund_result

        mock_result = MagicMock()
        mock_result.composite_score = 6.0
        mock_compute.return_value = mock_result

        response = await authenticated_client.post("/api/v1/stocks/SPY/ingest")
        assert response.status_code == 200

        # Verify compute_signals was called with piotroski_score=None
        mock_compute.assert_called_once()
        call_kwargs = mock_compute.call_args
        assert call_kwargs.kwargs.get("piotroski_score") is None

    @patch("backend.services.pipelines.ensure_stock_exists", new_callable=AsyncMock)
    async def test_ingest_unknown_ticker_returns_404(
        self,
        mock_ensure: AsyncMock,
        authenticated_client: AsyncClient,
    ) -> None:
        """Ticker not found on yfinance returns 404."""
        mock_ensure.side_effect = ValueError("Could not find stock info for 'ZZZZ'")
        response = await authenticated_client.post("/api/v1/stocks/ZZZZ/ingest")
        assert response.status_code == 404
