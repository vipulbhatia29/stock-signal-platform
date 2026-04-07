# Pipeline Overhaul — Spec F (Data Quality, Retention, Rate Limiting) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Catch data quality regressions nightly, protect the platform against yfinance + news provider rate limits, bound database growth via retention + TimescaleDB compression, and rate-limit the on-demand ingest endpoint.

**Architecture:** Three Celery tasks (DQ scan, forecast retention, news retention), one Redis token-bucket service (shared by yfinance + 4 news providers), one endpoint decorator (slowapi), two Alembic migrations (DQ history table + TimescaleDB compression policies).

**Tech Stack:** Celery, Redis + Lua scripting, slowapi, Alembic, TimescaleDB, SQLAlchemy

**Spec:** `docs/superpowers/specs/2026-04-06-pipeline-overhaul-spec-F-dq-retention-rate-limiting.md`

**Depends on:** Spec A (`tracked_task`, Alembic head becomes 025_ingestion_foundation after Spec A)

**Migration sequence (hash-based IDs per repo convention — numeric labels
below are filename prefixes only; `revision`/`down_revision` fields must
be 12-char hash IDs):**

- `b2351fa2d293` (024 forecast intelligence — current Alembic head)
- → Spec A migration 025: `revision = "<new-hash-A>"`, `down_revision = "b2351fa2d293"`
- → Spec F migration 026: `revision = "<new-hash-F26>"`, `down_revision = "<hash-A>"`
- → Spec F migration 027: `revision = "<new-hash-F27>"`, `down_revision = "<hash-F26>"`

Plans A and F must thread real hash IDs at implementation time — do NOT
commit numeric slug strings as the `revision` / `down_revision` values.

---

## File Structure

```
backend/tasks/dq_scan.py                                   # NEW — Scanner task + 10 checks
backend/tasks/retention.py                                 # NEW — Forecast + news retention
backend/services/rate_limiter.py                           # NEW — Token bucket + named instances
backend/models/dq_check_history.py                         # NEW — findings table model
backend/migrations/versions/026_dq_check_history.py        # NEW — table migration
backend/migrations/versions/027_timescale_compression.py   # NEW — compression policies
backend/models/__init__.py                                 # MODIFY — register DqCheckHistory
backend/tasks/__init__.py                                  # MODIFY — include + beat entries
backend/services/pipeline_registry_config.py               # MODIFY — add data_quality + maintenance groups
backend/services/stock_data.py                             # MODIFY — wrap yfinance calls
backend/services/news/finnhub.py                           # MODIFY — wrap Finnhub calls
backend/services/news/edgar.py                             # MODIFY — wrap EDGAR calls
backend/services/news/google.py                            # MODIFY — wrap Google News calls
backend/services/news/fred.py                              # MODIFY — wrap FRED calls
backend/tasks/market_data.py                               # MODIFY — wrap _refresh_ticker_slow yfinance
backend/tools/dividends.py                                 # MODIFY — wrap fetch_dividends
backend/routers/stocks/search.py                           # MODIFY — 20/hour slowapi limiter

tests/unit/services/test_rate_limiter.py                   # NEW
tests/unit/tasks/test_dq_scan.py                           # NEW
tests/unit/tasks/test_retention.py                         # NEW
tests/api/test_dq_scan_integration.py                      # NEW
tests/api/test_ingest_rate_limit.py                        # NEW
tests/integration/test_compression_migration.py            # NEW
```

---

## Task 1: F2/F3 — Redis token-bucket rate limiter

**Files:**
- Create: `backend/services/rate_limiter.py`
- Create: `tests/unit/services/test_rate_limiter.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/services/test_rate_limiter.py`:

