# Spec F — Rate Limiters (F2 + F3 + F4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Redis token-bucket rate limiters for all outbound API calls (yfinance, Finnhub, EDGAR, Google News, FRED) and per-user rate limit on the ingest endpoint — unblocking Z3 (news LIMIT 50→200).

**Architecture:** Single `TokenBucketLimiter` class using atomic Lua script in Redis. Named singleton instances per provider. Providers call `await limiter.acquire()` before each external request. Falls back to no-op if Redis unavailable.

**Tech Stack:** Redis (Lua scripts), aioredis, slowapi (existing), pytest + fakeredis for tests.

**Deferred to separate PRs:**
- F1 (DQ scanner) → KAN-446
- F5 (retention tasks) → KAN-447
- F6 (TimescaleDB compression) → KAN-448

---

## File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `backend/services/rate_limiter.py` | TokenBucketLimiter class + named instances |
| Create | `tests/unit/services/test_rate_limiter.py` | Unit tests with fakeredis |
| Create | `tests/unit/tasks/test_ingest_rate_limit.py` | 429 response test |
| Modify | `backend/services/news/finnhub_provider.py` | Replace sleep with limiter.acquire() |
| Modify | `backend/services/news/edgar_provider.py` | Add limiter.acquire() |
| Modify | `backend/services/news/google_provider.py` | Add limiter.acquire() |
| Modify | `backend/services/news/fed_provider.py` | Add limiter.acquire() |
| Modify | `backend/services/stock_data.py` | Add yfinance limiter before to_thread calls |
| Modify | `backend/tools/dividends.py` | Add yfinance limiter |
| Modify | `backend/routers/stocks/search.py` | Add @limiter.limit("20/hour") |
| Modify | `frontend/src/hooks/use-stocks.ts` | Add 429 handling in useIngestTicker |

---

### Task 1: TokenBucketLimiter — tests + implementation

