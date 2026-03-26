"""API tests for market briefing endpoint."""

import pytest
from httpx import AsyncClient


class TestMarketBriefing:
    """Tests for GET /api/v1/market/briefing."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated request should return 401."""
        response = await client.get("/api/v1/market/briefing")
        assert response.status_code == 401
