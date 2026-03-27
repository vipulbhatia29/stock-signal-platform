"""Stock search → ingest flow hardening tests."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.conftest import StockFactory, UserFactory, UserPreferenceFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_stock(db_url: str, ticker: str, name: str = "Test Corp") -> None:
    """Insert a Stock row for test data."""
    engine = create_async_engine(db_url, echo=False)
    factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory_() as session:
        stock = StockFactory.build(ticker=ticker, name=name)
        session.add(stock)
        await session.commit()
    await engine.dispose()


async def _make_auth_client(client: AsyncClient, db_url: str) -> AsyncClient:
    """Create an authenticated client."""
    from backend.dependencies import create_access_token

    engine = create_async_engine(db_url, echo=False)
    factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory_() as session:
        user = UserFactory.build()
        session.add(user)
        pref = UserPreferenceFactory.build(user_id=user.id)
        session.add(pref)
        await session.commit()
    await engine.dispose()

    token = create_access_token(user.id)
    return AsyncClient(
        transport=client._transport,
        base_url=client.base_url,
        headers={**dict(client.headers), "Authorization": f"Bearer {token}"},
    )


# ===========================================================================
# Tests
# ===========================================================================


class TestSearchFlow:
    """Stock search endpoint hardening."""

    @pytest.mark.asyncio
    async def test_search_db_hit(self, client: AsyncClient, db_url) -> None:
        """Search returns DB-stored stock when ticker matches."""
        await _seed_stock(db_url, "AAPL", "Apple Inc")
        ac = await _make_auth_client(client, db_url)

        resp = await ac.get("/api/v1/stocks/search", params={"q": "AAPL"})
        assert resp.status_code == 200
        results = resp.json()
        assert any(r["ticker"] == "AAPL" for r in results)
        assert any(r["in_db"] is True for r in results if r["ticker"] == "AAPL")
        await ac.aclose()

    @pytest.mark.asyncio
    async def test_search_prefix_match(self, client: AsyncClient, db_url) -> None:
        """Search by prefix matches stocks starting with query."""
        await _seed_stock(db_url, "MSFT", "Microsoft Corp")
        ac = await _make_auth_client(client, db_url)

        resp = await ac.get("/api/v1/stocks/search", params={"q": "MS"})
        assert resp.status_code == 200
        results = resp.json()
        assert any(r["ticker"] == "MSFT" for r in results)
        await ac.aclose()

    @pytest.mark.asyncio
    async def test_search_name_match(self, client: AsyncClient, db_url) -> None:
        """Search by company name substring finds the stock."""
        await _seed_stock(db_url, "GOOG", "Alphabet Inc")
        ac = await _make_auth_client(client, db_url)

        resp = await ac.get("/api/v1/stocks/search", params={"q": "Alphabet"})
        assert resp.status_code == 200
        results = resp.json()
        assert any(r["ticker"] == "GOOG" for r in results)
        await ac.aclose()

    @pytest.mark.asyncio
    async def test_search_unknown_ticker_returns_empty_or_external(
        self, client: AsyncClient, db_url
    ) -> None:
        """Searching for a non-existent ticker returns empty or Yahoo results."""
        ac = await _make_auth_client(client, db_url)

        with patch(
            "backend.routers.stocks.search._yahoo_search",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await ac.get("/api/v1/stocks/search", params={"q": "XYZNOTREAL"})
        assert resp.status_code == 200
        assert resp.json() == []
        await ac.aclose()

    @pytest.mark.asyncio
    async def test_search_requires_auth(self, client: AsyncClient) -> None:
        """Search endpoint requires authentication."""
        resp = await client.get("/api/v1/stocks/search", params={"q": "AAPL"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_search_empty_query_rejected(self, authenticated_client: AsyncClient) -> None:
        """Empty search query is rejected (min_length=1)."""
        resp = await authenticated_client.get("/api/v1/stocks/search", params={"q": ""})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_search_xss_safe(self, client: AsyncClient, db_url) -> None:
        """XSS payload in search query does not cause 500."""
        ac = await _make_auth_client(client, db_url)

        with patch(
            "backend.routers.stocks.search._yahoo_search",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await ac.get(
                "/api/v1/stocks/search",
                params={"q": "<script>alert(1)"},
            )
        # Should return 200 empty or 422, never 500
        assert resp.status_code in (200, 422)
        await ac.aclose()

    @pytest.mark.asyncio
    async def test_search_results_have_required_fields(self, client: AsyncClient, db_url) -> None:
        """Search results contain all required schema fields."""
        await _seed_stock(db_url, "NVDA", "NVIDIA Corp")
        ac = await _make_auth_client(client, db_url)

        resp = await ac.get("/api/v1/stocks/search", params={"q": "NVDA"})
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) > 0
        for r in results:
            assert "ticker" in r
            assert "name" in r
            assert "in_db" in r
        await ac.aclose()

    @pytest.mark.asyncio
    async def test_search_limit_respected(self, client: AsyncClient, db_url) -> None:
        """Search returns at most 10 results."""
        for i in range(15):
            await _seed_stock(db_url, f"T{i:03d}", f"Test Corp {i}")
        ac = await _make_auth_client(client, db_url)

        resp = await ac.get("/api/v1/stocks/search", params={"q": "T"})
        assert resp.status_code == 200
        assert len(resp.json()) <= 10
        await ac.aclose()

    @pytest.mark.asyncio
    async def test_search_yahoo_fallback(self, client: AsyncClient, db_url) -> None:
        """When DB has no match, Yahoo fallback is called."""
        ac = await _make_auth_client(client, db_url)

        from backend.schemas.stock import StockSearchResponse

        mock_result = StockSearchResponse(
            ticker="PLTR", name="Palantir", exchange="NYSE", in_db=False
        )
        with patch(
            "backend.routers.stocks.search._yahoo_search",
            new_callable=AsyncMock,
            return_value=[mock_result],
        ) as mock_yahoo:
            resp = await ac.get("/api/v1/stocks/search", params={"q": "Palantir"})
        assert resp.status_code == 200
        mock_yahoo.assert_called_once()
        results = resp.json()
        assert any(r["ticker"] == "PLTR" and r["in_db"] is False for r in results)
        await ac.aclose()
