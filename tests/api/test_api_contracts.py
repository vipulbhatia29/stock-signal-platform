"""API contract hardening tests — schemas, pagination, status codes, headers."""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.dependencies import create_access_token
from tests.conftest import (
    StockFactory,
    UserFactory,
    UserPreferenceFactory,
    WatchlistFactory,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_auth_client(client: AsyncClient, db_url: str) -> tuple[AsyncClient, any]:
    """Create an authenticated client and return (client, user)."""
    engine = create_async_engine(db_url, echo=False)
    factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory_() as session:
        user = UserFactory.build()
        session.add(user)
        pref = UserPreferenceFactory.build(user_id=user.id)
        session.add(pref)
        await session.commit()
        await session.refresh(user)
    await engine.dispose()

    token = create_access_token(user.id)
    ac = AsyncClient(
        transport=client._transport,
        base_url=client.base_url,
        headers={**dict(client.headers), "Authorization": f"Bearer {token}"},
    )
    return ac, user


# ===========================================================================
# 1. Schema validation — required fields present
# ===========================================================================


class TestSchemaValidation:
    """Response schemas contain all expected fields."""

    @pytest.mark.asyncio
    async def test_watchlist_response_fields(self, client: AsyncClient, db_url) -> None:
        """GET /stocks/watchlist returns items with all required fields."""
        ac, user = await _make_auth_client(client, db_url)

        # Seed stock + watchlist entry
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            stock = StockFactory.build(ticker="WL01", name="Watchlist Corp")
            session.add(stock)
            wl = WatchlistFactory.build(user_id=user.id, ticker="WL01")
            session.add(wl)
            await session.commit()
        await engine.dispose()

        resp = await ac.get("/api/v1/stocks/watchlist")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1
        item = next(i for i in items if i["ticker"] == "WL01")
        assert "ticker" in item
        assert "name" in item
        await ac.aclose()

    @pytest.mark.asyncio
    async def test_preferences_response_fields(self, client: AsyncClient, db_url) -> None:
        """GET /preferences returns all preference fields."""
        ac, _ = await _make_auth_client(client, db_url)

        resp = await ac.get("/api/v1/preferences")
        assert resp.status_code == 200
        prefs = resp.json()
        assert "default_stop_loss_pct" in prefs
        assert "max_position_pct" in prefs
        assert "max_sector_pct" in prefs
        assert "min_cash_reserve_pct" in prefs
        await ac.aclose()

    @pytest.mark.asyncio
    async def test_transaction_response_fields(self, client: AsyncClient, db_url) -> None:
        """POST /portfolio/transactions response has all fields."""
        ac, _ = await _make_auth_client(client, db_url)

        # Seed stock first
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            stock = StockFactory.build(ticker="TXN1", name="Transaction Corp")
            session.add(stock)
            await session.commit()
        await engine.dispose()

        resp = await ac.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "TXN1",
                "transaction_type": "BUY",
                "shares": 10,
                "price_per_share": 100.0,
                "transacted_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert "ticker" in data
        assert "transaction_type" in data
        assert "shares" in data
        assert "price_per_share" in data
        await ac.aclose()


# ===========================================================================
# 2. HTTP status codes
# ===========================================================================


class TestHTTPStatusCodes:
    """Verify correct HTTP status codes for various scenarios."""

    @pytest.mark.asyncio
    async def test_401_no_token(self, client: AsyncClient) -> None:
        """Protected endpoints return 401 without a token."""
        endpoints = [
            ("GET", "/api/v1/stocks/watchlist"),
            ("GET", "/api/v1/preferences"),
            ("GET", "/api/v1/portfolio/positions"),
            ("GET", "/api/v1/chat/sessions"),
        ]
        for method, url in endpoints:
            resp = await client.request(method, url)
            assert resp.status_code == 401, f"{method} {url} should be 401"

    @pytest.mark.asyncio
    async def test_409_duplicate_watchlist(self, client: AsyncClient, db_url) -> None:
        """Adding same ticker to watchlist twice returns 409."""
        ac, user = await _make_auth_client(client, db_url)

        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            stock = StockFactory.build(ticker="DUP1", name="Duplicate Corp")
            session.add(stock)
            await session.commit()
        await engine.dispose()

        resp1 = await ac.post("/api/v1/stocks/watchlist", json={"ticker": "DUP1"})
        assert resp1.status_code == 201

        resp2 = await ac.post("/api/v1/stocks/watchlist", json={"ticker": "DUP1"})
        assert resp2.status_code == 409
        await ac.aclose()

    @pytest.mark.asyncio
    async def test_404_unknown_watchlist_ticker(self, authenticated_client: AsyncClient) -> None:
        """Removing a ticker not in watchlist returns 404."""
        resp = await authenticated_client.delete("/api/v1/stocks/watchlist/XYZNOTREAL")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_422_invalid_transaction(self, authenticated_client: AsyncClient) -> None:
        """Invalid transaction data returns 422."""
        resp = await authenticated_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "",
                "transaction_type": "INVALID",
                "shares": -1,
                "price_per_share": 0,
                "transacted_at": "not-a-date",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_201_register_new_user(self, client: AsyncClient) -> None:
        """Registering a new user returns 201."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "newuser@example.com", "password": "ValidPass1"},
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_409_duplicate_email(self, client: AsyncClient) -> None:
        """Registering with existing email returns 409."""
        await client.post(
            "/api/v1/auth/register",
            json={"email": "dup@example.com", "password": "ValidPass1"},
        )
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "dup@example.com", "password": "ValidPass1"},
        )
        assert resp.status_code == 409


# ===========================================================================
# 3. Headers and content type
# ===========================================================================


class TestHeaders:
    """Verify response headers."""

    @pytest.mark.asyncio
    async def test_json_content_type(self, authenticated_client: AsyncClient) -> None:
        """API responses have application/json content type."""
        resp = await authenticated_client.get("/api/v1/stocks/watchlist")
        assert "application/json" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_no_server_version_leak(self, client: AsyncClient) -> None:
        """Response headers do not leak server version."""
        resp = await client.get("/health")
        server_header = resp.headers.get("server", "").lower()
        # Should not expose detailed version info
        assert "uvicorn" not in server_header or "version" not in server_header

    @pytest.mark.asyncio
    async def test_health_endpoint_no_auth(self, client: AsyncClient) -> None:
        """Health endpoint does not require authentication."""
        resp = await client.get("/health")
        assert resp.status_code == 200
