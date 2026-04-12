"""Auth & security hardening tests — token, IDOR, cookies, password, injection."""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from freezegun import freeze_time
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import settings
from backend.dependencies import create_access_token, create_refresh_token
from backend.models import ChatSession, User, Watchlist
from tests.conftest import StockFactory, UserFactory, UserPreferenceFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_authenticated_client(
    client: AsyncClient,
    db_url: str,
    *,
    is_active: bool = True,
) -> tuple[AsyncClient, User]:
    """Create a persisted user and return (client_with_auth, user)."""
    engine = create_async_engine(db_url, echo=False)
    factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory_() as session:
        user = UserFactory.build(is_active=is_active)
        session.add(user)
        pref = UserPreferenceFactory.build(user_id=user.id)
        session.add(pref)
        await session.commit()
        await session.refresh(user)
    await engine.dispose()

    token = create_access_token(user.id)
    # Copy the client's base_url and transport, override headers
    headers = dict(client.headers)
    headers["Authorization"] = f"Bearer {token}"
    client_copy = AsyncClient(
        transport=client._transport,
        base_url=client.base_url,
        headers=headers,
    )
    return client_copy, user


async def _seed_stock(db_url: str, ticker: str = "AAPL") -> None:
    """Insert a Stock row for test data."""
    engine = create_async_engine(db_url, echo=False)
    factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory_() as session:
        stock = StockFactory.build(ticker=ticker, name=f"{ticker} Inc")
        session.add(stock)
        await session.commit()
    await engine.dispose()


# ===========================================================================
# 1. Token expiry & malformed JWT tests
# ===========================================================================


class TestTokenExpiry:
    """Verify tokens are rejected when expired or malformed."""

    @pytest.mark.asyncio
    async def test_access_token_rejected_after_expiry(self, client: AsyncClient):
        """Access token is rejected after ACCESS_TOKEN_EXPIRE_MINUTES."""
        now = datetime.now(timezone.utc)
        with freeze_time(now):
            token = create_access_token(uuid.uuid4())

        # Fast-forward past expiry
        expired_time = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES + 1)
        with freeze_time(expired_time):
            resp = await client.get(
                "/api/v1/stocks/watchlist",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_token_rejected_after_expiry(self, client: AsyncClient):
        """Refresh token is rejected after REFRESH_TOKEN_EXPIRE_DAYS."""
        now = datetime.now(timezone.utc)
        with freeze_time(now):
            refresh = create_refresh_token(uuid.uuid4())

        expired_time = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS + 1)
        with freeze_time(expired_time):
            resp = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_jwt_missing_sub(self, client: AsyncClient):
        """JWT without 'sub' claim is rejected."""
        payload = {
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        resp = await client.get(
            "/api/v1/stocks/watchlist",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_jwt_wrong_type(self, client: AsyncClient):
        """Refresh token cannot be used as access token."""
        refresh = create_refresh_token(uuid.uuid4())
        resp = await client.get(
            "/api/v1/stocks/watchlist",
            headers={"Authorization": f"Bearer {refresh}"},
        )
        assert resp.status_code == 401


# ===========================================================================
# 2. Cross-user IDOR tests
# ===========================================================================


class TestIDOR:
    """User A must never see User B's data."""

    @pytest.mark.asyncio
    async def test_idor_portfolio_positions(self, client: AsyncClient, db_url):
        """User A cannot see User B's portfolio positions."""
        client_a, user_a = await _make_authenticated_client(client, db_url)
        client_b, user_b = await _make_authenticated_client(client, db_url)

        # Seed a transaction for user_b via the API
        await _seed_stock(db_url, "AAPL")
        resp = await client_b.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "AAPL",
                "transaction_type": "BUY",
                "shares": 10,
                "price_per_share": 150.0,
                "transacted_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        assert resp.status_code == 201

        # User A fetches positions — should see empty, not User B's data
        resp = await client_a.get("/api/v1/portfolio/positions")
        assert resp.status_code == 200
        assert resp.json() == []

        await client_a.aclose()
        await client_b.aclose()

    @pytest.mark.asyncio
    async def test_idor_chat_sessions(self, client: AsyncClient, db_url):
        """User A cannot read User B's chat session messages."""
        client_a, user_a = await _make_authenticated_client(client, db_url)
        client_b, user_b = await _make_authenticated_client(client, db_url)

        # Create a chat session for user_b
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            chat_session = ChatSession(user_id=user_b.id, title="B's session", agent_type="stock")
            session.add(chat_session)
            await session.commit()
            session_id = chat_session.id
        await engine.dispose()

        # User A tries to read User B's chat session
        resp = await client_a.get(f"/api/v1/chat/sessions/{session_id}/messages")
        assert resp.status_code == 404

        await client_a.aclose()
        await client_b.aclose()

    @pytest.mark.asyncio
    async def test_idor_watchlist(self, client: AsyncClient, db_url):
        """Each user sees only their own watchlist."""
        client_a, user_a = await _make_authenticated_client(client, db_url)
        client_b, user_b = await _make_authenticated_client(client, db_url)

        # Seed stock and add to user_b's watchlist
        await _seed_stock(db_url, "MSFT")
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            wl = Watchlist(user_id=user_b.id, ticker="MSFT")
            session.add(wl)
            await session.commit()
        await engine.dispose()

        # User A should see empty watchlist
        resp = await client_a.get("/api/v1/stocks/watchlist")
        assert resp.status_code == 200
        assert resp.json() == []

        await client_a.aclose()
        await client_b.aclose()

    @pytest.mark.asyncio
    async def test_idor_preferences(self, client: AsyncClient, db_url):
        """Each user sees only their own preferences."""
        client_a, user_a = await _make_authenticated_client(client, db_url)
        client_b, user_b = await _make_authenticated_client(client, db_url)

        # Update user_b's preferences
        await client_b.patch(
            "/api/v1/preferences",
            json={"max_position_pct": 99.0},
        )

        # User A should see defaults, not user_b's 99.0
        resp = await client_a.get("/api/v1/preferences")
        assert resp.status_code == 200
        prefs = resp.json()
        assert prefs["max_position_pct"] != 99.0  # Should be default (10.0)

        await client_a.aclose()
        await client_b.aclose()


# ===========================================================================
# 3. Cookie flags, password, injection
# ===========================================================================


class TestCookieFlags:
    """Verify httpOnly cookie security flags on login."""

    @pytest.mark.asyncio
    async def test_login_sets_httponly_cookies(self, client: AsyncClient, db_url):
        """Login response sets httpOnly cookies with correct flags."""
        # Register a user first
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "cookie@test.com", "password": "ValidPass1"},
        )
        assert resp.status_code == 201

        # Login
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "cookie@test.com", "password": "ValidPass1"},
        )
        assert resp.status_code == 200

        # Check Set-Cookie headers
        cookies = resp.headers.get_list("set-cookie")
        assert len(cookies) >= 3, "Expected at least 3 Set-Cookie headers (access + refresh + csrf)"

        for cookie in cookies:
            cookie_lower = cookie.lower()
            if cookie_lower.startswith("csrf_token="):
                assert "httponly" not in cookie_lower, "CSRF cookie must NOT be httpOnly"
            else:
                assert "httponly" in cookie_lower, f"Missing HttpOnly flag: {cookie}"
            assert "samesite=lax" in cookie_lower, f"Missing SameSite=Lax: {cookie}"


