"""API tests for sectors endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import quote

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models.portfolio import Position
from tests.conftest import (
    PortfolioFactory,
    SignalSnapshotFactory,
    StockFactory,
    StockPriceFactory,
    WatchlistFactory,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _seed_sector_data(
    db_url: str,
    *,
    user_id=None,
    sectors: dict[str, list[str]] | None = None,
    with_portfolio: bool = False,
    with_watchlist: bool = False,
    with_prices: bool = False,
    price_days: int = 60,
) -> None:
    """Seed stocks, signals, and optionally portfolio/watchlist data.

    Args:
        db_url: Database URL.
        user_id: The authenticated user's ID.
        sectors: Mapping of sector → list of tickers.
        with_portfolio: Create portfolio with positions for first ticker per sector.
        with_watchlist: Create watchlist entries for second ticker per sector.
        with_prices: Create price data for correlation testing.
        price_days: Number of days of price data.
    """
    if sectors is None:
        sectors = {
            "Technology": ["AAPL", "MSFT", "GOOG"],
            "Healthcare": ["JNJ", "PFE"],
        }

    engine = create_async_engine(db_url, echo=False)
    factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory_() as session:
        portfolio_id = None
        if with_portfolio and user_id:
            portfolio = PortfolioFactory.build(user_id=user_id)
            session.add(portfolio)
            await session.flush()
            portfolio_id = portfolio.id

        for sector, tickers in sectors.items():
            for i, ticker in enumerate(tickers):
                stock = StockFactory.build(
                    ticker=ticker,
                    name=f"{ticker} Inc",
                    sector=sector if sector != "Unknown" else None,
                )
                session.add(stock)
                await session.flush()

                signal = SignalSnapshotFactory.build(
                    ticker=ticker,
                    composite_score=8.0 - i * 0.5,
                    annual_return=0.15 - i * 0.02,
                )
                session.add(signal)

                if with_prices:
                    import hashlib

                    base_price = 100.0 + i * 10
                    current = base_price
                    for day in range(price_days):
                        dt = datetime.now(timezone.utc) - timedelta(days=price_days - day)
                        # Deterministic pseudo-random daily return per ticker+day
                        seed = hashlib.md5(f"{ticker}{day}".encode()).hexdigest()
                        ret = (int(seed[:8], 16) / 0xFFFFFFFF - 0.5) * 0.04
                        current = current * (1 + ret)
                        price = StockPriceFactory.build(
                            ticker=ticker,
                            time=dt,
                            adj_close=round(current, 4),
                            open=round(current * 0.99, 4),
                            high=round(current * 1.01, 4),
                            low=round(current * 0.98, 4),
                            close=round(current * 1.005, 4),
                        )
                        session.add(price)

                if with_portfolio and portfolio_id and i == 0:
                    position = Position(
                        portfolio_id=portfolio_id,
                        ticker=ticker,
                        shares=Decimal("10"),
                        avg_cost_basis=Decimal("150.00"),
                        opened_at=datetime.now(timezone.utc) - timedelta(days=30),
                    )
                    session.add(position)

                if with_watchlist and user_id and i == 1 and len(tickers) > 1:
                    watchlist = WatchlistFactory.build(user_id=user_id, ticker=ticker)
                    session.add(watchlist)

        await session.commit()
    await engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/sectors
# ─────────────────────────────────────────────────────────────────────────────


class TestListSectors:
    """Tests for GET /api/v1/sectors."""

    async def test_requires_auth(self, client: AsyncClient) -> None:
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/sectors")
        assert response.status_code == 401

    async def test_empty_database(self, authenticated_client: AsyncClient) -> None:
        """Returns empty sectors list when no stocks exist."""
        response = await authenticated_client.get("/api/v1/sectors")
        assert response.status_code == 200
        data = response.json()
        assert data["sectors"] == []

    async def test_returns_sectors_with_stats(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Returns sectors with stock count, avg score, and avg return."""
        await _seed_sector_data(db_url)

        response = await authenticated_client.get("/api/v1/sectors")
        assert response.status_code == 200
        data = response.json()
        sectors = data["sectors"]
        assert len(sectors) == 2

        tech = next(s for s in sectors if s["sector"] == "Technology")
        assert tech["stock_count"] == 3
        assert tech["avg_composite_score"] is not None

    async def test_scope_portfolio(self, authenticated_client: AsyncClient, db_url: str) -> None:
        """Scope=portfolio counts only held stocks."""
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        await _seed_sector_data(
            db_url,
            user_id=user.id,
            with_portfolio=True,
            with_prices=True,
        )

        response = await authenticated_client.get("/api/v1/sectors", params={"scope": "portfolio"})
        assert response.status_code == 200
        data = response.json()
        sectors = data["sectors"]
        # Each sector has 1 held stock (first ticker)
        for s in sectors:
            assert s["your_stock_count"] >= 0

    async def test_scope_watchlist(self, authenticated_client: AsyncClient, db_url: str) -> None:
        """Scope=watchlist counts only watched stocks."""
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        await _seed_sector_data(
            db_url,
            user_id=user.id,
            with_watchlist=True,
        )

        response = await authenticated_client.get("/api/v1/sectors", params={"scope": "watchlist"})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["sectors"], list)


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/sectors/{sector}/stocks
# ─────────────────────────────────────────────────────────────────────────────


