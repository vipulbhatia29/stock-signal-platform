"""Tests for stock index API endpoints."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.conftest import (
    SignalSnapshotFactory,
    StockFactory,
    StockIndexFactory,
    StockIndexMembershipFactory,
    StockPriceFactory,
)


class TestListIndexes:
    """Tests for GET /api/v1/indexes."""

    async def test_list_indexes_requires_auth(self, client: AsyncClient) -> None:
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/indexes")
        assert response.status_code == 401

    async def test_list_indexes_empty(self, authenticated_client: AsyncClient) -> None:
        """Returns empty list when no indexes exist."""
        response = await authenticated_client.get("/api/v1/indexes")
        assert response.status_code == 200
        assert response.json() == []

    async def test_list_indexes_with_data(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Returns indexes with stock counts."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            idx = StockIndexFactory.build(name="S&P 500", slug="sp500")
            session.add(idx)
            stock = StockFactory.build(ticker="AAPL", name="Apple Inc")
            session.add(stock)
            await session.flush()
            membership = StockIndexMembershipFactory.build(ticker="AAPL", index_id=idx.id)
            session.add(membership)
            await session.commit()
        await engine.dispose()

        response = await authenticated_client.get("/api/v1/indexes")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "S&P 500"
        assert data[0]["slug"] == "sp500"
        assert data[0]["stock_count"] == 1


class TestGetIndexStocks:
    """Tests for GET /api/v1/indexes/{slug}/stocks."""

    async def test_index_stocks_requires_auth(self, client: AsyncClient) -> None:
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/indexes/sp500/stocks")
        assert response.status_code == 401

    async def test_index_stocks_not_found(self, authenticated_client: AsyncClient) -> None:
        """Unknown index slug returns 404."""
        response = await authenticated_client.get("/api/v1/indexes/nonexistent/stocks")
        assert response.status_code == 404

    async def test_index_stocks_returns_data(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Returns stocks with signal and price data for a valid index."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            idx = StockIndexFactory.build(name="Dow 30", slug="dow30")
            session.add(idx)
            stock = StockFactory.build(ticker="MSFT", name="Microsoft Corp")
            session.add(stock)
            await session.flush()

            membership = StockIndexMembershipFactory.build(ticker="MSFT", index_id=idx.id)
            session.add(membership)

            signal = SignalSnapshotFactory.build(ticker="MSFT", composite_score=7.5)
            session.add(signal)

            price = StockPriceFactory.build(ticker="MSFT", adj_close=420.0)
            session.add(price)

            await session.commit()
        await engine.dispose()

        response = await authenticated_client.get("/api/v1/indexes/dow30/stocks")
        assert response.status_code == 200
        data = response.json()
        assert data["index_name"] == "Dow 30"
        assert data["total"] == 1
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["ticker"] == "MSFT"
        assert item["composite_score"] == 7.5
        assert item["latest_price"] == 420.0

    async def test_index_stocks_pagination(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Pagination limit and offset work correctly."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            idx = StockIndexFactory.build(name="Test Idx", slug="test-idx")
            session.add(idx)

            for i in range(5):
                ticker = f"T{i:03d}"
                stock = StockFactory.build(ticker=ticker, name=f"Test {i}")
                session.add(stock)
                await session.flush()
                m = StockIndexMembershipFactory.build(ticker=ticker, index_id=idx.id)
                session.add(m)

            await session.commit()
        await engine.dispose()

        response = await authenticated_client.get(
            "/api/v1/indexes/test-idx/stocks", params={"limit": 2, "offset": 0}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2

    async def test_index_stocks_empty_index(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Index with no members returns empty items list."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            idx = StockIndexFactory.build(name="Empty Idx", slug="empty-idx")
            session.add(idx)
            await session.commit()
        await engine.dispose()

        response = await authenticated_client.get("/api/v1/indexes/empty-idx/stocks")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []
