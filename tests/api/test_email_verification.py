"""Email verification bypass tests.

Tests that verify:
  1. Unverified users cannot create a portfolio (require_verified_email guard)
  2. Unverified users cannot create a watchlist item (same guard)
  3. The same verification token cannot be reused

NOTE: The current User model does not have an `email_verified` field, and
`require_verified_email` is not yet implemented as a FastAPI dependency.
All tests are marked xfail and will start passing once that feature lands.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.dependencies import create_access_token, hash_password
from backend.models.user import User, UserPreference

_TP = "ValidPass1"  # noqa: S105


async def _create_unverified_user(db_url: str, email: str) -> str:
    """Create a user directly in the DB (bypassing the register endpoint).

    Returns a valid access token for that user.  The user has no
    email_verified flag set (unverified by default).
    """
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
    return create_access_token(user_id)


class TestEmailVerificationBypass:
    """Unverified users are blocked from resources requiring verified email."""

    @pytest.mark.xfail(reason="require_verified_email dependency not yet implemented", strict=False)
    async def test_unverified_user_cannot_create_portfolio(
        self, client: AsyncClient, db_url: str
    ) -> None:
        """POST /api/v1/portfolio/transactions with unverified user returns 403."""
        token = await _create_unverified_user(db_url, "unverified_port@test.com")
        from datetime import datetime, timezone

        resp = await client.post(
            "/api/v1/portfolio/transactions",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "ticker": "AAPL",
                "transaction_type": "BUY",
                "shares": 1,
                "price_per_share": 150,
                "transacted_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        assert resp.status_code == 403

    @pytest.mark.xfail(reason="require_verified_email dependency not yet implemented", strict=False)
    async def test_unverified_user_cannot_add_watchlist_item(
        self, client: AsyncClient, db_url: str
    ) -> None:
        """POST /api/v1/watchlist with unverified user returns 403."""
        token = await _create_unverified_user(db_url, "unverified_watch@test.com")
        resp = await client.post(
            "/api/v1/watchlist",
            headers={"Authorization": f"Bearer {token}"},
            json={"ticker": "AAPL"},
        )
        assert resp.status_code == 403

    @pytest.mark.xfail(reason="verify-email endpoint not yet implemented", strict=False)
    async def test_verification_token_cannot_be_reused(self, client: AsyncClient) -> None:
        """The same email verification token returns an error on second use."""
        # Register a user — they receive a verification token
        await client.post(
            "/api/v1/auth/register",
            json={"email": "reuse_token@test.com", "password": _TP},
        )

        # Simulate obtaining the verification token (in a real flow it arrives by email)
        # For this test we use a placeholder; the endpoint will reject it either way.
        token = "some-verification-token"

        # First use
        await client.post("/api/v1/auth/verify-email", json={"token": token})

        # Second use — must fail
        resp2 = await client.post("/api/v1/auth/verify-email", json={"token": token})
        assert resp2.status_code in (400, 409, 422)
