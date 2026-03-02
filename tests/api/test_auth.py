"""Tests for authentication endpoints."""

import pytest
from httpx import AsyncClient


class TestRegister:
    """Tests for POST /api/v1/auth/register."""

    async def test_register_success(self, client: AsyncClient) -> None:
        """Valid registration creates a user and returns 201."""
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "new@test.com", "password": "ValidPass1"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "new@test.com"
        assert "id" in data
        assert "created_at" in data

    async def test_register_duplicate_email(self, client: AsyncClient) -> None:
        """Registering with an existing email returns 409."""
        payload = {"email": "dupe@test.com", "password": "ValidPass1"}
        await client.post("/api/v1/auth/register", json=payload)
        response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 409
        assert "already registered" in response.json()["detail"].lower()

    async def test_register_weak_password_no_uppercase(self, client: AsyncClient) -> None:
        """Password without uppercase letter is rejected."""
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "weak@test.com", "password": "nouppercase1"},
        )
        assert response.status_code == 422

    async def test_register_weak_password_no_digit(self, client: AsyncClient) -> None:
        """Password without digit is rejected."""
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "weak@test.com", "password": "NoDigitHere"},
        )
        assert response.status_code == 422

    async def test_register_short_password(self, client: AsyncClient) -> None:
        """Password shorter than 8 chars is rejected."""
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "short@test.com", "password": "Ab1"},
        )
        assert response.status_code == 422

    async def test_register_invalid_email(self, client: AsyncClient) -> None:
        """Invalid email format is rejected."""
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": "ValidPass1"},
        )
        assert response.status_code == 422


class TestLogin:
    """Tests for POST /api/v1/auth/login."""

    async def _register_user(self, client: AsyncClient) -> dict:
        """Helper: register a user and return credentials."""
        email, password = "login@test.com", "LoginPass1"
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        return {"email": email, "password": password}

    async def test_login_success(self, client: AsyncClient) -> None:
        """Valid credentials return token pair."""
        creds = await self._register_user(client)
        response = await client.post("/api/v1/auth/login", json=creds)
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

    async def test_login_wrong_password(self, client: AsyncClient) -> None:
        """Wrong password returns 401."""
        await self._register_user(client)
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "login@test.com", "password": "WrongPass1"},
        )
        assert response.status_code == 401

    async def test_login_nonexistent_email(self, client: AsyncClient) -> None:
        """Unknown email returns 401."""
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "noone@test.com", "password": "Whatever1"},
        )
        assert response.status_code == 401


class TestRefreshToken:
    """Tests for POST /api/v1/auth/refresh."""

    async def _get_tokens(self, client: AsyncClient) -> dict:
        """Helper: register + login and return tokens."""
        email, password = "refresh@test.com", "RefreshPass1"
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        return response.json()

    async def test_refresh_success(self, client: AsyncClient) -> None:
        """Valid refresh token returns new token pair."""
        tokens = await self._get_tokens(client)
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_refresh_with_access_token_fails(self, client: AsyncClient) -> None:
        """Using an access token as refresh token returns 401."""
        tokens = await self._get_tokens(client)
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["access_token"]},
        )
        assert response.status_code == 401

    async def test_refresh_with_invalid_token_fails(self, client: AsyncClient) -> None:
        """Invalid token string returns 401."""
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid.token.string"},
        )
        assert response.status_code == 401
