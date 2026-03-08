"""Tests for authentication endpoints."""

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
