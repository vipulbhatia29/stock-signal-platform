"""Tests for OIDC SSO endpoints (Langfuse integration)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient

from backend.config import settings


class _FakeRedis:
    """In-memory fake async Redis for testing OIDC auth code storage."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        """Store a key with TTL (TTL ignored in tests)."""
        self._store[key] = value

    async def getdel(self, key: str) -> str | None:
        """Get and delete a key atomically."""
        return self._store.pop(key, None)

    async def aclose(self) -> None:
        """No-op close."""


# Module-level fake redis instance so data persists across endpoint calls
# within a single test.
_fake_redis = _FakeRedis()


@pytest.fixture(autouse=True)
def _mock_oidc_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the OIDC Redis connection with an in-memory fake."""
    _fake_redis._store.clear()

    async def _get_fake_redis():  # noqa: ANN202
        return _fake_redis

    monkeypatch.setattr(
        "backend.services.oidc_provider._get_async_redis",
        _get_fake_redis,
    )


class TestOIDCDiscovery:
    """Tests for GET /api/v1/auth/.well-known/openid-configuration."""

    async def test_discovery_returns_valid_document(self, client: AsyncClient) -> None:
        """Discovery endpoint returns a well-formed OIDC config."""
        response = await client.get("/api/v1/auth/.well-known/openid-configuration")
        assert response.status_code == 200
        data = response.json()
        assert "issuer" in data
        assert "authorization_endpoint" in data
        assert "token_endpoint" in data
        assert "userinfo_endpoint" in data
        assert data["response_types_supported"] == ["code"]
        assert "openid" in data["scopes_supported"]

    async def test_discovery_urls_use_correct_prefix(self, client: AsyncClient) -> None:
        """Discovery URLs point to the auth router prefix."""
        response = await client.get("/api/v1/auth/.well-known/openid-configuration")
        data = response.json()
        assert "/api/v1/auth/authorize" in data["authorization_endpoint"]
        assert "/api/v1/auth/token" in data["token_endpoint"]
        assert "/api/v1/auth/userinfo" in data["userinfo_endpoint"]