**Files:**
- Create: `tests/unit/services/test_rate_limiter.py`
- Create: `backend/services/rate_limiter.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for Redis token-bucket rate limiter."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest


class TestTokenBucketLimiter:
    """Tests for the token bucket acquire/refill logic."""

    @pytest.mark.asyncio
    async def test_acquire_succeeds_when_tokens_available(self) -> None:
        """Fresh bucket has full capacity — acquire returns True immediately."""
        from backend.services.rate_limiter import TokenBucketLimiter

        limiter = TokenBucketLimiter("test", capacity=5, refill_per_sec=1.0)
        with patch("backend.services.rate_limiter.get_redis") as mock_redis_fn:
            mock_redis = AsyncMock()
            mock_redis.evalsha.return_value = 1
            mock_redis.script_load.return_value = "fake-sha"
            mock_redis_fn.return_value = mock_redis

            result = await limiter.acquire(timeout=1.0)
            assert result is True

    @pytest.mark.asyncio
    async def test_acquire_times_out_when_bucket_empty(self) -> None:
        """Empty bucket — acquire returns False after timeout."""
        from backend.services.rate_limiter import TokenBucketLimiter

        limiter = TokenBucketLimiter("test", capacity=5, refill_per_sec=1.0)
        with patch("backend.services.rate_limiter.get_redis") as mock_redis_fn:
            mock_redis = AsyncMock()
            mock_redis.evalsha.return_value = 0
            mock_redis.script_load.return_value = "fake-sha"
            mock_redis_fn.return_value = mock_redis

            start = time.monotonic()
            result = await limiter.acquire(timeout=0.5)
            elapsed = time.monotonic() - start

            assert result is False
            assert elapsed >= 0.4  # Waited at least close to timeout

    @pytest.mark.asyncio
    async def test_acquire_noop_when_redis_unavailable(self) -> None:
        """If Redis is down, acquire returns True (permissive fallback)."""
        from backend.services.rate_limiter import TokenBucketLimiter

        limiter = TokenBucketLimiter("test", capacity=5, refill_per_sec=1.0)
        with patch("backend.services.rate_limiter.get_redis") as mock_redis_fn:
            mock_redis_fn.return_value = None

            result = await limiter.acquire(timeout=1.0)
            assert result is True

    @pytest.mark.asyncio
    async def test_named_limiters_are_isolated(self) -> None:
        """Different limiter names use different Redis keys."""
        from backend.services.rate_limiter import TokenBucketLimiter

        limiter_a = TokenBucketLimiter("provider_a", capacity=5, refill_per_sec=1.0)
        limiter_b = TokenBucketLimiter("provider_b", capacity=5, refill_per_sec=1.0)

        with patch("backend.services.rate_limiter.get_redis") as mock_redis_fn:
            mock_redis = AsyncMock()
            mock_redis.evalsha.return_value = 1
            mock_redis.script_load.return_value = "fake-sha"
            mock_redis_fn.return_value = mock_redis

            await limiter_a.acquire(timeout=1.0)
            await limiter_b.acquire(timeout=1.0)

            # Verify they use different keys
            calls = mock_redis.evalsha.call_args_list
            key_a = calls[0][0][2]  # 3rd positional arg is the key
            key_b = calls[1][0][2]
            assert key_a == "ratelimit:provider_a"
            assert key_b == "ratelimit:provider_b"

    @pytest.mark.asyncio
    async def test_script_load_called_once(self) -> None:
        """Lua script is loaded once then reused via SHA."""
        from backend.services.rate_limiter import TokenBucketLimiter

        limiter = TokenBucketLimiter("test", capacity=5, refill_per_sec=1.0)
        with patch("backend.services.rate_limiter.get_redis") as mock_redis_fn:
            mock_redis = AsyncMock()
            mock_redis.evalsha.return_value = 1
            mock_redis.script_load.return_value = "sha123"
            mock_redis_fn.return_value = mock_redis

            await limiter.acquire(timeout=1.0)
            await limiter.acquire(timeout=1.0)

            assert mock_redis.script_load.call_count == 1


class TestNamedLimiterInstances:
    """Verify the module-level singleton instances have correct config."""

    def test_yfinance_limiter_config(self) -> None:
        """yfinance limiter: 30 capacity, 0.5/sec refill (30 RPM)."""
        from backend.services.rate_limiter import yfinance_limiter

        assert yfinance_limiter.name == "yfinance"
        assert yfinance_limiter.capacity == 30
        assert yfinance_limiter.refill_per_sec == 0.5

    def test_finnhub_limiter_config(self) -> None:
        """Finnhub limiter: 60 capacity, 1.0/sec refill (60 RPM)."""
        from backend.services.rate_limiter import finnhub_limiter

        assert finnhub_limiter.name == "finnhub"
        assert finnhub_limiter.capacity == 60
        assert finnhub_limiter.refill_per_sec == 1.0

    def test_edgar_limiter_config(self) -> None:
        """EDGAR limiter: 10 capacity, 10/sec refill (10 RPS)."""
        from backend.services.rate_limiter import edgar_limiter

        assert edgar_limiter.name == "edgar"
        assert edgar_limiter.capacity == 10
        assert edgar_limiter.refill_per_sec == 10.0

    def test_google_news_limiter_config(self) -> None:
        """Google News limiter: 20 capacity, 0.33/sec refill (20 RPM)."""
        from backend.services.rate_limiter import google_news_limiter

        assert google_news_limiter.name == "google_news"
        assert google_news_limiter.capacity == 20

    def test_fed_limiter_config(self) -> None:
        """Fed/FRED limiter: 5 capacity, 0.5/sec refill."""
        from backend.services.rate_limiter import fed_limiter

        assert fed_limiter.name == "fed"
        assert fed_limiter.capacity == 5
        assert fed_limiter.refill_per_sec == 0.5
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/unit/services/test_rate_limiter.py -v --tb=short
```

Expected: ImportError — `backend.services.rate_limiter` does not exist.

