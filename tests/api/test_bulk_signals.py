"""Tests for bulk signals (screener) endpoint."""

from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.conftest import (
    SignalSnapshotFactory,
    StockFactory,
    StockIndexFactory,
    StockIndexMembershipFactory,
    StockPriceFactory,
)


class TestBulkSignals:
    """Tests for GET /api/v1/stocks/signals/bulk."""

    async def test_bulk_signals_requires_auth(self, client: AsyncClient) -> None:
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/stocks/signals/bulk")
        assert response.status_code == 401

    async def test_bulk_signals_empty(self, authenticated_client: AsyncClient) -> None:
        """Returns empty list when no signals exist."""
        response = await authenticated_client.get("/api/v1/stocks/signals/bulk")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    async def test_bulk_signals_returns_data(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Returns signal data for stocks with signals."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            stock = StockFactory.build(ticker="AAPL", name="Apple Inc", sector="Technology")
            session.add(stock)
            await session.flush()

            signal = SignalSnapshotFactory.build(
                ticker="AAPL",
                composite_score=8.0,
                rsi_signal="OVERSOLD",
                macd_signal_label="BULLISH",
            )
            session.add(signal)
            await session.commit()
        await engine.dispose()

        response = await authenticated_client.get("/api/v1/stocks/signals/bulk")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["ticker"] == "AAPL"
        assert data["items"][0]["composite_score"] == 8.0

    async def test_bulk_signals_filter_by_score(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Score range filter works correctly."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            for ticker, score in [("AAA0", 3.0), ("BBB0", 7.0), ("CCC0", 9.0)]:
                stock = StockFactory.build(ticker=ticker, name=f"Test {ticker}")
                session.add(stock)
                await session.flush()
                signal = SignalSnapshotFactory.build(ticker=ticker, composite_score=score)
                session.add(signal)
            await session.commit()
        await engine.dispose()

        response = await authenticated_client.get(
            "/api/v1/stocks/signals/bulk",
            params={"score_min": 5.0, "score_max": 8.0},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["ticker"] == "BBB0"

    async def test_bulk_signals_filter_by_index(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Index filter returns only stocks in that index."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            idx = StockIndexFactory.build(name="Test Bulk", slug="test-bulk")
            session.add(idx)

            # Stock in index
            s1 = StockFactory.build(ticker="IN01", name="In Index")
            session.add(s1)
            await session.flush()
            m = StockIndexMembershipFactory.build(ticker="IN01", index_id=idx.id)
            session.add(m)
            sig1 = SignalSnapshotFactory.build(ticker="IN01", composite_score=6.0)
            session.add(sig1)

            # Stock NOT in index
            s2 = StockFactory.build(ticker="OUT1", name="Not In Index")
            session.add(s2)
            await session.flush()
            sig2 = SignalSnapshotFactory.build(ticker="OUT1", composite_score=5.0)
            session.add(sig2)

            await session.commit()
            index_id = str(idx.id)
        await engine.dispose()

        response = await authenticated_client.get(
            "/api/v1/stocks/signals/bulk",
            params={"index_id": index_id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["ticker"] == "IN01"

    async def test_bulk_signals_pagination(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Pagination limit and offset work correctly."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            for i in range(5):
                ticker = f"PG{i:02d}"
                stock = StockFactory.build(ticker=ticker, name=f"Page Test {i}")
                session.add(stock)
                await session.flush()
                signal = SignalSnapshotFactory.build(ticker=ticker, composite_score=float(i))
                session.add(signal)
            await session.commit()
        await engine.dispose()

        response = await authenticated_client.get(
            "/api/v1/stocks/signals/bulk",
            params={"limit": 2, "offset": 0, "sort_by": "ticker", "sort_order": "asc"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2

    async def test_bulk_signals_sort_ascending(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Sorting by composite_score ascending works."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            for ticker, score in [("SA01", 9.0), ("SB01", 3.0)]:
                stock = StockFactory.build(ticker=ticker, name=f"Sort {ticker}")
                session.add(stock)
                await session.flush()
                signal = SignalSnapshotFactory.build(ticker=ticker, composite_score=score)
                session.add(signal)
            await session.commit()
        await engine.dispose()

        response = await authenticated_client.get(
            "/api/v1/stocks/signals/bulk",
            params={"sort_by": "composite_score", "sort_order": "asc"},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["ticker"] == "SB01"
        assert items[1]["ticker"] == "SA01"

    async def test_bulk_signals_includes_price_history(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """price_history field contains exactly 30 chronological adj_close floats."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            stock = StockFactory.build(ticker="PH01", name="Price History Test")
            session.add(stock)
            await session.flush()

            signal = SignalSnapshotFactory.build(ticker="PH01", composite_score=7.0)
            session.add(signal)

            base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
            for i in range(35):
                price = StockPriceFactory.build(
                    ticker="PH01",
                    time=base_time + timedelta(days=i),
                    adj_close=float(100 + i),
                )
                session.add(price)
            await session.commit()
        await engine.dispose()

        response = await authenticated_client.get("/api/v1/stocks/signals/bulk")
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        ph = items[0]
        assert ph["ticker"] == "PH01"
        assert ph["price_history"] is not None
        # 35 rows inserted, limit is 30 — must return exactly 30
        assert len(ph["price_history"]) == 30
        # Values should be floats
        assert all(isinstance(v, float) for v in ph["price_history"])
        # Must be in chronological (ascending) order — sparkline depends on this
        assert ph["price_history"] == sorted(ph["price_history"])

    async def test_bulk_signals_sharpe_filter(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """sharpe_min filter returns only stocks at or above the threshold."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            for ticker, sharpe in [("SH1", 1.5), ("SH2", 0.8), ("SH3", 0.3)]:
                stock = StockFactory.build(ticker=ticker, name=f"Sharpe {ticker}")
                session.add(stock)
                await session.flush()
                signal = SignalSnapshotFactory.build(ticker=ticker, sharpe_ratio=sharpe)
                session.add(signal)
            await session.commit()
        await engine.dispose()

        # With sharpe_min=0.7: only SH1 (1.5) and SH2 (0.8) qualify
        response = await authenticated_client.get(
            "/api/v1/stocks/signals/bulk",
            params={"sharpe_min": 0.7},
        )
        assert response.status_code == 200
        data = response.json()
        returned = [item["ticker"] for item in data["items"]]
        assert "SH1" in returned
        assert "SH2" in returned
        assert "SH3" not in returned

        # Without filter: SH3 also returned
        response2 = await authenticated_client.get("/api/v1/stocks/signals/bulk")
        assert response2.status_code == 200
        returned2 = [item["ticker"] for item in response2.json()["items"]]
        assert "SH3" in returned2
