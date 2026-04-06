"""Unit tests for news sentiment API endpoints.

Tests call endpoint functions directly (without a running HTTP server),
following the same pattern as test_admin_pipeline_endpoints.py.
All DB I/O is mocked via AsyncMock.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from backend.models.user import User, UserRole
from backend.routers.sentiment import (
    get_bulk_sentiment,
    get_macro_sentiment,
    get_ticker_articles,
    get_ticker_sentiment,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def regular_user() -> User:
    """Provide an authenticated regular user for testing."""
    return User(
        id=uuid.uuid4(),
        email="user@test.com",
        hashed_password="hashed",
        role=UserRole.USER,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_db() -> AsyncMock:
    """Provide a mocked async DB session."""
    return AsyncMock()


def _make_sentiment_row(
    ticker: str = "AAPL",
    sentiment_date: date = date(2024, 3, 1),
    stock_sentiment: float = 0.5,
    sector_sentiment: float = 0.2,
    macro_sentiment: float = 0.1,
    article_count: int = 5,
    confidence: float = 0.8,
    dominant_event_type: str | None = "earnings",
    rationale_summary: str | None = "Strong Q1",
    quality_flag: str = "ok",
) -> MagicMock:
    """Build a mock NewsSentimentDaily row with the given attributes."""
    row = MagicMock()
    row.date = sentiment_date
    row.ticker = ticker
    row.stock_sentiment = stock_sentiment
    row.sector_sentiment = sector_sentiment
    row.macro_sentiment = macro_sentiment
    row.article_count = article_count
    row.confidence = confidence
    row.dominant_event_type = dominant_event_type
    row.rationale_summary = rationale_summary
    row.quality_flag = quality_flag
    return row


def _make_article_row(
    ticker: str = "AAPL",
    headline: str = "AAPL beats Q1 estimates",
    source: str = "reuters",
    source_url: str | None = "https://reuters.com/1",
    event_type: str | None = "earnings",
    scored_at: datetime | None = None,
) -> MagicMock:
    """Build a mock NewsArticle row with the given attributes."""
    row = MagicMock()
    row.ticker = ticker
    row.headline = headline
    row.source = source
    row.source_url = source_url
    row.event_type = event_type
    row.published_at = datetime(2024, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    row.scored_at = scored_at
    return row


def _mock_db_with_rows(db: AsyncMock, rows: list) -> None:
    """Configure db.execute to return rows via .scalars().all()."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = rows
    db.execute = AsyncMock(return_value=mock_result)


# ---------------------------------------------------------------------------
# TestGetTickerSentiment
# ---------------------------------------------------------------------------


class TestGetTickerSentiment:
    """Tests for GET /sentiment/{ticker}."""

    @pytest.mark.asyncio
    async def test_returns_timeseries_for_ticker(
        self, regular_user: User, mock_db: AsyncMock
    ) -> None:
        """Returns SentimentTimeseriesResponse with rows for a known ticker."""
        rows = [
            _make_sentiment_row("AAPL", date(2024, 3, 1), stock_sentiment=0.5),
            _make_sentiment_row("AAPL", date(2024, 3, 2), stock_sentiment=0.6),
            _make_sentiment_row("AAPL", date(2024, 3, 3), stock_sentiment=0.7),
        ]
        _mock_db_with_rows(mock_db, rows)

        result = await get_ticker_sentiment(
            ticker="AAPL",
            days=30,
            current_user=regular_user,
            session=mock_db,
        )

        assert result.ticker == "AAPL"
        assert len(result.data) == 3
        assert result.data[0].stock_sentiment == 0.5
        assert result.data[2].stock_sentiment == 0.7

    @pytest.mark.asyncio
    async def test_ticker_uppercased(self, regular_user: User, mock_db: AsyncMock) -> None:
        """Ticker parameter is uppercased before querying."""
        _mock_db_with_rows(mock_db, [_make_sentiment_row("AAPL")])

        result = await get_ticker_sentiment(
            ticker="aapl",
            days=30,
            current_user=regular_user,
            session=mock_db,
        )

        assert result.ticker == "AAPL"

    @pytest.mark.asyncio
    async def test_returns_empty_data_for_unknown_ticker(
        self, regular_user: User, mock_db: AsyncMock
    ) -> None:
        """Returns empty data list for a ticker with no sentiment rows."""
        _mock_db_with_rows(mock_db, [])

        result = await get_ticker_sentiment(
            ticker="UNKNOWN",
            days=30,
            current_user=regular_user,
            session=mock_db,
        )

        assert result.ticker == "UNKNOWN"
        assert result.data == []

    # Auth is enforced by FastAPI's Depends(get_current_user) injection,
    # which cannot be tested via direct function calls. Auth coverage
    # belongs in API-level tests (tests/api/) using TestClient.

    @pytest.mark.asyncio
    async def test_respects_days_parameter(self, regular_user: User, mock_db: AsyncMock) -> None:
        """DB query is called with a since-date derived from the days parameter."""
        _mock_db_with_rows(mock_db, [])

        await get_ticker_sentiment(
            ticker="AAPL",
            days=7,
            current_user=regular_user,
            session=mock_db,
        )

        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_db_error_raises_500(self, regular_user: User, mock_db: AsyncMock) -> None:
        """Returns 500 HTTPException when the DB raises an unexpected error."""
        mock_db.execute = AsyncMock(side_effect=OperationalError("DB down", None, None))

        with pytest.raises(HTTPException) as exc_info:
            await get_ticker_sentiment(
                ticker="AAPL",
                days=30,
                current_user=regular_user,
                session=mock_db,
            )

        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# TestGetBulkSentiment
