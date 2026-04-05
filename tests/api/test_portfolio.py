"""API tests for portfolio endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.conftest import SignalSnapshotFactory, StockFactory


@pytest.mark.asyncio
class TestPortfolioAuth:
    """Unauthenticated requests return 401."""

    async def test_create_transaction_requires_auth(self, client: AsyncClient) -> None:
        """POST /portfolio/transactions without token returns 401."""
        resp = await client.post("/api/v1/portfolio/transactions", json={})
        assert resp.status_code == 401

    async def test_list_transactions_requires_auth(self, client: AsyncClient) -> None:
        """GET /portfolio/transactions without token returns 401."""
        resp = await client.get("/api/v1/portfolio/transactions")
        assert resp.status_code == 401

    async def test_positions_requires_auth(self, client: AsyncClient) -> None:
        """GET /portfolio/positions without token returns 401."""
        resp = await client.get("/api/v1/portfolio/positions")
        assert resp.status_code == 401

    async def test_summary_requires_auth(self, client: AsyncClient) -> None:
        """GET /portfolio/summary without token returns 401."""
        resp = await client.get("/api/v1/portfolio/summary")
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestCreateTransaction:
    """Tests for POST /api/v1/portfolio/transactions."""

    async def test_log_buy_returns_201(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """BUY transaction logged successfully returns 201 with transaction data."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            stock = StockFactory.build(ticker="AAPL", name="Apple Inc.")
            session.add(stock)
            await session.commit()
        await engine.dispose()

        resp = await authenticated_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "AAPL",
                "transaction_type": "BUY",
                "shares": "10",
                "price_per_share": "182.50",
                "transacted_at": "2026-01-15T00:00:00Z",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["ticker"] == "AAPL"
        assert data["transaction_type"] == "BUY"
        assert float(data["shares"]) == 10.0

    async def test_log_buy_unknown_ticker_returns_422(
        self, authenticated_client: AsyncClient
    ) -> None:
        """BUY for ticker not in stocks table returns 422 with clear message."""
        resp = await authenticated_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "ZZZZZ",
                "transaction_type": "BUY",
                "shares": "5",
                "price_per_share": "100.00",
                "transacted_at": "2026-01-15T00:00:00Z",
            },
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"].lower()
        assert "not recognized" in detail or "not found" in detail or "invalid" in detail

    async def test_oversell_returns_422(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """SELL exceeding held shares returns 422."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            stock = StockFactory.build(ticker="MSFT", name="Microsoft")
            session.add(stock)
            await session.commit()
        await engine.dispose()

        # Buy 5 shares first
        await authenticated_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "MSFT",
                "transaction_type": "BUY",
                "shares": "5",
                "price_per_share": "300.00",
                "transacted_at": "2026-01-15T00:00:00Z",
            },
        )

        # Try to sell 10
        resp = await authenticated_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "MSFT",
                "transaction_type": "SELL",
                "shares": "10",
                "price_per_share": "320.00",
                "transacted_at": "2026-01-20T00:00:00Z",
            },
        )
        assert resp.status_code == 422

    async def test_invalid_payload_returns_422(self, authenticated_client: AsyncClient) -> None:
        """Missing required fields returns 422."""
        resp = await authenticated_client.post(
            "/api/v1/portfolio/transactions",
            json={"ticker": "AAPL"},
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestListTransactions:
    """Tests for GET /api/v1/portfolio/transactions."""

    async def test_empty_returns_empty_list(self, authenticated_client: AsyncClient) -> None:
        """No transactions returns empty list."""
        resp = await authenticated_client.get("/api/v1/portfolio/transactions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["transactions"] == []
        assert data["total"] == 0

    async def test_filter_by_ticker(self, authenticated_client: AsyncClient, db_url: str) -> None:
        """?ticker=AAPL filters to only AAPL transactions."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            for ticker in ("AAPL", "MSFT"):
                stock = StockFactory.build(ticker=ticker, name=ticker)
                session.add(stock)
            await session.commit()
        await engine.dispose()

        for ticker in ("AAPL", "MSFT"):
            await authenticated_client.post(
                "/api/v1/portfolio/transactions",
                json={
                    "ticker": ticker,
                    "transaction_type": "BUY",
                    "shares": "5",
                    "price_per_share": "100.00",
                    "transacted_at": "2026-01-15T00:00:00Z",
                },
            )

        resp = await authenticated_client.get("/api/v1/portfolio/transactions?ticker=AAPL")
        assert resp.status_code == 200
        data = resp.json()
        tickers = [t["ticker"] for t in data["transactions"]]
        assert all(t == "AAPL" for t in tickers)


@pytest.mark.asyncio
class TestDeleteTransaction:
    """Tests for DELETE /api/v1/portfolio/transactions/{id}."""

    async def test_delete_buy_with_no_sells_succeeds(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """DELETE a BUY with no associated SELLs returns 204."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            stock = StockFactory.build(ticker="NVDA", name="NVIDIA")
            session.add(stock)
            await session.commit()
        await engine.dispose()

        create_resp = await authenticated_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "NVDA",
                "transaction_type": "BUY",
                "shares": "10",
                "price_per_share": "500.00",
                "transacted_at": "2026-01-15T00:00:00Z",
            },
        )
        txn_id = create_resp.json()["id"]

        resp = await authenticated_client.delete(f"/api/v1/portfolio/transactions/{txn_id}")
        assert resp.status_code == 204

    async def test_delete_buy_underlying_sell_returns_422(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """DELETE BUY that underlies a SELL returns 422."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            stock = StockFactory.build(ticker="TSLA", name="Tesla")
            session.add(stock)
            await session.commit()
        await engine.dispose()

        buy_resp = await authenticated_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "TSLA",
                "transaction_type": "BUY",
                "shares": "10",
                "price_per_share": "200.00",
                "transacted_at": "2026-01-15T00:00:00Z",
            },
        )
        buy_id = buy_resp.json()["id"]

        await authenticated_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "TSLA",
                "transaction_type": "SELL",
                "shares": "10",
                "price_per_share": "250.00",
                "transacted_at": "2026-01-20T00:00:00Z",
            },
        )

        resp = await authenticated_client.delete(f"/api/v1/portfolio/transactions/{buy_id}")
        assert resp.status_code == 422

    async def test_delete_nonexistent_returns_404(self, authenticated_client: AsyncClient) -> None:
        """DELETE unknown transaction ID returns 404."""
        import uuid

        resp = await authenticated_client.delete(f"/api/v1/portfolio/transactions/{uuid.uuid4()}")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestPositions:
    """Tests for GET /api/v1/portfolio/positions."""

    async def test_empty_portfolio_returns_empty_list(
        self, authenticated_client: AsyncClient
    ) -> None:
        """No transactions → empty positions list."""
        resp = await authenticated_client.get("/api/v1/portfolio/positions")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_buy_creates_position(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """BUY transaction creates a position with correct shares and cost basis."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            stock = StockFactory.build(ticker="GOOG", name="Alphabet")
            session.add(stock)
            await session.commit()
        await engine.dispose()

        await authenticated_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "GOOG",
                "transaction_type": "BUY",
                "shares": "5",
                "price_per_share": "150.00",
                "transacted_at": "2026-01-15T00:00:00Z",
            },
        )

        resp = await authenticated_client.get("/api/v1/portfolio/positions")
        assert resp.status_code == 200
        positions = resp.json()
        goog = next((p for p in positions if p["ticker"] == "GOOG"), None)
        assert goog is not None
        assert float(goog["shares"]) == 5.0
        assert float(goog["avg_cost_basis"]) == pytest.approx(150.0, abs=0.01)


@pytest.mark.asyncio
class TestPortfolioSummary:
    """Tests for GET /api/v1/portfolio/summary."""

    async def test_empty_portfolio_summary(self, authenticated_client: AsyncClient) -> None:
        """Empty portfolio summary returns zero totals."""
        resp = await authenticated_client.get("/api/v1/portfolio/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_value"] == 0.0
        assert data["position_count"] == 0
        assert data["sectors"] == []


@pytest.mark.asyncio
class TestPortfolioHistory:
    """Tests for GET /api/v1/portfolio/history."""

    async def test_history_requires_auth(self, client: AsyncClient) -> None:
        """Unauthenticated request returns 401."""
        resp = await client.get("/api/v1/portfolio/history")
        assert resp.status_code == 401

    async def test_history_empty_returns_list(self, authenticated_client: AsyncClient) -> None:
        """Empty history returns an empty list (no snapshots yet)."""
        resp = await authenticated_client.get("/api/v1/portfolio/history")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_history_respects_days_param(self, authenticated_client: AsyncClient) -> None:
        """Days parameter is accepted and validated."""
        resp = await authenticated_client.get("/api/v1/portfolio/history?days=30")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_history_invalid_days_returns_422(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Invalid days param returns 422."""
        resp = await authenticated_client.get("/api/v1/portfolio/history?days=0")
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestPositionAlerts:
    """Tests for divestment alerts on GET /api/v1/portfolio/positions."""

    async def test_positions_include_alerts_field(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Positions response includes an alerts field (empty when healthy)."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            stock = StockFactory.build(ticker="HLTH", name="Healthy Inc.", sector="Technology")
            session.add(stock)
            await session.commit()
        await engine.dispose()

        await authenticated_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "HLTH",
                "transaction_type": "BUY",
                "shares": "5",
                "price_per_share": "100.00",
                "transacted_at": "2026-01-15T00:00:00Z",
            },
        )

        resp = await authenticated_client.get("/api/v1/portfolio/positions")
        assert resp.status_code == 200
        positions = resp.json()
        assert len(positions) >= 1
        hlth = next(p for p in positions if p["ticker"] == "HLTH")
        assert "alerts" in hlth
        assert "sector" in hlth
        assert isinstance(hlth["alerts"], list)

    async def test_positions_alerts_respect_user_prefs(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Custom user prefs with very low thresholds trigger alerts."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            stock = StockFactory.build(ticker="ALRT", name="Alert Corp", sector="Energy")
            session.add(stock)
            await session.flush()  # stock must exist before signal FK
            signal = SignalSnapshotFactory.build(
                ticker="ALRT",
                composite_score=1.5,
                computed_at=datetime.now(timezone.utc),
            )
            session.add(signal)
            await session.commit()
        await engine.dispose()

        # Set very low max_position_pct so the alert fires
        await authenticated_client.patch(
            "/api/v1/preferences",
            json={"max_position_pct": 1.0},
        )

        await authenticated_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "ALRT",
                "transaction_type": "BUY",
                "shares": "10",
                "price_per_share": "100.00",
                "transacted_at": "2026-01-15T00:00:00Z",
            },
        )

        resp = await authenticated_client.get("/api/v1/portfolio/positions")
        assert resp.status_code == 200
        positions = resp.json()
        alrt = next(p for p in positions if p["ticker"] == "ALRT")
        rules = {a["rule"] for a in alrt["alerts"]}
        # weak_fundamentals should fire (composite_score 1.5 < 3)
        assert "weak_fundamentals" in rules


