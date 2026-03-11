"""Tests for signal history endpoint."""

from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.conftest import SignalSnapshotFactory, StockFactory


class TestSignalHistory:
    """Tests for GET /api/v1/stocks/{ticker}/signals/history."""

    async def test_signal_history_requires_auth(self, client: AsyncClient) -> None:
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/stocks/AAPL/signals/history")
        assert response.status_code == 401

    async def test_signal_history_stock_not_found(self, authenticated_client: AsyncClient) -> None:
        """Unknown ticker returns 404."""
        response = await authenticated_client.get("/api/v1/stocks/ZZZZ/signals/history")
        assert response.status_code == 404

    async def test_signal_history_empty(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Stock with no signals returns empty list."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            stock = StockFactory.build(ticker="EMPT", name="Empty Stock")
            session.add(stock)
            await session.commit()
        await engine.dispose()

        response = await authenticated_client.get("/api/v1/stocks/EMPT/signals/history")
        assert response.status_code == 200
        assert response.json() == []

    async def test_signal_history_returns_chronological_data(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Returns signal snapshots in chronological order."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        now = datetime.now(timezone.utc)
        async with factory_() as session:
            stock = StockFactory.build(ticker="HIST", name="History Stock")
            session.add(stock)
            await session.flush()

            for i in range(3):
                signal = SignalSnapshotFactory.build(
                    ticker="HIST",
                    composite_score=float(5 + i),
                    computed_at=now - timedelta(days=3 - i),
                )
                session.add(signal)
            await session.commit()
        await engine.dispose()

        response = await authenticated_client.get("/api/v1/stocks/HIST/signals/history")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        # Should be in ascending order (oldest first)
        assert data[0]["composite_score"] == 5.0
        assert data[2]["composite_score"] == 7.0

    async def test_signal_history_respects_days_param(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Days parameter limits how far back to look."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        now = datetime.now(timezone.utc)
        async with factory_() as session:
            stock = StockFactory.build(ticker="DAYS", name="Days Stock")
            session.add(stock)
            await session.flush()

            # One signal from 10 days ago, one from 1 day ago
            old = SignalSnapshotFactory.build(
                ticker="DAYS",
                computed_at=now - timedelta(days=10),
            )
            recent = SignalSnapshotFactory.build(
                ticker="DAYS",
                computed_at=now - timedelta(days=1),
            )
            session.add(old)
            session.add(recent)
            await session.commit()
        await engine.dispose()

        response = await authenticated_client.get(
            "/api/v1/stocks/DAYS/signals/history",
            params={"days": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1  # Only the recent one

    async def test_signal_history_has_expected_fields(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Response items contain all expected fields."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            stock = StockFactory.build(ticker="FLDS", name="Fields Stock")
            session.add(stock)
            await session.flush()

            signal = SignalSnapshotFactory.build(ticker="FLDS")
            session.add(signal)
            await session.commit()
        await engine.dispose()

        response = await authenticated_client.get("/api/v1/stocks/FLDS/signals/history")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        item = data[0]
        expected_keys = {
            "computed_at",
            "composite_score",
            "rsi_value",
            "rsi_signal",
            "macd_value",
            "macd_signal",
            "sma_signal",
            "bb_position",
        }
        assert expected_keys == set(item.keys())
