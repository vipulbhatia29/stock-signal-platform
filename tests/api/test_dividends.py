"""API tests for dividend endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestDividendAuth:
    """Unauthenticated requests return 401."""

    async def test_dividends_requires_auth(self, client: AsyncClient) -> None:
        """GET /portfolio/dividends/AAPL without token returns 401."""
        resp = await client.get("/api/v1/portfolio/dividends/AAPL")
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestGetDividends:
    """Tests for GET /api/v1/portfolio/dividends/{ticker}."""

    @patch(
        "backend.routers.portfolio.get_latest_price",
        new_callable=AsyncMock,
        return_value=185.0,
    )
    @patch(
        "backend.routers.portfolio.get_dividend_summary",
        new_callable=AsyncMock,
    )
    async def test_returns_dividend_summary(
        self,
        mock_summary: AsyncMock,
        mock_price: AsyncMock,
        authenticated_client: AsyncClient,
    ) -> None:
        """Happy path: returns dividend summary with history."""
        mock_summary.return_value = {
            "ticker": "AAPL",
            "total_received": 2.0,
            "annual_dividends": 1.0,
            "dividend_yield": 0.54,
            "last_ex_date": datetime(2026, 2, 14, tzinfo=timezone.utc),
            "payment_count": 8,
            "history": [
                {
                    "ticker": "AAPL",
                    "ex_date": datetime(2026, 2, 14, tzinfo=timezone.utc),
                    "amount": 0.25,
                },
            ],
        }

        resp = await authenticated_client.get("/api/v1/portfolio/dividends/AAPL")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "AAPL"
        assert data["total_received"] == 2.0
        assert data["annual_dividends"] == 1.0
        assert data["dividend_yield"] == 0.54
        assert data["payment_count"] == 8
        assert len(data["history"]) == 1
        assert data["history"][0]["amount"] == 0.25

    @patch(
        "backend.routers.portfolio.get_latest_price",
        new_callable=AsyncMock,
        return_value=None,
    )
    @patch(
        "backend.routers.portfolio.get_dividend_summary",
        new_callable=AsyncMock,
    )
    async def test_no_dividends_returns_empty(
        self,
        mock_summary: AsyncMock,
        mock_price: AsyncMock,
        authenticated_client: AsyncClient,
    ) -> None:
        """Ticker with no dividends returns zeroed summary."""
        mock_summary.return_value = {
            "ticker": "TSLA",
            "total_received": 0.0,
            "annual_dividends": 0.0,
            "dividend_yield": None,
            "last_ex_date": None,
            "payment_count": 0,
            "history": [],
        }

        resp = await authenticated_client.get("/api/v1/portfolio/dividends/TSLA")

        assert resp.status_code == 200
        data = resp.json()
        assert data["payment_count"] == 0
        assert data["history"] == []
        assert data["dividend_yield"] is None

    @patch(
        "backend.routers.portfolio.get_latest_price",
        new_callable=AsyncMock,
        return_value=185.0,
    )
    @patch(
        "backend.routers.portfolio.get_dividend_summary",
        new_callable=AsyncMock,
    )
    async def test_ticker_case_insensitive(
        self,
        mock_summary: AsyncMock,
        mock_price: AsyncMock,
        authenticated_client: AsyncClient,
    ) -> None:
        """Lowercase ticker in URL is passed through to tool functions."""
        mock_summary.return_value = {
            "ticker": "AAPL",
            "total_received": 0.0,
            "annual_dividends": 0.0,
            "dividend_yield": None,
            "last_ex_date": None,
            "payment_count": 0,
            "history": [],
        }

        resp = await authenticated_client.get("/api/v1/portfolio/dividends/aapl")

        assert resp.status_code == 200
        # The tool normalises to uppercase internally
        mock_summary.assert_called_once()
