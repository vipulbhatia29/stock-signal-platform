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
    """GET /health should return {"status": "ok"}."""
    response = await simple_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_check_is_unauthenticated(simple_client: AsyncClient) -> None:
    """Health check should not require authentication."""
    response = await simple_client.get("/health")
    assert response.status_code == 200
