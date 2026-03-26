"""API tests for portfolio health endpoint."""

import pytest
from httpx import AsyncClient


class TestPortfolioHealth:
    """Tests for GET /api/v1/portfolio/health."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated request should return 401."""
        response = await client.get("/api/v1/portfolio/health")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_authenticated_returns_200(self, authenticated_client: AsyncClient) -> None:
        """Authenticated request should return 200 (even with no portfolio)."""
        response = await authenticated_client.get("/api/v1/portfolio/health")
        assert response.status_code == 200
