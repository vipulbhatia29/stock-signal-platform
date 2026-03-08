"""Tests for on-demand data ingestion endpoint."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from httpx import AsyncClient


class TestIngestTicker:
    """Tests for POST /api/v1/stocks/{ticker}/ingest."""

    async def test_ingest_requires_auth(self, client: AsyncClient) -> None:
        """Unauthenticated request returns 401."""
        response = await client.post("/api/v1/stocks/AAPL/ingest")
        assert response.status_code == 401

    async def test_ingest_invalid_ticker_format(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Invalid ticker format returns 400."""
        response = await authenticated_client.post("/api/v1/stocks/$INVALID!/ingest")
        assert response.status_code == 400
        assert "invalid ticker" in response.json()["detail"].lower()

    @patch("backend.tools.signals.store_signal_snapshot", new_callable=AsyncMock)
    @patch("backend.tools.signals.compute_signals")
    @patch(
        "backend.tools.market_data.update_last_fetched_at", new_callable=AsyncMock
    )
    @patch("backend.tools.market_data.fetch_prices_delta", new_callable=AsyncMock)
    @patch("backend.tools.market_data.ensure_stock_exists", new_callable=AsyncMock)
    async def test_ingest_new_ticker_success(
        self,
        mock_ensure: AsyncMock,
        mock_fetch: AsyncMock,
        mock_update: AsyncMock,
        mock_compute: MagicMock,
        mock_store_signal: AsyncMock,
        authenticated_client: AsyncClient,
    ) -> None:
        """Ingesting a new ticker fetches data and computes signals."""
        mock_stock = MagicMock()
        mock_stock.name = "Apple Inc"
        mock_stock.last_fetched_at = None
        mock_ensure.return_value = mock_stock

        df = pd.DataFrame({"Close": [150.0, 151.0]})
        mock_fetch.return_value = df

        mock_compute.return_value = {"composite_score": 7.5}

        response = await authenticated_client.post("/api/v1/stocks/AAPL/ingest")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert data["name"] == "Apple Inc"
        assert data["rows_fetched"] == 2
        assert data["composite_score"] == 7.5

    @patch("backend.tools.market_data.ensure_stock_exists", new_callable=AsyncMock)
    async def test_ingest_unknown_ticker_returns_404(
        self,
        mock_ensure: AsyncMock,
        authenticated_client: AsyncClient,
    ) -> None:
        """Ticker not found on yfinance returns 404."""
        mock_ensure.side_effect = ValueError("Could not find stock info for 'ZZZZ'")
        response = await authenticated_client.post("/api/v1/stocks/ZZZZ/ingest")
        assert response.status_code == 404