@pytest.mark.asyncio
class TestRebalancing:
    """Tests for GET /api/v1/portfolio/rebalancing."""

    async def test_rebalancing_requires_auth(self, client: AsyncClient) -> None:
        """Unauthenticated request returns 401."""
        resp = await client.get("/api/v1/portfolio/rebalancing")
        assert resp.status_code == 401

    async def test_rebalancing_empty_portfolio(self, authenticated_client: AsyncClient) -> None:
        """Empty portfolio returns zero totals and no suggestions."""
        resp = await authenticated_client.get("/api/v1/portfolio/rebalancing")
        assert resp.status_code == 200
        data = resp.json()
        assert data["suggestions"] == []
        assert data["total_value"] == 0.0
        assert data["available_cash"] == 0.0
        assert data["num_positions"] == 0

    async def test_rebalancing_response_structure(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """With a real position, response should have correct structure."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            stock = StockFactory.build(ticker="RBAL", name="Rebalance Corp", sector="Technology")
            session.add(stock)
            await session.commit()
        await engine.dispose()

        await authenticated_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "RBAL",
                "transaction_type": "BUY",
                "shares": "10",
                "price_per_share": "100.00",
                "transacted_at": "2026-01-15T00:00:00Z",
            },
        )

        resp = await authenticated_client.get("/api/v1/portfolio/rebalancing")
        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data
        assert "total_value" in data
        assert "available_cash" in data
        assert "num_positions" in data
        assert isinstance(data["suggestions"], list)
        assert data["num_positions"] >= 1
        if data["suggestions"]:
            suggestion = data["suggestions"][0]
            assert "ticker" in suggestion
            assert "action" in suggestion
            assert "current_allocation_pct" in suggestion
            assert "target_allocation_pct" in suggestion
            assert "suggested_amount" in suggestion
            assert "reason" in suggestion
            assert suggestion["action"] in ("BUY_MORE", "HOLD", "AT_CAP")