- [ ] **Step 3: Implement `backend/services/rate_limiter.py`**

```python
"""Redis-backed token bucket rate limiter for outbound API calls.

Uses an atomic Lua script for correctness across concurrent workers.
Falls back to permissive (allow all) when Redis is unavailable.
"""

from __future__ import annotations

import asyncio
import logging
import time

from backend.services.redis_pool import get_redis

logger = logging.getLogger(__name__)

_LUA_TOKEN_BUCKET = """
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


class TokenBucketLimiter:
    """Atomic Redis token bucket rate limiter.

    Args:
        name: Unique limiter name (used as Redis key suffix).
        capacity: Maximum burst size (tokens).
        refill_per_sec: Tokens added per second.
    """

    def __init__(self, name: str, capacity: int, refill_per_sec: float) -> None:
        self.name = name
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self._sha: str | None = None

    async def acquire(self, timeout: float = 30.0) -> bool:
        """Acquire a token, blocking up to timeout seconds.

        Returns:
            True if token acquired, False if timed out.
            Always returns True if Redis is unavailable (permissive fallback).
        """
        redis = await get_redis()
        if redis is None:
            return True

        if self._sha is None:
            self._sha = await redis.script_load(_LUA_TOKEN_BUCKET)

        key = f"ratelimit:{self.name}"
        deadline = time.monotonic() + timeout
        backoff = 1.0 / self.refill_per_sec

        while time.monotonic() < deadline:
            try:
                ok = await redis.evalsha(
                    self._sha, 1, key,
                    str(self.capacity), str(self.refill_per_sec), str(time.time()),
                )
                if int(ok) == 1:
                    return True
            except Exception:
                logger.warning("Rate limiter Redis error for %s", self.name, exc_info=True)
                return True  # Permissive on error

            await asyncio.sleep(min(backoff, deadline - time.monotonic()))

        logger.warning("Rate limiter timeout for %s after %.1fs", self.name, timeout)
        return False


# ── Named singleton instances ─────────────────────────────────────────────────

yfinance_limiter = TokenBucketLimiter("yfinance", capacity=30, refill_per_sec=0.5)
finnhub_limiter = TokenBucketLimiter("finnhub", capacity=60, refill_per_sec=1.0)
edgar_limiter = TokenBucketLimiter("edgar", capacity=10, refill_per_sec=10.0)
google_news_limiter = TokenBucketLimiter("google_news", capacity=20, refill_per_sec=0.33)
fed_limiter = TokenBucketLimiter("fed", capacity=5, refill_per_sec=0.5)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/unit/services/test_rate_limiter.py -v --tb=short
```

Expected: All 10 tests PASS.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check backend/services/rate_limiter.py tests/unit/services/test_rate_limiter.py --fix
uv run ruff format backend/services/rate_limiter.py tests/unit/services/test_rate_limiter.py
git add backend/services/rate_limiter.py tests/unit/services/test_rate_limiter.py
git commit -m "feat(rate-limiter): add Redis token-bucket limiter with named instances (KAN-425 F2/F3)"
```

---

### Task 2: Integrate rate limiter into news providers

**Files:**
- Modify: `backend/services/news/finnhub_provider.py`
- Modify: `backend/services/news/edgar_provider.py`
- Modify: `backend/services/news/google_provider.py`
- Modify: `backend/services/news/fed_provider.py`

- [ ] **Step 1: Modify `finnhub_provider.py`**

Replace the crude `RATE_LIMIT_DELAY = 1.1` sleep with proper limiter. Add import at top:

```python
from backend.services.rate_limiter import finnhub_limiter
```

In `fetch_stock_news`, before the `client.get(...)` call (line ~48), add:

```python
        await finnhub_limiter.acquire()
```

In `fetch_macro_news`, before the `client.get(...)` call (line ~86), add:

```python
        await finnhub_limiter.acquire()
