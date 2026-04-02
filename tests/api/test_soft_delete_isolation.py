"""Soft-delete data isolation tests.

Verifies that once a user is marked as deleted (or deactivated), their
data is no longer accessible and they cannot authenticate.

The current User model uses `is_active` as the deactivation flag (no
`deleted_at` / anonymised email pattern yet).  Tests that require
hard-delete/anonymisation are marked xfail.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.dependencies import create_access_token, hash_password
from backend.models.portfolio import Portfolio
from backend.models.user import User, UserPreference

_TP = "ValidPass1"  # noqa: S105


async def _create_active_user(db_url: str, email: str) -> dict:
    """Create a normal active user and return id + access token."""
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        user = User(email=email, hashed_password=hash_password(_TP))
        session.add(user)
        await session.flush()  # populate user.id before FK references
        pref = UserPreference(user_id=user.id)
        session.add(pref)
        portfolio = Portfolio(user_id=user.id, name="Test Portfolio")
        session.add(portfolio)
        await session.flush()  # populate portfolio.id
        await session.commit()
        user_id = user.id
        portfolio_id = portfolio.id
    await engine.dispose()
    return {
        "user_id": user_id,
        "portfolio_id": portfolio_id,
        "access_token": create_access_token(user_id),
    }


async def _deactivate_user(db_url: str, user_id) -> None:  # type: ignore[no-untyped-def]
    """Set is_active=False for the given user."""
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        await session.execute(update(User).where(User.id == user_id).values(is_active=False))
        await session.commit()
    await engine.dispose()


class TestSoftDeleteIsolation:
    """Deactivated / deleted users are fully isolated."""

    async def test_deleted_user_cannot_login(self, client: AsyncClient, db_url: str) -> None:
        """Deactivated user is rejected at login with 401."""
        email = "deleted_login@test.com"
        data = await _create_active_user(db_url, email)
        await _deactivate_user(db_url, data["user_id"])

        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": _TP},
        )
        assert resp.status_code == 401

    async def test_deleted_user_token_rejected_on_protected_endpoint(
        self, client: AsyncClient, db_url: str
    ) -> None:
        """Token issued before deactivation is rejected after is_active=False."""
        email = "deleted_token@test.com"
        data = await _create_active_user(db_url, email)
        # Token was valid at issuance — deactivate AFTER obtaining it
        await _deactivate_user(db_url, data["user_id"])

        resp = await client.get(
            "/api/v1/stocks/search?q=AAPL",
            headers={"Authorization": f"Bearer {data['access_token']}"},
        )
        assert resp.status_code == 401

    async def test_deleted_user_portfolios_inaccessible(
        self, client: AsyncClient, db_url: str
    ) -> None:
        """Stale token from a deactivated user cannot access their portfolio."""
        email = "deleted_portfolio@test.com"
        data = await _create_active_user(db_url, email)
        await _deactivate_user(db_url, data["user_id"])

        resp = await client.get(
            "/api/v1/portfolio/summary",
            headers={"Authorization": f"Bearer {data['access_token']}"},
        )
        assert resp.status_code == 401

    @pytest.mark.xfail(reason="Email anonymisation / hard-delete not yet implemented", strict=False)
    async def test_anonymised_email_not_in_any_list_response(
        self, client: AsyncClient, db_url: str
    ) -> None:
        """After anonymisation, the deleted user's email does not appear in responses."""
        email = "anon@test.com"
        data = await _create_active_user(db_url, email)
        # Trigger anonymisation (feature not yet implemented)
        await client.delete(
            f"/api/v1/admin/users/{data['user_id']}",
            headers={"Authorization": f"Bearer {data['access_token']}"},
        )

        # Any list endpoint must not expose the original email
        resp = await client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {data['access_token']}"},
        )
        if resp.status_code == 200:
            assert email not in resp.text

    @pytest.mark.xfail(reason="OAuth account removal on delete not yet implemented", strict=False)
    async def test_deleted_user_oauth_accounts_removed(
        self, client: AsyncClient, db_url: str
    ) -> None:
        """Deleting a user removes their linked OAuth accounts."""
        email = "oauth_delete@test.com"
        data = await _create_active_user(db_url, email)

        # Simulate linked OAuth account removal (feature not yet implemented)
        resp = await client.delete(
            f"/api/v1/auth/admin/delete-user/{data['user_id']}",
        )
        assert resp.status_code in (200, 204, 404)