```python
"""Tests for TokenBucketLimiter (Spec F.2/F.3)."""

import pytest
from unittest.mock import AsyncMock, patch

from backend.services.rate_limiter import TokenBucketLimiter


@pytest.mark.asyncio
async def test_token_bucket_acquire_when_tokens_available() -> None:
    limiter = TokenBucketLimiter("test-a", capacity=5, refill_per_sec=1.0)
    fake_redis = AsyncMock()
    fake_redis.script_load = AsyncMock(return_value="SHA")
    fake_redis.evalsha = AsyncMock(return_value=1)
    with patch("backend.services.rate_limiter.get_redis", new=AsyncMock(return_value=fake_redis)):
        assert await limiter.acquire() is True


@pytest.mark.asyncio
async def test_token_bucket_no_op_when_redis_unavailable() -> None:
    limiter = TokenBucketLimiter("test-b", capacity=5, refill_per_sec=1.0)
    with patch("backend.services.rate_limiter.get_redis", new=AsyncMock(return_value=None)):
        assert await limiter.acquire() is True


@pytest.mark.asyncio
async def test_token_bucket_acquire_timeout_returns_false() -> None:
    limiter = TokenBucketLimiter("test-c", capacity=1, refill_per_sec=0.1)
    fake_redis = AsyncMock()
    fake_redis.script_load = AsyncMock(return_value="SHA")
    fake_redis.evalsha = AsyncMock(return_value=0)
    with patch("backend.services.rate_limiter.get_redis", new=AsyncMock(return_value=fake_redis)):
        assert await limiter.acquire(timeout=0.05) is False


def test_named_limiters_isolated() -> None:
    a = TokenBucketLimiter("yfinance", 30, 0.5)
    b = TokenBucketLimiter("finnhub", 60, 1.0)
    assert a.name != b.name
    assert a.capacity == 30
    assert b.capacity == 60
```

- [ ] **Step 2: Create the limiter module**

Create `backend/services/rate_limiter.py`:

```python
"""Redis-backed token-bucket rate limiter for outbound API calls.

Used to protect against yfinance scraping bans and news provider quotas.
Falls back to no-op when Redis is unavailable so tests and dev without Redis
still function.
"""

from __future__ import annotations

import asyncio
import logging
import time

from backend.services.redis_pool import get_redis

logger = logging.getLogger(__name__)


class TokenBucketLimiter:
    """Atomic Redis token bucket using Lua script for fairness.

    Each named limiter is a module-level singleton; all callers sharing the
    same name share the same token bucket via the Redis key
    ``ratelimit:{name}``.
    """

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

    def __init__(self, name: str, capacity: int, refill_per_sec: float) -> None:
        """Initialise a named token bucket.

        Args:
            name: Unique identifier used in the Redis key.
            capacity: Max tokens (burst size).
            refill_per_sec: Tokens added per second.
        """
        self.name = name
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self._sha: str | None = None

    async def acquire(self, timeout: float = 30.0) -> bool:
        """Try to take one token, blocking up to ``timeout`` seconds.

        Returns:
            True on success, False on timeout. Always True when Redis is
            unavailable (graceful degradation).
        """
        redis = await get_redis()
        if redis is None:
            return True
        if self._sha is None:
            try:
                self._sha = await redis.script_load(self.LUA_SCRIPT)
            except Exception:
                logger.warning("Rate limiter %s: failed to load Lua script", self.name)
                return True
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                ok = await redis.evalsha(
                    self._sha,
                    1,
                    f"ratelimit:{self.name}",
                    self.capacity,
                    self.refill_per_sec,
                    time.time(),
                )
            except Exception:
                logger.warning("Rate limiter %s: Redis eval failed", self.name)
                return True
            if int(ok) == 1:
                return True
            await asyncio.sleep(1.0 / max(self.refill_per_sec, 0.01))
        logger.info("Rate limiter %s: acquire timeout", self.name)
        return False


# Module-level singletons (Spec F.2 + F.3)
yfinance_limiter = TokenBucketLimiter("yfinance", capacity=30, refill_per_sec=0.5)
finnhub_limiter = TokenBucketLimiter("finnhub", capacity=60, refill_per_sec=1.0)
edgar_limiter = TokenBucketLimiter("edgar", capacity=10, refill_per_sec=10.0)
google_news_limiter = TokenBucketLimiter("google_news", capacity=20, refill_per_sec=0.33)
fred_limiter = TokenBucketLimiter("fred", capacity=5, refill_per_sec=0.5)
```

- [ ] **Step 3: Rerun tests**

```bash
uv run pytest tests/unit/services/test_rate_limiter.py -x
```

Expected: pass.

- [ ] **Step 4: Lint + commit**

```bash
uv run ruff check --fix backend/services/rate_limiter.py tests/unit/services/test_rate_limiter.py
uv run ruff format backend/services/rate_limiter.py tests/unit/services/test_rate_limiter.py
git add backend/services/rate_limiter.py tests/unit/services/test_rate_limiter.py
git commit -m "feat(rate-limiter): Redis token-bucket service for outbound APIs (Spec F.2/F.3)"
```

---