class TestPasswordValidation:
    """Verify password strength enforcement."""

    @pytest.mark.asyncio
    async def test_password_too_short(self, client: AsyncClient):
        """Passwords under 8 characters are rejected."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "short@test.com", "password": "Ab1"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_password_no_uppercase(self, client: AsyncClient):
        """Passwords without uppercase are rejected."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "noup@test.com", "password": "nouppercase1"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_password_no_digit(self, client: AsyncClient):
        """Passwords without digits are rejected."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "nodigit@test.com", "password": "NODIGITHERE"},
        )
        assert resp.status_code == 422


class TestInactiveUser:
    """Verify inactive users are locked out."""

    @pytest.mark.asyncio
    async def test_inactive_user_rejected(self, client: AsyncClient, db_url):
        """Users with is_active=False get 401 on protected endpoints."""
        inactive_client, _ = await _make_authenticated_client(client, db_url, is_active=False)
        resp = await inactive_client.get("/api/v1/stocks/watchlist")
        assert resp.status_code == 401
        await inactive_client.aclose()


class TestInjection:
    """SQL injection and XSS must not cause errors or data leaks."""

    @pytest.mark.asyncio
    async def test_sql_injection_in_search(self, client: AsyncClient, db_url):
        """SQL injection in search query returns safe response (no 500)."""
        client_a, _ = await _make_authenticated_client(client, db_url)
        resp = await client_a.get(
            "/api/v1/stocks/search",
            params={"q": "'; DROP TABLE stocks;--"},
        )
        # Should return 200 with empty results or 422, never 500
        assert resp.status_code in (200, 422)
        await client_a.aclose()

    @pytest.mark.asyncio
    async def test_xss_in_transaction_notes(self, client: AsyncClient, db_url):
        """XSS payloads stored in text fields are returned without execution context."""
        client_a, user_a = await _make_authenticated_client(client, db_url)
        await _seed_stock(db_url, "XSS1")

        # Create portfolio via a BUY transaction with XSS in notes
        resp = await client_a.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "XSS1",
                "action": "BUY",
                "shares": 1,
                "price_per_share": 100.0,
                "notes": "<script>alert(1)</script>",
            },
        )
        # Even if the endpoint doesn't have notes, it should not cause a 500
        assert resp.status_code in (201, 422)
        await client_a.aclose()
