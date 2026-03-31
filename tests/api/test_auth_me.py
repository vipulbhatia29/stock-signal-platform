"""Tests for GET /auth/me endpoint."""

import pytest
from httpx import AsyncClient


async def _register_and_login(client: AsyncClient) -> AsyncClient:
    """Register a user, login, and return the client with auth cookies set."""
    email, password = "metest@example.com", "MeTest1234"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    # httpx AsyncClient automatically stores cookies from Set-Cookie headers
    assert resp.status_code == 200
    return client


@pytest.mark.asyncio
async def test_me_unauthenticated(client: AsyncClient) -> None:
    """Unauthenticated request to /auth/me returns 401."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_profile(client: AsyncClient) -> None:
    """Authenticated request to /auth/me returns the user's profile."""
    client = await _register_and_login(client)
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["email"] == "metest@example.com"
    assert data["role"] in ("admin", "user")
    assert data["is_active"] is True
