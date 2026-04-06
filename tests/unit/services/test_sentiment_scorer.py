"""Unit tests for SentimentScorer — sentiment scoring and daily aggregation.

Tests cover:
- ArticleScore dataclass behaviour
- _build_scoring_prompt formatting
- _parse_scoring_response parsing and clamping
- SentimentScorer.score_batch batching + API call
- SentimentScorer.aggregate_daily with hand-calculated expected values
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.news.base import RawArticle
from backend.services.news.sentiment_scorer import (
    BATCH_SIZE,
    DECAY_RATE,
    ArticleScore,
    SentimentScorer,
    _build_scoring_prompt,
    _clamp,
    _parse_scoring_response,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_article(
    headline: str = "Test headline",
    ticker: str | None = "AAPL",
    days_ago: int = 0,
    summary: str | None = None,
    source: str = "finnhub",
) -> RawArticle:
    """Create a RawArticle published `days_ago` days before 2026-04-02."""
    target = date(2026, 4, 2)
    pub_date = date(target.year, target.month, target.day)
    # Subtract days
    from datetime import timedelta

    pub_date = pub_date - timedelta(days=days_ago)
    published_at = datetime(
        pub_date.year, pub_date.month, pub_date.day, 12, 0, 0, tzinfo=timezone.utc
    )
    return RawArticle(
        headline=headline,
        summary=summary,
        source=source,
        source_url="https://example.com",
        ticker=ticker,
        published_at=published_at,
    )


def _make_score(
    article: RawArticle,
    stock_sentiment: float = 0.0,
    sector_sentiment: float = 0.0,
    macro_sentiment: float = 0.0,
    event_type: str = "other",
    confidence: float = 0.5,
    rationale: str = "test rationale",
) -> ArticleScore:
    """Create an ArticleScore for the given article."""
    return ArticleScore(
        dedupe_hash=article.dedupe_hash,
        stock_sentiment=stock_sentiment,
        sector_sentiment=sector_sentiment,
        macro_sentiment=macro_sentiment,
        event_type=event_type,
        confidence=confidence,
        rationale=rationale,
    )


TARGET_DATE = date(2026, 4, 2)


# ── TestArticleScore ──────────────────────────────────────────────────────────


class TestArticleScore:
    """Tests for ArticleScore dataclass construction."""

    def test_creation_with_all_fields(self) -> None:
        """ArticleScore stores all fields correctly."""
        score = ArticleScore(
            dedupe_hash="abc123",
            stock_sentiment=0.75,
            sector_sentiment=-0.25,
            macro_sentiment=0.1,
            event_type="earnings",
            confidence=0.9,
            rationale="Strong quarterly beat",
        )
        assert score.dedupe_hash == "abc123"
        assert score.stock_sentiment == 0.75
        assert score.sector_sentiment == -0.25
        assert score.macro_sentiment == 0.1
        assert score.event_type == "earnings"
        assert score.confidence == 0.9
        assert score.rationale == "Strong quarterly beat"

    def test_clamp_function_constrains_values(self) -> None:
        """_clamp keeps values within [min_val, max_val]."""
        assert _clamp(1.5, -1.0, 1.0) == 1.0
        assert _clamp(-2.0, -1.0, 1.0) == -1.0
        assert _clamp(0.5, -1.0, 1.0) == 0.5
        assert _clamp(0.0, 0.0, 1.0) == 0.0

    def test_rationale_in_parse_is_truncated_to_200_chars(self) -> None:
        """_parse_scoring_response truncates rationale to 200 characters."""
        article = _make_article()
        long_rationale = "x" * 300

        data = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "scores": [
                                    {
                                        "index": 0,
                                        "stock_sentiment": 0.1,
                                        "sector_sentiment": 0.0,
                                        "macro_sentiment": 0.0,
                                        "event_type": "other",
                                        "confidence": 0.5,
                                        "rationale": long_rationale,
                                    }
                                ]
                            }
                        )
                    }
                }
            ]
        }
        results = _parse_scoring_response(data, [article])
        assert len(results) == 1
        assert len(results[0].rationale) == 200


# ── TestBuildScoringPrompt ────────────────────────────────────────────────────


class TestBuildScoringPrompt:
    """Tests for _build_scoring_prompt output format."""

    def test_formats_articles_with_index_and_ticker(self) -> None:
        """Prompt includes article index and ticker label."""
        articles = [
            _make_article("Apple beats earnings", ticker="AAPL"),
            _make_article("Fed raises rates", ticker=None),
        ]
        prompt = _build_scoring_prompt(articles)
        assert "0. [AAPL] Apple beats earnings" in prompt
        assert "1. [MACRO] Fed raises rates" in prompt

    def test_includes_summary_when_available(self) -> None:
        """Prompt appends truncated summary when article has one."""
        article = _make_article(
            "NVDA blowout quarter", ticker="NVDA", summary="Revenue up 120% YoY"
        )
        prompt = _build_scoring_prompt([article])
        assert "Summary: Revenue up 120% YoY" in prompt

    def test_truncates_long_summaries_to_200_chars(self) -> None:
        """Prompt truncates summaries longer than 200 characters."""
        # Use a distinct marker at position 200 to detect truncation
        long_summary = "A" * 200 + "TRUNCATE_MARKER"
        article = _make_article("Headline", summary=long_summary)
        prompt = _build_scoring_prompt([article])
        assert "A" * 200 in prompt
        assert "TRUNCATE_MARKER" not in prompt


# ── TestParseScoringResponse ──────────────────────────────────────────────────


class TestParseScoringResponse:
    """Tests for _parse_scoring_response parsing logic."""

    def _valid_response(self, scores: list[dict]) -> dict:  # type: ignore[type-arg]
        return {"choices": [{"message": {"content": json.dumps({"scores": scores})}}]}

    def test_parses_valid_llm_response(self) -> None:
        """Valid LLM response produces one ArticleScore per article."""
        article = _make_article("Good earnings", ticker="MSFT")
        data = self._valid_response(
            [
                {
                    "index": 0,
                    "stock_sentiment": 0.8,
                    "sector_sentiment": 0.3,
                    "macro_sentiment": 0.0,
                    "event_type": "earnings",
                    "confidence": 0.95,
                    "rationale": "Beat on EPS and revenue",
                }
            ]
        )
        results = _parse_scoring_response(data, [article])
        assert len(results) == 1
        assert results[0].stock_sentiment == pytest.approx(0.8)
        assert results[0].event_type == "earnings"
        assert results[0].confidence == pytest.approx(0.95)

    def test_returns_empty_on_malformed_json(self) -> None:
        """Malformed JSON in the response returns an empty list."""
        data = {"choices": [{"message": {"content": "not-valid-json"}}]}
        article = _make_article()
        results = _parse_scoring_response(data, [article])
        assert results == []

    def test_skips_entries_with_invalid_index(self) -> None:
        """Entries with out-of-range or missing index are skipped."""
        article = _make_article()
        data = self._valid_response(
            [
                {
                    "index": 99,  # out of range
                    "stock_sentiment": 0.5,
                    "sector_sentiment": 0.0,
                    "macro_sentiment": 0.0,
                    "event_type": "other",
                    "confidence": 0.5,
                    "rationale": "ignored",
                }
            ]
        )
        results = _parse_scoring_response(data, [article])
        assert results == []

    def test_clamps_out_of_range_sentiment_values(self) -> None:
        """Sentiment values outside [-1, 1] are clamped to the boundary."""
        article = _make_article()
        data = self._valid_response(
            [
                {
                    "index": 0,
                    "stock_sentiment": 2.5,  # too high
                    "sector_sentiment": -3.0,  # too low
                    "macro_sentiment": 0.0,
                    "event_type": "other",
                    "confidence": 1.5,  # too high — clamped to 1.0
                    "rationale": "extreme",
                }
            ]
        )
        results = _parse_scoring_response(data, [article])
        assert len(results) == 1
        assert results[0].stock_sentiment == pytest.approx(1.0)
        assert results[0].sector_sentiment == pytest.approx(-1.0)
        assert results[0].confidence == pytest.approx(1.0)

    def test_handles_missing_optional_fields_with_defaults(self) -> None:
        """Missing fields fall back to safe defaults."""
        article = _make_article()
        data = self._valid_response([{"index": 0}])  # only index present
        results = _parse_scoring_response(data, [article])
        assert len(results) == 1
        assert results[0].stock_sentiment == pytest.approx(0.0)
        assert results[0].sector_sentiment == pytest.approx(0.0)
        assert results[0].macro_sentiment == pytest.approx(0.0)
        assert results[0].event_type == "other"
        assert results[0].confidence == pytest.approx(0.5)
        assert results[0].rationale == ""


# ── TestSentimentScorer ───────────────────────────────────────────────────────


class TestSentimentScorer:
    """Tests for SentimentScorer.score_batch behaviour."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_api_key(self) -> None:
        """score_batch returns [] immediately when api_key is empty string."""
        # Patch settings so the fallback is also empty
        with patch("backend.services.news.sentiment_scorer.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            mock_settings.NEWS_SCORING_MODEL = "gpt-4o-mini"
            scorer = SentimentScorer(api_key="", model="gpt-4o-mini")
            # _api_key is set in __init__ — force it empty directly
            scorer._api_key = ""
            articles = [_make_article()]
            result = await scorer.score_batch(articles)
        assert result == []

    @pytest.mark.asyncio
    async def test_batches_articles_into_batch_size_groups(self) -> None:
        """score_batch splits articles into groups of BATCH_SIZE."""
        n_articles = BATCH_SIZE + 3  # 18 articles → 2 batches
        articles = [_make_article(f"Headline {i}") for i in range(n_articles)]

        call_count = 0
        batch_sizes: list[int] = []

        async def fake_score_single_batch(
            batch: list[RawArticle],
        ) -> list[ArticleScore]:
            nonlocal call_count
            call_count += 1
            batch_sizes.append(len(batch))
            return [_make_score(a) for a in batch]

        scorer = SentimentScorer(api_key="sk-test", model="gpt-4o-mini")
        scorer._score_single_batch = fake_score_single_batch  # type: ignore[method-assign]

        results = await scorer.score_batch(articles)

        assert call_count == 2
        assert batch_sizes[0] == BATCH_SIZE
        assert batch_sizes[1] == 3
        assert len(results) == n_articles

    @pytest.mark.asyncio
    async def test_calls_openai_api_with_correct_payload(self) -> None:
        """_score_single_batch sends correct model, temperature, and messages."""
        article = _make_article("Apple Q1 earnings beat", ticker="AAPL")
        mock_response_data = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "scores": [
                                    {
                                        "index": 0,
                                        "stock_sentiment": 0.5,
                                        "sector_sentiment": 0.2,
                                        "macro_sentiment": 0.0,
                                        "event_type": "earnings",
                                        "confidence": 0.9,
                                        "rationale": "Strong Q1",
                                    }
                                ]
                            }
                        )
                    }
                }
            ]
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_response_data
        mock_resp.raise_for_status = MagicMock()

        captured_payload: dict = {}  # type: ignore[type-arg]

        async def mock_post(url: str, **kwargs: object) -> MagicMock:
            captured_payload.update(kwargs.get("json", {}))  # type: ignore[arg-type]
            return mock_resp

        scorer = SentimentScorer(api_key="sk-test", model="gpt-4o-mini")

        mock_client = AsyncMock()
        mock_client.post = mock_post

        with patch(
            "backend.services.news.sentiment_scorer.get_http_client",
            return_value=mock_client,
        ):
            results = await scorer._score_single_batch([article])

        assert captured_payload["model"] == "gpt-4o-mini"
        assert captured_payload["temperature"] == 0
        assert captured_payload["response_format"] == {"type": "json_object"}
        messages = captured_payload["messages"]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert len(results) == 1
        assert results[0].stock_sentiment == pytest.approx(0.5)