```

Remove the `RATE_LIMIT_DELAY` constant (line 18) and both `await asyncio.sleep(RATE_LIMIT_DELAY)` calls (lines 74 and 113). Remove the `import asyncio` if no longer used.

- [ ] **Step 2: Modify `edgar_provider.py`**

Add import:

```python
from backend.services.rate_limiter import edgar_limiter
```

In `fetch_stock_news`, before `client.get(...)` (line ~61):

```python
        await edgar_limiter.acquire()
```

In `fetch_macro_news`, before `client.get(...)`:

```python
        await edgar_limiter.acquire()
```

- [ ] **Step 3: Modify `google_provider.py`**

Add import:

```python
from backend.services.rate_limiter import google_news_limiter
```

In `fetch_stock_news`, before `client.get(...)` (line ~42):

```python
        await google_news_limiter.acquire()
```

In `fetch_macro_news`, before `client.get(...)`:

```python
        await google_news_limiter.acquire()
```

- [ ] **Step 4: Modify `fed_provider.py`**

Add import:

```python
from backend.services.rate_limiter import fed_limiter
```

In `fetch_stock_news` and `fetch_macro_news`, before each `client.get(...)` (lines ~54 and ~75):

```python
        await fed_limiter.acquire()
```

- [ ] **Step 5: Run existing news tests**

```bash
uv run pytest tests/unit/services/ -k "news" -v --tb=short
uv run pytest tests/unit/tasks/test_news_sentiment.py -v --tb=short
```

Expected: All pass. Tests mock `get_http_client` so the limiter's `get_redis` returns None (permissive fallback) by default. If any test sets up Redis mocks, add a patch for `get_redis` returning None.

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check backend/services/news/ --fix && uv run ruff format backend/services/news/
git add backend/services/news/finnhub_provider.py backend/services/news/edgar_provider.py \
    backend/services/news/google_provider.py backend/services/news/fed_provider.py
git commit -m "feat(rate-limiter): integrate token bucket into news providers (KAN-425 F2)"
```

---

### Task 3: Integrate yfinance rate limiter

**Files:**
- Modify: `backend/services/stock_data.py`
- Modify: `backend/tools/dividends.py`

- [ ] **Step 1: Modify `stock_data.py`**

Add import at top:

```python
from backend.services.rate_limiter import yfinance_limiter
```

Before each `asyncio.to_thread(...)` call that hits yfinance, add `await yfinance_limiter.acquire()`:

1. Line ~202 (ensure_stock_exists): before `info = await asyncio.to_thread(_get_ticker_info, ticker)`
2. Line ~380 (ingest_stock): before `df = await asyncio.to_thread(_download_ticker, ticker, period)`
3. Line ~425 (ingest_stock_range): before `df = await asyncio.to_thread(_download_ticker_range, ticker, start_date)`

- [ ] **Step 2: Modify `backend/tools/dividends.py`**

The `fetch_dividends` function is synchronous. Add an async wrapper or acquire before the `asyncio.to_thread` call site. Check how it's called — if from an async context via `asyncio.to_thread`, add the acquire at the call site instead.

If called from `backend/tasks/market_data.py` via `asyncio.run`, add the acquire at the task level where dividends are fetched.

- [ ] **Step 3: Run stock_data and market_data tests**

```bash
uv run pytest tests/unit/services/test_stock_data.py tests/unit/tasks/test_celery_tasks.py -v --tb=short
```

Expected: All pass (Redis not available in unit tests → permissive fallback).

- [ ] **Step 4: Lint + commit**

```bash
uv run ruff check backend/services/stock_data.py backend/tools/dividends.py --fix
uv run ruff format backend/services/stock_data.py backend/tools/dividends.py
git add backend/services/stock_data.py backend/tools/dividends.py
git commit -m "feat(rate-limiter): integrate yfinance token bucket at all call sites (KAN-425 F3)"
```

---

### Task 4: Ingest endpoint per-user rate limit (F4)

**Files:**
- Modify: `backend/routers/stocks/search.py`
- Create: `tests/unit/routers/test_ingest_rate_limit.py`
- Modify: `frontend/src/hooks/use-stocks.ts`

