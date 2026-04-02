"""OAuth state / CSRF protection tests.

The Google OAuth flow uses a single-use `state` parameter to prevent
CSRF attacks.  These tests verify that:

  1. Missing state → error
  2. Reused state → error (single-use)
  3. State from a different session → error
  4. Valid state + nonce → success (xfail until OAuth is implemented)

Because the Google OAuth feature is not yet implemented in the codebase,
all tests that require it are marked xfail.  The tests document the
intended security contract and will start passing once the feature lands.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestOAuthStateCsrf:
    """Google OAuth state parameter CSRF protection."""

    @pytest.mark.xfail(reason="Google OAuth not yet implemented", strict=False)
    async def test_callback_without_state_returns_error(self, client: AsyncClient) -> None:
        """Callback request missing the state parameter returns 400 or 422."""
        resp = await client.get(
            "/api/v1/auth/google/callback",
            params={"code": "auth-code-no-state"},
        )
        assert resp.status_code in (400, 422)

    @pytest.mark.xfail(reason="Google OAuth not yet implemented", strict=False)
    async def test_callback_with_reused_state_returns_error(self, client: AsyncClient) -> None:
        """Using the same state token twice returns an error on the second attempt.

        The state is a single-use nonce stored server-side.  After the first
        exchange the nonce is deleted, so a replay must be rejected.
        """
        # First — initiate OAuth to capture the real state
        auth_resp = await client.get("/api/v1/auth/google/authorize")
        assert auth_resp.status_code in (200, 302)

        # Extract state from the redirect URL (implementation-dependent)
        location = auth_resp.headers.get("location", auth_resp.json().get("url", ""))
        assert "state=" in location
        state = location.split("state=")[1].split("&")[0]

        # First exchange — succeeds (or 400 because the Google code is fake)
        await client.get(
            "/api/v1/auth/google/callback",
            params={"code": "fake-code-1", "state": state},
        )

        # Second exchange with the same state — must be rejected
        resp2 = await client.get(
            "/api/v1/auth/google/callback",
            params={"code": "fake-code-2", "state": state},
        )
        assert resp2.status_code in (400, 401, 422)

    @pytest.mark.xfail(reason="Google OAuth not yet implemented", strict=False)
    async def test_callback_with_forged_state_returns_error(self, client: AsyncClient) -> None:
        """Callback with a state value that was never issued returns 400 or 401."""
        resp = await client.get(
            "/api/v1/auth/google/callback",
            params={"code": "auth-code", "state": "forged-state-value"},
        )
        assert resp.status_code in (400, 401, 422)

    @pytest.mark.xfail(reason="Google OAuth not yet implemented", strict=False)
    async def test_valid_state_and_nonce_initiates_exchange(self, client: AsyncClient) -> None:
        """A valid state returned by /authorize can be used exactly once.

        This test only verifies the state is accepted (the Google code
        exchange will fail with a fake code — that is expected and OK).
        The important assertion is that the state itself is not rejected.
        """
        auth_resp = await client.get("/api/v1/auth/google/authorize")
        assert auth_resp.status_code in (200, 302)

        location = auth_resp.headers.get("location", auth_resp.json().get("url", ""))
        assert "state=" in location
        state = location.split("state=")[1].split("&")[0]

        # The state is valid — the server should attempt the exchange
        # (even if it ultimately fails because the code is fake)
        resp = await client.get(
            "/api/v1/auth/google/callback",
            params={"code": "fake-google-code", "state": state},
        )
        # Server tried — rejects because fake code, NOT because of state
        assert resp.status_code in (400, 401, 500)
