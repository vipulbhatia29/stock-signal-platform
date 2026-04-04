"""API endpoint tests for stock, signal, watchlist, and recommendation routes.

These tests use the FastAPI test client (httpx AsyncClient) with a real
Postgres+TimescaleDB test container. Each test:
  1. Sets up data directly in the database (via db_session)
  2. Calls the API endpoint via the authenticated HTTP client
  3. Asserts the response status code and body

Test categories:
  - Auth: verify endpoints require JWT
  - Happy path: verify correct responses with valid data
  - Error path: verify correct error codes for invalid input
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from tests.conftest import (
    RecommendationSnapshotFactory,
    SignalSnapshotFactory,
    StockFactory,
    StockPriceFactory,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helper: insert test data into the database
# ─────────────────────────────────────────────────────────────────────────────


async def _insert_stock(db_url: str, **kwargs) -> None:
    """Insert a stock record into the test database.

    We create a separate engine + session for test setup so it doesn't
    interfere with the FastAPI app's session (which is overridden per-test).
    """
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        stock = StockFactory.build(**kwargs)
        session.add(stock)
        await session.commit()
    await engine.dispose()


async def _insert_stock_with_signals(
    db_url: str, ticker: str, user_id: uuid.UUID | None = None
) -> None:
    """Insert a stock with price data, signals, and optionally a recommendation."""
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        # Create the stock record
        stock = StockFactory.build(ticker=ticker, name=f"{ticker} Inc")
        session.add(stock)
        await session.flush()

        # Create a signal snapshot (recent — within last 24 hours)
        signal = SignalSnapshotFactory.build(
            ticker=ticker,
            computed_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        session.add(signal)

        # Create some price data
        for i in range(5):
            price = StockPriceFactory.build(
                ticker=ticker,
                time=datetime.now(timezone.utc) - timedelta(days=i),
                close=150.0 + i,
                adj_close=150.0 + i,
            )
            session.add(price)

        # Optionally create a recommendation
        if user_id is not None:
            rec = RecommendationSnapshotFactory.build(
                ticker=ticker,
                user_id=user_id,
                generated_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
            session.add(rec)

        await session.commit()
    await engine.dispose()


# ═════════════════════════════════════════════════════════════════════════════
# Stock Search Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestStockSearch:
    """Tests for GET /api/v1/stocks/search."""

    @pytest.mark.asyncio
    async def test_search_requires_auth(self, client: AsyncClient) -> None:
        """Search endpoint should return 401 without a JWT token."""
        response = await client.get("/api/v1/stocks/search?q=AAPL")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_search_by_ticker(self, authenticated_client: AsyncClient, db_url: str) -> None:
        """Should find stocks by ticker prefix match. DB results come first."""
        await _insert_stock(db_url, ticker="AAPL", name="Apple Inc")
        await _insert_stock(db_url, ticker="AMZN", name="Amazon.com Inc")

        response = await authenticated_client.get("/api/v1/stocks/search?q=AA")
        assert response.status_code == 200

        data = response.json()
        assert len(data) >= 1
        # DB result should be first, marked as in_db=True
        assert data[0]["ticker"] == "AAPL"
        assert data[0]["in_db"] is True

    @pytest.mark.asyncio
    async def test_search_by_name(self, authenticated_client: AsyncClient, db_url: str) -> None:
        """Should find stocks by company name substring match."""
        await _insert_stock(db_url, ticker="AAPL", name="Apple Inc")

        response = await authenticated_client.get("/api/v1/stocks/search?q=Apple")
        assert response.status_code == 200

        data = response.json()
        assert len(data) >= 1
        assert any(s["ticker"] == "AAPL" for s in data)

    @pytest.mark.asyncio
    async def test_search_empty_result(self, authenticated_client: AsyncClient) -> None:
        """Should return an empty list when no stocks match."""
        response = await authenticated_client.get("/api/v1/stocks/search?q=ZZZZZ")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_search_requires_query(self, authenticated_client: AsyncClient) -> None:
        """Should return 422 when q parameter is missing."""
        response = await authenticated_client.get("/api/v1/stocks/search")
        assert response.status_code == 422


# ═════════════════════════════════════════════════════════════════════════════
# Price History Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestPriceHistory:
    """Tests for GET /api/v1/stocks/{ticker}/prices."""

    @pytest.mark.asyncio
    async def test_prices_requires_auth(self, client: AsyncClient) -> None:
        """Price endpoint should return 401 without a JWT token."""
        response = await client.get("/api/v1/stocks/AAPL/prices")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_prices_not_found(self, authenticated_client: AsyncClient) -> None:
        """Should return 404 for a ticker that doesn't exist."""
        response = await authenticated_client.get("/api/v1/stocks/FAKE/prices")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_prices_returns_data(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Should return price data for a valid ticker."""
        await _insert_stock_with_signals(db_url, "AAPL")

        response = await authenticated_client.get("/api/v1/stocks/AAPL/prices?period=1mo")
        assert response.status_code == 200

        data = response.json()
        assert len(data) >= 1
        assert "time" in data[0]
        assert "close" in data[0]
        assert "volume" in data[0]

    @pytest.mark.asyncio
    async def test_prices_default_format_is_list(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Default format (no param) should return a list of price objects."""
        await _insert_stock_with_signals(db_url, "AAPL")

        response = await authenticated_client.get("/api/v1/stocks/AAPL/prices?period=1mo")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert "time" in data[0]

    @pytest.mark.asyncio
    async def test_prices_format_list_explicit(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Explicit format=list should return the same list format."""
        await _insert_stock_with_signals(db_url, "AAPL")

        response = await authenticated_client.get(
            "/api/v1/stocks/AAPL/prices?period=1mo&format=list"
        )
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert "close" in data[0]

    @pytest.mark.asyncio
    async def test_prices_format_ohlc(self, authenticated_client: AsyncClient, db_url: str) -> None:
        """format=ohlc should return parallel arrays for candlestick charts."""
        await _insert_stock_with_signals(db_url, "AAPL")

        response = await authenticated_client.get(
            "/api/v1/stocks/AAPL/prices?period=1mo&format=ohlc"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["ticker"] == "AAPL"
        assert data["period"] == "1mo"
        assert isinstance(data["count"], int)
        assert data["count"] >= 1
        assert len(data["timestamps"]) == data["count"]
        assert len(data["open"]) == data["count"]
        assert len(data["high"]) == data["count"]
        assert len(data["low"]) == data["count"]
        assert len(data["close"]) == data["count"]
        assert len(data["volume"]) == data["count"]

    @pytest.mark.asyncio
    async def test_prices_format_ohlc_empty(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """format=ohlc with no price data should return empty arrays with count=0."""
        await _insert_stock(db_url, ticker="MSFT", name="Microsoft Corp")

        response = await authenticated_client.get(
            "/api/v1/stocks/MSFT/prices?period=1mo&format=ohlc"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["ticker"] == "MSFT"
        assert data["count"] == 0
        assert data["timestamps"] == []
        assert data["open"] == []

    @pytest.mark.asyncio
    async def test_prices_invalid_format(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Invalid format value should return 422 validation error."""
        await _insert_stock_with_signals(db_url, "AAPL")

        response = await authenticated_client.get("/api/v1/stocks/AAPL/prices?format=invalid")
        assert response.status_code == 422


# ═════════════════════════════════════════════════════════════════════════════
# Signal Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestSignals:
    """Tests for GET /api/v1/stocks/{ticker}/signals."""

    @pytest.mark.asyncio
    async def test_signals_requires_auth(self, client: AsyncClient) -> None:
        """Signal endpoint should return 401 without a JWT token."""
        response = await client.get("/api/v1/stocks/AAPL/signals")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_signals_not_found_stock(self, authenticated_client: AsyncClient) -> None:
        """Should return 404 for a ticker that doesn't exist."""
        response = await authenticated_client.get("/api/v1/stocks/FAKE/signals")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_signals_not_found_no_snapshot(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Should return 404 when stock exists but has no signal data."""
        await _insert_stock(db_url, ticker="MSFT", name="Microsoft Corp")

        response = await authenticated_client.get("/api/v1/stocks/MSFT/signals")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_signals_returns_full_response(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Should return nested signal response with all indicator groups."""
        await _insert_stock_with_signals(db_url, "AAPL")

        response = await authenticated_client.get("/api/v1/stocks/AAPL/signals")
        assert response.status_code == 200

        data = response.json()
        assert data["ticker"] == "AAPL"
        assert data["computed_at"] is not None

        # Verify nested structure
        assert "rsi" in data
        assert "value" in data["rsi"]
        assert "signal" in data["rsi"]

        assert "macd" in data
        assert "sma" in data
        assert "bollinger" in data
        assert "returns" in data
        assert "composite_score" in data

    @pytest.mark.asyncio
    async def test_signals_stale_flag(self, authenticated_client: AsyncClient, db_url: str) -> None:
        """Signals older than 24 hours should be flagged as stale."""
        engine = create_async_engine(db_url, echo=False)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            stock = StockFactory.build(ticker="OLD1", name="Old Corp")
            session.add(stock)
            await session.flush()

            # Signal from 48 hours ago (stale)
            signal = SignalSnapshotFactory.build(
                ticker="OLD1",
                computed_at=datetime.now(timezone.utc) - timedelta(hours=48),
            )
            session.add(signal)
            await session.commit()
        await engine.dispose()

        response = await authenticated_client.get("/api/v1/stocks/OLD1/signals")
        assert response.status_code == 200

        data = response.json()
        assert data["is_stale"] is True


# ═════════════════════════════════════════════════════════════════════════════
# Watchlist Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestWatchlist:
    """Tests for watchlist CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_watchlist_requires_auth(self, client: AsyncClient) -> None:
        """Watchlist endpoints should return 401 without a JWT token."""
        response = await client.get("/api/v1/stocks/watchlist")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_add_to_watchlist(self, authenticated_client: AsyncClient, db_url: str) -> None:
        """Should add a ticker to the user's watchlist."""
        await _insert_stock(db_url, ticker="AAPL", name="Apple Inc")

        response = await authenticated_client.post(
            "/api/v1/stocks/watchlist",
            json={"ticker": "AAPL"},
        )
        assert response.status_code == 201

        data = response.json()
        assert data["ticker"] == "AAPL"
        assert data["name"] == "Apple Inc"
        assert "added_at" in data

    @pytest.mark.asyncio
    async def test_add_to_watchlist_unknown_ticker(self, authenticated_client: AsyncClient) -> None:
        """Should return 404 when adding a ticker that doesn't exist."""
        response = await authenticated_client.post(
            "/api/v1/stocks/watchlist",
            json={"ticker": "FAKE"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_add_to_watchlist_duplicate(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Should return 409 when adding a ticker that's already in watchlist."""
        await _insert_stock(db_url, ticker="AAPL", name="Apple Inc")

        # Add once — should succeed
        response1 = await authenticated_client.post(
            "/api/v1/stocks/watchlist",
            json={"ticker": "AAPL"},
        )
        assert response1.status_code == 201

        # Add again — should fail with 409
        response2 = await authenticated_client.post(
            "/api/v1/stocks/watchlist",
            json={"ticker": "AAPL"},
        )
        assert response2.status_code == 409

    @pytest.mark.asyncio
    async def test_get_watchlist(self, authenticated_client: AsyncClient, db_url: str) -> None:
        """Should return the user's watchlist items."""
        await _insert_stock(db_url, ticker="AAPL", name="Apple Inc")

        # Add to watchlist
        await authenticated_client.post(
            "/api/v1/stocks/watchlist",
            json={"ticker": "AAPL"},
        )

        # Get watchlist
        response = await authenticated_client.get("/api/v1/stocks/watchlist")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_remove_from_watchlist(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Should remove a ticker from the user's watchlist."""
        await _insert_stock(db_url, ticker="AAPL", name="Apple Inc")

        # Add then remove
        await authenticated_client.post(
            "/api/v1/stocks/watchlist",
            json={"ticker": "AAPL"},
        )
        response = await authenticated_client.delete("/api/v1/stocks/watchlist/AAPL")
        assert response.status_code == 204

        # Verify it's gone
        get_response = await authenticated_client.get("/api/v1/stocks/watchlist")
        assert get_response.json() == []

    @pytest.mark.asyncio
    async def test_remove_from_watchlist_not_found(self, authenticated_client: AsyncClient) -> None:
        """Should return 404 when removing a ticker not in watchlist."""
        response = await authenticated_client.delete("/api/v1/stocks/watchlist/FAKE")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_watchlist(self, authenticated_client: AsyncClient) -> None:
        """Should return an empty list when the user has no watchlist items."""
        response = await authenticated_client.get("/api/v1/stocks/watchlist")
        assert response.status_code == 200
        assert response.json() == []


# ═════════════════════════════════════════════════════════════════════════════
# Recommendation Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestRecommendations:
    """Tests for GET /api/v1/stocks/recommendations."""

    @pytest.mark.asyncio
    async def test_recommendations_requires_auth(self, client: AsyncClient) -> None:
        """Recommendation endpoint should return 401 without a JWT token."""
        response = await client.get("/api/v1/stocks/recommendations")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_recommendations_empty(self, authenticated_client: AsyncClient) -> None:
        """Should return an empty list when no recommendations exist."""
        response = await authenticated_client.get("/api/v1/stocks/recommendations")
        assert response.status_code == 200
        data = response.json()
        assert data["recommendations"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_recommendations_returns_data(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Should return recent recommendations for the user."""
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        await _insert_stock_with_signals(db_url, "AAPL", user_id=user.id)

        response = await authenticated_client.get("/api/v1/stocks/recommendations")
        assert response.status_code == 200

        data = response.json()
        recs = data["recommendations"]
        assert data["total"] >= 1
        assert len(recs) >= 1
        assert recs[0]["ticker"] == "AAPL"
        assert "action" in recs[0]
        assert "confidence" in recs[0]
        assert "composite_score" in recs[0]

    @pytest.mark.asyncio
    async def test_recommendations_filter_by_action(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Should filter recommendations by action parameter."""
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        await _insert_stock_with_signals(db_url, "AAPL", user_id=user.id)

        # The default factory creates WATCH recommendations
        response = await authenticated_client.get("/api/v1/stocks/recommendations?action=WATCH")
        assert response.status_code == 200
        data = response.json()
        assert all(r["action"] == "WATCH" for r in data["recommendations"])

    @pytest.mark.asyncio
    async def test_recommendations_filter_no_match(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Filtering for an action that doesn't match should return empty."""
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        await _insert_stock_with_signals(db_url, "AAPL", user_id=user.id)

        # Factory creates WATCH, so BUY should return empty
        response = await authenticated_client.get("/api/v1/stocks/recommendations?action=BUY")
        assert response.status_code == 200
        data = response.json()
        assert data["recommendations"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_stale_recommendations_excluded(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Recommendations older than 24 hours should NOT be returned."""
        user = authenticated_client._test_user  # type: ignore[attr-defined]

        engine = create_async_engine(db_url, echo=False)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            stock = StockFactory.build(ticker="OLD2", name="Old Corp")
            session.add(stock)
            await session.flush()

            # Old recommendation (48 hours ago)
            rec = RecommendationSnapshotFactory.build(
                ticker="OLD2",
                user_id=user.id,
                generated_at=datetime.now(timezone.utc) - timedelta(hours=48),
            )
            session.add(rec)
            await session.commit()
        await engine.dispose()

        response = await authenticated_client.get("/api/v1/stocks/recommendations")
        assert response.status_code == 200
        # Old recommendation should be excluded
        data = response.json()
        assert all(r["ticker"] != "OLD2" for r in data["recommendations"])

    @pytest.mark.asyncio
    async def test_recommendation_includes_stock_name(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Recommendation response should include the stock name from a JOIN."""
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        await _insert_stock_with_signals(db_url, "MSFT", user_id=user.id)

        response = await authenticated_client.get("/api/v1/stocks/recommendations")
        assert response.status_code == 200

        data = response.json()
        recs = data["recommendations"]
        msft_recs = [r for r in recs if r["ticker"] == "MSFT"]
        assert len(msft_recs) >= 1
        assert msft_recs[0]["name"] == "MSFT Inc"


# ═════════════════════════════════════════════════════════════════════════════
# Stock Intelligence Tests — KAN-320 regression
# ═════════════════════════════════════════════════════════════════════════════


class TestStockIntelligence:
    """Tests for GET /api/v1/stocks/{ticker}/intelligence.

    KAN-320: Endpoint returned 500 on first call due to missing
    return_exceptions=True on asyncio.gather() — any exception escaping a
    yfinance tool (e.g. network timeout on cold start) propagated as an
    unhandled 500 instead of being caught and replaced with a safe default.
    """

    @pytest.mark.asyncio
    async def test_intelligence_requires_auth(self, client: AsyncClient) -> None:
        """Intelligence endpoint should return 401 without a JWT token."""
        response = await client.get("/api/v1/stocks/AAPL/intelligence")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_intelligence_not_found(self, authenticated_client: AsyncClient) -> None:
        """Should return 404 or 422 for a ticker not in the database."""
        response = await authenticated_client.get("/api/v1/stocks/DOESNOTEXIST/intelligence")
        assert response.status_code in (404, 422)

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_intelligence_happy_path_all_tools_succeed(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """Happy path: all yfinance tools return data, response is 200.

        Regression for KAN-320 — verifies the endpoint returns 200 even when
        all tools succeed and return realistic data.
        """
        from unittest.mock import patch

        await _insert_stock(db_url, ticker="AAPL", name="Apple Inc")

        mock_upgrades = [
            {
                "firm": "UBS",
                "to_grade": "Buy",
                "from_grade": "Neutral",
                "action": "up",
                "date": "2026-03-20",
            }
        ]
        mock_insider = [
            {
                "insider_name": "Tim Cook",
                "relation": "CEO",
                "transaction_type": "Sale",
                "shares": 50000,
                "value": 8500000.0,
                "date": "2026-03-01",
            }
        ]

        with (
            patch(
                "backend.routers.stocks.data.fetch_upgrades_downgrades",
                return_value=mock_upgrades,
            ),
            patch(
                "backend.routers.stocks.data.fetch_insider_transactions",
                return_value=mock_insider,
            ),
            patch(
                "backend.routers.stocks.data.fetch_next_earnings_date",
                return_value="2026-04-28",
            ),
            patch(
                "backend.routers.stocks.data.fetch_eps_revisions",
                return_value=None,
            ),
            patch(
                "backend.routers.stocks.data.fetch_short_interest",
                return_value={
                    "short_percent_of_float": 4.23,
                    "short_ratio": 2.5,
                    "shares_short": 15_000_000,
                },
            ),
        ):
            response = await authenticated_client.get("/api/v1/stocks/AAPL/intelligence")

        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert len(data["upgrades_downgrades"]) == 1
        assert data["upgrades_downgrades"][0]["firm"] == "UBS"
        assert len(data["insider_transactions"]) == 1
        assert data["insider_transactions"][0]["insider_name"] == "Tim Cook"
        assert data["next_earnings_date"] == "2026-04-28"
        assert data["short_interest"]["short_percent_of_float"] == 4.23
        assert "fetched_at" in data

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_intelligence_survives_partial_tool_failure(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """KAN-320 regression: endpoint must return 200 when some tools raise.

        Before the fix, asyncio.gather() lacked return_exceptions=True.
        Any exception escaping a tool's own try/except (e.g. a network
        timeout on cold start, a yfinance BaseException on first call)
        propagated directly as an unhandled 500.

        After the fix, exceptions are caught per-tool and replaced with safe
        empty defaults so the remaining tools' data is still returned.
        """
        from unittest.mock import patch

        await _insert_stock(db_url, ticker="TSLA", name="Tesla Inc")

        # Two tools raise, three succeed — endpoint must still return 200
        with (
            patch(
                "backend.routers.stocks.data.fetch_upgrades_downgrades",
                side_effect=RuntimeError("Yahoo Finance cold-start timeout"),
            ),
            patch(
                "backend.routers.stocks.data.fetch_insider_transactions",
                side_effect=ConnectionError("network unavailable on first call"),
            ),
            patch(
                "backend.routers.stocks.data.fetch_next_earnings_date",
                return_value="2026-07-22",
            ),
            patch(
                "backend.routers.stocks.data.fetch_eps_revisions",
                return_value=None,
            ),
            patch(
                "backend.routers.stocks.data.fetch_short_interest",
                return_value=None,
            ),
        ):
            response = await authenticated_client.get("/api/v1/stocks/TSLA/intelligence")

        # Must be 200, not 500
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "TSLA"
        # Failed tools fall back to empty defaults
        assert data["upgrades_downgrades"] == []
        assert data["insider_transactions"] == []
        # Successful tools still return their data
        assert data["next_earnings_date"] == "2026-07-22"
        assert "fetched_at" in data

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_intelligence_survives_all_tools_failing(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """KAN-320 regression: endpoint returns 200 with empty data when all tools fail.

        If all five yfinance tools raise (e.g. Yahoo Finance is down), the
        response should be a valid 200 with all fields at their empty defaults
        rather than a 500.
        """
        from unittest.mock import patch

        await _insert_stock(db_url, ticker="NVDA", name="NVIDIA Corp")

        with (
            patch(
                "backend.routers.stocks.data.fetch_upgrades_downgrades",
                side_effect=Exception("all tools down"),
            ),
            patch(
                "backend.routers.stocks.data.fetch_insider_transactions",
                side_effect=Exception("all tools down"),
            ),
            patch(
                "backend.routers.stocks.data.fetch_next_earnings_date",
                side_effect=Exception("all tools down"),
            ),
            patch(
                "backend.routers.stocks.data.fetch_eps_revisions",
                side_effect=Exception("all tools down"),
            ),
            patch(
                "backend.routers.stocks.data.fetch_short_interest",
                side_effect=Exception("all tools down"),
            ),
        ):
            response = await authenticated_client.get("/api/v1/stocks/NVDA/intelligence")

        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "NVDA"
        assert data["upgrades_downgrades"] == []
        assert data["insider_transactions"] == []
        assert data["next_earnings_date"] is None
        assert data["eps_revisions"] is None
        assert data["short_interest"] is None
