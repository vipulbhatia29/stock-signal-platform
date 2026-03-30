"""API tests for the dashboard news endpoint."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import (
    PortfolioFactory,
    RecommendationSnapshotFactory,
    StockFactory,
)

pytestmark = pytest.mark.asyncio


class TestDashboardNewsAuth:
    """Authentication tests for GET /api/v1/news/dashboard."""

    async def test_unauthenticated_returns_401(self, client):
        """Unauthenticated request should return 401."""
        resp = await client.get("/api/v1/news/dashboard")
        assert resp.status_code == 401

    async def test_authenticated_returns_200(self, authenticated_client):
        """Authenticated user with empty portfolio gets 200 with empty articles."""
        resp = await authenticated_client.get("/api/v1/news/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["articles"] == []
        assert data["ticker_count"] == 0


class TestDashboardNewsResponseShape:
    """Response structure tests for GET /api/v1/news/dashboard."""

    async def test_dashboard_news_response_shape(self, authenticated_client):
        """Response matches DashboardNewsResponse schema."""
        resp = await authenticated_client.get("/api/v1/news/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "articles" in data
        assert "ticker_count" in data
        assert isinstance(data["articles"], list)
        assert isinstance(data["ticker_count"], int)


class TestDashboardNewsEmpty:
    """Tests for users with no portfolio and no recommendations."""

    async def test_empty_portfolio_returns_empty(self, authenticated_client):
        """User with no portfolio and no recommendations gets empty articles."""
        resp = await authenticated_client.get("/api/v1/news/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["articles"] == []
        assert data["ticker_count"] == 0


class TestDashboardNewsWithData:
    """Tests for users with portfolio positions or recommendations."""

    async def test_portfolio_tickers_trigger_news_fetch(self, authenticated_client, db_session):
        """User with portfolio positions should get news articles."""
        user = authenticated_client._test_user  # type: ignore[attr-defined]

        # Create stock + portfolio + position
        stock = StockFactory.build(ticker="AAPL")
        db_session.add(stock)
        await db_session.flush()

        portfolio = PortfolioFactory.build(user_id=user.id)
        db_session.add(portfolio)
        await db_session.flush()

        from backend.models.portfolio import Position

        position = Position(
            portfolio_id=portfolio.id,
            ticker="AAPL",
            shares=Decimal("10"),
            avg_cost_basis=Decimal("150.00"),
            opened_at=datetime.now(timezone.utc),
        )
        db_session.add(position)
        await db_session.commit()

        mock_articles = [
            {
                "title": "Apple earnings beat expectations",
                "link": "https://example.com/apple-1",
                "publisher": "Test News",
                "published": "2026-03-30T10:00:00Z",
                "source": "google_news",
            },
        ]

        with patch(
            "backend.routers.news.fetch_google_news_rss",
            new_callable=AsyncMock,
            return_value=mock_articles,
        ):
            resp = await authenticated_client.get("/api/v1/news/dashboard")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker_count"] == 1
        assert len(data["articles"]) == 1
        assert data["articles"][0]["title"] == "Apple earnings beat expectations"
        assert data["articles"][0]["portfolio_ticker"] == "AAPL"

    async def test_recommendation_tickers_trigger_news_fetch(
        self, authenticated_client, db_session
    ):
        """User with BUY recommendations should get news for those tickers."""
        user = authenticated_client._test_user  # type: ignore[attr-defined]

        # Create stock + recommendation
        stock = StockFactory.build(ticker="MSFT")
        db_session.add(stock)
        await db_session.flush()

        rec = RecommendationSnapshotFactory.build(
            ticker="MSFT",
            user_id=user.id,
            action="BUY",
            composite_score=9.0,
            generated_at=datetime.now(timezone.utc),
        )
        db_session.add(rec)
        await db_session.commit()

        mock_articles = [
            {
                "title": "Microsoft AI push",
                "link": "https://example.com/msft-1",
                "publisher": "Test News",
                "published": "2026-03-30T10:00:00Z",
                "source": "google_news",
            },
        ]

        with patch(
            "backend.routers.news.fetch_google_news_rss",
            new_callable=AsyncMock,
            return_value=mock_articles,
        ):
            resp = await authenticated_client.get("/api/v1/news/dashboard")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker_count"] == 1
        assert len(data["articles"]) == 1
        assert data["articles"][0]["portfolio_ticker"] == "MSFT"

    async def test_deduplicates_tickers(self, authenticated_client, db_session):
        """Portfolio and recommendation tickers should be deduplicated."""
        user = authenticated_client._test_user  # type: ignore[attr-defined]

        # Create stock in both portfolio and recommendations
        stock = StockFactory.build(ticker="GOOG")
        db_session.add(stock)
        await db_session.flush()

        portfolio = PortfolioFactory.build(user_id=user.id)
        db_session.add(portfolio)
        await db_session.flush()

        from backend.models.portfolio import Position

        position = Position(
            portfolio_id=portfolio.id,
            ticker="GOOG",
            shares=Decimal("5"),
            avg_cost_basis=Decimal("140.00"),
            opened_at=datetime.now(timezone.utc),
        )
        db_session.add(position)

        rec = RecommendationSnapshotFactory.build(
            ticker="GOOG",
            user_id=user.id,
            action="STRONG_BUY",
            composite_score=9.5,
            generated_at=datetime.now(timezone.utc),
        )
        db_session.add(rec)
        await db_session.commit()

        with patch(
            "backend.routers.news.fetch_google_news_rss",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await authenticated_client.get("/api/v1/news/dashboard")

        assert resp.status_code == 200
        data = resp.json()
        # GOOG appears once (deduplicated)
        assert data["ticker_count"] == 1

    async def test_news_fetch_failure_returns_partial(self, authenticated_client, db_session):
        """If news fetch fails for a ticker, other tickers still return."""
        user = authenticated_client._test_user  # type: ignore[attr-defined]

        stock1 = StockFactory.build(ticker="NVDA")
        stock2 = StockFactory.build(ticker="AMD")
        db_session.add_all([stock1, stock2])
        await db_session.flush()

        portfolio = PortfolioFactory.build(user_id=user.id)
        db_session.add(portfolio)
        await db_session.flush()

        from backend.models.portfolio import Position

        pos1 = Position(
            portfolio_id=portfolio.id,
            ticker="NVDA",
            shares=Decimal("10"),
            avg_cost_basis=Decimal("800.00"),
            opened_at=datetime.now(timezone.utc),
        )
        pos2 = Position(
            portfolio_id=portfolio.id,
            ticker="AMD",
            shares=Decimal("20"),
            avg_cost_basis=Decimal("150.00"),
            opened_at=datetime.now(timezone.utc),
        )
        db_session.add_all([pos1, pos2])
        await db_session.commit()

        call_count = 0

        async def _mock_fetch(ticker):
            nonlocal call_count
            call_count += 1
            if ticker == "NVDA":
                raise RuntimeError("Network error")
            return [
                {
                    "title": f"{ticker} news",
                    "link": f"https://example.com/{ticker}",
                    "publisher": "Test",
                    "published": "2026-03-30T10:00:00Z",
                    "source": "google_news",
                },
            ]

        with patch(
            "backend.routers.news.fetch_google_news_rss",
            side_effect=_mock_fetch,
        ):
            resp = await authenticated_client.get("/api/v1/news/dashboard")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker_count"] == 2
        # Only AMD articles come through (NVDA fetch failed)
        assert len(data["articles"]) == 1
        assert data["articles"][0]["portfolio_ticker"] == "AMD"
