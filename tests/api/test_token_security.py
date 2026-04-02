"""Token security tests.

Covers:
- Tampered JWT rejected
- Expired access token rejected
- JWT without `iat` claim — allowed (current impl does not require iat)
- JWT with wrong type rejected
- Revoked token handling (mocked Redis blocklist)
- Refresh token rotation

NOTE: The current implementation does not use a Redis token blocklist
(no token_blocklist module exists).  Tests that require blocklist behaviour
are marked xfail and will start passing once that feature is implemented.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import settings
from backend.dependencies import create_access_token, create_refresh_token, hash_password
from backend.models.user import User, UserPreference

_TP = "ValidPass1"  # noqa: S105


# ---------------------------------------------------------------------------
# Helper to create a registered+logged-in user and return tokens
# ---------------------------------------------------------------------------


async def _setup_user(client: AsyncClient, db_url: str, email: str) -> dict:
    """Create a user directly in the DB and return a fresh token pair."""
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        user = User(email=email, hashed_password=hash_password(_TP))
        session.add(user)
        await session.flush()  # populate user.id before FK reference
        pref = UserPreference(user_id=user.id)
        session.add(pref)
        await session.commit()
        user_id = user.id
    await engine.dispose()
    return {
        "user_id": user_id,
        "access_token": create_access_token(user_id),
        "refresh_token": create_refresh_token(user_id),
    }


def _protected_endpoint() -> str:
    """Return a lightweight protected endpoint path for token validation checks."""
    return "/api/v1/stocks/search?q=AAPL"


# ---------------------------------------------------------------------------
# JWT structural validation
# ---------------------------------------------------------------------------


class TestJWTStructuralValidation:
    """The server rejects JWTs that fail structural or signature checks."""

    async def test_tampered_jwt_returns_401(self, client: AsyncClient, db_url: str) -> None:
        """JWT with a modified payload (bad signature) returns 401."""
        data = await _setup_user(client, db_url, "tamper_tok@test.com")
        tampered = data["access_token"] + "X"
        resp = await client.get(
            _protected_endpoint(),
            headers={"Authorization": f"Bearer {tampered}"},
        )
        assert resp.status_code == 401

    async def test_expired_access_token_returns_401(self, client: AsyncClient) -> None:
        """Expired access token returns 401 on a protected endpoint."""
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        expired = jwt.encode(
            {"sub": str(uuid.uuid4()), "exp": past, "type": "access"},
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        resp = await client.get(
            _protected_endpoint(),
            headers={"Authorization": f"Bearer {expired}"},
        )
        assert resp.status_code == 401

    async def test_wrong_token_type_access_with_refresh_returns_401(
        self, client: AsyncClient, db_url: str
    ) -> None:
        """Using a refresh token as an access token returns 401."""
        data = await _setup_user(client, db_url, "wrong_type@test.com")
        resp = await client.get(
            _protected_endpoint(),
            headers={"Authorization": f"Bearer {data['refresh_token']}"},
        )
        assert resp.status_code == 401

    async def test_garbage_token_returns_401(self, client: AsyncClient) -> None:
        """Completely invalid token string returns 401."""
        resp = await client.get(
            _protected_endpoint(),
            headers={"Authorization": "Bearer not.a.jwt"},
        )
        assert resp.status_code == 401

    async def test_no_token_returns_401(self, client: AsyncClient) -> None:
        """Missing Authorization header returns 401."""
        resp = await client.get(_protected_endpoint())
        assert resp.status_code == 401

    async def test_jwt_without_iat_claim_accepted(self, client: AsyncClient, db_url: str) -> None:
        """JWT without iat claim is accepted (current impl does not require iat)."""
        data = await _setup_user(client, db_url, "no_iat@test.com")
        expire = datetime.now(timezone.utc) + timedelta(minutes=30)
        token_no_iat = jwt.encode(
            {"sub": str(data["user_id"]), "exp": expire, "type": "access"},
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        resp = await client.get(
            _protected_endpoint(),
            headers={"Authorization": f"Bearer {token_no_iat}"},
        )
        # Current impl does not enforce iat — 200 expected
        assert resp.status_code == 200

    async def test_jwt_signed_with_wrong_key_returns_401(self, client: AsyncClient) -> None:
        """JWT signed with a different secret key returns 401."""
        # Use a hardcoded key that is guaranteed to differ from any real secret.
        # Reversing the real key is unsafe (palindromes would match).
        WRONG_JWT_SECRET = "definitely-not-the-real-secret-key-for-testing"  # noqa: S105  # nosemgrep
        wrong_key = WRONG_JWT_SECRET
        expire = datetime.now(timezone.utc) + timedelta(minutes=30)
        bad_token = jwt.encode(  # nosemgrep
            {"sub": str(uuid.uuid4()), "exp": expire, "type": "access"},
            wrong_key,
            algorithm=settings.JWT_ALGORITHM,
        )
        resp = await client.get(
            _protected_endpoint(),
            headers={"Authorization": f"Bearer {bad_token}"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Refresh token rotation
# ---------------------------------------------------------------------------


class TestRefreshTokenRotation:
    """Verify that refresh token rotation works correctly."""

    async def test_refresh_returns_new_tokens(self, client: AsyncClient, db_url: str) -> None:
        """A valid refresh produces new access and refresh tokens."""
        data = await _setup_user(client, db_url, "rotation@test.com")
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": data["refresh_token"]},
        )
        assert resp.status_code == 200
        new_tokens = resp.json()
        assert "access_token" in new_tokens
        assert "refresh_token" in new_tokens

    async def test_new_access_token_is_valid(self, client: AsyncClient, db_url: str) -> None:
        """New access token from refresh can authenticate subsequent requests."""
        data = await _setup_user(client, db_url, "rotation2@test.com")
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": data["refresh_token"]},
        )
        assert resp.status_code == 200
        new_access = resp.json()["access_token"]
        protected = await client.get(
            _protected_endpoint(),
            headers={"Authorization": f"Bearer {new_access}"},
        )
        assert protected.status_code == 200


# ---------------------------------------------------------------------------
# Blocklist tests (xfail until blocklist is implemented)
# ---------------------------------------------------------------------------


class TestTokenBlocklist:
    """Token blocklist behaviour — fail-closed security requirements.

    These tests are xfail because the backend does not yet have a Redis
    token blocklist.  They document the intended security contract.
    """

    @pytest.mark.xfail(reason="Token blocklist not yet implemented", strict=False)
    async def test_revoked_token_redis_up_returns_401(
        self, client: AsyncClient, db_url: str
    ) -> None:
        """Revoked token with Redis available returns 401 (blocklist enforced)."""
        data = await _setup_user(client, db_url, "revoked@test.com")
        # Simulate revocation by blocklisting the token
        with patch("backend.services.token_blocklist.is_token_revoked", return_value=True):
            resp = await client.get(
                _protected_endpoint(),
                headers={"Authorization": f"Bearer {data['access_token']}"},
            )
        assert resp.status_code == 401

    @pytest.mark.xfail(reason="Token blocklist not yet implemented", strict=False)
    async def test_revoked_token_redis_down_on_refresh_rejected(
        self, client: AsyncClient, db_url: str
    ) -> None:
        """Refresh endpoint rejects tokens when Redis is unavailable (fail-closed)."""
        data = await _setup_user(client, db_url, "redis_down_refresh@test.com")
        import redis.asyncio as aioredis

        with patch.object(
            aioredis.Redis,
            "get",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Redis down"),
        ):
            resp = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": data["refresh_token"]},
            )
        assert resp.status_code == 401

    @pytest.mark.xfail(reason="Token blocklist not yet implemented", strict=False)
    async def test_logout_redis_down_returns_success_known_limitation(
        self, client: AsyncClient, db_url: str
    ) -> None:
        """Logout succeeds even when Redis is down (known limitation: token stays valid)."""
        data = await _setup_user(client, db_url, "logout_redis_down@test.com")
        import redis.asyncio as aioredis

        with patch.object(
            aioredis.Redis,
            "set",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Redis down"),
        ):
            resp = await client.post(
                "/api/v1/auth/logout",
                headers={"Authorization": f"Bearer {data['access_token']}"},
            )
        # Logout itself succeeds — token may still be usable (known limitation)
        assert resp.status_code == 204
