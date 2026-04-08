"""LLM-based sentiment scoring for news articles.

Uses GPT-4o-mini with temperature=0 for deterministic structured JSON output.
Batch-scores articles (10-20 per prompt) and aggregates per ticker per day
using exponential decay weighting.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from dataclasses import dataclass
from datetime import date

import httpx

from backend.config import settings
from backend.services.http_client import get_http_client
from backend.services.news.base import RawArticle

logger = logging.getLogger(__name__)

# ── Significance tiers ──
SIGNIFICANCE: dict[str, float] = {
    "earnings": 3.0,
    "fda": 3.0,
    "m_and_a": 3.0,
    "fed_rate": 3.0,
    "management": 3.0,
    "guidance": 1.5,
    "regulatory": 1.5,
    "cpi": 1.5,
    "employment": 1.5,
    "product": 1.0,
    "sector_trend": 1.0,
    "legal": 1.0,
    "other": 1.0,
    "general": 1.0,
    "macro": 1.0,
    "restructuring": 1.0,
    "impairment": 1.5,
    "governance": 1.0,
}

# Exponential decay: weight = sig × conf × exp(-0.3 × days)
DECAY_RATE = 0.3  # Half-life ≈ 2.3 days

# Maximum articles per LLM prompt
BATCH_SIZE = 15


@dataclass
class ArticleScore:
    """Structured score for a single article from the LLM."""

    dedupe_hash: str
    stock_sentiment: float  # -1.0 to 1.0
    sector_sentiment: float  # -1.0 to 1.0
    macro_sentiment: float  # -1.0 to 1.0
    event_type: str
    confidence: float  # 0.0 to 1.0
    rationale: str


@dataclass
class DailySentiment:
    """Aggregated daily sentiment for a ticker."""

    ticker: str
    date: date
    stock_sentiment: float
    sector_sentiment: float
    macro_sentiment: float
    article_count: int
    confidence: float
    dominant_event_type: str
    rationale_summary: str


class SentimentScorer:
    """Scores news articles using GPT-4o-mini and aggregates daily sentiment."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        """Initialize the scorer.

        Args:
            api_key: OpenAI API key. Falls back to settings.OPENAI_API_KEY.
            model: Model name. Falls back to settings.NEWS_SCORING_MODEL.
        """
        self._api_key = api_key or settings.OPENAI_API_KEY
        self._model = model or settings.NEWS_SCORING_MODEL
        self._base_url = "https://api.openai.com/v1/chat/completions"

    async def score_batch(self, articles: list[RawArticle]) -> list[ArticleScore]:
        """Score a batch of articles via the OpenAI API concurrently.

        Articles are split into groups of BATCH_SIZE and dispatched in parallel
        using asyncio.gather, bounded by settings.NEWS_SCORING_MAX_CONCURRENCY
        to avoid overwhelming the upstream API.

        If a single batch fails, it is logged and skipped; the remaining
        batches continue and their scores are returned.

        Args:
            articles: List of RawArticle objects to score.

        Returns:
            List of ArticleScore objects for all successfully scored articles.
        """
        if not self._api_key:
            logger.warning("OPENAI_API_KEY not set — skipping sentiment scoring")
            return []
        if not articles:
            return []

        sem = asyncio.Semaphore(settings.NEWS_SCORING_MAX_CONCURRENCY)

        async def _bounded(batch: list[RawArticle]) -> list[ArticleScore]:
            async with sem:
                return await self._score_single_batch(batch)

        batches = [articles[i : i + BATCH_SIZE] for i in range(0, len(articles), BATCH_SIZE)]
        results = await asyncio.gather(*(_bounded(b) for b in batches), return_exceptions=True)

        all_scores: list[ArticleScore] = []
        for idx, result in enumerate(results):
            if isinstance(result, BaseException):
                logger.error("Batch %d failed during concurrent scoring", idx, exc_info=result)
                continue
            all_scores.extend(result)
        return all_scores

    async def _score_single_batch(self, articles: list[RawArticle]) -> list[ArticleScore]:
        """Send a single batch to the LLM and parse the response."""
        prompt = _build_scoring_prompt(articles)

        payload = {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            client = get_http_client()
            resp = await client.post(self._base_url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError:
            logger.error("OpenAI API error during sentiment scoring", exc_info=True)
            return []

        return _parse_scoring_response(data, articles)

    def aggregate_daily(
        self,
        scores: list[ArticleScore],
        articles: list[RawArticle],
        target_date: date,
    ) -> dict[str, DailySentiment]:
        """Aggregate article scores into daily sentiment per ticker.

        Uses exponential decay weighting:
            weight = significance × confidence × exp(-0.3 × days_since_pub)

        Args:
            scores: List of ArticleScore from score_batch().
            articles: Original RawArticle list (for published_at + ticker).
            target_date: The date to aggregate for (usually today).

        Returns:
            Dict mapping ticker → DailySentiment. Macro articles use "__MACRO__".
        """
        # Build lookup from dedupe_hash → score
        score_map = {s.dedupe_hash: s for s in scores}

        # Group by ticker
        ticker_data: dict[str, list[tuple[ArticleScore, RawArticle]]] = {}
        for article in articles:
            score = score_map.get(article.dedupe_hash)
            if score is None:
                continue
            ticker = article.ticker or "__MACRO__"
            ticker_data.setdefault(ticker, []).append((score, article))

        results: dict[str, DailySentiment] = {}
        for ticker, pairs in ticker_data.items():
            results[ticker] = _compute_weighted_sentiment(ticker, pairs, target_date)

        return results


# ── Prompt templates ──

_SYSTEM_PROMPT = (
    "You are a financial news sentiment analyzer. For each article, output structured"
    " JSON with sentiment scores.\n\n"
    'Output format: {"scores": [{"index": 0, "stock_sentiment": 0.5,'
    ' "sector_sentiment": 0.2, "macro_sentiment": 0.0, "event_type": "earnings",'
    ' "confidence": 0.9, "rationale": "Strong Q1 beat"}, ...]}\n\n'
    "Rules:\n"
    "- stock_sentiment, sector_sentiment, macro_sentiment: float from -1.0"
    " (very bearish) to 1.0 (very bullish), 0.0 = neutral\n"
    "- event_type: one of [earnings, fda, m_and_a, fed_rate, management, guidance,"
    " regulatory, cpi, employment, product, sector_trend, legal, macro, other]\n"
    "- confidence: 0.0 to 1.0 (how confident in the sentiment assessment)\n"
    "- rationale: brief 1-sentence explanation\n"
    '- Always output valid JSON with a "scores" array matching the number of'
    " input articles"
)


def _build_scoring_prompt(articles: list[RawArticle]) -> str:
    """Build the user prompt containing article headlines for scoring."""
    lines = ["Score the following news articles:\n"]
    for i, article in enumerate(articles):
        ticker_label = f"[{article.ticker}]" if article.ticker else "[MACRO]"
        lines.append(f"{i}. {ticker_label} {article.headline}")
        if article.summary:
            lines.append(f"   Summary: {article.summary[:200]}")
    return "\n".join(lines)


def _parse_scoring_response(
    data: dict,  # type: ignore[type-arg]
    articles: list[RawArticle],
) -> list[ArticleScore]:
    """Parse the LLM JSON response into ArticleScore objects."""
    try:
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        raw_scores = parsed.get("scores", [])
    except (KeyError, IndexError, json.JSONDecodeError):
        logger.error("Failed to parse LLM scoring response", exc_info=True)
        return []

    results: list[ArticleScore] = []
    for raw in raw_scores:
        try:
            idx = raw.get("index", -1)
            if 0 <= idx < len(articles):
                article = articles[idx]
                results.append(
                    ArticleScore(
                        dedupe_hash=article.dedupe_hash,
                        stock_sentiment=_clamp(float(raw.get("stock_sentiment", 0)), -1, 1),
                        sector_sentiment=_clamp(float(raw.get("sector_sentiment", 0)), -1, 1),
                        macro_sentiment=_clamp(float(raw.get("macro_sentiment", 0)), -1, 1),
                        event_type=_validate_event_type(raw.get("event_type", "other")),
                        confidence=_clamp(float(raw.get("confidence", 0.5)), 0, 1),
                        rationale=str(raw.get("rationale", ""))[:200],
                    )
                )
        except (ValueError, TypeError):
            logger.warning("Skipping malformed score entry", exc_info=True)

    return results


def _clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value to [min_val, max_val].

    Args:
        value: The value to clamp.
        min_val: Minimum allowed value.
        max_val: Maximum allowed value.

    Returns:
        Clamped value within [min_val, max_val].
    """
    return max(min_val, min(max_val, value))