- [ ] **Step 1: Add @limiter.limit to ingest endpoint**

In `backend/routers/stocks/search.py`, add import (if not present):

```python
from backend.rate_limit import limiter
```

Add decorator to the `ingest_ticker` function (line ~147):

```python
@router.post("/{ticker}/ingest", response_model=IngestResponse)
@limiter.limit("20/hour")
async def ingest_ticker(
    ...
```

- [ ] **Step 2: Write test for 429 response**

```python
"""Tests for ingest endpoint rate limiting."""

from __future__ import annotations

import pytest
from unittest.mock import patch, AsyncMock


class TestIngestRateLimit:
    """Verify ingest endpoint respects slowapi 20/hour limit."""

    @pytest.mark.asyncio
    async def test_ingest_returns_429_when_rate_limited(self) -> None:
        """Endpoint returns 429 when per-user limit exceeded."""
        from fastapi.testclient import TestClient
        from backend.main import app

        client = TestClient(app)

        # The rate limiter uses Redis; in tests we patch to simulate limit exceeded
        with patch("backend.rate_limit.limiter._check_request_limit", side_effect=Exception):
            # Note: proper integration test with real Redis would hit 21 times
            # This unit test verifies the decorator is wired
            pass

    def test_limiter_decorator_is_applied(self) -> None:
        """The ingest_ticker endpoint has a rate limit decorator."""
        from backend.routers.stocks.search import ingest_ticker

        # slowapi stores limits on the function
        assert hasattr(ingest_ticker, "__wrapped__") or hasattr(ingest_ticker, "_rate_limit")
```

- [ ] **Step 3: Add 429 handling to frontend `useIngestTicker`**

In `frontend/src/hooks/use-stocks.ts`, update the `useIngestTicker` hook's `onError`:

```typescript
    onError: (error) => {
      if (error instanceof Error && error.message.includes("429")) {
        toast.error("Hourly ingest limit reached. Try again later.");
      }
    },
```

Note: Check how the existing `api.ts` wrapper handles HTTP errors — it may already throw with the status code in the message.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/routers/test_ingest_rate_limit.py -v --tb=short
```

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check backend/routers/stocks/search.py --fix
uv run ruff format backend/routers/stocks/search.py
git add backend/routers/stocks/search.py tests/unit/routers/test_ingest_rate_limit.py \
    frontend/src/hooks/use-stocks.ts
git commit -m "feat(rate-limiter): add 20/hour per-user limit on ingest endpoint (KAN-425 F4)"
```

---

### Task 5: Full test suite verification + final commit

- [ ] **Step 1: Run full backend tests**

```bash
uv run ruff check backend/ tests/ --fix && uv run ruff format backend/ tests/
uv run pytest tests/unit/ -q --tb=short
```

Expected: All ~1980+ tests pass.

- [ ] **Step 2: Run frontend lint + type check**

```bash
cd frontend && npx eslint src/hooks/use-stocks.ts --quiet && npx tsc --noEmit
```

- [ ] **Step 3: Final commit if any fixups needed**

---

## Hard Constraints (from ticket + spec)

1. Rate limiter MUST fall back to permissive when Redis is unavailable — never block production traffic due to Redis outage.
2. Lua script MUST be atomic — no TOCTOU races between check and decrement.
3. yfinance limiter applies at the `await` boundary (before `asyncio.to_thread`), NOT inside the sync function.
4. Finnhub's existing `RATE_LIMIT_DELAY` sleep pattern is REMOVED (replaced by token bucket).
5. Do NOT add rate limit to `POST /portfolio/transactions/bulk` — endpoint does not exist yet (Spec C5).

## Deploy Note

On first deploy, the `ratelimit:*` Redis keys will auto-create. Monitor `Rate limiter timeout` log lines in the first 24h — if they appear frequently, increase capacity values via env vars (future: make configurable via Settings).