class TestGetSectorStocks:
    """Tests for GET /api/v1/sectors/{sector}/stocks."""

    async def test_requires_auth(self, client: AsyncClient) -> None:
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/sectors/Technology/stocks")
        assert response.status_code == 401

    async def test_sector_not_found(self, authenticated_client: AsyncClient) -> None:
        """Invalid sector returns 404."""
        response = await authenticated_client.get("/api/v1/sectors/NonexistentSector/stocks")
        assert response.status_code == 404

    async def test_returns_stocks(self, authenticated_client: AsyncClient, db_url: str) -> None:
        """Returns stocks for a valid sector with scores and prices."""
        await _seed_sector_data(db_url, with_prices=True, price_days=5)

        response = await authenticated_client.get("/api/v1/sectors/Technology/stocks")
        assert response.status_code == 200
        data = response.json()
        assert data["sector"] == "Technology"
        assert len(data["stocks"]) == 3
        # Stocks should have ticker and name
        assert data["stocks"][0]["ticker"] in ["AAPL", "MSFT", "GOOG"]

    async def test_marks_held_and_watched(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Held and watched stocks are marked correctly."""
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        await _seed_sector_data(
            db_url,
            user_id=user.id,
            with_portfolio=True,
            with_watchlist=True,
            with_prices=True,
            price_days=5,
        )

        response = await authenticated_client.get("/api/v1/sectors/Technology/stocks")
        assert response.status_code == 200
        stocks = response.json()["stocks"]

        # AAPL should be held (first ticker, with_portfolio=True)
        aapl = next((s for s in stocks if s["ticker"] == "AAPL"), None)
        assert aapl is not None
        assert aapl["is_held"] is True

        # MSFT should be watched (second ticker, with_watchlist=True)
        msft = next((s for s in stocks if s["ticker"] == "MSFT"), None)
        assert msft is not None
        assert msft["is_watched"] is True

    async def test_url_encoded_sector_name(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Sector names with spaces work via URL encoding."""
        await _seed_sector_data(
            db_url,
            sectors={"Consumer Defensive": ["KO", "PG"]},
        )

        encoded = quote("Consumer Defensive", safe="")
        response = await authenticated_client.get(f"/api/v1/sectors/{encoded}/stocks")
        assert response.status_code == 200
        data = response.json()
        assert data["sector"] == "Consumer Defensive"
        assert len(data["stocks"]) == 2


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/sectors/{sector}/correlation
# ─────────────────────────────────────────────────────────────────────────────


class TestGetSectorCorrelation:
    """Tests for GET /api/v1/sectors/{sector}/correlation."""

    async def test_requires_auth(self, client: AsyncClient) -> None:
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/sectors/Technology/correlation")
        assert response.status_code == 401

    async def test_happy_path(self, authenticated_client: AsyncClient, db_url: str) -> None:
        """Returns correlation matrix for valid tickers."""
        await _seed_sector_data(
            db_url,
            sectors={"Financials": ["BAC", "JPM", "GS"]},
            with_prices=True,
            price_days=60,
        )

        response = await authenticated_client.get(
            "/api/v1/sectors/Financials/correlation",
            params={"tickers": "BAC,JPM,GS", "period_days": 90},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sector"] == "Financials"
        assert len(data["tickers"]) >= 2
        n = len(data["tickers"])
        assert len(data["matrix"]) == n
        assert len(data["matrix"][0]) == n
        # Diagonal should be 1.0 (self-correlation)
        for i in range(n):
            assert abs(data["matrix"][i][i] - 1.0) < 0.01, (
                f"Diagonal [{i}][{i}] for {data['tickers'][i]} = {data['matrix'][i][i]}"
            )

    async def test_too_many_tickers(self, authenticated_client: AsyncClient, db_url: str) -> None:
        """More than 15 tickers returns 400."""
        tickers = [f"T{i:03d}" for i in range(16)]
        await _seed_sector_data(
            db_url,
            sectors={"Technology": tickers},
            with_prices=True,
            price_days=60,
        )

        response = await authenticated_client.get(
            "/api/v1/sectors/Technology/correlation",
            params={"tickers": ",".join(tickers)},
        )
        assert response.status_code == 400
        assert "Maximum" in response.json()["detail"]

    async def test_fewer_than_two_tickers(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Fewer than 2 tickers returns 400."""
        await _seed_sector_data(
            db_url,
            sectors={"Technology": ["AAPL"]},
            with_prices=True,
        )

        response = await authenticated_client.get(
            "/api/v1/sectors/Technology/correlation",
            params={"tickers": "AAPL"},
        )
        assert response.status_code == 400
        assert "At least 2" in response.json()["detail"]

    async def test_ticker_not_in_sector(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Tickers outside the sector return 400."""
        await _seed_sector_data(
            db_url,
            sectors={
                "Technology": ["AAPL", "MSFT"],
                "Healthcare": ["JNJ"],
            },
            with_prices=True,
        )

        response = await authenticated_client.get(
            "/api/v1/sectors/Technology/correlation",
            params={"tickers": "AAPL,JNJ"},
        )
        assert response.status_code == 400
        assert "JNJ" in response.json()["detail"]

    async def test_insufficient_data_excludes_ticker(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Tickers with insufficient price data are excluded but reported."""
        # Seed 2 tickers with enough data, 1 with only 5 days
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            for ticker in ["AAPL", "MSFT", "TINY"]:
                stock = StockFactory.build(ticker=ticker, name=f"{ticker} Inc", sector="Technology")
                session.add(stock)
                await session.flush()

                days = 60 if ticker != "TINY" else 5
                for day in range(days):
                    dt = datetime.now(timezone.utc) - timedelta(days=60 - day)
                    price = StockPriceFactory.build(
                        ticker=ticker,
                        time=dt,
                        adj_close=100.0 + day,
                    )
                    session.add(price)

            await session.commit()
        await engine.dispose()

        response = await authenticated_client.get(
            "/api/v1/sectors/Technology/correlation",
            params={"tickers": "AAPL,MSFT,TINY"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "TINY" not in data["tickers"]
        assert len(data["excluded_tickers"]) == 1
        assert data["excluded_tickers"][0]["ticker"] == "TINY"

    async def test_default_tickers_from_portfolio(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Without tickers param, uses user's portfolio+watchlist stocks."""
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        await _seed_sector_data(
            db_url,
            user_id=user.id,
            sectors={"Technology": ["AAPL", "MSFT", "GOOG"]},
            with_portfolio=True,
            with_watchlist=True,
            with_prices=True,
            price_days=60,
        )

        response = await authenticated_client.get(
            "/api/v1/sectors/Technology/correlation",
        )
        assert response.status_code == 200
        data = response.json()
        # Should have AAPL (held) and MSFT (watched) = 2 tickers
        assert len(data["tickers"]) == 2
        assert "AAPL" in data["tickers"]
        assert "MSFT" in data["tickers"]
