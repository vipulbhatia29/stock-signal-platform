"""CSRF protection API integration tests.

Uses real Redis testcontainer (via session-scoped fixture in tests/conftest.py).
Each test gets a fresh DB via per-test TRUNCATE fixture.
"""

import uuid

from httpx import AsyncClient


class TestCSRFProtection:
    """End-to-end CSRF validation for cookie-authenticated requests."""

    async def _register_and_login(self, client: AsyncClient) -> tuple[str, str]:
        """Register + login, return (email, csrf_token)."""
        email = f"csrf-{uuid.uuid4().hex[:8]}@test.com"
        password = "ValidPass1"
        register_resp = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        assert register_resp.status_code in (201, 409), (
            f"Unexpected register status: {register_resp.status_code}"
        )
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert login_resp.status_code == 200
        csrf_token = login_resp.cookies.get("csrf_token")
        assert csrf_token, "Login must set csrf_token cookie"
        return email, csrf_token

    async def test_mutating_request_with_valid_csrf_succeeds(self, client: AsyncClient) -> None:
        """POST with matching X-CSRF-Token passes."""
        _, csrf_token = await self._register_and_login(client)
        response = await client.post(
            "/api/v1/auth/resend-verification",
            headers={"X-CSRF-Token": csrf_token},
        )
        # 200 (already verified in dev) — the point is it's not 403
        assert response.status_code != 403

    async def test_mutating_request_without_csrf_returns_403(self, client: AsyncClient) -> None:
        """POST without X-CSRF-Token header → 403."""
        await self._register_and_login(client)
        response = await client.post("/api/v1/auth/resend-verification")
        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]

    async def test_mutating_request_with_wrong_csrf_returns_403(self, client: AsyncClient) -> None:
        """POST with wrong X-CSRF-Token → 403."""
        await self._register_and_login(client)
        response = await client.post(
            "/api/v1/auth/resend-verification",
            headers={"X-CSRF-Token": "wrong-value"},
        )
        assert response.status_code == 403

    async def test_bearer_auth_bypasses_csrf(self, client: AsyncClient) -> None:
        """Requests with Authorization Bearer skip CSRF (even without token)."""
        email, _ = await self._register_and_login(client)
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "ValidPass1"},
        )
        access_token = login_resp.json()["access_token"]

        response = await client.post(
            "/api/v1/auth/resend-verification",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code != 403

    async def test_refresh_issues_new_csrf_token(self, client: AsyncClient) -> None:
        """Refresh endpoint issues a new CSRF token (rotates on every refresh)."""
        email, old_csrf = await self._register_and_login(client)
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "ValidPass1"},
        )
        assert login_resp.status_code == 200
        old_csrf = login_resp.cookies.get("csrf_token")
        refresh_token = login_resp.json()["refresh_token"]

        refresh_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_resp.status_code == 200
        new_csrf = refresh_resp.cookies.get("csrf_token")
        assert new_csrf, "Refresh must set csrf_token cookie"
        assert new_csrf != old_csrf, "CSRF token must rotate on refresh"

    async def test_logout_clears_csrf_token(self, client: AsyncClient) -> None:
        """Logout MUST clear csrf_token cookie (CSRF-exempt, no header needed)."""
        # Don't use _register_and_login — the refresh_token cookie causes Redis
        # blocklist calls that may fail during test teardown. Logout works without auth.
        response = await client.post("/api/v1/auth/logout")
        assert response.status_code == 204
        csrf_headers = [
            h for h in response.headers.get_list("set-cookie") if h.startswith("csrf_token=")
        ]
        assert csrf_headers, "Logout should emit csrf_token clear header"

    async def test_cors_preflight_allows_x_csrf_token_header(self, client: AsyncClient) -> None:
        """CORS preflight OPTIONS must advertise X-CSRF-Token in allow_headers."""
        response = await client.options(
            "/api/v1/auth/resend-verification",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-CSRF-Token",
            },
        )
        # CORS middleware should reflect the allowed headers
        allow_headers = response.headers.get("access-control-allow-headers", "").lower()
        assert "x-csrf-token" in allow_headers, (
            f"CORS must allow X-CSRF-Token header, got: {allow_headers}"
        )