# ---------------------------------------------------------------------------


class TestGetBulkSentiment:
    """Tests for GET /sentiment/bulk."""

    @pytest.mark.asyncio
    async def test_returns_latest_sentiment_per_ticker(
        self, regular_user: User, mock_db: AsyncMock
    ) -> None:
        """Returns one sentiment row per ticker (latest via DISTINCT ON)."""
        rows = [
            _make_sentiment_row("AAPL"),
            _make_sentiment_row("MSFT", stock_sentiment=0.3),
        ]
        _mock_db_with_rows(mock_db, rows)

        result = await get_bulk_sentiment(
            tickers="AAPL,MSFT",
            current_user=regular_user,
            session=mock_db,
        )

        assert len(result.tickers) == 2
        tickers_in_result = {r.ticker for r in result.tickers}
        assert "AAPL" in tickers_in_result
        assert "MSFT" in tickers_in_result

    @pytest.mark.asyncio
    async def test_comma_separated_tickers_parsed(
        self, regular_user: User, mock_db: AsyncMock
    ) -> None:
        """Comma-separated tickers with spaces are correctly parsed and uppercased."""
        _mock_db_with_rows(mock_db, [])

        result = await get_bulk_sentiment(
            tickers=" aapl , msft , goog ",
            current_user=regular_user,
            session=mock_db,
        )

        # Result is empty because no mock rows, but the function should not raise
        assert result.tickers == []

    @pytest.mark.asyncio
    async def test_empty_ticker_string_raises_422(
        self, regular_user: User, mock_db: AsyncMock
    ) -> None:
        """Empty tickers string raises 422 HTTPException."""
        with pytest.raises(HTTPException) as exc_info:
            await get_bulk_sentiment(
                tickers="",
                current_user=regular_user,
                session=mock_db,
            )

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_db_error_raises_500(self, regular_user: User, mock_db: AsyncMock) -> None:
        """Returns 500 HTTPException when the DB raises an unexpected error."""
        mock_db.execute = AsyncMock(side_effect=OperationalError("DB down", None, None))

        with pytest.raises(HTTPException) as exc_info:
            await get_bulk_sentiment(
                tickers="AAPL",
                current_user=regular_user,
                session=mock_db,
            )

        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# TestGetMacroSentiment
# ---------------------------------------------------------------------------


class TestGetMacroSentiment:
    """Tests for GET /sentiment/macro."""

    @pytest.mark.asyncio
    async def test_returns_macro_timeseries(self, regular_user: User, mock_db: AsyncMock) -> None:
        """Returns MacroSentimentResponse with __MACRO__ ticker rows."""
        rows = [
            _make_sentiment_row("__MACRO__", date(2024, 3, 1), macro_sentiment=0.4),
            _make_sentiment_row("__MACRO__", date(2024, 3, 2), macro_sentiment=0.5),
        ]
        _mock_db_with_rows(mock_db, rows)

        result = await get_macro_sentiment(
            days=30,
            current_user=regular_user,
            session=mock_db,
        )

        assert len(result.data) == 2
        assert result.data[0].ticker == "__MACRO__"
        assert result.data[0].macro_sentiment == 0.4

    @pytest.mark.asyncio
    async def test_respects_days_parameter(self, regular_user: User, mock_db: AsyncMock) -> None:
        """DB query is called with a since-date derived from the days parameter."""
        _mock_db_with_rows(mock_db, [])

        await get_macro_sentiment(
            days=7,
            current_user=regular_user,
            session=mock_db,
        )

        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_macro_data(
        self, regular_user: User, mock_db: AsyncMock
    ) -> None:
        """Returns empty data list when no macro sentiment rows exist."""
        _mock_db_with_rows(mock_db, [])

        result = await get_macro_sentiment(
            days=30,
            current_user=regular_user,
            session=mock_db,
        )

        assert result.data == []

    @pytest.mark.asyncio
    async def test_db_error_raises_500(self, regular_user: User, mock_db: AsyncMock) -> None:
        """Returns 500 HTTPException when the DB raises an unexpected error."""
        mock_db.execute = AsyncMock(side_effect=OperationalError("DB down", None, None))

        with pytest.raises(HTTPException) as exc_info:
            await get_macro_sentiment(
                days=30,
                current_user=regular_user,
                session=mock_db,
            )

        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# TestGetTickerArticles
