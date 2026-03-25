"""Tests for authentication endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.fixture(autouse=True)
def _mock_blocklist():
    """Mock Redis blocklist for all auth API tests to avoid real Redis calls."""
    with (
        patch(
            "backend.routers.auth.is_blocklisted",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_check,
        patch(
            "backend.routers.auth.add_to_blocklist",
            new_callable=AsyncMock,
        ) as mock_add,
        patch(
            "backend.services.redis_pool.get_redis",
            new_callable=AsyncMock,
            return_value=AsyncMock(),
        ),
    ):
        yield {"is_blocklisted": mock_check, "add_to_blocklist": mock_add}


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

    async def test_login_sets_cookies(self, client: AsyncClient) -> None:
        """Login sets httpOnly access_token and refresh_token cookies."""
        creds = await self._register_user(client)
        response = await client.post("/api/v1/auth/login", json=creds)
        assert response.status_code == 200

        cookies = response.cookies
        assert "access_token" in cookies
        assert "refresh_token" in cookies

    async def test_login_cookies_are_httponly(self, client: AsyncClient) -> None:
        """Login cookies have httpOnly flag set."""
        creds = await self._register_user(client)
        response = await client.post("/api/v1/auth/login", json=creds)

        # Check Set-Cookie headers for httponly
        set_cookie_headers = response.headers.get_list("set-cookie")
        assert len(set_cookie_headers) >= 2
        for header in set_cookie_headers:
            assert "httponly" in header.lower()

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


class TestCookieAuth:
    """Tests for cookie-based authentication on protected endpoints."""

    async def _login_and_get_cookies(self, client: AsyncClient) -> dict:
        """Helper: register, login, return cookies from response."""
        email, password = "cookie@test.com", "CookiePass1"
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        return dict(response.cookies)

    async def test_cookie_auth_on_protected_endpoint(self, client: AsyncClient) -> None:
        """Protected endpoint works with cookie-based auth (no Authorization header)."""
        cookies = await self._login_and_get_cookies(client)
        response = await client.get(
            "/api/v1/stocks/search",
            params={"q": "AAPL"},
            cookies=cookies,
        )
        assert response.status_code == 200

    async def test_header_auth_still_works(self, client: AsyncClient) -> None:
        """Authorization header still works for backward compatibility."""
        email, password = "header@test.com", "HeaderPass1"
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        token = login_resp.json()["access_token"]
        response = await client.get(
            "/api/v1/stocks/search",
            params={"q": "AAPL"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

    async def test_no_auth_returns_401(self, client: AsyncClient) -> None:
        """Protected endpoint without any auth returns 401."""
        response = await client.get(
            "/api/v1/stocks/search",
            params={"q": "AAPL"},
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

    async def test_refresh_sets_cookies(self, client: AsyncClient) -> None:
        """Refresh endpoint updates httpOnly cookies."""
        tokens = await self._get_tokens(client)
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert response.status_code == 200
        cookies = response.cookies
        assert "access_token" in cookies
        assert "refresh_token" in cookies

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


class TestLogout:
    """Tests for POST /api/v1/auth/logout."""

    async def test_logout_clears_cookies(self, client: AsyncClient) -> None:
        """Logout clears auth cookies by setting max-age=0."""
        response = await client.post("/api/v1/auth/logout")
        assert response.status_code == 204

        set_cookie_headers = response.headers.get_list("set-cookie")
        cookie_names = [h.split("=")[0] for h in set_cookie_headers]
        assert "access_token" in cookie_names
        assert "refresh_token" in cookie_names

    async def test_logout_without_auth_succeeds(self, client: AsyncClient) -> None:
        """Logout works even without being logged in (idempotent)."""
        response = await client.post("/api/v1/auth/logout")
        assert response.status_code == 204


class TestTokenRevocation:
    """Tests for refresh token revocation via Redis blocklist."""

    async def _register_and_login(self, client: AsyncClient, email: str) -> dict:
        """Helper: register + login and return tokens."""
        password = "ValidPass1"
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        return response.json()

    async def test_refresh_blocklists_old_token(
        self, client: AsyncClient, _mock_blocklist: dict
    ) -> None:
        """Refreshing should blocklist the old refresh token JTI."""
        tokens = await self._register_and_login(client, "revoke1@test.com")
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert response.status_code == 200
        # Old token should have been blocklisted
        _mock_blocklist["add_to_blocklist"].assert_called()

    async def test_refresh_with_revoked_token_returns_401(
        self, client: AsyncClient, _mock_blocklist: dict
    ) -> None:
        """Using a blocklisted refresh token should return 401."""
        tokens = await self._register_and_login(client, "revoke2@test.com")

        # Simulate: token is blocklisted
        _mock_blocklist["is_blocklisted"].return_value = True

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert response.status_code == 401
        assert "revoked" in response.json()["detail"].lower()

    async def test_refresh_token_rotation_invalidates_old(
        self, client: AsyncClient, _mock_blocklist: dict
    ) -> None:
        """After refresh, old token should be blocked and new token valid."""
        tokens = await self._register_and_login(client, "rotate@test.com")
        old_refresh = tokens["refresh_token"]

        # First refresh succeeds
        resp1 = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert resp1.status_code == 200
        new_tokens = resp1.json()

        # Simulate blocklist: old token now blocked
        _mock_blocklist["is_blocklisted"].return_value = True

        # Old token should fail
        resp2 = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert resp2.status_code == 401

        # New token should work
        _mock_blocklist["is_blocklisted"].return_value = False
        resp3 = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": new_tokens["refresh_token"]},
        )
        assert resp3.status_code == 200

    async def test_logout_blocklists_refresh_token(
        self, client: AsyncClient, _mock_blocklist: dict
    ) -> None:
        """Logout with a valid refresh token cookie should blocklist it."""
        tokens = await self._register_and_login(client, "logout_bl@test.com")

        response = await client.post(
            "/api/v1/auth/logout",
            cookies={"refresh_token": tokens["refresh_token"]},
        )
        assert response.status_code == 204
        _mock_blocklist["add_to_blocklist"].assert_called()

    async def test_logout_without_refresh_token_still_clears_cookies(
        self, client: AsyncClient
    ) -> None:
        """Logout without a refresh token cookie still clears cookies gracefully."""
        response = await client.post("/api/v1/auth/logout")
        assert response.status_code == 204
        set_cookie_headers = response.headers.get_list("set-cookie")
        cookie_names = [h.split("=")[0] for h in set_cookie_headers]
        assert "access_token" in cookie_names
        assert "refresh_token" in cookie_names
