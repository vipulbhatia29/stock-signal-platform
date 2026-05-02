# KAN-564: FinBERT Sentiment Pipeline

## Problem

Our current sentiment scoring uses the **OpenAI API** (`SentimentScorer` in `backend/services/news/sentiment_scorer.py`). This has three issues:

1. **Cost** — Every article scored = API call. At 116 tickers × ~5 articles × daily = ~580 API calls/day just for sentiment.
2. **Latency** — Each batch requires a network round-trip. Total scoring time ~30-60s.
3. **No feature integration** — Sentiment scores are stored in `news_articles.sentiment_score` but NOT fed into the forecast model as a feature. The LightGBM/XGBoost models in `ForecastEngine` have no sentiment signal.

## Solution

Replace LLM-based scoring with **ProsusAI/finbert** (local inference, zero API cost, ~50 headlines/sec on CPU) as the primary scorer, with Groq round-robin pool (KAN-570) as fallback. Add dormancy tracking to skip tickers with no news history. Feed daily sentiment into `historical_features` for forecast model consumption.

## Architecture

### Component 1: FinBERT Scorer (`backend/services/news/finbert_scorer.py`)

Lazy-loaded singleton. Scores headlines locally. Falls back to Groq on failure.

```
score_headlines_finbert(headlines: list[str]) → list[dict]
    Returns: [{"label": "positive"|"negative"|"neutral", "confidence": float, "mapped": float}]

compute_weighted_score(scored: list[dict], weights: list[float]) → float | None
    Returns: weighted average of mapped scores in [-1, +1]
```

**Lazy singleton pattern:**
- Module-level `_PIPELINE: object | None = None` + `_LOADED: bool = False`
- First call loads model (~5s, ~500MB). All subsequent calls reuse cached pipeline.
- If load fails → `_LOADED = True`, `_PIPELINE = None` → all calls return `None` (never retry)
- Batch size 16. CPU only (`device=-1`).

### Component 2: Fallback Chain (modifies `SentimentScorer`)

```
FinBERT (local, zero cost)
  → fails? → Groq round-robin pool (KAN-570, free tier)
    → fails? → return None (skip scoring for this batch)
```

The existing `SentimentScorer._score_single_batch()` becomes the Groq fallback path (replace OpenAI URL with Groq via the GroqProvider).

### Component 3: Dormancy Tracking (`backend/models/sentiment_dormant.py`)

New table — tracks tickers whose news fetches consistently return zero articles.

```sql
CREATE TABLE sentiment_dormant (
    ticker          VARCHAR(20) PRIMARY KEY REFERENCES stocks(ticker),
    consecutive_empty   INT NOT NULL DEFAULT 0,
    last_checked_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    next_retry_at       TIMESTAMPTZ,
    last_headline_count INT NOT NULL DEFAULT 0,
    last_seen_headlines_at TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_sentiment_dormant_retry ON sentiment_dormant(next_retry_at);
```

**Cooldown schedule (capped exponential):**

| consecutive_empty | next_retry_at |
|---|---|
| 1 | +2 days |
| 2 | +4 days |
| 3 | +8 days |
| 4 | +16 days |
| ≥5 | +30 days (cap) |

**Helpers** (in `backend/services/news/dormancy.py`):
- `get_dormant_tickers(db) → set[str]` — tickers where `next_retry_at > now()`
- `record_empty_fetch(db, ticker)` — bumps streak, sets next_retry
- `record_successful_fetch(db, ticker, count)` — resets streak to 0
- `get_probe_candidates(db, limit=5) → list[str]` — oldest dormant tickers for periodic re-check

### Component 4: Daily Sentiment Task (`backend/tasks/sentiment.py`)

New Celery task in the nightly chain (runs before forecast_refresh, after price refresh):

```
sentiment_refresh_task()
  1. Get all active tickers
  2. Exclude dormant tickers (next_retry_at > now())
  3. Include 5% probe sample (oldest dormant, for re-discovery)
  4. For each ticker:
     a. Fetch headlines (existing NewsIngestionService or direct RSS)
     b. If 0 headlines → record_empty_fetch(), skip
     c. If headlines found → record_successful_fetch()
     d. Score with FinBERT (source-weighted, time-decayed)
     e. Store daily score in news_sentiment_daily table
  5. Log summary: scored/skipped/dormant/errors
```

### Component 5: Source-Weighted Time-Decay Scoring

Headlines from multiple sources get different reliability weights:

| Source | Weight | Notes |
|--------|--------|-------|
| Finnhub | 1.0 | Curated financial news |
| Google RSS | 0.7 | Broad but noisy |
| yfinance | 0.9 | Direct from Yahoo Finance |

Time decay: `weight *= exp(-DECAY_RATE * days_since_published)` where `DECAY_RATE = 0.3` (3-day half-life).

Final score per ticker per day: `Σ(mapped_score × source_weight × time_decay) / Σ(weights)`

### Component 6: Per-Source Timeout

Each news source fetch gets a hard 10-second timeout using `asyncio.wait_for()`. If a source hangs, it's skipped — the batch continues with remaining sources.

```python
async def _fetch_with_timeout(provider, ticker, timeout=10.0):
    try:
        return await asyncio.wait_for(provider.fetch_stock_news(ticker), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("News fetch timeout: %s for %s", provider.source_name, ticker)
        return []
```