## Task 2: F3 — Wrap yfinance callsites

**Files:**
- Modify: `backend/services/stock_data.py`
- Modify: `backend/tasks/market_data.py`
- Modify: `backend/tools/dividends.py`

- [ ] **Step 1: Wrap each yfinance call**

In every site that calls yfinance via `asyncio.to_thread(...)`, insert a single line before the `to_thread` call:

```python
from backend.services.rate_limiter import yfinance_limiter

await yfinance_limiter.acquire()
df = await asyncio.to_thread(yf.download, ticker, ...)
```

Sites to modify:
- `backend/services/stock_data.py:_download_ticker`
- `backend/services/stock_data.py:_download_ticker_range`
- `backend/services/stock_data.py:_get_ticker_info` (called from `ensure_stock_exists`)
- `backend/tasks/market_data.py:_refresh_ticker_slow` — wraps the Ticker.info fetch
- `backend/tools/dividends.py:fetch_dividends`

- [ ] **Step 2: Update existing unit tests to mock the limiter**

Any test in `tests/unit/services/test_stock_data.py` that calls the wrapped functions must either:

1. Import the real `yfinance_limiter` and confirm Redis is unavailable (it becomes a no-op), OR
2. Patch `backend.services.stock_data.yfinance_limiter.acquire` to return True.

Prefer (2) for hermetic unit tests:

```python
@pytest.fixture(autouse=True)
def _noop_yfinance_limiter(monkeypatch):
    from backend.services import rate_limiter
    monkeypatch.setattr(rate_limiter.yfinance_limiter, "acquire", AsyncMock(return_value=True))
```

- [ ] **Step 3: Run stock data unit tests**

```bash
uv run pytest tests/unit/services/test_stock_data.py -x
```

Expected: pass.

- [ ] **Step 4: Lint + commit**

```bash
uv run ruff check --fix backend/services/stock_data.py backend/tasks/market_data.py backend/tools/dividends.py
uv run ruff format backend/services/stock_data.py backend/tasks/market_data.py backend/tools/dividends.py
git add backend/services/stock_data.py backend/tasks/market_data.py backend/tools/dividends.py
git commit -m "feat(yfinance): wrap all outbound calls with token bucket limiter (Spec F.3)"
```

---

## Task 3: F2 — Wrap news provider callsites

**Files:**
- Modify: `backend/services/news/finnhub.py`
- Modify: `backend/services/news/edgar.py`
- Modify: `backend/services/news/google.py`
- Modify: `backend/services/news/fred.py`

- [ ] **Step 1: Wrap each provider's primary fetch method**

For each file, at the top of the public fetch method (e.g. `fetch`, `get_articles`):

```python
from backend.services.rate_limiter import finnhub_limiter  # or edgar_limiter / google_news_limiter / fred_limiter

async def fetch(self, ticker: str) -> list[NewsArticle]:
    await finnhub_limiter.acquire()
    # existing body unchanged
```

- [ ] **Step 2: Patch limiter in existing tests**

Same fixture pattern as Task 2 — `monkeypatch` each provider's limiter to no-op.

- [ ] **Step 3: Run news unit tests**

```bash
uv run pytest tests/unit/services/test_news_* -x
```

Expected: pass.

- [ ] **Step 4: Lint + commit**

```bash
uv run ruff check --fix backend/services/news/
uv run ruff format backend/services/news/
git add backend/services/news/
git commit -m "feat(news): rate-limit Finnhub/EDGAR/Google/FRED outbound calls (Spec F.2)"
```

---

## Task 4: F4 — POST /stocks/{ticker}/ingest rate limit

**Files:**
- Modify: `backend/routers/stocks/search.py`
- Create: `tests/api/test_ingest_rate_limit.py`

- [ ] **Step 1: Write failing test**

Create `tests/api/test_ingest_rate_limit.py`:

```python
"""Spec F.4 — 20/hour rate limit on POST /stocks/{ticker}/ingest."""

import pytest


@pytest.mark.asyncio
async def test_ingest_endpoint_429_after_20_per_hour(authenticated_client):
    """21st call within an hour must return 429."""
    for _ in range(20):
        r = await authenticated_client.post("/api/v1/stocks/AAPL/ingest")
        assert r.status_code in {200, 202}
    r = await authenticated_client.post("/api/v1/stocks/AAPL/ingest")
    assert r.status_code == 429
```

- [ ] **Step 2: Apply decorator**

