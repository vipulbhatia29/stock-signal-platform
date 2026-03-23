"""Tests for the health check endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.fixture
async def simple_client() -> AsyncClient:
    """Client without DB dependency for health check."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_health_check_returns_ok(simple_client: AsyncClient) -> None:
    """GET /api/v1/health should return status and version."""
    response = await simple_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert "version" in data
    assert "mcp_tools" in data


async def test_health_check_is_unauthenticated(simple_client: AsyncClient) -> None:
    """Health check should not require authentication."""
    response = await simple_client.get("/api/v1/health")
    assert response.status_code == 200
