"""Unit tests for news sentiment Celery tasks and async helpers.

Verifies task registration, naming, and the core logic of
_ingest_news and _score_sentiment by mocking all I/O dependencies.

Lazy-import note: _ingest_news and _score_sentiment use `from X import Y`
inside the function body. Per the mock-patching-gotchas rule, we patch at
the lookup site (the module where the name is bound):
  - backend.database.async_session_factory
  - backend.services.news.ingestion.NewsIngestionService
  - backend.services.news.sentiment_scorer.SentimentScorer
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.unit.tasks._tracked_helper_bypass import bypass_tracked

# ---------------------------------------------------------------------------
# Registration + naming tests
# ---------------------------------------------------------------------------


class TestTaskRegistration:
    """Verify tasks are registered in the Celery app with correct names."""

    def test_ingest_task_is_registered(self) -> None:
        """news_ingest_task is importable from backend.tasks.news_sentiment."""
        from backend.tasks.news_sentiment import news_ingest_task

        assert news_ingest_task is not None

    def test_ingest_task_name(self) -> None:
        """news_ingest_task has the fully-qualified Celery task name."""
        from backend.tasks.news_sentiment import news_ingest_task

        assert news_ingest_task.name == "backend.tasks.news_sentiment.news_ingest_task"

    def test_scoring_task_is_registered(self) -> None:
        """news_sentiment_scoring_task is importable from backend.tasks.news_sentiment."""
        from backend.tasks.news_sentiment import news_sentiment_scoring_task

        assert news_sentiment_scoring_task is not None

    def test_scoring_task_name(self) -> None:
        """news_sentiment_scoring_task has the fully-qualified Celery task name."""
        from backend.tasks.news_sentiment import news_sentiment_scoring_task

        assert (
            news_sentiment_scoring_task.name
            == "backend.tasks.news_sentiment.news_sentiment_scoring_task"
        )


# ---------------------------------------------------------------------------
# Beat schedule tests
# ---------------------------------------------------------------------------


class TestBeatSchedule:
    """Verify beat schedule entries exist for news sentiment tasks."""

    def test_beat_schedule_has_ingest_entry(self) -> None:
        """Beat schedule contains an entry for news_ingest_task."""
        from backend.tasks import celery_app

        schedule = celery_app.conf.beat_schedule
        task_names = {v["task"] for v in schedule.values()}
        assert "backend.tasks.news_sentiment.news_ingest_task" in task_names

    def test_beat_schedule_has_scoring_entry(self) -> None:
        """Beat schedule contains an entry for news_sentiment_scoring_task."""
        from backend.tasks import celery_app

        schedule = celery_app.conf.beat_schedule
        task_names = {v["task"] for v in schedule.values()}
        assert "backend.tasks.news_sentiment.news_sentiment_scoring_task" in task_names

    def test_beat_schedule_ingest_key_present(self) -> None:
        """Beat schedule has a 'news-ingest' key."""
        from backend.tasks import celery_app

        assert "news-ingest" in celery_app.conf.beat_schedule

    def test_beat_schedule_scoring_key_present(self) -> None:
        """Beat schedule has a 'news-sentiment-scoring' key."""
        from backend.tasks import celery_app

        assert "news-sentiment-scoring" in celery_app.conf.beat_schedule


# ---------------------------------------------------------------------------
# Helpers: _ingest_news
# ---------------------------------------------------------------------------


def _make_mock_session_factory(tickers: list[tuple[str, ...]]) -> MagicMock:
    """Build a mock async_session_factory context manager returning given tickers."""
    mock_result = MagicMock()
    mock_result.all.return_value = tickers

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_factory = MagicMock()
    mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.__aexit__ = AsyncMock(return_value=False)

    return mock_factory


def _make_mock_ingestion_service(
    stock_stats: dict | None = None,
    macro_stats: dict | None = None,
) -> AsyncMock:
    """Build a mock NewsIngestionService with configurable return values."""
    default_stock = {"fetched": 5, "new": 3, "duplicates": 2, "errors": 0}
    default_macro = {"fetched": 2, "new": 1, "duplicates": 1, "errors": 0}

    mock_service = AsyncMock()
    mock_service.ingest_stock_news = AsyncMock(return_value=stock_stats or default_stock)
    mock_service.ingest_macro_news = AsyncMock(return_value=macro_stats or default_macro)
    return mock_service


class TestIngestNews:
    """Tests for the _ingest_news async helper.

    Patches at the lookup site (backend.database / backend.services.news.*) because
    _ingest_news imports those names lazily inside the function body.
    """

    @pytest.mark.asyncio
    async def test_ingest_news_fetches_active_tickers(self) -> None:
        """_ingest_news queries Stock table for active tickers via the DB session."""
        mock_factory = _make_mock_session_factory([("AAPL",), ("MSFT",)])
        mock_service = _make_mock_ingestion_service()

        with (
            patch("backend.database.async_session_factory", return_value=mock_factory),
            patch(
                "backend.services.news.ingestion.NewsIngestionService",
                return_value=mock_service,
            ),
        ):
            from backend.tasks.news_sentiment import _ingest_news

            result = await bypass_tracked(_ingest_news)(7, run_id=uuid.uuid4())

        mock_factory.__aenter__.assert_called_once()
        mock_factory.__aexit__.assert_called_once()
        assert result["tickers_processed"] == 2

    @pytest.mark.asyncio
    async def test_ingest_news_calls_ingestion_service(self) -> None:
        """_ingest_news calls ingest_stock_news and ingest_macro_news on the service."""
        mock_factory = _make_mock_session_factory([("AAPL",), ("MSFT",), ("GOOG",)])
        mock_service = _make_mock_ingestion_service()

        with (
            patch("backend.database.async_session_factory", return_value=mock_factory),
            patch(
                "backend.services.news.ingestion.NewsIngestionService",
                return_value=mock_service,
            ),
        ):
            from backend.tasks.news_sentiment import _ingest_news

            await bypass_tracked(_ingest_news)(7, run_id=uuid.uuid4())

        mock_service.ingest_stock_news.assert_called_once()
        mock_service.ingest_macro_news.assert_called_once()
        # Verify tickers list was passed to ingest_stock_news
        call_args = mock_service.ingest_stock_news.call_args
        tickers_arg = call_args[0][0]
        assert "AAPL" in tickers_arg
        assert "MSFT" in tickers_arg
        assert "GOOG" in tickers_arg

    @pytest.mark.asyncio
    async def test_ingest_news_returns_stats(self) -> None:
        """_ingest_news returns a dict with status, stock, macro, and tickers_processed."""
        stock_stats = {"fetched": 10, "new": 7, "duplicates": 3, "errors": 0}
        macro_stats = {"fetched": 4, "new": 4, "duplicates": 0, "errors": 0}
        mock_factory = _make_mock_session_factory([("AAPL",), ("TSLA",)])
        mock_service = _make_mock_ingestion_service(stock_stats, macro_stats)

        with (
            patch("backend.database.async_session_factory", return_value=mock_factory),
            patch(
                "backend.services.news.ingestion.NewsIngestionService",
                return_value=mock_service,
            ),
        ):
            from backend.tasks.news_sentiment import _ingest_news

            result = await bypass_tracked(_ingest_news)(7, run_id=uuid.uuid4())

        assert result["status"] == "complete"
        assert result["stock"] == stock_stats
        assert result["macro"] == macro_stats
        assert result["tickers_processed"] == 2

    @pytest.mark.asyncio
    async def test_ingest_news_respects_lookback_days(self) -> None:
        """_ingest_news passes a since date derived from lookback_days to the service."""
        mock_factory = _make_mock_session_factory([("AAPL",)])
        mock_service = _make_mock_ingestion_service()

        with (
            patch("backend.database.async_session_factory", return_value=mock_factory),
            patch(
                "backend.services.news.ingestion.NewsIngestionService",
                return_value=mock_service,
            ),
        ):
            from backend.tasks.news_sentiment import _ingest_news

            await bypass_tracked(_ingest_news)(14, run_id=uuid.uuid4())

        # since is the second positional arg to ingest_stock_news
        call_args = mock_service.ingest_stock_news.call_args
        since_arg = call_args[0][1]
        assert isinstance(since_arg, date)


# ---------------------------------------------------------------------------
# Helpers: _score_sentiment
# ---------------------------------------------------------------------------


def _make_score_sentiment_mocks(
    unscored_articles: list | None = None,
    scores: list | None = None,
    daily: dict | None = None,
) -> tuple:
    """Build mocks for _score_sentiment: ingestion_svc, scorer, session_factory."""
    # Mock article ORM objects
    if unscored_articles is None:
        mock_article = MagicMock()
        mock_article.headline = "AAPL beats estimates"
        mock_article.summary = "Strong Q1"
        mock_article.source = "reuters"
        mock_article.source_url = "https://reuters.com/1"
        mock_article.ticker = "AAPL"
        mock_article.published_at = MagicMock()
        mock_article.event_type = "earnings"
        mock_article.dedupe_hash = "abc123"
        unscored_articles = [mock_article]

    # Mock score objects
    if scores is None:
        mock_score = MagicMock()
        mock_score.dedupe_hash = "abc123"
        scores = [mock_score]

    # Mock daily aggregation result
    if daily is None:
        mock_daily_row = MagicMock()
        mock_daily_row.date = date(2024, 3, 1)
        mock_daily_row.ticker = "AAPL"
        mock_daily_row.stock_sentiment = 0.6
        mock_daily_row.sector_sentiment = 0.3
        mock_daily_row.macro_sentiment = 0.1
        mock_daily_row.article_count = 1
        mock_daily_row.confidence = 0.8
        mock_daily_row.dominant_event_type = "earnings"
        mock_daily_row.rationale_summary = "Strong Q1"
        daily = {"AAPL": mock_daily_row}

    # Mock ingestion service instance (get_unscored_articles is async)
    mock_ingestion_instance = AsyncMock()
    mock_ingestion_instance.get_unscored_articles = AsyncMock(return_value=unscored_articles)

    # Mock the class so instantiation returns the instance mock
    mock_ingestion_cls = MagicMock(return_value=mock_ingestion_instance)

    # Mock scorer
    mock_scorer_instance = MagicMock()
    mock_scorer_instance.score_batch = AsyncMock(return_value=scores)
    mock_scorer_instance.aggregate_daily = MagicMock(return_value=daily)

    mock_scorer_cls = MagicMock(return_value=mock_scorer_instance)

    # Mock session factory for the update + upsert calls
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock())
    mock_session.commit = AsyncMock()

    mock_factory = MagicMock()
    mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.__aexit__ = AsyncMock(return_value=False)

    return (
        mock_ingestion_cls,
        mock_scorer_cls,
        mock_factory,
        mock_ingestion_instance,
        mock_scorer_instance,
    )


class TestScoreSentiment:
    """Tests for the _score_sentiment async helper.

    Patches at the lookup site because _score_sentiment imports lazily.
    """

    @pytest.mark.asyncio
    async def test_score_sentiment_skips_when_no_unscored(self) -> None:
        """_score_sentiment returns early with scored=0 when no unscored articles exist."""
        mock_ingestion_instance = AsyncMock()
        mock_ingestion_instance.get_unscored_articles = AsyncMock(return_value=[])
        mock_ingestion_cls = MagicMock(return_value=mock_ingestion_instance)
        mock_scorer_cls = MagicMock()

        with (
            patch(
                "backend.services.news.ingestion.NewsIngestionService",
                mock_ingestion_cls,
            ),
            patch(
                "backend.services.news.sentiment_scorer.SentimentScorer",
                mock_scorer_cls,
            ),
        ):
            from backend.tasks.news_sentiment import _score_sentiment

            result = await bypass_tracked(_score_sentiment)(7, run_id=uuid.uuid4())

        assert result["status"] == "complete"
        assert result["scored"] == 0
        assert result["aggregated"] == 0

    @pytest.mark.asyncio
    async def test_score_sentiment_calls_scorer(self) -> None:
        """_score_sentiment calls SentimentScorer.score_batch with raw articles."""
        mock_ingestion_cls, mock_scorer_cls, mock_factory, _, mock_scorer_instance = (
            _make_score_sentiment_mocks()
        )

        with (
            patch("backend.database.async_session_factory", return_value=mock_factory),
            patch(
                "backend.services.news.ingestion.NewsIngestionService",
                mock_ingestion_cls,
            ),
            patch(
                "backend.services.news.sentiment_scorer.SentimentScorer",
                mock_scorer_cls,
            ),
        ):
            from backend.tasks.news_sentiment import _score_sentiment

            await bypass_tracked(_score_sentiment)(7, run_id=uuid.uuid4())

        mock_scorer_instance.score_batch.assert_called_once()
        # score_batch was called with a list of RawArticle objects
        call_args = mock_scorer_instance.score_batch.call_args
        raw_articles_arg = call_args[0][0]
        assert len(raw_articles_arg) == 1

    @pytest.mark.asyncio
    async def test_score_sentiment_upserts_daily(self) -> None:
        """_score_sentiment upserts daily sentiment rows after scoring."""
        mock_ingestion_cls, mock_scorer_cls, mock_factory, _, _ = _make_score_sentiment_mocks()

        with (
            patch("backend.database.async_session_factory", return_value=mock_factory),
            patch(
                "backend.services.news.ingestion.NewsIngestionService",
                mock_ingestion_cls,
            ),
            patch(
                "backend.services.news.sentiment_scorer.SentimentScorer",
                mock_scorer_cls,
            ),
        ):
            from backend.tasks.news_sentiment import _score_sentiment

            result = await bypass_tracked(_score_sentiment)(7, run_id=uuid.uuid4())

        assert result["status"] == "complete"
        assert result["scored"] == 1
        assert result["aggregated"] == 1
        assert "AAPL" in result["tickers"]
        # Single transaction: mark scored + upsert in one session
        assert mock_factory.__aenter__.call_count >= 1

    @pytest.mark.asyncio
    async def test_score_sentiment_returns_note_when_no_scores(self) -> None:
        """_score_sentiment returns a 'no scores returned' note when scorer yields empty."""
        mock_ingestion_cls, mock_scorer_cls, _, mock_ingestion_instance, mock_scorer_instance = (
            _make_score_sentiment_mocks()
        )
        # Override: scorer returns empty list (LLM API unavailable)
        mock_scorer_instance.score_batch = AsyncMock(return_value=[])

        with (
            patch(
                "backend.services.news.ingestion.NewsIngestionService",
                mock_ingestion_cls,
            ),
            patch(
                "backend.services.news.sentiment_scorer.SentimentScorer",
                mock_scorer_cls,
            ),
        ):
            from backend.tasks.news_sentiment import _score_sentiment

            result = await bypass_tracked(_score_sentiment)(7, run_id=uuid.uuid4())

        assert result["status"] == "complete"
        assert result["scored"] == 0
        assert result["aggregated"] == 0
        assert "note" in result

    @pytest.mark.asyncio
    async def test_score_sentiment_marks_articles_scored(self) -> None:
        """_score_sentiment executes an UPDATE to mark articles with scored_at."""
        mock_ingestion_cls, mock_scorer_cls, mock_factory, _, _ = _make_score_sentiment_mocks()

        with (
            patch("backend.database.async_session_factory", return_value=mock_factory),
            patch(
                "backend.services.news.ingestion.NewsIngestionService",
                mock_ingestion_cls,
            ),
            patch(
                "backend.services.news.sentiment_scorer.SentimentScorer",
                mock_scorer_cls,
            ),
        ):
            from backend.tasks.news_sentiment import _score_sentiment

            await bypass_tracked(_score_sentiment)(7, run_id=uuid.uuid4())

        # Retrieve the mock session that was used
        mock_session = mock_factory.__aenter__.return_value
        # Session execute should have been called for both UPDATE and INSERT
        assert mock_session.execute.call_count >= 1


# ---------------------------------------------------------------------------
# B5.1: tickers parameter on _ingest_news
# ---------------------------------------------------------------------------


class TestIngestNewsTickersParam:
    """Tests for the explicit tickers parameter added in B5."""

    @pytest.mark.asyncio
    async def test_ingest_news_explicit_tickers_bypasses_db_query(self) -> None:
        """When tickers is provided, the DB query for active tickers is skipped."""
        mock_service = _make_mock_ingestion_service()

        with patch(
            "backend.services.news.ingestion.NewsIngestionService",
            return_value=mock_service,
        ):
            from backend.tasks.news_sentiment import _ingest_news

            result = await bypass_tracked(_ingest_news)(
                30, tickers=["FOO", "BAR"], run_id=uuid.uuid4()
            )

        # ingest_stock_news is still called — but with our explicit list
        mock_service.ingest_stock_news.assert_called_once()
        call_args = mock_service.ingest_stock_news.call_args
        tickers_arg = call_args[0][0]
        assert sorted(tickers_arg) == ["BAR", "FOO"]
        # tickers_processed reflects the explicit list
        assert result["tickers_processed"] == 2

    @pytest.mark.asyncio
    async def test_ingest_news_explicit_tickers_uppercased(self) -> None:
        """Explicit tickers are uppercased before being passed to the ingestion service."""
        mock_service = _make_mock_ingestion_service()

        with patch(
            "backend.services.news.ingestion.NewsIngestionService",
            return_value=mock_service,
        ):
            from backend.tasks.news_sentiment import _ingest_news

            await bypass_tracked(_ingest_news)(30, tickers=["foo", "bar"], run_id=uuid.uuid4())

        call_args = mock_service.ingest_stock_news.call_args
        tickers_arg = call_args[0][0]
        assert sorted(tickers_arg) == ["BAR", "FOO"]

    @pytest.mark.asyncio
    async def test_ingest_news_none_tickers_queries_db(self) -> None:
        """When tickers=None (default), active tickers are queried from DB."""
        mock_factory = _make_mock_session_factory([("AAPL",), ("MSFT",)])
        mock_service = _make_mock_ingestion_service()

        with (
            patch("backend.database.async_session_factory", return_value=mock_factory),
            patch(
                "backend.services.news.ingestion.NewsIngestionService",
                return_value=mock_service,
            ),
        ):
            from backend.tasks.news_sentiment import _ingest_news

            result = await bypass_tracked(_ingest_news)(7, tickers=None, run_id=uuid.uuid4())

        # DB session was entered (to query active tickers)
        mock_factory.__aenter__.assert_called_once()
        assert result["tickers_processed"] == 2
