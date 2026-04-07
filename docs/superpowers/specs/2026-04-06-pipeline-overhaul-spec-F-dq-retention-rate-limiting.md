# Spec F: Data Quality, Retention, Rate Limiting

**Status:** Draft
**Date:** 2026-04-06
**Authors:** Pipeline Overhaul team
**Part of:** Pipeline Architecture Overhaul Epic

---

## Problem Statement

Three reliability/operational gaps:

1. **No automated data quality checks.** Session 95 (full reseed) found 4 data quality bugs (KAN-401 tz mismatch, KAN-402 column overflow, KAN-403 negative Prophet prices, KAN-404 missing portfolio ticker data) — all caught only by manual reseed. There's no nightly DQ scanner. New regressions ship undetected.

2. **No outbound rate limiting.** yfinance has anti-scraping protection that bans IPs at high call rates. The new fast path with concurrency=10 (Spec E3) plus on-demand ingest (Spec C1/C2) increases call volume substantially. News providers (Finnhub: 60 RPM free tier, EDGAR: 10 RPS, Fed RSS: undocumented) can also rate-limit silently.

3. **No retention policy.** `forecast_results`, `news_articles`, `signal_snapshots`, `signal_convergence_daily` all grow unbounded. TimescaleDB hypertables aren't compressed despite being ideal candidates. No `POST /stocks/{ticker}/ingest` rate limit means a single user can spam the endpoint and DDoS yfinance from our IP.

---

## Goals

- Catch data quality regressions same-day they're introduced
- Protect against yfinance + news provider rate limits / bans
- Bound database growth via retention + TimescaleDB compression
- Prevent abuse of on-demand ingest endpoint

## Non-Goals

- Real-time DQ alerting (24h scan cadence is enough)
- Cost-based retention (size cap rather than age cap) — defer
- Per-user storage quotas — defer

---

## Design

### F1. Data quality scanner task

**New file:** `backend/tasks/dq_scan.py`

```python
"""Nightly data quality scanner."""
import asyncio
from datetime import datetime, timezone

from backend.database import async_session_factory
from backend.tasks import celery_app
from backend.tasks.pipeline import tracked_task

@celery_app.task(name="backend.tasks.dq_scan.dq_scan_task")
@tracked_task("dq_scan", "scheduled")
def dq_scan_task() -> dict:
    return asyncio.run(_dq_scan_async())


async def _dq_scan_async() -> dict:
    findings: list[dict] = []
    async with async_session_factory() as db:
        findings += await _check_negative_prices(db)
        findings += await _check_rsi_out_of_range(db)
        findings += await _check_composite_score_out_of_range(db)
        findings += await _check_null_sectors(db)
        findings += await _check_forecast_extreme_ratios(db)
        findings += await _check_orphan_positions(db)
        findings += await _check_duplicate_signals(db)
        findings += await _check_stale_universe_coverage(db)
        findings += await _check_negative_volume(db)
        findings += await _check_bollinger_violations(db)

        # Persist run history
        for f in findings:
            await _persist_finding(db, f)
        await db.commit()

    # Create alerts for critical findings
    critical = [f for f in findings if f["severity"] == "critical"]
    if critical:
        from backend.tasks.alerts import _create_alert
        async with async_session_factory() as db:
            for f in critical:
                await _create_alert(
                    db,
                    alert_type="data_quality",
                    title=f["check"],
                    message=f["message"],
                    severity="critical",
                    ticker=f.get("ticker"),
                    dedup_key=f"dq:{f['check']}:{f.get('ticker', 'global')}",
                )
            await db.commit()

    return {"status": "ok", "findings": len(findings), "critical": len(critical)}
```

**Checks (each is a function returning a list of findings):**

