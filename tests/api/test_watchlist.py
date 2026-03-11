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
