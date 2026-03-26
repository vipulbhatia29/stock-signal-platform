"""API tests for portfolio health history endpoint."""

import pytest
from httpx import AsyncClient


class TestHealthHistory:
    """Tests for GET /api/v1/portfolio/health/history."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated should return 401."""
        response = await client.get("/api/v1/portfolio/health/history")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_returns_empty_list_initially(self, authenticated_client: AsyncClient) -> None:
        """New user with no snapshots should get empty list."""
        response = await authenticated_client.get("/api/v1/portfolio/health/history")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_days_param_validation(self, authenticated_client: AsyncClient) -> None:
        """Days > 365 should return 422."""
        response = await authenticated_client.get("/api/v1/portfolio/health/history?days=500")
        assert response.status_code == 422
