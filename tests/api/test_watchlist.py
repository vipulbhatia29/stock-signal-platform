"""Tests for watchlist API endpoints."""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.conftest import StockFactory, StockPriceFactory


class TestWatchlistPrice:
    """Tests for watchlist price fields."""

    async def test_watchlist_returns_price(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """GET /watchlist includes current_price and price_updated_at."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            stock = StockFactory.build(ticker="PRICETEST", name="Price Test")
            session.add(stock)
            await session.flush()
            price = StockPriceFactory.build(ticker="PRICETEST", adj_close=Decimal("123.45"))
            session.add(price)
            await session.commit()
        await engine.dispose()

        # Add to watchlist
        await authenticated_client.post(
            "/api/v1/stocks/watchlist",
            json={"ticker": "PRICETEST"},
        )

        response = await authenticated_client.get("/api/v1/stocks/watchlist")
        assert response.status_code == 200
        items = response.json()
        pricetest = next((i for i in items if i["ticker"] == "PRICETEST"), None)
        assert pricetest is not None
        assert pricetest["current_price"] == pytest.approx(123.45, abs=0.01)
        assert pricetest["price_updated_at"] is not None


class TestWatchlistAcknowledge:
    """Tests for the watchlist acknowledge endpoint."""

    async def test_acknowledge_clears_stale_indicator(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """POST /watchlist/{ticker}/acknowledge sets price_acknowledged_at."""
        from decimal import Decimal

        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from tests.conftest import StockFactory, StockPriceFactory

        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            stock = StockFactory.build(ticker="ACKTEST", name="Ack Test")
            session.add(stock)
            await session.flush()
            price = StockPriceFactory.build(ticker="ACKTEST", adj_close=Decimal("50.00"))
            session.add(price)
            await session.commit()
        await engine.dispose()

        await authenticated_client.post(
            "/api/v1/stocks/watchlist",
            json={"ticker": "ACKTEST"},
        )

        response = await authenticated_client.post("/api/v1/stocks/watchlist/ACKTEST/acknowledge")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "ACKTEST"
        assert data["price_acknowledged_at"] is not None

    async def test_acknowledge_returns_404_for_missing_ticker(
        self, authenticated_client: AsyncClient
    ) -> None:
        """POST /watchlist/{ticker}/acknowledge returns 404 if not in watchlist."""
        response = await authenticated_client.post("/api/v1/stocks/watchlist/NOTHERE/acknowledge")
        assert response.status_code == 404

    async def test_acknowledge_requires_auth(self, client: AsyncClient) -> None:
        """POST /watchlist/{ticker}/acknowledge requires authentication."""
        response = await client.post("/api/v1/stocks/watchlist/AAPL/acknowledge")
        assert response.status_code == 401

    async def test_watchlist_returns_price_acknowledged_at_field(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """GET /watchlist includes price_acknowledged_at field (None by default)."""
        from decimal import Decimal

        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from tests.conftest import StockFactory, StockPriceFactory

        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            stock = StockFactory.build(ticker="ACKFLD", name="Ack Field Test")
            session.add(stock)
            await session.flush()
            price = StockPriceFactory.build(ticker="ACKFLD", adj_close=Decimal("99.00"))
            session.add(price)
            await session.commit()
        await engine.dispose()

        await authenticated_client.post(
            "/api/v1/stocks/watchlist",
            json={"ticker": "ACKFLD"},
        )

        response = await authenticated_client.get("/api/v1/stocks/watchlist")
        assert response.status_code == 200
        items = response.json()
        item = next((i for i in items if i["ticker"] == "ACKFLD"), None)
        assert item is not None
        assert "price_acknowledged_at" in item
        assert item["price_acknowledged_at"] is None