_VALID_EVENT_TYPES = frozenset(SIGNIFICANCE.keys())


def _validate_event_type(event_type: str) -> str:
    """Validate event_type against known allowlist.

    Args:
        event_type: Raw event_type from LLM output.

    Returns:
        Validated event_type, or "other" if not in allowlist.
    """
    return event_type if event_type in _VALID_EVENT_TYPES else "other"


def _compute_weighted_sentiment(
    ticker: str,
    pairs: list[tuple[ArticleScore, RawArticle]],
    target_date: date,
) -> DailySentiment:
    """Compute weighted daily sentiment for a single ticker.

    Weight formula: significance × confidence × exp(-0.3 × days_since_pub)

    Args:
        ticker: Ticker symbol (or "__MACRO__" for macro articles).
        pairs: List of (ArticleScore, RawArticle) tuples for this ticker.
        target_date: The date to aggregate for.

    Returns:
        DailySentiment with weighted averages across all articles.
    """
    total_weight = 0.0
    weighted_stock = 0.0
    weighted_sector = 0.0
    weighted_macro = 0.0
    event_counts: dict[str, float] = {}

    for score, article in pairs:
        days = (target_date - article.published_at.date()).days
        if days < 0:
            days = 0
        significance = SIGNIFICANCE.get(score.event_type, 1.0)
        weight = significance * score.confidence * math.exp(-DECAY_RATE * days)

        total_weight += weight
        weighted_stock += weight * score.stock_sentiment
        weighted_sector += weight * score.sector_sentiment
        weighted_macro += weight * score.macro_sentiment
        event_counts[score.event_type] = event_counts.get(score.event_type, 0) + weight

    if total_weight == 0:
        return DailySentiment(
            ticker=ticker,
            date=target_date,
            stock_sentiment=0.0,
            sector_sentiment=0.0,
            macro_sentiment=0.0,
            article_count=len(pairs),
            confidence=0.0,
            dominant_event_type="other",
            rationale_summary="No scored articles",
        )

    dominant = max(event_counts, key=event_counts.get)  # type: ignore[arg-type]
    avg_confidence = sum(s.confidence for s, _ in pairs) / len(pairs)

    # Build rationale from top-weighted articles
    top_rationales = sorted(
        pairs,
        key=lambda p: SIGNIFICANCE.get(p[0].event_type, 1.0) * p[0].confidence,
        reverse=True,
    )
    summary = "; ".join(s.rationale for s, _ in top_rationales[:3] if s.rationale)

    stock_sent = weighted_stock / total_weight
    sector_sent = weighted_sector / total_weight
    macro_sent = weighted_macro / total_weight

    # Guard against floating-point anomalies (NaN/Inf)
    if not all(math.isfinite(v) for v in (stock_sent, sector_sent, macro_sent)):
        logger.warning("Non-finite sentiment for %s, defaulting to 0.0", ticker)
        stock_sent = sector_sent = macro_sent = 0.0

    return DailySentiment(
        ticker=ticker,
        date=target_date,
        stock_sentiment=stock_sent,
        sector_sentiment=sector_sent,
        macro_sentiment=macro_sent,
        article_count=len(pairs),
        confidence=avg_confidence,
        dominant_event_type=dominant,
        rationale_summary=summary[:500],
    )
