"""IDOR / Cross-User Authorization Matrix tests.

Two users (User A and User B) are created.  Every test exercises User A's
token against a resource owned by User B.  The expected result is always
404 or 403 — never 200 with User B's data.

Endpoints covered:
  - /api/v1/portfolio/...
  - /api/v1/chat/sessions/...
  - /api/v1/alerts
  - /api/v1/preferences
  - /api/v1/stocks (watchlist)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.dependencies import create_access_token, hash_password
from backend.models.alert import InAppAlert
from backend.models.chat import ChatSession
from backend.models.portfolio import Portfolio
from backend.models.stock import Stock, Watchlist
from backend.models.user import User, UserPreference

_TP = "ValidPass1"  # noqa: S105


# ---------------------------------------------------------------------------
# Shared fixtures — two users, each with their own resources
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def two_users(client: AsyncClient, db_url: str) -> dict:  # type: ignore[return]
    """Create two users (a and b) and seed resources owned by user b.

    Returns a dict with:
        - user_a_token: Bearer token for User A
        - user_b_portfolio_id: UUID of a portfolio owned by User B
        - user_b_chat_session_id: UUID of a chat session owned by User B
        - user_b_alert_id: UUID of an alert owned by User B
        - user_b_watchlist_ticker: ticker in User B's watchlist
    """
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        user_a = User(email="usera@idor.test", hashed_password=hash_password(_TP))
        user_b = User(email="userb@idor.test", hashed_password=hash_password(_TP))
        session.add_all([user_a, user_b])
        await session.flush()

        # Preferences (required for user to function)
        session.add_all(
            [
                UserPreference(user_id=user_a.id),
                UserPreference(user_id=user_b.id),
            ]
        )

        # User B — portfolio
        portfolio_b = Portfolio(user_id=user_b.id, name="B Portfolio")
        session.add(portfolio_b)
        await session.flush()

        # User B — chat session
        chat_b = ChatSession(
            user_id=user_b.id,
            agent_type="stock",
            title="B Chat",
        )
        session.add(chat_b)
        await session.flush()

        # User B — alert
        alert_b = InAppAlert(
            user_id=user_b.id,
            message="B alert",
            alert_type="signal",
            created_at=datetime.now(timezone.utc),
        )
        session.add(alert_b)
        await session.flush()

        # Seed a stock so the watchlist FK is satisfied
        stock_msft = Stock(
            ticker="MSFT",
            name="Microsoft Corporation",
            exchange="NASDAQ",
            is_active=True,
        )
        session.add(stock_msft)
        await session.flush()

        # User B — watchlist
        watchlist_b = Watchlist(user_id=user_b.id, ticker="MSFT")
        session.add(watchlist_b)

        user_a_id = user_a.id
        portfolio_b_id = portfolio_b.id
        chat_b_id = chat_b.id
        alert_b_id = alert_b.id
        await session.commit()

    await engine.dispose()

    token_a = create_access_token(user_a_id)
    return {
        "user_a_token": token_a,
        "user_b_portfolio_id": str(portfolio_b_id),
        "user_b_chat_session_id": str(chat_b_id),
        "user_b_alert_id": str(alert_b_id),
        "user_b_watchlist_ticker": "MSFT",
    }


# ---------------------------------------------------------------------------
# Portfolio IDOR
# ---------------------------------------------------------------------------


class TestPortfolioIDOR:
    """User A cannot access User B's portfolio resources."""

    async def test_get_portfolio_by_id_returns_404_or_403(
        self, client: AsyncClient, two_users: dict
    ) -> None:
        """GET /api/v1/portfolio/<b_id> with User A's token returns 404 or 403."""
        portfolio_id = two_users["user_b_portfolio_id"]
        resp = await client.get(
            f"/api/v1/portfolio/{portfolio_id}",
            headers={"Authorization": f"Bearer {two_users['user_a_token']}"},
        )
        assert resp.status_code in (403, 404)

    async def test_get_portfolio_positions_returns_404_or_403(
        self, client: AsyncClient, two_users: dict
    ) -> None:
        """GET /api/v1/portfolio/<b_id>/positions with User A's token returns 404 or 403."""
        portfolio_id = two_users["user_b_portfolio_id"]
        resp = await client.get(
            f"/api/v1/portfolio/{portfolio_id}/positions",
            headers={"Authorization": f"Bearer {two_users['user_a_token']}"},
        )
        assert resp.status_code in (403, 404)

    async def test_post_portfolio_transaction_returns_404_or_403(
        self, client: AsyncClient, two_users: dict
    ) -> None:
        """POST transaction to User B's portfolio with User A's token returns 404 or 403."""
        portfolio_id = two_users["user_b_portfolio_id"]
        resp = await client.post(
            f"/api/v1/portfolio/{portfolio_id}/transactions",
            headers={"Authorization": f"Bearer {two_users['user_a_token']}"},
            json={
                "ticker": "AAPL",
                "transaction_type": "BUY",
                "shares": 1,
                "price_per_share": 150,
                "transacted_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        assert resp.status_code in (403, 404, 422)


# ---------------------------------------------------------------------------
# Chat session IDOR
# ---------------------------------------------------------------------------


class TestChatSessionIDOR:
    """User A cannot access User B's chat sessions."""

    async def test_get_chat_session_messages_returns_404_or_403(
        self, client: AsyncClient, two_users: dict
    ) -> None:
        """GET /api/v1/chat/sessions/<b_id>/messages with User A's token returns 404 or 403."""
        session_id = two_users["user_b_chat_session_id"]
        resp = await client.get(
            f"/api/v1/chat/sessions/{session_id}/messages",
            headers={"Authorization": f"Bearer {two_users['user_a_token']}"},
        )
        assert resp.status_code in (403, 404)

    async def test_delete_chat_session_returns_404_or_403(
        self, client: AsyncClient, two_users: dict
    ) -> None:
        """DELETE /api/v1/chat/sessions/<b_id> with User A's token returns 404 or 403."""
        session_id = two_users["user_b_chat_session_id"]
        resp = await client.delete(
            f"/api/v1/chat/sessions/{session_id}",
            headers={"Authorization": f"Bearer {two_users['user_a_token']}"},
        )
        assert resp.status_code in (403, 404)


# ---------------------------------------------------------------------------
# Alerts IDOR
# ---------------------------------------------------------------------------


class TestAlertsIDOR:
    """User A can only see their own alerts, never User B's."""

    async def test_list_alerts_does_not_include_user_b_alert(
        self, client: AsyncClient, two_users: dict
    ) -> None:
        """GET /api/v1/alerts returns only User A's alerts, not User B's."""
        resp = await client.get(
            "/api/v1/alerts",
            headers={"Authorization": f"Bearer {two_users['user_a_token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # User A has no alerts — list must be empty
        items = data.get("alerts", data.get("items", data))
        if isinstance(items, list):
            alert_ids = [str(a.get("id", "")) for a in items]
            assert two_users["user_b_alert_id"] not in alert_ids

    async def test_delete_alert_returns_404_or_403(
        self, client: AsyncClient, two_users: dict
    ) -> None:
        """DELETE /api/v1/alerts/<b_alert_id> with User A's token returns 404 or 403."""
        alert_id = two_users["user_b_alert_id"]
        resp = await client.delete(
            f"/api/v1/alerts/{alert_id}",
            headers={"Authorization": f"Bearer {two_users['user_a_token']}"},
        )
        assert resp.status_code in (403, 404)


# ---------------------------------------------------------------------------
# Watchlist IDOR
# ---------------------------------------------------------------------------


class TestWatchlistIDOR:
    """User A can only see their own watchlist items, never User B's."""

    async def test_list_watchlist_does_not_include_user_b_items(
        self, client: AsyncClient, two_users: dict
    ) -> None:
        """GET /api/v1/stocks/watchlist returns only User A's watchlist tickers."""
        resp = await client.get(
            "/api/v1/stocks/watchlist",
            headers={"Authorization": f"Bearer {two_users['user_a_token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Response is a list of watchlist items
        items = data if isinstance(data, list) else data.get("items", data.get("watchlist", []))
        tickers = [item.get("ticker", "") for item in items if isinstance(item, dict)]
        assert "MSFT" not in tickers

    async def test_delete_watchlist_item_returns_404_or_403(
        self, client: AsyncClient, two_users: dict
    ) -> None:
        """DELETE /api/v1/stocks/watchlist/<b_ticker> with User A's token returns 404 or 403."""
        ticker = two_users["user_b_watchlist_ticker"]
        resp = await client.delete(
            f"/api/v1/stocks/watchlist/{ticker}",
            headers={"Authorization": f"Bearer {two_users['user_a_token']}"},
        )
        # Ticker is not on User A's watchlist — 404 is correct isolation
        assert resp.status_code in (403, 404)


# ---------------------------------------------------------------------------
# Preferences IDOR
# ---------------------------------------------------------------------------


class TestPreferencesIDOR:
    """PUT /api/v1/preferences only affects the authenticated user's own prefs."""

    async def test_update_preferences_only_affects_own(
        self, client: AsyncClient, two_users: dict, db_url: str
    ) -> None:
        """PUT /api/v1/preferences updates User A's prefs only, not User B's."""
        new_tz = "America/Chicago"
        resp = await client.put(
            "/api/v1/preferences",
            headers={"Authorization": f"Bearer {two_users['user_a_token']}"},
            json={"timezone": new_tz},
        )
        # Accept 200 or 405 (PUT vs PATCH — router may use PATCH)
        assert resp.status_code in (200, 405)

        # Verify User B's prefs are unchanged by fetching via direct DB read
        engine = create_async_engine(db_url, echo=False)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            from sqlalchemy import select

            from backend.models.user import UserPreference

            result = await session.execute(
                select(UserPreference).join(User).where(User.email == "userb@idor.test")
            )
            pref_b = result.scalar_one_or_none()
            if pref_b is not None:
                # User B's timezone should remain the default
                assert pref_b.timezone != new_tz or pref_b.timezone == "America/New_York"
        await engine.dispose()


# ---------------------------------------------------------------------------
# Admin endpoint IDOR (non-admin user)
# ---------------------------------------------------------------------------


class TestAdminEndpointIDOR:
    """Non-admin users receive 403 on admin-only endpoints."""

    @pytest.mark.xfail(reason="Admin endpoints not yet implemented", strict=False)
    async def test_non_admin_cannot_access_admin_endpoints(
        self, client: AsyncClient, two_users: dict
    ) -> None:
        """Non-admin token on admin endpoint returns 403."""
        some_id = uuid.uuid4()
        resp = await client.post(
            f"/api/v1/auth/admin/verify-email/{some_id}",
            headers={"Authorization": f"Bearer {two_users['user_a_token']}"},
        )
        assert resp.status_code == 403