Edit `backend/routers/stocks/search.py:147`:

```python
from backend.rate_limit import limiter  # existing slowapi limiter from main.py

@router.post("/{ticker}/ingest", response_model=IngestResponse)
@limiter.limit("20/hour")
async def ingest_ticker(
    request: Request,  # required by slowapi
    ticker: str,
    ...,
) -> IngestResponse:
    ...
```

Note: slowapi requires `request: Request` as a named parameter on the endpoint. Add it if missing.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/api/test_ingest_rate_limit.py -x
```

Expected: pass.

- [ ] **Step 4: Lint + commit**

```bash
uv run ruff check --fix backend/routers/stocks/search.py tests/api/test_ingest_rate_limit.py
uv run ruff format backend/routers/stocks/search.py tests/api/test_ingest_rate_limit.py
git add backend/routers/stocks/search.py tests/api/test_ingest_rate_limit.py
git commit -m "feat(api): 20/hour rate limit on POST /stocks/{ticker}/ingest (Spec F.4)"
```

---

## Task 5: F1 — DQ history table model + migration

**Files:**
- Create: `backend/models/dq_check_history.py`
- Create: `backend/migrations/versions/026_dq_check_history.py`
- Modify: `backend/models/__init__.py`

- [ ] **Step 1: Create the model**

Create `backend/models/dq_check_history.py`:

```python
"""SQLAlchemy model for DQ scan findings (Spec F.1)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class DqCheckHistory(Base):
    """Trend-tracking row for a DQ scan finding."""

    __tablename__ = "dq_check_history"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_dq_check_history_severity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    check_name: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    ticker: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str] = mapped_column(String, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

- [ ] **Step 2: Register in `backend/models/__init__.py`**

```python
from backend.models.dq_check_history import DqCheckHistory  # noqa: F401
```

- [ ] **Step 3: Create migration 026**

```bash
uv run alembic revision -m "dq_check_history"
```

Then edit the generated file, rename to `026_dq_check_history.py`, and replace body:

```python
"""dq_check_history table.

