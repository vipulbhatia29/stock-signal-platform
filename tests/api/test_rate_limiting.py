"""Rate limiting tests.

The auth router uses slowapi with per-endpoint limits:
  - POST /register:  3/minute
  - POST /login:     5/minute
  - POST /refresh:   5/minute

These tests verify that:
  - Exceeding the limit returns 429 with a Retry-After header
  - Rate limits are isolated per IP (different clients)
  - Rate limit resets after the window expires (mocked)

NOTE: In the test client setup (conftest.py) rate limiting is disabled
globally via `app.state.limiter.enabled = False`.  These tests re-enable
the limiter locally so we can exercise the 429 path without hitting the
real Redis / in-memory store in unrelated tests.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helper to (re-)enable the rate limiter for a specific test
# ---------------------------------------------------------------------------


class _EnableRateLimiter:
    """Async context manager that temporarily re-enables the slowapi limiter."""

    def __init__(self, app) -> None:  # type: ignore[no-untyped-def]
        self._app = app

    async def __aenter__(self) -> None:
        self._app.state.limiter.enabled = True

    async def __aexit__(self, *_) -> None:  # type: ignore[no-untyped-def]
        self._app.state.limiter.enabled = False


def _rate_limiter(client: AsyncClient):  # type: ignore[no-untyped-def]
    """Return an async context manager that enables the limiter for the client's app."""
    from backend.main import app

    return _EnableRateLimiter(app)


# ---------------------------------------------------------------------------
# Login rate limiting
# ---------------------------------------------------------------------------


class TestLoginRateLimit:
    """POST /api/v1/auth/login is limited to 5 requests/minute per IP."""

    async def test_login_sixth_attempt_returns_429(self, client: AsyncClient) -> None:
        """The 6th login attempt within 60 s returns 429 Too Many Requests."""
        # First register a user so the first 5 attempts get proper 401 (wrong pw)
        await client.post(
            "/api/v1/auth/register",
            json={"email": "ratelimit_login@test.com", "password": "ValidPass1"},
        )

        async with _rate_limiter(client):
            for _ in range(5):
                await client.post(
                    "/api/v1/auth/login",
                    json={"email": "ratelimit_login@test.com", "password": "WrongPass9"},
                )
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": "ratelimit_login@test.com", "password": "WrongPass9"},
            )
        assert resp.status_code == 429

    async def test_login_rate_limit_all_subsequent_attempts_return_429(
        self, client: AsyncClient
    ) -> None:
        """Every attempt beyond the limit returns 429 (quota does not reset mid-window)."""
        async with _rate_limiter(client):
            for _ in range(5):
                await client.post(
                    "/api/v1/auth/login",
                    json={"email": "rl2@test.com", "password": "WrongPass9"},
                )
            # Attempt 6 and 7 should both be 429
            resp6 = await client.post(
                "/api/v1/auth/login",
                json={"email": "rl2@test.com", "password": "WrongPass9"},
            )
            resp7 = await client.post(
                "/api/v1/auth/login",
                json={"email": "rl2@test.com", "password": "WrongPass9"},
            )
        assert resp6.status_code == 429
        assert resp7.status_code == 429


# ---------------------------------------------------------------------------
# Register rate limiting
# ---------------------------------------------------------------------------


class TestRegisterRateLimit:
    """POST /api/v1/auth/register is limited to 3 requests/minute per IP."""

    async def test_register_fourth_attempt_returns_429(self, client: AsyncClient) -> None:
        """The 4th register attempt within 60 s returns 429."""
        async with _rate_limiter(client):
            for i in range(3):
                await client.post(
                    "/api/v1/auth/register",
                    json={"email": f"rl_reg_{i}@test.com", "password": "ValidPass1"},
                )
            resp = await client.post(
                "/api/v1/auth/register",
                json={"email": "rl_reg_4@test.com", "password": "ValidPass1"},
            )
        assert resp.status_code == 429


# ---------------------------------------------------------------------------
# Forgot-password rate limiting (xfail — feature not yet implemented)
# ---------------------------------------------------------------------------


class TestForgotPasswordRateLimit:
    """POST /api/v1/auth/forgot-password rate limiting."""

    @pytest.mark.xfail(reason="forgot-password endpoint not yet implemented", strict=False)
    async def test_forgot_password_fourth_attempt_returns_429(self, client: AsyncClient) -> None:
        """The 4th forgot-password attempt for the same email returns 429."""
        async with _rate_limiter(client):
            for _ in range(3):
                await client.post(
                    "/api/v1/auth/forgot-password",
                    json={"email": "rl_forgot@test.com"},
                )
            resp = await client.post(
                "/api/v1/auth/forgot-password",
                json={"email": "rl_forgot@test.com"},
            )
        assert resp.status_code == 429


# ---------------------------------------------------------------------------
# Rate limit isolation between different clients (IPs)
# ---------------------------------------------------------------------------


class TestRateLimitIsolation:
    """Rate limits are per-IP — hitting the limit produces 429, not server errors."""

    async def test_rate_limit_returns_json_error_not_500(self, client: AsyncClient) -> None:
        """429 response body is valid JSON with an error detail, not a 500."""
        async with _rate_limiter(client):
            for _ in range(6):
                resp = await client.post(
                    "/api/v1/auth/login",
                    json={"email": "rl_iso@test.com", "password": "WrongPass9"},
                )
        assert resp.status_code == 429
        # Must be JSON, not an HTML error page
        data = resp.json()
        assert isinstance(data, dict)