### Component 7: Storage — `news_sentiment_daily` (ALREADY EXISTS)

Table exists at `backend/models/news_sentiment.py` with columns:
- `date`, `ticker`, `stock_sentiment`, `sector_sentiment`, `macro_sentiment`
- `article_count`, `confidence`, `dominant_event_type`, `rationale_summary`, `quality_flag`

**No new table needed.** FinBERT scores write to `stock_sentiment` column. Add `source` column (VARCHAR(20): "finbert" | "groq" | "llm") via migration to track scoring method.

### Component 8: Feature Integration

`historical_features` already has sentiment columns: `stock_sentiment`, `sector_sentiment`, `macro_sentiment`, `sentiment_confidence`. These are already in `FEATURE_NAMES` (forecast_engine.py lines 31-34).

**New column needed:** `sentiment_7d_avg` (rolling 7-day average of `news_sentiment_daily.stock_sentiment`).
- Migration: add nullable Float column
- Add to `FEATURE_NAMES` list
- Computed during daily feature population task

The forecast model (LightGBM/XGBoost) automatically picks it up since it reads all `FEATURE_NAMES`.

### Component 9: Historical Backfill (Price-Return Proxy)

Real FinBERT scores only exist from day 1 of deployment. For historical training data, use the ASET pattern — **price-return proxy**:

```python
def _return_to_sentiment(daily_return_pct: float) -> float:
    """Map daily return % to sentiment proxy score."""
    if daily_return_pct > 2.0: return 0.6
    if daily_return_pct > 0.5: return 0.3
    if daily_return_pct > -0.5: return 0.0
    if daily_return_pct > -2.0: return -0.3
    return -0.6
```

This gives the model something to train on historically. Over time, real FinBERT scores replace the proxy as days accumulate. The model learns the proxy is weakly predictive; real sentiment is stronger — natural feature importance shift.

### Component 10: Time Decay (Step Function, not Exponential)

ASET uses a step function (not continuous decay) which is simpler and avoids floating-point weirdness:

| Headline age | Weight multiplier |
|---|---|
| 0-2 days | 1.0 |
| 3-7 days | 0.5 |
| 8-30 days | 0.25 |
| >30 days | 0.1 |
| Unparseable date | 0.5 |

This is applied as a multiplier on the source weight before computing the weighted average.

## Integration Points

### Nightly Pipeline (backend/tasks/market_data.py)

Insert `sentiment_refresh_task` between Phase 1 (price refresh) and Phase 2 (forecast_refresh):

```
Phase 1:   price_refresh → signals
Phase 1.5: slow_path (yfinance info)
Phase 1.7: sentiment_refresh_task ← NEW
Phase 2:   forecast_refresh (now has sentiment features), recommendations, ...
```

### Config (backend/config.py)

```python
# Sentiment scoring
SENTIMENT_SCORER: str = "finbert"           # "finbert" | "llm" (legacy OpenAI)
SENTIMENT_FINBERT_BATCH_SIZE: int = 16
SENTIMENT_SOURCE_TIMEOUT: float = 10.0
SENTIMENT_DORMANCY_ENABLED: bool = True
SENTIMENT_PROBE_PCT: float = 0.05           # 5% of dormant tickers probed daily
```

### Dependencies

```
torch (CPU-only wheel)
transformers>=4.40
```

Install: `uv add torch --index-url https://download.pytorch.org/whl/cpu && uv add transformers`

Docker: separate `requirements-ml.txt` or conditional install in Dockerfile (ML worker vs API worker).

## Scope

### In scope
- FinBERT lazy singleton scorer
- Fallback to Groq (via KAN-570 round-robin pool)
- Dormancy tracking table + exponential backoff
- Daily Celery task
- Source-weighted time-decay aggregation
- Per-source 10s timeout
- `news_sentiment_daily` storage table
- `sentiment_7d_avg` in historical_features
- Integration into nightly pipeline
- Unit tests for scorer, dormancy, aggregation

### Out of scope
- Replacing the real-time chat sentiment (stays LLM-based for interactive UX)
- Historical backfill of sentiment (separate ticket — needs historical headlines)
- Frontend display of sentiment scores (future UI ticket)
- Market-wide fallback score (ticker-specific only for now)

## Dependencies

- **KAN-570** (Round-Robin Groq Pool) — provides the Groq fallback tier
- Existing `NewsIngestionService` + providers (Google, Finnhub) for headline fetching
- Existing `historical_features` table and `backfill_features.py` for feature integration

## Acceptance Criteria

- [ ] FinBERT scores 50 headlines/sec on CPU (benchmark test)
- [ ] Lazy singleton loads once, never retries on failure
- [ ] Fallback chain: FinBERT → Groq → None (integration test)
- [ ] Dormancy: after 3 empty fetches, ticker skipped for 8 days
- [ ] Dormancy: 5% probe re-discovers tickers with new coverage
- [ ] Per-source timeout: 10s max, batch continues on timeout
- [ ] Daily task completes for 116 tickers in <5 minutes
- [ ] `sentiment_7d_avg` appears in FEATURE_NAMES and forecast model uses it
- [ ] Config toggle: `SENTIMENT_SCORER=llm` reverts to OpenAI path
- [ ] No regression: existing news ingestion + article scoring unchanged