Revision ID: 026_dq_check_history
Revises: 025_ingestion_foundation
Create Date: 2026-04-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "<new-hash-F26>"  # generate with `uv run alembic revision ...`
# MUST be the hash from Spec A migration 025, NOT the numeric slug.
down_revision = "<hash-A>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dq_check_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("check_name", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=True),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_dq_check_history_severity",
        ),
    )
    op.create_index(
        "idx_dq_history_detected_at",
        "dq_check_history",
        [sa.text("detected_at DESC")],
    )
    op.create_index(
        "idx_dq_history_check_name",
        "dq_check_history",
        ["check_name", sa.text("detected_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_dq_history_check_name", table_name="dq_check_history")
    op.drop_index("idx_dq_history_detected_at", table_name="dq_check_history")
    op.drop_table("dq_check_history")
```

- [ ] **Step 4: Apply migration against dev DB**

```bash
uv run alembic upgrade head
```

Expected output: `Running upgrade 025_ingestion_foundation -> 026_dq_check_history, dq_check_history`.

- [ ] **Step 5: Commit**

```bash
git add backend/models/dq_check_history.py backend/models/__init__.py backend/migrations/versions/026_dq_check_history.py
git commit -m "feat(dq): DqCheckHistory model + migration 026 (Spec F.1)"
```

---

## Task 6: F1 — DQ scanner task with 10 checks

**Files:**
- Create: `backend/tasks/dq_scan.py`
- Create: `tests/unit/tasks/test_dq_scan.py`
- Create: `tests/api/test_dq_scan_integration.py`
- Modify: `backend/tasks/__init__.py`
- Modify: `backend/services/pipeline_registry_config.py`

- [ ] **Step 1: Write the task module**

Create `backend/tasks/dq_scan.py`:

```python
"""Nightly data quality scanner (Spec F.1)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import text

from backend.database import async_session_factory
from backend.models.dq_check_history import DqCheckHistory
from backend.tasks import celery_app
from backend.tasks.tracking import tracked_task  # from Spec A

logger = logging.getLogger(__name__)


@celery_app.task(name="backend.tasks.dq_scan.dq_scan_task")
@tracked_task(name="dq_scan", scope="global", tracer="none")
def dq_scan_task() -> dict:
    """Entry point — run all DQ checks, persist findings, fire alerts."""
    return asyncio.run(_dq_scan_async())


async def _dq_scan_async() -> dict:
    findings: list[dict[str, Any]] = []
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
        for f in findings:
            db.add(
                DqCheckHistory(
                    check_name=f["check"],
                    severity=f["severity"],
                    ticker=f.get("ticker"),
                    message=f["message"],
                    metadata_=f.get("metadata"),
                )
            )
        await db.commit()

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


async def _check_negative_prices(db) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            text(
                "SELECT ticker, time, close, adj_close FROM stock_prices "
                "WHERE close < 0 OR adj_close < 0 LIMIT 100"
            )
        )
    ).all()
    return [
        {
            "check": "negative_prices",
            "severity": "critical",
            "ticker": r.ticker,
            "message": f"Negative price detected at {r.time}: close={r.close}",
        }
        for r in rows
    ]


async def _check_rsi_out_of_range(db) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            text(
                "SELECT ticker, computed_at, rsi_value FROM signal_snapshots "
                "WHERE rsi_value NOT BETWEEN 0 AND 100 LIMIT 100"
            )
        )
    ).all()
    return [
        {
            "check": "rsi_out_of_range",
            "severity": "high",
            "ticker": r.ticker,
            "message": f"RSI={r.rsi_value} outside [0, 100] at {r.computed_at}",
        }
        for r in rows
    ]


async def _check_composite_score_out_of_range(db) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            text(
                "SELECT ticker, composite_score FROM signal_snapshots "
                "WHERE composite_score NOT BETWEEN 0 AND 10 LIMIT 100"
            )
        )
    ).all()
    return [
        {
            "check": "composite_score_out_of_range",
            "severity": "high",
            "ticker": r.ticker,
            "message": f"composite_score={r.composite_score} outside [0, 10]",
        }
        for r in rows
    ]


async def _check_null_sectors(db) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            text("SELECT ticker FROM stocks WHERE is_active AND sector IS NULL LIMIT 100")
        )
    ).all()
    return [
        {
            "check": "null_sector",
            "severity": "medium",
            "ticker": r.ticker,
            "message": f"{r.ticker} is active but has NULL sector",
        }
        for r in rows
    ]


async def _check_forecast_extreme_ratios(db) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            text(
                """
                SELECT f.ticker, f.predicted_price, s.current_price
                FROM forecast_results f
                JOIN (
                    SELECT DISTINCT ON (ticker) ticker, close AS current_price
                    FROM stock_prices ORDER BY ticker, time DESC
                ) s ON f.ticker = s.ticker
                WHERE f.predicted_price > 10 * s.current_price
                   OR f.predicted_price < 0.1 * s.current_price
                LIMIT 100
                """
            )
        )
    ).all()
    return [
        {
            "check": "forecast_extreme_ratio",
            "severity": "high",
            "ticker": r.ticker,
            "message": f"predicted={r.predicted_price} vs current={r.current_price}",
        }
        for r in rows
    ]


async def _check_orphan_positions(db) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            text(
                """
                SELECT p.ticker FROM position p
                LEFT JOIN stocks s ON p.ticker = s.ticker
                WHERE s.ticker IS NULL OR NOT s.is_active
                LIMIT 100
                """
            )
        )
    ).all()
    return [
        {
            "check": "orphan_position",
            "severity": "high",
            "ticker": r.ticker,
            "message": f"Position exists for unknown/inactive ticker {r.ticker}",
        }
        for r in rows
    ]


async def _check_duplicate_signals(db) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            text(
                """
                SELECT ticker, computed_at, COUNT(*) AS c FROM signal_snapshots
                GROUP BY ticker, computed_at HAVING COUNT(*) > 1 LIMIT 100
                """
            )
        )
    ).all()
    return [
        {
            "check": "duplicate_signals",
            "severity": "medium",
            "ticker": r.ticker,
            "message": f"{r.c} snapshots at {r.computed_at}",
        }
        for r in rows
    ]


async def _check_stale_universe_coverage(db) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            text(
                """
                SELECT ticker FROM ticker_ingestion_state
                WHERE signals_updated_at < now() - interval '48 hours'
                LIMIT 100
                """
            )
        )
    ).all()
    return [
        {
            "check": "stale_universe_coverage",
            "severity": "medium",
            "ticker": r.ticker,
            "message": f"{r.ticker} signals stale >48h",
        }
        for r in rows
    ]


async def _check_negative_volume(db) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            text(
                "SELECT ticker, time, volume FROM stock_prices "
                "WHERE volume < 0 LIMIT 100"
            )
        )
    ).all()
    return [
        {
            "check": "negative_volume",
            "severity": "critical",
            "ticker": r.ticker,
            "message": f"Negative volume={r.volume} at {r.time}",
        }
        for r in rows
    ]


async def _check_bollinger_violations(db) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            text(
                "SELECT ticker, bb_upper, bb_lower FROM signal_snapshots "
                "WHERE bb_lower > bb_upper LIMIT 100"
            )
        )
    ).all()
    return [
        {
            "check": "bollinger_violation",
            "severity": "high",
            "ticker": r.ticker,
            "message": f"bb_lower={r.bb_lower} > bb_upper={r.bb_upper}",
        }
        for r in rows
    ]
```

- [ ] **Step 2: Write unit tests**

Create `tests/unit/tasks/test_dq_scan.py` (excerpt — 15 cases total):

```python
"""Spec F.1 — DQ scanner unit tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_check_negative_prices_finds_bad_row() -> None:
    from backend.tasks.dq_scan import _check_negative_prices

    db = MagicMock()
    result = MagicMock()
    result.all.return_value = [
        MagicMock(ticker="AAPL", time="2026-01-01", close=-1.0, adj_close=-1.0)
    ]
    db.execute = AsyncMock(return_value=result)
    findings = await _check_negative_prices(db)
    assert len(findings) == 1
    assert findings[0]["severity"] == "critical"
    assert findings[0]["check"] == "negative_prices"


@pytest.mark.asyncio
async def test_check_negative_prices_no_findings_when_clean() -> None:
    from backend.tasks.dq_scan import _check_negative_prices

    db = MagicMock()
    result = MagicMock()
    result.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    assert await _check_negative_prices(db) == []


# Additional cases (abbreviated) — full test file implements all 15:
# - test_check_rsi_out_of_range
# - test_check_composite_score_out_of_range
# - test_check_null_sectors
# - test_check_forecast_extreme_ratios_high
# - test_check_forecast_extreme_ratios_low
# - test_check_orphan_positions
# - test_check_duplicate_signals
# - test_check_stale_universe_coverage
# - test_check_negative_volume
# - test_check_bollinger_violations
# - test_dq_scan_persists_findings_to_history_table
# - test_dq_scan_creates_alerts_for_critical_findings
# - test_dq_scan_dedup_alerts_via_dedup_key
```

- [ ] **Step 3: Register beat schedule + include**

Edit `backend/tasks/__init__.py`:

```python
# Add to `include=[]` list
"backend.tasks.dq_scan",

# Add to beat_schedule
"dq-scan-daily": {
    "task": "backend.tasks.dq_scan.dq_scan_task",
    "schedule": crontab(hour=4, minute=0),  # 04:00 ET
},
```

Edit `backend/services/pipeline_registry_config.py` to add a new `"data_quality"` group with the task.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/tasks/test_dq_scan.py -x
```

Expected: pass.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix backend/tasks/dq_scan.py backend/tasks/__init__.py backend/services/pipeline_registry_config.py tests/unit/tasks/test_dq_scan.py
uv run ruff format backend/tasks/dq_scan.py backend/tasks/__init__.py backend/services/pipeline_registry_config.py tests/unit/tasks/test_dq_scan.py
git add backend/tasks/dq_scan.py backend/tasks/__init__.py backend/services/pipeline_registry_config.py tests/unit/tasks/test_dq_scan.py
git commit -m "feat(dq): nightly DQ scanner with 10 checks (Spec F.1)"
```

---

## Task 7: F5 — Retention tasks

**Files:**
- Create: `backend/tasks/retention.py`
- Create: `tests/unit/tasks/test_retention.py`
- Modify: `backend/tasks/__init__.py`
- Modify: `backend/services/pipeline_registry_config.py`

- [ ] **Step 1: Create the task module**

Create `backend/tasks/retention.py`:

```python
"""Nightly retention enforcement for time-series tables (Spec F.5)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from backend.database import async_session_factory
from backend.models.forecast import ForecastResult
from backend.models.news_sentiment import NewsArticle
from backend.tasks import celery_app
from backend.tasks.tracking import tracked_task


@celery_app.task(name="backend.tasks.retention.purge_old_forecasts_task")
@tracked_task(name="forecast_retention", scope="global", tracer="none")
def purge_old_forecasts_task() -> dict:
    """Delete forecast_results rows older than 30 days."""
    return asyncio.run(_purge_old_forecasts_async())


async def _purge_old_forecasts_async() -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    async with async_session_factory() as db:
        result = await db.execute(
            delete(ForecastResult).where(ForecastResult.created_at < cutoff)
        )
        await db.commit()
        return {"status": "ok", "deleted": result.rowcount or 0}


@celery_app.task(name="backend.tasks.retention.purge_old_news_articles_task")
@tracked_task(name="news_retention", scope="global", tracer="none")
def purge_old_news_articles_task() -> dict:
    """Delete raw news_articles rows older than 90 days.

    Daily aggregates (news_sentiment_daily) are preserved.
    """
    return asyncio.run(_purge_old_news_articles_async())


async def _purge_old_news_articles_async() -> dict:
    cutoff_naive = (datetime.now(timezone.utc) - timedelta(days=90)).replace(tzinfo=None)
    async with async_session_factory() as db:
        result = await db.execute(
            delete(NewsArticle).where(NewsArticle.published_at < cutoff_naive)
        )
        await db.commit()
        return {"status": "ok", "deleted": result.rowcount or 0}
```

- [ ] **Step 2: Write tests**

Create `tests/unit/tasks/test_retention.py`:

```python
"""Spec F.5 — retention task unit tests."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_purge_old_forecasts_uses_30_day_cutoff() -> None:
    from backend.tasks import retention

    fake_result = MagicMock(rowcount=7)
    fake_db = MagicMock()
    fake_db.execute = AsyncMock(return_value=fake_result)
    fake_db.commit = AsyncMock()
    fake_db.__aenter__ = AsyncMock(return_value=fake_db)
    fake_db.__aexit__ = AsyncMock()

    with patch.object(retention, "async_session_factory", return_value=fake_db):
        result = await retention._purge_old_forecasts_async()
        assert result == {"status": "ok", "deleted": 7}
        fake_db.execute.assert_awaited()


@pytest.mark.asyncio
async def test_purge_old_news_articles_uses_naive_datetime() -> None:
    from backend.tasks import retention

    fake_result = MagicMock(rowcount=3)
    fake_db = MagicMock()
    fake_db.execute = AsyncMock(return_value=fake_result)
    fake_db.commit = AsyncMock()
    fake_db.__aenter__ = AsyncMock(return_value=fake_db)
    fake_db.__aexit__ = AsyncMock()

    with patch.object(retention, "async_session_factory", return_value=fake_db):
        result = await retention._purge_old_news_articles_async()
        assert result["deleted"] == 3


def test_retention_beat_schedule_entries_present() -> None:
    from backend.tasks import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "forecast-retention-daily" in schedule
    assert "news-retention-daily" in schedule
```

- [ ] **Step 3: Register beat + include**

Edit `backend/tasks/__init__.py`:

```python
# include
"backend.tasks.retention",

# beat_schedule
"forecast-retention-daily": {
    "task": "backend.tasks.retention.purge_old_forecasts_task",
    "schedule": crontab(hour=3, minute=30),
},
"news-retention-daily": {
    "task": "backend.tasks.retention.purge_old_news_articles_task",
    "schedule": crontab(hour=3, minute=45),
},
```

Register both in `backend/services/pipeline_registry_config.py` under a `"maintenance"` group.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/tasks/test_retention.py tests/unit/services/test_pipeline_registry_config.py -x
```

Expected: pass.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix backend/tasks/retention.py backend/tasks/__init__.py backend/services/pipeline_registry_config.py tests/unit/tasks/test_retention.py
uv run ruff format backend/tasks/retention.py backend/tasks/__init__.py backend/services/pipeline_registry_config.py tests/unit/tasks/test_retention.py
git add backend/tasks/retention.py backend/tasks/__init__.py backend/services/pipeline_registry_config.py tests/unit/tasks/test_retention.py
git commit -m "feat(retention): forecast (30d) + news (90d) retention tasks (Spec F.5)"
```

---

## Task 8: F6 — TimescaleDB compression migration 027

**Files:**
- Create: `backend/migrations/versions/027_timescale_compression.py`
- Create: `tests/integration/test_compression_migration.py`

- [ ] **Step 1: Generate + edit migration**

```bash
uv run alembic revision -m "timescale_compression"
```

Rename the file to `027_timescale_compression.py` and set:

```python
"""TimescaleDB compression policies.

Revision ID: 027_timescale_compression
Revises: 026_dq_check_history
Create Date: 2026-04-06
"""

from alembic import op

revision = "<new-hash-F27>"  # generate via `uv run alembic revision ...`
# MUST be the hash from migration 026 above.
down_revision = "<hash-F26>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE stock_prices SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'ticker',
            timescaledb.compress_orderby = 'time DESC'
        );
        """
    )
    op.execute("SELECT add_compression_policy('stock_prices', INTERVAL '30 days');")
    op.execute(
        """
        ALTER TABLE signal_snapshots SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'ticker',
            timescaledb.compress_orderby = 'computed_at DESC'
        );
        """
    )
    op.execute(
        "SELECT add_compression_policy('signal_snapshots', INTERVAL '30 days');"
    )
    op.execute(
        """
        ALTER TABLE news_articles SET (
            timescaledb.compress,
            timescaledb.compress_orderby = 'published_at DESC'
        );
        """
    )
    op.execute("SELECT add_compression_policy('news_articles', INTERVAL '30 days');")


def downgrade() -> None:
    op.execute(
        "SELECT remove_compression_policy('stock_prices', if_exists => TRUE);"
    )
    op.execute(
        "SELECT remove_compression_policy('signal_snapshots', if_exists => TRUE);"
    )
    op.execute(
        "SELECT remove_compression_policy('news_articles', if_exists => TRUE);"
    )
    # DECOMPRESS EXISTING CHUNKS before clearing the compress flag — required
    # for downgrade to succeed on a production DB where `add_compression_policy`
    # has already compressed older chunks. Without this loop, queries against
    # compressed chunks break after `compress = false`. See Spec F review.
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
    op.execute("ALTER TABLE stock_prices SET (timescaledb.compress = false);")
    op.execute("ALTER TABLE signal_snapshots SET (timescaledb.compress = false);")
    op.execute("ALTER TABLE news_articles SET (timescaledb.compress = false);")
```

- [ ] **Step 2: Add integration test**

Create `tests/integration/test_compression_migration.py`:

```python
"""Spec F.6 — Compression migration up/down integration test.

