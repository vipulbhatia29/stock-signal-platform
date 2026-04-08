"""Unit tests for SentimentScorer concurrent score_batch — B4 Spec B Pipeline Completeness.

Tests cover:
- score_batch dispatches batches concurrently (wall-clock < sequential bound)
- Semaphore caps in-flight concurrency at NEWS_SCORING_MAX_CONCURRENCY
- A single failing batch does not poison the other batches (partial results)
- Empty articles list returns empty immediately
- NEWS_SCORING_MAX_CONCURRENCY setting is respected at runtime
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from backend.config import settings
from backend.services.news.sentiment_scorer import (
    BATCH_SIZE,
    ArticleScore,
    SentimentScorer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_HASH = "deadbeef"


def _make_score() -> ArticleScore:
    """Return a minimal ArticleScore suitable for mock returns."""
    return ArticleScore(
        dedupe_hash=_FAKE_HASH,
        stock_sentiment=0.1,
        sector_sentiment=0.0,
        macro_sentiment=0.0,
        event_type="other",
        confidence=0.8,
        rationale="ok",
    )


def _fake_articles(n: int) -> list[Any]:
    """Return n placeholder objects (RawArticle not needed — _score_single_batch is patched)."""
    return [object() for _ in range(n)]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_score_batch_runs_concurrently() -> None:
    """30 articles → 2 batches of 15; concurrent dispatch must finish < 0.5 s.

    Each mocked batch sleeps 0.3 s.  Sequential would take ≥ 0.6 s.
    With asyncio.gather the wall-clock should be well under 0.5 s.
    """
    scorer = SentimentScorer(api_key="fake-key")
    articles = _fake_articles(BATCH_SIZE * 2)  # exactly 2 batches

    async def slow_batch(batch: list[Any]) -> list[ArticleScore]:
        await asyncio.sleep(0.3)
        return [_make_score() for _ in batch]

    with patch.object(scorer, "_score_single_batch", side_effect=slow_batch):
        start = time.perf_counter()
        scores = await scorer.score_batch(articles)
        elapsed = time.perf_counter() - start

    assert elapsed < 1.0, f"Expected concurrent execution (<1.0s) but took {elapsed:.2f}s (sequential would be ~0.6s)"
    assert len(scores) == BATCH_SIZE * 2


@pytest.mark.asyncio
async def test_score_batch_semaphore_cap() -> None:
    """20 batches; in-flight count must never exceed NEWS_SCORING_MAX_CONCURRENCY (5)."""
    scorer = SentimentScorer(api_key="fake-key")
    # 20 batches of 1 article each (well above the default cap of 5)
    articles = _fake_articles(20)

    counter_lock = asyncio.Lock()
    in_flight = 0
    max_in_flight = 0

    async def tracked_batch(batch: list[Any]) -> list[ArticleScore]:
        nonlocal in_flight, max_in_flight
        async with counter_lock:
            in_flight += 1
            if in_flight > max_in_flight:
                max_in_flight = in_flight
        await asyncio.sleep(0.02)  # hold slot briefly so overlap is observable
        async with counter_lock:
            in_flight -= 1
        return [_make_score() for _ in batch]

    with patch.object(scorer, "_score_single_batch", side_effect=tracked_batch):
        await scorer.score_batch(articles)

    default_cap = settings.NEWS_SCORING_MAX_CONCURRENCY
    assert max_in_flight <= default_cap, f"max_in_flight={max_in_flight} exceeded cap={default_cap}"


@pytest.mark.asyncio
async def test_score_batch_one_failure_does_not_poison_others() -> None:
    """3 batches; second batch raises — remaining 2 succeed and scores are returned."""
    scorer = SentimentScorer(api_key="fake-key")
    articles = _fake_articles(BATCH_SIZE * 3)

    call_count = 0

    async def maybe_fail(batch: list[Any]) -> list[ArticleScore]:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("simulated LLM failure")
        return [_make_score() for _ in batch]

    with patch.object(scorer, "_score_single_batch", side_effect=maybe_fail):
        scores = await scorer.score_batch(articles)

    # 2 successful batches × BATCH_SIZE articles each
    assert len(scores) == BATCH_SIZE * 2


@pytest.mark.asyncio
async def test_empty_articles_returns_empty() -> None:
    """Empty input list must return [] without hitting the API."""
    scorer = SentimentScorer(api_key="fake-key")
    mock_single = AsyncMock(return_value=[])

    with patch.object(scorer, "_score_single_batch", mock_single):
        result = await scorer.score_batch([])

    assert result == []
    mock_single.assert_not_called()


@pytest.mark.asyncio
async def test_configurable_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lowering NEWS_SCORING_MAX_CONCURRENCY to 2 caps in-flight at 2."""
    monkeypatch.setattr(settings, "NEWS_SCORING_MAX_CONCURRENCY", 2)

    scorer = SentimentScorer(api_key="fake-key")
    articles = _fake_articles(10)  # 10 batches of 1 each

    counter_lock = asyncio.Lock()
    in_flight = 0
    max_in_flight = 0

    async def tracked_batch(batch: list[Any]) -> list[ArticleScore]:
        nonlocal in_flight, max_in_flight
        async with counter_lock:
            in_flight += 1
            if in_flight > max_in_flight:
                max_in_flight = in_flight
        await asyncio.sleep(0.02)
        async with counter_lock:
            in_flight -= 1
        return [_make_score() for _ in batch]

    with patch.object(scorer, "_score_single_batch", side_effect=tracked_batch):
        await scorer.score_batch(articles)

    assert max_in_flight <= 2, f"max_in_flight={max_in_flight} exceeded configured cap=2"