1. **Negative prices** — `SELECT ticker, time, close FROM stock_prices WHERE close < 0 OR adj_close < 0` (limit 100). Severity critical.
2. **RSI out of [0, 100]** — `SELECT ticker, computed_at, rsi_value FROM signal_snapshots WHERE rsi_value NOT BETWEEN 0 AND 100`. Severity high.
3. **Composite score out of [0, 10]** — `SELECT ticker, composite_score FROM signal_snapshots WHERE composite_score NOT BETWEEN 0 AND 10`. Severity high.
4. **NULL sector** — `SELECT ticker FROM stocks WHERE is_active AND sector IS NULL`. Severity medium. (KAN-322 was this exact bug.)
5. **Forecast extreme ratios** — `SELECT ticker, predicted_price, current_price FROM forecast_results JOIN ... WHERE predicted_price > 10 * current_price OR predicted_price < 0.1 * current_price`. Severity high. (Catches Prophet runaway predictions like KAN-403.)
6. **Orphan positions** — `SELECT position.ticker FROM position LEFT JOIN stocks ON ... WHERE stocks.ticker IS NULL OR NOT stocks.is_active`. Severity high.
7. **Duplicate signals** — `SELECT ticker, computed_at, COUNT(*) FROM signal_snapshots GROUP BY ticker, computed_at HAVING COUNT(*) > 1`. Severity medium.
8. **Stale universe coverage** — for each ticker in canonical universe, check `ticker_ingestion_state.signals_updated_at` is within SLA. Findings list = tickers with stale signals.
9. **Negative volume** — `SELECT ticker, time, volume FROM stock_prices WHERE volume < 0`. Severity critical.
10. **Bollinger violations** — `SELECT ticker, bb_upper, bb_lower FROM signal_snapshots WHERE bb_lower > bb_upper`. Severity high.

**New table** `dq_check_history` for trend tracking:

```sql
CREATE TABLE dq_check_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    check_name TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    ticker TEXT,
    message TEXT NOT NULL,
    metadata JSONB,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_dq_history_detected_at ON dq_check_history (detected_at DESC);
CREATE INDEX idx_dq_history_check_name ON dq_check_history (check_name, detected_at DESC);
```

Migration: `backend/migrations/versions/026_dq_check_history.py`

**Beat schedule entry:** add to `backend/tasks/__init__.py`:

```python
"dq-scan-daily": {
    "task": "backend.tasks.dq_scan.dq_scan_task",
    "schedule": crontab(hour=4, minute=0),  # 04:00 ET — after nightly chain finishes
},
```

Also include in `backend/tasks/__init__.py:11-24` `include=[]` list.

**Register in PipelineRegistry:** add to `backend/services/pipeline_registry_config.py` in a new "data_quality" group.

---

### F2. News provider rate limiter (Redis token bucket)

**New file:** `backend/services/rate_limiter.py`

```python
"""Redis-backed token bucket rate limiter for outbound API calls."""
import asyncio
import time
from backend.services.redis_pool import get_redis

class TokenBucketLimiter:
    """Atomic Redis token bucket using Lua script for fairness."""

    LUA_SCRIPT = """
    local key = KEYS[1]
    local capacity = tonumber(ARGV[1])
    local refill_rate = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])

    local data = redis.call("HMGET", key, "tokens", "last_refill")
    local tokens = tonumber(data[1]) or capacity
    local last = tonumber(data[2]) or now

    local elapsed = math.max(0, now - last)
    tokens = math.min(capacity, tokens + elapsed * refill_rate)

    if tokens >= 1 then
        tokens = tokens - 1
        redis.call("HMSET", key, "tokens", tokens, "last_refill", now)
        redis.call("EXPIRE", key, math.ceil(capacity / refill_rate) + 60)
        return 1
    else
        return 0
    end
    """

    def __init__(self, name: str, capacity: int, refill_per_sec: float):
        self.name = name
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self._sha: str | None = None

    async def acquire(self, timeout: float = 30.0) -> bool:
        redis = await get_redis()
        if redis is None:
            return True  # No-op if Redis down
        if self._sha is None:
            self._sha = await redis.script_load(self.LUA_SCRIPT)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            now = time.time()
            ok = await redis.evalsha(
                self._sha, 1, f"ratelimit:{self.name}",
                self.capacity, self.refill_per_sec, now
            )
            if int(ok) == 1:
                return True
            await asyncio.sleep(1.0 / self.refill_per_sec)
        return False
```

**Integration sites:**