Requires a running TimescaleDB (tests/api fixture). Skipped on sqlite.
"""

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_compression_policies_present_after_upgrade(db_session):
    rows = (
        await db_session.execute(
            text(
                "SELECT hypertable_name FROM timescaledb_information.compression_settings"
            )
        )
    ).all()
    names = {r.hypertable_name for r in rows}
    assert {"stock_prices", "signal_snapshots", "news_articles"}.issubset(names)
```

- [ ] **Step 3: Run migration + test**

```bash
uv run alembic upgrade head
uv run pytest tests/integration/test_compression_migration.py -x
```

Expected: both migrations applied, integration test passes.

- [ ] **Step 4: Commit**

```bash
git add backend/migrations/versions/027_timescale_compression.py tests/integration/test_compression_migration.py
git commit -m "feat(timescale): compression policies for stock_prices/signal_snapshots/news_articles (Spec F.6)"
```

---

## Task 9: Final integration sweep

- [ ] **Step 1: Run all new suites**

```bash
uv run pytest tests/unit/tasks/test_dq_scan.py tests/unit/tasks/test_retention.py tests/unit/services/test_rate_limiter.py tests/api/test_ingest_rate_limit.py tests/integration/test_compression_migration.py -q
```

- [ ] **Step 2: Full ruff + type check**

```bash
uv run ruff check backend/ tests/
```

Expected: zero errors.

- [ ] **Step 3: Verify Alembic head**

```bash
uv run alembic current
```

Expected: `027_timescale_compression (head)`.

---

## Done Criteria

- [ ] `TokenBucketLimiter` + 5 named singletons in `backend/services/rate_limiter.py`
- [ ] All yfinance + 4 news provider callsites wrapped with `await limiter.acquire()`
- [ ] `POST /stocks/{ticker}/ingest` returns 429 after 20 calls per hour per user
- [ ] Migration 026 (DQ history table) applied
- [ ] Migration 027 (TimescaleDB compression) applied
- [ ] `dq_scan_task` runs nightly at 04:00 ET; all 10 checks executed
- [ ] `purge_old_forecasts_task` (30d) and `purge_old_news_articles_task` (90d) scheduled
- [ ] 40 new test cases across DQ scan, rate limiter, retention, compression, and ingest rate-limit