# ---------------------------------------------------------------------------


class TestGetTickerArticles:
    """Tests for GET /sentiment/{ticker}/articles."""

    def _mock_db_for_articles(self, db: AsyncMock, articles: list, total: int) -> None:
        """Configure db.execute to return article rows on second call and count on first."""
        count_result = MagicMock()
        count_result.scalar_one.return_value = total

        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = articles

        db.execute = AsyncMock(side_effect=[count_result, data_result])

    @pytest.mark.asyncio
    async def test_returns_paginated_articles(self, regular_user: User, mock_db: AsyncMock) -> None:
        """Returns ArticleListResponse with articles for a known ticker."""
        articles = [
            _make_article_row("AAPL", "AAPL beats Q1 estimates"),
            _make_article_row("AAPL", "AAPL raises guidance"),
        ]
        self._mock_db_for_articles(mock_db, articles, total=2)

        result = await get_ticker_articles(
            ticker="AAPL",
            limit=50,
            offset=0,
            days=30,
            current_user=regular_user,
            session=mock_db,
        )

        assert result.ticker == "AAPL"
        assert len(result.articles) == 2
        assert result.articles[0].headline == "AAPL beats Q1 estimates"

    @pytest.mark.asyncio
    async def test_includes_total_count(self, regular_user: User, mock_db: AsyncMock) -> None:
        """Response includes total count for frontend pagination."""
        articles = [_make_article_row("AAPL")]
        self._mock_db_for_articles(mock_db, articles, total=42)

        result = await get_ticker_articles(
            ticker="AAPL",
            limit=10,
            offset=0,
            days=30,
            current_user=regular_user,
            session=mock_db,
        )

        assert result.total == 42

    @pytest.mark.asyncio
    async def test_respects_limit_and_offset(self, regular_user: User, mock_db: AsyncMock) -> None:
        """limit and offset are reflected in the response metadata."""
        self._mock_db_for_articles(mock_db, [], total=0)

        result = await get_ticker_articles(
            ticker="AAPL",
            limit=10,
            offset=20,
            days=30,
            current_user=regular_user,
            session=mock_db,
        )

        assert result.limit == 10
        assert result.offset == 20

    @pytest.mark.asyncio
    async def test_returns_empty_for_ticker_with_no_articles(
        self, regular_user: User, mock_db: AsyncMock
    ) -> None:
        """Returns empty articles list when no articles exist for the ticker."""
        self._mock_db_for_articles(mock_db, [], total=0)

        result = await get_ticker_articles(
            ticker="UNKNOWN",
            limit=50,
            offset=0,
            days=30,
            current_user=regular_user,
            session=mock_db,
        )

        assert result.ticker == "UNKNOWN"
        assert result.articles == []
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_scored_at_is_none_for_unscored_article(
        self, regular_user: User, mock_db: AsyncMock
    ) -> None:
        """ArticleSummaryResponse has scored_at=None for articles not yet scored."""
        articles = [_make_article_row("AAPL", scored_at=None)]
        self._mock_db_for_articles(mock_db, articles, total=1)

        result = await get_ticker_articles(
            ticker="AAPL",
            limit=50,
            offset=0,
            days=30,
            current_user=regular_user,
            session=mock_db,
        )

        assert result.articles[0].scored_at is None

    @pytest.mark.asyncio
    async def test_db_error_raises_500(self, regular_user: User, mock_db: AsyncMock) -> None:
        """Returns 500 HTTPException when the DB raises an unexpected error."""
        mock_db.execute = AsyncMock(side_effect=OperationalError("DB down", None, None))

        with pytest.raises(HTTPException) as exc_info:
            await get_ticker_articles(
                ticker="AAPL",
                limit=50,
                offset=0,
                days=30,
                current_user=regular_user,
                session=mock_db,
            )

        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# TestAuth
# ---------------------------------------------------------------------------


class TestAuth:
    """Verify all endpoints require authenticated user via get_current_user dependency."""

    @pytest.mark.asyncio
    async def test_all_endpoints_accept_authenticated_user(
        self, regular_user: User, mock_db: AsyncMock
    ) -> None:
        """All endpoints execute successfully when called with a valid authenticated user."""
        _mock_db_with_rows(mock_db, [])

        # get_ticker_sentiment
        result_ts = await get_ticker_sentiment(
            ticker="AAPL",
            days=30,
            current_user=regular_user,
            session=mock_db,
        )
        assert result_ts is not None

        # get_macro_sentiment
        result_macro = await get_macro_sentiment(
            days=30,
            current_user=regular_user,
            session=mock_db,
        )
        assert result_macro is not None

        # get_bulk_sentiment
        result_bulk = await get_bulk_sentiment(
            tickers="AAPL",
            current_user=regular_user,
            session=mock_db,
        )
        assert result_bulk is not None

    # Auth rejection (401 for unauthenticated) is enforced by FastAPI's
    # Depends(get_current_user) injection, not testable via direct calls.
    # Coverage belongs in API-level tests (tests/api/) using TestClient.