class TestOIDCAuthorize:
    """Tests for GET /api/v1/auth/authorize."""

    async def test_authorize_redirects_with_code(self, authenticated_client: AsyncClient) -> None:
        """Authenticated user gets redirected with an auth code."""
        response = await authenticated_client.get(
            "/api/v1/auth/authorize",
            params={
                "response_type": "code",
                "client_id": settings.OIDC_CLIENT_ID,
                "redirect_uri": "http://localhost:3001/callback",
                "state": "test-state-123",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        location = response.headers["location"]
        parsed = urlparse(location)
        qs = parse_qs(parsed.query)
        assert "code" in qs
        assert qs["state"] == ["test-state-123"]
        assert parsed.scheme == "http"
        assert parsed.netloc == "localhost:3001"

    async def test_authorize_requires_authentication(self, client: AsyncClient) -> None:
        """Unauthenticated request returns 401."""
        response = await client.get(
            "/api/v1/auth/authorize",
            params={
                "response_type": "code",
                "client_id": settings.OIDC_CLIENT_ID,
                "redirect_uri": "http://localhost:3001/callback",
            },
        )
        assert response.status_code == 401

    async def test_authorize_rejects_invalid_client_id(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Invalid client_id returns 400."""
        response = await authenticated_client.get(
            "/api/v1/auth/authorize",
            params={
                "response_type": "code",
                "client_id": "wrong-client",
                "redirect_uri": "http://localhost:3001/callback",
            },
            follow_redirects=False,
        )
        assert response.status_code == 400

    async def test_authorize_rejects_invalid_response_type(
        self, authenticated_client: AsyncClient
    ) -> None:
        """response_type other than 'code' returns 400."""
        response = await authenticated_client.get(
            "/api/v1/auth/authorize",
            params={
                "response_type": "token",
                "client_id": settings.OIDC_CLIENT_ID,
                "redirect_uri": "http://localhost:3001/callback",
            },
            follow_redirects=False,
        )
        assert response.status_code == 400

    async def test_authorize_rejects_missing_redirect_uri(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Missing redirect_uri returns 400."""
        response = await authenticated_client.get(
            "/api/v1/auth/authorize",
            params={
                "response_type": "code",
                "client_id": settings.OIDC_CLIENT_ID,
            },
            follow_redirects=False,
        )
        assert response.status_code == 400


class TestOIDCToken:
    """Tests for POST /api/v1/auth/token."""

    async def _get_auth_code(self, authenticated_client: AsyncClient) -> str:
        """Helper: perform authorize flow and extract the auth code."""
        response = await authenticated_client.get(
            "/api/v1/auth/authorize",
            params={
                "response_type": "code",
                "client_id": settings.OIDC_CLIENT_ID,
                "redirect_uri": "http://localhost:3001/callback",
            },
            follow_redirects=False,
        )
        location = response.headers["location"]
        qs = parse_qs(urlparse(location).query)
        return qs["code"][0]

    async def test_token_exchange_success(self, authenticated_client: AsyncClient) -> None:
        """Valid auth code exchange returns an access token."""
        code = await self._get_auth_code(authenticated_client)
        response = await authenticated_client.post(
            "/api/v1/auth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.OIDC_CLIENT_ID,
                "client_secret": settings.OIDC_CLIENT_SECRET,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "Bearer"
        assert data["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    async def test_token_exchange_invalid_code(self, authenticated_client: AsyncClient) -> None:
        """Invalid auth code returns 400."""
        response = await authenticated_client.post(
            "/api/v1/auth/token",
            data={
                "grant_type": "authorization_code",
                "code": "invalid-code-xyz",
                "client_id": settings.OIDC_CLIENT_ID,
                "client_secret": settings.OIDC_CLIENT_SECRET,
            },
        )
        assert response.status_code == 400

    async def test_token_exchange_code_consumed(self, authenticated_client: AsyncClient) -> None:
        """Auth code can only be used once (consumed on first exchange)."""
        code = await self._get_auth_code(authenticated_client)
        # First exchange succeeds
        response1 = await authenticated_client.post(
            "/api/v1/auth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.OIDC_CLIENT_ID,
                "client_secret": settings.OIDC_CLIENT_SECRET,
            },
        )
        assert response1.status_code == 200

        # Second exchange fails (code consumed)
        response2 = await authenticated_client.post(
            "/api/v1/auth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.OIDC_CLIENT_ID,
                "client_secret": settings.OIDC_CLIENT_SECRET,
            },
        )
        assert response2.status_code == 400

    async def test_token_exchange_invalid_client_secret(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Wrong client secret returns 401."""
        code = await self._get_auth_code(authenticated_client)
        response = await authenticated_client.post(
            "/api/v1/auth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.OIDC_CLIENT_ID,
                "client_secret": "wrong-secret",
            },
        )
        assert response.status_code == 401

    async def test_token_exchange_invalid_grant_type(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Unsupported grant_type returns 400."""
        response = await authenticated_client.post(
            "/api/v1/auth/token",
            data={
                "grant_type": "client_credentials",
                "code": "any",
                "client_id": settings.OIDC_CLIENT_ID,
                "client_secret": settings.OIDC_CLIENT_SECRET,
            },
        )
        assert response.status_code == 400

    async def test_token_exchange_missing_code(self, authenticated_client: AsyncClient) -> None:
        """Missing authorization code returns 400."""
        response = await authenticated_client.post(
            "/api/v1/auth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": settings.OIDC_CLIENT_ID,
                "client_secret": settings.OIDC_CLIENT_SECRET,
            },
        )
        assert response.status_code == 400


class TestOIDCUserinfo:
    """Tests for GET /api/v1/auth/userinfo."""

    async def test_userinfo_returns_profile(self, authenticated_client: AsyncClient) -> None:
        """Authenticated request returns user profile."""
        response = await authenticated_client.get("/api/v1/auth/userinfo")
        assert response.status_code == 200
        data = response.json()
        assert "sub" in data
        assert "email" in data
        assert "name" in data
        assert data["auth_provider"] == "local"

    async def test_userinfo_requires_authentication(self, client: AsyncClient) -> None:
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/auth/userinfo")
        assert response.status_code == 401

    async def test_userinfo_email_matches_user(self, authenticated_client: AsyncClient) -> None:
        """Returned email matches the authenticated user."""
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        response = await authenticated_client.get("/api/v1/auth/userinfo")
        data = response.json()
        assert data["email"] == user.email
        assert data["sub"] == str(user.id)