# ── TestAggregateDailySentiment ───────────────────────────────────────────────


class TestAggregateDailySentiment:
    """Hand-calculated tests for aggregate_daily weighting."""

    def test_single_article_zero_days_old(self) -> None:
        """Single article published today: weight = sig × conf × exp(0) = conf.

        sig=1.0 (other), conf=0.8, days=0 → weight=0.8
        stock_sentiment = (0.8 × 0.5) / 0.8 = 0.5
        """
        article = _make_article("Headline", ticker="AAPL", days_ago=0)
        score = _make_score(article, stock_sentiment=0.5, event_type="other", confidence=0.8)

        scorer = SentimentScorer(api_key="sk-test")
        result = scorer.aggregate_daily([score], [article], TARGET_DATE)

        assert "AAPL" in result
        ds = result["AAPL"]
        assert ds.stock_sentiment == pytest.approx(0.5)
        assert ds.article_count == 1
        assert ds.dominant_event_type == "other"

    def test_two_articles_same_ticker_different_ages(self) -> None:
        """Two articles with different ages produce decay-weighted average.

        Art 1: earnings(sig=3.0), conf=0.9, days=0, stock=0.6
          weight1 = 3.0 × 0.9 × exp(0) = 2.7

        Art 2: product(sig=1.0), conf=0.7, days=2, stock=-0.3
          weight2 = 1.0 × 0.7 × exp(-0.6) = 0.7 × 0.548812 ≈ 0.38417

        total_weight = 2.7 + 0.38417 = 3.08417
        stock = (2.7 × 0.6 + 0.38417 × -0.3) / 3.08417
              = (1.62 - 0.11525) / 3.08417
              ≈ 1.50475 / 3.08417
              ≈ 0.4879
        """
        art1 = _make_article("Earnings beat", ticker="AAPL", days_ago=0)
        art2 = _make_article("New product launch", ticker="AAPL", days_ago=2)

        score1 = _make_score(art1, stock_sentiment=0.6, event_type="earnings", confidence=0.9)
        score2 = _make_score(art2, stock_sentiment=-0.3, event_type="product", confidence=0.7)

        weight1 = 3.0 * 0.9 * math.exp(0)
        weight2 = 1.0 * 0.7 * math.exp(-DECAY_RATE * 2)
        expected = (weight1 * 0.6 + weight2 * -0.3) / (weight1 + weight2)

        scorer = SentimentScorer(api_key="sk-test")
        result = scorer.aggregate_daily([score1, score2], [art1, art2], TARGET_DATE)

        ds = result["AAPL"]
        assert ds.stock_sentiment == pytest.approx(expected, abs=1e-4)
        assert ds.article_count == 2
        # earnings has higher weighted sum → dominant
        assert ds.dominant_event_type == "earnings"

    def test_all_zero_weights_returns_neutral(self) -> None:
        """When confidence=0 for all articles, total_weight=0 → neutral result."""
        article = _make_article("Headline", ticker="GOOG", days_ago=0)
        # confidence=0 → weight=0
        score = ArticleScore(
            dedupe_hash=article.dedupe_hash,
            stock_sentiment=0.9,
            sector_sentiment=0.9,
            macro_sentiment=0.9,
            event_type="earnings",
            confidence=0.0,
            rationale="zero confidence",
        )

        scorer = SentimentScorer(api_key="sk-test")
        result = scorer.aggregate_daily([score], [article], TARGET_DATE)

        ds = result["GOOG"]
        assert ds.stock_sentiment == pytest.approx(0.0)
        assert ds.sector_sentiment == pytest.approx(0.0)
        assert ds.macro_sentiment == pytest.approx(0.0)
        assert ds.dominant_event_type == "other"
        assert ds.rationale_summary == "No scored articles"

    def test_macro_articles_use_macro_ticker_key(self) -> None:
        """Articles with ticker=None are aggregated under '__MACRO__'."""
        article = _make_article("Fed raises rates 50bps", ticker=None, days_ago=0)
        score = _make_score(
            article,
            stock_sentiment=0.0,
            macro_sentiment=-0.6,
            event_type="fed_rate",
            confidence=0.85,
        )

        scorer = SentimentScorer(api_key="sk-test")
        result = scorer.aggregate_daily([score], [article], TARGET_DATE)

        assert "__MACRO__" in result
        assert "None" not in result
        ds = result["__MACRO__"]
        assert ds.macro_sentiment == pytest.approx(-0.6)

    def test_multiple_tickers_split_correctly(self) -> None:
        """Articles for different tickers produce separate DailySentiment entries."""
        art_aapl = _make_article("Apple news", ticker="AAPL", days_ago=0)
        art_msft = _make_article("Microsoft news", ticker="MSFT", days_ago=0)
        art_macro = _make_article("Fed news", ticker=None, days_ago=0)

        score_aapl = _make_score(
            art_aapl, stock_sentiment=0.7, event_type="earnings", confidence=0.9
        )
        score_msft = _make_score(
            art_msft, stock_sentiment=-0.4, event_type="guidance", confidence=0.8
        )
        score_macro = _make_score(
            art_macro, macro_sentiment=-0.5, event_type="fed_rate", confidence=0.7
        )

        scorer = SentimentScorer(api_key="sk-test")
        result = scorer.aggregate_daily(
            [score_aapl, score_msft, score_macro],
            [art_aapl, art_msft, art_macro],
            TARGET_DATE,
        )

        assert set(result.keys()) == {"AAPL", "MSFT", "__MACRO__"}
        assert result["AAPL"].stock_sentiment == pytest.approx(0.7)
        assert result["MSFT"].stock_sentiment == pytest.approx(-0.4)
        assert result["__MACRO__"].macro_sentiment == pytest.approx(-0.5)

    def test_dominant_event_type_is_highest_weighted(self) -> None:
        """The dominant event_type is the one with the highest cumulative weight.

        Two articles for same ticker:
          Art 1: macro(sig=1.0), conf=0.6, days=0   → weight=0.6
          Art 2: earnings(sig=3.0), conf=0.5, days=0 → weight=1.5
        earnings wins despite lower confidence because sig=3.0.
        """
        art1 = _make_article("Macro outlook", ticker="TSLA", days_ago=0)
        art2 = _make_article("TSLA earnings", ticker="TSLA", days_ago=0)

        score1 = _make_score(art1, event_type="macro", confidence=0.6, stock_sentiment=0.2)
        score2 = _make_score(art2, event_type="earnings", confidence=0.5, stock_sentiment=0.8)

        scorer = SentimentScorer(api_key="sk-test")
        result = scorer.aggregate_daily([score1, score2], [art1, art2], TARGET_DATE)

        assert result["TSLA"].dominant_event_type == "earnings"

    def test_future_articles_treated_as_zero_days(self) -> None:
        """Articles with published_at after target_date use days=0 (no decay).

        days = max(0, negative_days) = 0 → weight = sig × conf × exp(0)
        """

        future_published = datetime(2026, 4, 5, 12, 0, 0, tzinfo=timezone.utc)
        article = RawArticle(
            headline="Future article",
            summary=None,
            source="finnhub",
            source_url=None,
            ticker="AMZN",
            published_at=future_published,
        )
        score = _make_score(article, stock_sentiment=0.6, event_type="other", confidence=1.0)

        scorer = SentimentScorer(api_key="sk-test")
        # target_date is 2026-04-02, article is 2026-04-05 → days = -3 → clamped to 0
        result = scorer.aggregate_daily([score], [article], TARGET_DATE)

        ds = result["AMZN"]
        # weight = 1.0 × 1.0 × exp(0) = 1.0 → stock = 0.6 / 1.0 = 0.6
        assert ds.stock_sentiment == pytest.approx(0.6)

    def test_seven_day_old_article_has_negligible_weight(self) -> None:
        """7-day-old article has weight factor exp(-0.3 × 7) ≈ 0.1225.

        Compared to a fresh article (weight=1.0), the old one barely moves
        the weighted average.

        Art1 (today): sig=1.0, conf=1.0, days=0  → weight=1.0,  stock=0.9
        Art2 (7 days): sig=1.0, conf=1.0, days=7 → weight≈0.1225, stock=-0.9

        expected = (1.0 × 0.9 + 0.1225 × -0.9) / (1.0 + 0.1225)
                 = (0.9 - 0.11025) / 1.1225
                 ≈ 0.78975 / 1.1225
                 ≈ 0.7035
        """
        art_fresh = _make_article("Fresh news", ticker="META", days_ago=0)
        art_old = _make_article("Old news", ticker="META", days_ago=7)

        score_fresh = _make_score(
            art_fresh, stock_sentiment=0.9, event_type="other", confidence=1.0
        )
        score_old = _make_score(art_old, stock_sentiment=-0.9, event_type="other", confidence=1.0)

        decay_7 = math.exp(-DECAY_RATE * 7)
        expected = (1.0 * 0.9 + decay_7 * -0.9) / (1.0 + decay_7)

        scorer = SentimentScorer(api_key="sk-test")
        result = scorer.aggregate_daily([score_fresh, score_old], [art_fresh, art_old], TARGET_DATE)

        ds = result["META"]
        assert ds.stock_sentiment == pytest.approx(expected, abs=1e-4)
        # Verify decay factor is indeed small
        assert decay_7 == pytest.approx(0.1225, abs=0.001)