- `backend/services/news/finnhub.py` — wrap each API call with `await finnhub_limiter.acquire()` (capacity=60, refill=1.0/sec → 60 RPM)
- `backend/services/news/edgar.py` — wrap with `edgar_limiter.acquire()` (capacity=10, refill=10.0/sec → 10 RPS)
- `backend/services/news/google.py` — Google News RSS, no documented limit, use a conservative `google_limiter.acquire()` (capacity=20, refill=0.33/sec → 20 RPM)
- `backend/services/news/fred.py` — already rate-limited by FRED key, but add a defensive limiter anyway (capacity=5, refill=0.5/sec → 30 RPM well under FRED's 120/min)

Each limiter is a module-level singleton instance.

---

### F3. yfinance outbound rate limiter

**Same `backend/services/rate_limiter.py`** module, additional limiter:

- `yfinance_limiter = TokenBucketLimiter("yfinance", capacity=30, refill_per_sec=0.5)` — 30 RPM globally

**Integration sites:**

- `backend/services/stock_data.py:_download_ticker` — wrap with `await yfinance_limiter.acquire()` before `yf.download(...)`
- `backend/services/stock_data.py:_download_ticker_range` — same
- `backend/services/stock_data.py:ensure_stock_exists` — `_get_ticker_info` call (line 202) wrap
- `backend/tasks/market_data.py:_refresh_ticker_slow` — yfinance Ticker.info call wrap
- `backend/tools/dividends.py:fetch_dividends` — wrap

**Note:** yfinance is not async; the wrappers go around `asyncio.to_thread(...)` calls. The acquire is the async part; the wrapped function runs in a thread.

---

### F4. POST /stocks/{ticker}/ingest rate limit (per-user)

**File modified:** `backend/routers/stocks/search.py:147-199`

Add `@limiter.limit("20/hour")` decorator to the `ingest_ticker` endpoint. The `limiter` fixture is already registered in `backend/main.py` from `slowapi`.

```python
from backend.rate_limit import limiter

@router.post("/{ticker}/ingest", response_model=IngestResponse)
@limiter.limit("20/hour")
async def ingest_ticker(...):
    ...
```

20/hour per user prevents abuse (100s of ingests in a session) without blocking legitimate portfolio uploads (which use the bulk endpoint anyway, which has its own limit — see C5).

**Bulk endpoint rate limit:** also add `@limiter.limit("3/hour")` to `POST /portfolio/transactions/bulk` from Spec C5 — bulk imports are infrequent.

---

### F5. Forecast retention policy task

**New file:** `backend/tasks/retention.py`

```python
"""Nightly retention enforcement for time-series tables."""
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete

from backend.database import async_session_factory
from backend.models.forecast import ForecastResult
from backend.models.news_sentiment import NewsArticle
from backend.tasks import celery_app
from backend.tasks.pipeline import tracked_task

@celery_app.task(name="backend.tasks.retention.purge_old_forecasts_task")
@tracked_task("forecast_retention", "scheduled")
def purge_old_forecasts_task() -> dict:
    return asyncio.run(_purge_old_forecasts_async())


async def _purge_old_forecasts_async() -> dict:
    """Keep last 30 days of forecasts per ticker; delete older.

    Future enhancement: keep weekly snapshots beyond 30 days. For now, hard delete >30d.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    async with async_session_factory() as db:
        result = await db.execute(
            delete(ForecastResult).where(ForecastResult.created_at < cutoff)
        )
        await db.commit()
        return {"status": "ok", "deleted": result.rowcount or 0}


@celery_app.task(name="backend.tasks.retention.purge_old_news_articles_task")
@tracked_task("news_retention", "scheduled")
def purge_old_news_articles_task() -> dict:
    return asyncio.run(_purge_old_news_articles_async())


async def _purge_old_news_articles_async() -> dict:
    """Keep raw articles 90 days; daily aggregates retained forever."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    cutoff_naive = cutoff.replace(tzinfo=None)  # NewsArticle.published_at is naive
    async with async_session_factory() as db:
        result = await db.execute(
            delete(NewsArticle).where(NewsArticle.published_at < cutoff_naive)
        )
        await db.commit()
        return {"status": "ok", "deleted": result.rowcount or 0}
```

**Beat schedule:** add to `backend/tasks/__init__.py`:

```python
"forecast-retention-daily": {
    "task": "backend.tasks.retention.purge_old_forecasts_task",
    "schedule": crontab(hour=3, minute=30),
},
"news-retention-daily": {
    "task": "backend.tasks.retention.purge_old_news_articles_task",
    "schedule": crontab(hour=3, minute=45),
},
```

Add to `include=[]` and to PipelineRegistry "maintenance" group.

---

### F6. TimescaleDB compression policy

**Migration:** `backend/migrations/versions/027_timescale_compression.py`

```python
"""Enable TimescaleDB compression for older chunks."""
from alembic import op

revision = "..."  # generate new 12-char hash (e.g. `c4d5e6f7a8b9`)
# NOTE: must use the HASH revision id from migration 026, NOT the numeric slug.
# The repo convention (verified against b2351fa2d293_024_*.py) is hash-based
# revision IDs. Migration 026 generates its own hash; insert it here at
# implementation time.
down_revision = "<hash-of-026>"

def upgrade():
    # Enable compression with optimal segmentby per table
    op.execute("""
        ALTER TABLE stock_prices SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'ticker',
            timescaledb.compress_orderby = 'time DESC'
        );
        SELECT add_compression_policy('stock_prices', INTERVAL '30 days');
    """)
    op.execute("""
        ALTER TABLE signal_snapshots SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'ticker',
            timescaledb.compress_orderby = 'computed_at DESC'
        );
        SELECT add_compression_policy('signal_snapshots', INTERVAL '30 days');
    """)
    op.execute("""
        ALTER TABLE news_articles SET (
            timescaledb.compress,
            timescaledb.compress_orderby = 'published_at DESC'
        );
        SELECT add_compression_policy('news_articles', INTERVAL '30 days');
    """)
    # signal_convergence_daily — small table, skip compression for now

def downgrade():
    # 1. Remove future policies so new chunks stop compressing.
    op.execute("SELECT remove_compression_policy('stock_prices', if_exists => TRUE);")
    op.execute("SELECT remove_compression_policy('signal_snapshots', if_exists => TRUE);")
    op.execute("SELECT remove_compression_policy('news_articles', if_exists => TRUE);")

    # 2. DECOMPRESS EXISTING CHUNKS — required before clearing the
    #    `timescaledb.compress = false` flag; otherwise queries against the
    #    already-compressed chunks fail. This is the piece the earlier draft
    #    missed (Spec F review CRITICAL).
    for table in ("stock_prices", "signal_snapshots", "news_articles"):
        op.execute(
            f"""
            DO $$
            DECLARE chunk regclass;
            BEGIN
                FOR chunk IN
                    SELECT format('%I.%I', chunk_schema, chunk_name)::regclass
                    FROM timescaledb_information.chunks
                    WHERE hypertable_name = '{table}' AND is_compressed
                LOOP
                    PERFORM decompress_chunk(chunk);
                END LOOP;
            END $$;
            """
        )

    # 3. Now it is safe to disable compression.
    op.execute("ALTER TABLE stock_prices SET (timescaledb.compress = false);")
    op.execute("ALTER TABLE signal_snapshots SET (timescaledb.compress = false);")
    op.execute("ALTER TABLE news_articles SET (timescaledb.compress = false);")
```

**Note:** TimescaleDB compression is transparent to queries. The downgrade
is fully reversible **provided it walks every compressed chunk and
decompresses it before clearing the flag** (above). Without the decompress
loop, existing compressed chunks become query-broken.

**Estimated savings:** TimescaleDB compresses at ~95% for time-series data. With ~1.2M price rows + ~600 signal snapshots/day × 365 = 220K signals/year + ~30K news articles, expected disk reduction: 80-90% on chunks older than 30 days.

---

## Files Created

| Path | Purpose |
|---|---|
| `backend/tasks/dq_scan.py` | DQ scanner task + 10 check functions |
| `backend/tasks/retention.py` | Forecast + news retention tasks |
| `backend/services/rate_limiter.py` | Token bucket Redis limiter + named instances |
| `backend/models/dq_check_history.py` | DQ findings table model |
| `backend/migrations/versions/026_dq_check_history.py` | Migration for findings table |
| `backend/migrations/versions/027_timescale_compression.py` | TimescaleDB compression policies |
| `tests/unit/tasks/test_dq_scan.py` | DQ check unit tests |
| `tests/unit/services/test_rate_limiter.py` | Token bucket tests |
| `tests/unit/tasks/test_retention.py` | Retention task tests |
| `tests/api/test_dq_scan_integration.py` | Real DB DQ scan integration |
| `tests/integration/test_compression_migration.py` | Verify migration up/down |

## Files Modified

| File | What changes |
|---|---|
| `backend/tasks/__init__.py` | Add 3 beat entries (dq-scan-daily, forecast-retention-daily, news-retention-daily); add 3 imports to include[] |
| `backend/services/pipeline_registry_config.py` | Add "data_quality" group + register dq_scan_task; add to "maintenance" group: retention tasks |
| `backend/routers/stocks/search.py:147` | Add @limiter.limit("20/hour") to ingest endpoint |
| `backend/routers/portfolio.py` | (from Spec C5) Add @limiter.limit("3/hour") to bulk endpoint |
| `backend/services/stock_data.py` | Wrap yfinance calls with `yfinance_limiter.acquire()` (5 sites) |
| `backend/services/news/finnhub.py` | Wrap calls with `finnhub_limiter.acquire()` |
| `backend/services/news/edgar.py` | Wrap with `edgar_limiter.acquire()` |
| `backend/services/news/google.py` | Wrap with `google_limiter.acquire()` |
| `backend/services/news/fred.py` | Wrap with `fred_limiter.acquire()` |
| `backend/tasks/market_data.py:_refresh_ticker_slow` | Wrap yfinance Ticker.info + dividend calls |
| `backend/tools/dividends.py:fetch_dividends` | Wrap with `yfinance_limiter.acquire()` |
| `backend/models/__init__.py` | Register `DqCheckHistory` for Alembic discovery |

---

## API Contract Changes

| Endpoint | Change |
|---|---|
| `POST /api/v1/stocks/{ticker}/ingest` | New rate limit response: 429 Too Many Requests when 20/hour exceeded |
| `POST /api/v1/portfolio/transactions/bulk` | New rate limit response: 429 when 3/hour exceeded |

No new endpoints in Spec F (DQ admin endpoints come in Spec D).

## Frontend Impact

| File | Change |
|---|---|
| `frontend/src/hooks/use-stocks.ts` | `useIngestTicker.onError` add 429 handling: show "You've reached the hourly ingest limit. Try again later." |
| `frontend/src/hooks/use-bulk-transactions.ts` (from Spec C) | Same 429 handling |

No new types needed.

---

## Test Impact

### Existing test files affected

Grep evidence:

- `tests/unit/services/test_finnhub.py` (if exists) — need to mock new rate limiter
- `tests/unit/services/test_news_*.py` — same
- `tests/unit/services/test_stock_data.py` — yfinance calls now go through limiter; mock the limiter to no-op in tests
- `tests/unit/tasks/test_celery_tasks.py` — assert new tasks are registered
- `tests/api/test_ingest_endpoint.py` (if exists) — add 429 test
- `tests/api/test_security_logging.py` — verify rate limit responses are logged
- `tests/semgrep/test_rules_ok.py` — no expected change

### New test files (enumerated above)

### Specific test cases

**DQ scanner (15 cases):**
1. test_check_negative_prices_finds_bad_row
2. test_check_negative_prices_no_findings_when_clean
3. test_check_rsi_out_of_range
4. test_check_composite_score_out_of_range
5. test_check_null_sectors
6. test_check_forecast_extreme_ratios_high
7. test_check_forecast_extreme_ratios_low
8. test_check_orphan_positions
9. test_check_duplicate_signals
10. test_check_stale_universe_coverage
11. test_check_negative_volume
12. test_check_bollinger_violations
13. test_dq_scan_persists_findings_to_history_table
14. test_dq_scan_creates_alerts_for_critical_findings
15. test_dq_scan_dedup_alerts_via_dedup_key

**Rate limiter (10 cases):**
1. test_token_bucket_acquire_when_tokens_available
2. test_token_bucket_blocks_when_empty
3. test_token_bucket_refills_over_time
4. test_token_bucket_no_op_when_redis_unavailable
5. test_token_bucket_lua_atomicity
6. test_yfinance_limiter_capacity_30_per_minute
7. test_finnhub_limiter_60_per_minute
8. test_edgar_limiter_10_per_second
9. test_named_limiters_isolated (acquiring from one doesn't drain another)
10. test_acquire_timeout_returns_false

**Retention (8 cases):**
1. test_purge_old_forecasts_deletes_only_old_rows
2. test_purge_old_forecasts_preserves_30_day_window
3. test_purge_old_forecasts_returns_deleted_count
4. test_purge_old_news_articles_uses_naive_datetime_for_naive_column
5. test_purge_old_news_articles_does_not_delete_aggregates
6. test_retention_tasks_use_tracked_task_decorator
7. test_retention_failures_logged_not_swallowed
8. test_retention_beat_schedule_entries_present

**Compression migration (4 cases):**
1. test_migration_027_upgrade_creates_compression_policies
2. test_migration_027_downgrade_removes_policies
3. test_compression_does_not_break_select_queries
4. test_compression_chunks_older_than_30d_are_compressed (slow integration)

**Endpoint rate limit (3 cases):**
1. test_ingest_endpoint_429_after_20_per_hour
2. test_ingest_endpoint_429_resets_after_window
3. test_bulk_endpoint_429_after_3_per_hour

---

## Migration Strategy

- Migration 026 (DQ history): additive table
- Migration 027 (compression): additive policies, no data movement
- Both fully reversible
- DQ scanner runs nightly; first run will write findings — review them before promoting alerts to "critical"
- Rate limiters: deploy first with permissive caps, observe `ratelimit:*` Redis keys, tighten if needed

## Risk + Rollback

| Risk | Mitigation | Rollback |
|---|---|---|
| Rate limiter blocks legitimate refresh | Generous defaults; monitor `acquire timeout` log lines | Reduce capacity to 1000 per limiter (effectively no-op) |
| DQ scanner false positives flood alerts | Review first 7 days of findings before enabling alert generation | Set severity to "info" for noisy checks |
| Retention deletes user-visible data | 30-day window aligned with UX expectation; weekly snapshots can be added later | Restore from backup; pause retention |
| Compression breaks legacy queries | TimescaleDB compression is transparent; tested in dev | Downgrade migration |
| Lua script bug in token bucket | Unit tests with fakeredis | Rate limiters become no-op when Redis errors |

## Open Questions

1. **Retention window:** 30 days for forecasts, 90 days for news? Recommendation: yes for now. Add weekly snapshots in Spec F2 if PMs want longer history.
2. **Compression threshold:** 30 days vs 7 days? Recommendation: 30 days. Recent data is queried often; older data is archival.
3. **DQ check schedule:** 04:00 ET vs immediately after nightly chain? Recommendation: 04:00 — gives nightly chain (21:30 ET) ~6h to complete.
4. **Rate limiter timeout:** 30s default block on `acquire`? Recommendation: yes for sync API calls. For background tasks, override to 60s.

---

## Dependencies

- **Blocks:** None — all additive
- **Depends on:** Spec A (`tracked_task` decorator, `mark_stage_updated`)
- **Supersedes JIRA:** Implicitly KAN-401, KAN-402, KAN-403, KAN-404 (DQ scanner would have caught these)

---

## Doc Delta

- `docs/TDD.md`: add Section "Data Quality + Retention", document DQ scanner + retention tasks + compression policy
- `docs/PRD.md`: no change
- `docs/FSD.md`: add FR for "in-app data quality alerts"
- `README.md`: add note about retention windows
- ADR-013: "Outbound rate limiter for third-party APIs (yfinance, news providers)"
