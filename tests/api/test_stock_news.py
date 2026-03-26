"""API tests for stock news and intelligence endpoints."""

import pytest
from httpx import AsyncClient


class TestStockNews:
    """Tests for GET /api/v1/stocks/{ticker}/news."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated request should return 401."""
        response = await client.get("/api/v1/stocks/AAPL/news")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unknown_ticker_returns_404(self, authenticated_client: AsyncClient) -> None:
        """Unknown ticker should return 404."""
        response = await authenticated_client.get("/api/v1/stocks/ZZZZZ/news")
        assert response.status_code == 404


class TestStockIntelligence:
    """Tests for GET /api/v1/stocks/{ticker}/intelligence."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated request should return 401."""
        response = await client.get("/api/v1/stocks/AAPL/intelligence")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unknown_ticker_returns_404(self, authenticated_client: AsyncClient) -> None:
        """Unknown ticker should return 404."""
        response = await authenticated_client.get("/api/v1/stocks/ZZZZZ/intelligence")
        assert response.status_code == 404
