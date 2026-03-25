# KAN-148 Redis Cache Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Redis cache-aside layer with 3-tier key namespaces (app/user/session), TTL tiers, agent tool result caching, and cache warmup.

**Architecture:** `CacheService` wraps `redis.asyncio` with namespaced keys and TTL tiers. Endpoints check cache before DB. Executor checks session cache before tool execution. Shared Redis pool replaces token_blocklist's standalone connection.

**Tech Stack:** `redis.asyncio` (already installed), FastAPI `Depends()`, Pydantic JSON serialization

**Spec:** `docs/superpowers/specs/2026-03-25-redis-cache-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/services/redis_pool.py` | Shared async Redis connection pool |
| Create | `backend/services/cache.py` | CacheService + CacheTier enum |
| Modify | `backend/services/token_blocklist.py` | Use shared pool |
| Modify | `backend/routers/stocks.py` | Cache signals, prices, fundamentals |
| Modify | `backend/routers/sectors.py` | Cache sector endpoints |
| Modify | `backend/routers/forecasts.py` | Cache forecast data |
| Modify | `backend/routers/portfolio.py` | Cache portfolio summary, invalidate on write |
| Modify | `backend/agents/executor.py` | Tool result session cache |
| Modify | `backend/main.py` | Init CacheService, dependency, warmup, shutdown |
| Modify | `backend/tasks/__init__.py` | Invalidate cache in nightly pipeline |
| Create | `tests/unit/services/__init__.py` | Package init |
| Create | `tests/unit/services/test_cache.py` | CacheService unit tests |
| Create | `tests/unit/services/test_redis_pool.py` | Pool tests |

---

### Task 1: Shared Redis Pool

**Files:**
- Create: `backend/services/redis_pool.py`
- Modify: `backend/services/token_blocklist.py`
- Create: `tests/unit/services/__init__.py`
- Create: `tests/unit/services/test_redis_pool.py`

- [ ] **Step 1: Write tests for redis_pool**

```python
# tests/unit/services/__init__.py
# (empty file)

# tests/unit/services/test_redis_pool.py
"""Tests for shared Redis connection pool."""

from unittest.mock import AsyncMock, patch

import pytest


class TestGetRedis:
    """Tests for get_redis singleton."""

    @pytest.mark.asyncio
    async def test_returns_redis_instance(self) -> None:
        """get_redis should return a Redis client."""
        from backend.services import redis_pool

        redis_pool._pool = None  # reset singleton
        with patch("backend.services.redis_pool.aioredis") as mock_redis:
            mock_client = AsyncMock()
            mock_redis.from_url.return_value = mock_client
            result = await redis_pool.get_redis()
            assert result is mock_client
            mock_redis.from_url.assert_called_once()
        redis_pool._pool = None  # cleanup

    @pytest.mark.asyncio
    async def test_returns_same_instance(self) -> None:
        """get_redis should return singleton on second call."""
        from backend.services import redis_pool

        redis_pool._pool = None
        with patch("backend.services.redis_pool.aioredis") as mock_redis:
            mock_client = AsyncMock()
            mock_redis.from_url.return_value = mock_client
            first = await redis_pool.get_redis()
            second = await redis_pool.get_redis()
            assert first is second
            assert mock_redis.from_url.call_count == 1
        redis_pool._pool = None

    @pytest.mark.asyncio
    async def test_close_redis(self) -> None:
        """close_redis should close and clear the singleton."""
        from backend.services import redis_pool

        mock_client = AsyncMock()
        redis_pool._pool = mock_client
        await redis_pool.close_redis()
        mock_client.aclose.assert_awaited_once()
        assert redis_pool._pool is None
```

- [ ] **Step 2: Run tests — expect ImportError**

Run: `uv run pytest tests/unit/services/test_redis_pool.py -v`

- [ ] **Step 3: Implement redis_pool.py**

```python
# backend/services/redis_pool.py
"""Shared async Redis connection pool.

Single pool used by CacheService, token_blocklist, rate_limiter.
"""

from __future__ import annotations

import redis.asyncio as aioredis

from backend.config import settings

_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Get or create the shared async Redis client."""
    global _pool  # noqa: PLW0603
    if _pool is None:
        _pool = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _pool


async def close_redis() -> None:
    """Close Redis pool on shutdown."""
    global _pool  # noqa: PLW0603
    if _pool is not None:
        await _pool.aclose()
        _pool = None
```

- [ ] **Step 4: Refactor token_blocklist to use shared pool**

Replace `_get_redis()` and `_redis_client` in `backend/services/token_blocklist.py` with the shared pool:

```python
# backend/services/token_blocklist.py — updated
"""Redis-backed blocklist for revoked refresh token JTIs."""

from __future__ import annotations

import logging

from backend.services.redis_pool import get_redis

logger = logging.getLogger(__name__)

_KEY_PREFIX = "blocklist:jti:"


async def add_to_blocklist(jti: str, expires_in_seconds: int) -> None:
    """Add a revoked refresh token JTI to the blocklist."""
    if expires_in_seconds <= 0:
        return
    r = await get_redis()
    key = f"{_KEY_PREFIX}{jti}"
    await r.set(key, "1", ex=expires_in_seconds)
    logger.debug("Blocklisted JTI %s (TTL=%ds)", jti, expires_in_seconds)


async def is_blocklisted(jti: str) -> bool:
    """Check if a refresh token JTI has been revoked."""
    r = await get_redis()
    key = f"{_KEY_PREFIX}{jti}"
    return await r.exists(key) > 0


async def close() -> None:
    """Close Redis — delegates to shared pool."""
    from backend.services.redis_pool import close_redis
    await close_redis()
```

Note: `_get_redis()` was synchronous, now `get_redis()` is async. Update all callers — `add_to_blocklist` and `is_blocklisted` already use `await` on Redis ops, just need `await get_redis()` instead of `_get_redis()`.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/unit/services/test_redis_pool.py tests/unit/auth/test_token_blocklist.py -v
```

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check --fix backend/services/redis_pool.py backend/services/token_blocklist.py tests/unit/services/
uv run ruff format backend/services/redis_pool.py backend/services/token_blocklist.py tests/unit/services/
git add backend/services/redis_pool.py backend/services/token_blocklist.py tests/unit/services/
git commit -m "feat(cache): shared Redis pool + refactor token_blocklist"
```

---

### Task 2: CacheService Core

**Files:**
- Create: `backend/services/cache.py`
- Create: `tests/unit/services/test_cache.py`

- [ ] **Step 1: Write tests for CacheService**

```python
# tests/unit/services/test_cache.py
"""Tests for CacheService — Redis cache with TTL tiers."""

import json
from unittest.mock import AsyncMock

import pytest

from backend.services.cache import CacheService, CacheTier


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Mock Redis client."""
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock()
    r.delete = AsyncMock()
    r.scan = AsyncMock(return_value=(0, []))
    return r


@pytest.fixture
def cache(mock_redis: AsyncMock) -> CacheService:
    """CacheService with mocked Redis."""
    return CacheService(mock_redis)


class TestGet:
    """Tests for cache get."""

    @pytest.mark.asyncio
    async def test_returns_none_on_miss(self, cache: CacheService, mock_redis: AsyncMock) -> None:
        """Cache miss should return None."""
        result = await cache.get("app:signals:AAPL")
        assert result is None
        mock_redis.get.assert_awaited_once_with("app:signals:AAPL")

    @pytest.mark.asyncio
    async def test_returns_value_on_hit(self, cache: CacheService, mock_redis: AsyncMock) -> None:
        """Cache hit should return stored value."""
        mock_redis.get.return_value = '{"score": 8.5}'
        result = await cache.get("app:signals:AAPL")
        assert result == '{"score": 8.5}'


class TestSet:
    """Tests for cache set with TTL tiers."""

    @pytest.mark.asyncio
    async def test_volatile_ttl(self, cache: CacheService, mock_redis: AsyncMock) -> None:
        """Volatile tier should use ~300s TTL."""
        await cache.set("app:price:AAPL", '{"price": 185}', CacheTier.VOLATILE)
        mock_redis.set.assert_awaited_once()
        call_kwargs = mock_redis.set.call_args
        ttl = call_kwargs[1]["ex"]
        assert 270 <= ttl <= 330  # 300 ± 10%

    @pytest.mark.asyncio
    async def test_standard_ttl(self, cache: CacheService, mock_redis: AsyncMock) -> None:
        """Standard tier should use ~1800s TTL."""
        await cache.set("app:signals:AAPL", '{}', CacheTier.STANDARD)
        call_kwargs = mock_redis.set.call_args
        ttl = call_kwargs[1]["ex"]
        assert 1620 <= ttl <= 1980  # 1800 ± 10%

    @pytest.mark.asyncio
    async def test_stable_ttl(self, cache: CacheService, mock_redis: AsyncMock) -> None:
        """Stable tier should use ~86400s TTL."""
        await cache.set("app:indexes", '{}', CacheTier.STABLE)
        call_kwargs = mock_redis.set.call_args
        ttl = call_kwargs[1]["ex"]
        assert 77760 <= ttl <= 95040  # 86400 ± 10%

    @pytest.mark.asyncio
    async def test_session_ttl(self, cache: CacheService, mock_redis: AsyncMock) -> None:
        """Session tier should use 7200s TTL (no jitter)."""
        await cache.set("session:abc:tool:x", '{}', CacheTier.SESSION)
        call_kwargs = mock_redis.set.call_args
        assert call_kwargs[1]["ex"] == 7200


class TestDelete:
    """Tests for cache delete."""

    @pytest.mark.asyncio
    async def test_delete_single_key(self, cache: CacheService, mock_redis: AsyncMock) -> None:
        """Should delete a single key."""
        await cache.delete("app:signals:AAPL")
        mock_redis.delete.assert_awaited_once_with("app:signals:AAPL")


class TestInvalidateTicker:
    """Tests for ticker-level invalidation."""

    @pytest.mark.asyncio
    async def test_invalidate_deletes_matching_keys(self, cache: CacheService, mock_redis: AsyncMock) -> None:
        """Should scan and delete all keys matching the ticker."""
        mock_redis.scan.return_value = (0, ["app:signals:AAPL", "app:price:AAPL", "app:fundamentals:AAPL"])
        deleted = await cache.invalidate_ticker("AAPL")
        assert deleted == 3


class TestDeletePattern:
    """Tests for pattern-based deletion."""

    @pytest.mark.asyncio
    async def test_delete_pattern_uses_scan(self, cache: CacheService, mock_redis: AsyncMock) -> None:
        """Should use SCAN (not KEYS) for safe pattern deletion."""
        mock_redis.scan.return_value = (0, ["app:screener:abc", "app:screener:def"])
        deleted = await cache.delete_pattern("app:screener:*")
        assert deleted == 2
        mock_redis.scan.assert_awaited()
```

- [ ] **Step 2: Run tests — expect ImportError**

Run: `uv run pytest tests/unit/services/test_cache.py -v`

- [ ] **Step 3: Implement CacheService**

```python
# backend/services/cache.py
"""Redis cache service with namespaced keys and TTL tiers.

Cache-aside pattern: check Redis → miss → query DB → store → return.
Three key namespaces: app (shared), user (per-user), session (per-chat).
"""

from __future__ import annotations

import logging
import random
from enum import Enum

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class CacheTier(str, Enum):
    """TTL tiers for different data volatility levels."""

    VOLATILE = "volatile"    # 5 min — prices, portfolio summary
    STANDARD = "standard"    # 30 min — signals, screener, sectors
    STABLE = "stable"        # 24h — company profiles, indexes
    SESSION = "session"      # 2h — agent tool results

    @property
    def base_ttl(self) -> int:
        """Base TTL in seconds for this tier."""
        return {
            CacheTier.VOLATILE: 300,
            CacheTier.STANDARD: 1800,
            CacheTier.STABLE: 86400,
            CacheTier.SESSION: 7200,
        }[self]

    @property
    def ttl(self) -> int:
        """TTL with ±10% jitter (except SESSION which is fixed)."""
        base = self.base_ttl
        if self == CacheTier.SESSION:
            return base
        jitter = int(base * 0.1)
        return base + random.randint(-jitter, jitter)


class CacheService:
    """Async Redis cache with namespaced keys and TTL tiers."""

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    async def get(self, key: str) -> str | None:
        """Get a value from cache. Returns None on miss."""
        try:
            return await self._redis.get(key)
        except Exception:
            logger.warning("Cache get failed for key=%s", key, exc_info=True)
            return None

    async def set(self, key: str, value: str, tier: CacheTier) -> None:
        """Set a value with TTL from the specified tier."""
        try:
            await self._redis.set(key, value, ex=tier.ttl)
        except Exception:
            logger.warning("Cache set failed for key=%s", key, exc_info=True)

    async def delete(self, key: str) -> None:
        """Delete a single cache key."""
        try:
            await self._redis.delete(key)
        except Exception:
            logger.warning("Cache delete failed for key=%s", key, exc_info=True)

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern using SCAN (production-safe)."""
        deleted = 0
        try:
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    await self._redis.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
        except Exception:
            logger.warning("Cache delete_pattern failed for %s", pattern, exc_info=True)
        return deleted

    async def invalidate_ticker(self, ticker: str) -> int:
        """Invalidate all cached data for a ticker."""
        t = ticker.upper()
        total = 0
        for prefix in ("app:signals:", "app:price:", "app:fundamentals:", "app:forecast:"):
            await self.delete(f"{prefix}{t}")
            total += 1
        # Also scan for any other app:*:TICKER keys
        extra = await self.delete_pattern(f"app:*:{t}")
        return total + extra

    async def invalidate_user(self, user_id: str) -> int:
        """Invalidate all cached data for a user."""
        return await self.delete_pattern(f"user:{user_id}:*")
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/services/test_cache.py -v`
Expected: All pass

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix backend/services/cache.py tests/unit/services/test_cache.py
uv run ruff format backend/services/cache.py tests/unit/services/test_cache.py
git add backend/services/cache.py tests/unit/services/test_cache.py
git commit -m "feat(cache): CacheService with TTL tiers + jitter + pattern deletion"
```

---

### Task 3: Wire CacheService in main.py + FastAPI Dependency

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/dependencies.py` (or create cache dependency inline)

- [ ] **Step 1: Add CacheService initialization to lifespan**

In `backend/main.py`, after the observability collector setup, add:

```python
    # Cache service
    from backend.services.cache import CacheService
    from backend.services.redis_pool import get_redis

    cache_redis = await get_redis()
    cache_service = CacheService(cache_redis)
    app.state.cache = cache_service
    logger.info("CacheService initialized")
```

- [ ] **Step 2: Update shutdown to use shared pool**

In the shutdown section, replace the existing `close_blocklist()` with:

```python
    from backend.services.redis_pool import close_redis
    if mcp_manager:
        await mcp_manager.stop()
    await close_redis()  # closes shared pool (used by cache + blocklist)
    logger.info("Application shutting down")
```

Remove the `from backend.services.token_blocklist import close as close_blocklist` import and `await close_blocklist()` call (since `close()` in blocklist now delegates to `close_redis()`).

- [ ] **Step 3: Add FastAPI dependency for cache**

Add a dependency function (can go at the top of `main.py` or in `dependencies.py`). Simplest: in each router that needs it, access via `request.app.state.cache`. No separate dependency needed — same pattern as `app.state.collector`.

- [ ] **Step 4: Run full test suite**

```bash
uv run pytest tests/unit/ -q --tb=short
```
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add backend/main.py
git commit -m "feat(cache): wire CacheService into app lifespan + shutdown"
```

---

### Task 4: Cache Stock Endpoints

**Files:**
- Modify: `backend/routers/stocks.py`

- [ ] **Step 1: Add cache to get_signals endpoint**

In `backend/routers/stocks.py`, modify `get_signals()` (line ~253):

```python
@router.get("/{ticker}/signals", response_model=SignalResponse)
async def get_signals(
    ticker: str,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> SignalResponse:
    # Cache check
    cache = getattr(request.app.state, "cache", None)
    cache_key = f"app:signals:{ticker.upper()}"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return SignalResponse.model_validate_json(cached)

    # ... existing DB query logic ...

    # Cache store (before return)
    if cache:
        from backend.services.cache import CacheTier
        await cache.set(cache_key, response.model_dump_json(), CacheTier.STANDARD)

    return response
```

Add `from fastapi import Request` to the imports if not already present.

- [ ] **Step 2: Add cache invalidation to ingest endpoint**

In the ingest endpoint (same file), after successful ingestion:

```python
    # Invalidate cache for this ticker
    cache = getattr(request.app.state, "cache", None)
    if cache:
        await cache.invalidate_ticker(ticker)
```

- [ ] **Step 3: Run existing stock API tests**

```bash
uv run pytest tests/api/test_stocks.py -v --tb=short
```
Expected: All pass (cache is optional — `getattr` returns None in tests)

- [ ] **Step 4: Commit**

```bash
git add backend/routers/stocks.py
git commit -m "feat(cache): cache signals endpoint + invalidate on ingest"
```

---

### Task 5: Cache Sectors + Forecasts + Portfolio

**Files:**
- Modify: `backend/routers/sectors.py`
- Modify: `backend/routers/forecasts.py`
- Modify: `backend/routers/portfolio.py`

- [ ] **Step 1: Add cache to sectors endpoints**

Cache `GET /sectors/summary` with key `app:sectors:summary` (STANDARD tier) and `GET /sectors/{sector}/stocks` with key `app:sectors:{sector}:stocks` (STANDARD tier). Same pattern as Task 4.

- [ ] **Step 2: Add cache to forecast endpoint**

Cache `GET /forecasts/{ticker}` with key `app:forecast:{ticker}` (STANDARD tier).

- [ ] **Step 3: Add cache to portfolio summary + invalidation on writes**

Cache `GET /portfolio/summary` with key `user:{user_id}:portfolio:summary` (VOLATILE tier). On `POST /portfolio/transactions` and `DELETE /portfolio/positions/{id}`, call `cache.invalidate_user(str(user.id))`.

- [ ] **Step 4: Run API tests**

```bash
uv run pytest tests/api/test_sectors_api.py tests/api/test_portfolio.py -v --tb=short
```

- [ ] **Step 5: Commit**

```bash
git add backend/routers/sectors.py backend/routers/forecasts.py backend/routers/portfolio.py
git commit -m "feat(cache): cache sectors, forecasts, portfolio summary endpoints"
```

---

### Task 6: Agent Tool Result Session Cache

**Files:**
- Modify: `backend/agents/executor.py`
- Create: `tests/unit/agents/test_executor_cache.py`

- [ ] **Step 1: Write tests**

```python
# tests/unit/agents/test_executor_cache.py
"""Tests for agent tool result session caching in executor."""

from unittest.mock import AsyncMock

import pytest

from backend.services.cache import CacheService, CacheTier
from backend.tools.base import ToolResult


# Tools that should be cached
CACHEABLE_TOOLS = {
    "analyze_stock", "get_fundamentals", "get_forecast",
    "get_analyst_targets", "get_earnings_history", "get_company_profile",
    "compare_stocks", "get_recommendation_scorecard",
    "dividend_sustainability", "risk_narrative",
}


class TestToolResultCache:
    """Tests for tool result session caching."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_execution(self) -> None:
        """A cached tool result should skip execution."""
        from backend.agents.executor import execute_plan

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value='{"status":"ok","data":{"ticker":"AAPL"}}')
        mock_redis.set = AsyncMock()
        cache = CacheService(mock_redis)

        tool_executor = AsyncMock()
        steps = [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}]
        result = await execute_plan(steps, tool_executor, cache=cache, session_id="sess-123")

        # Tool should NOT have been called — served from cache
        tool_executor.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_executes_and_stores(self) -> None:
        """A cache miss should execute the tool and store the result."""
        from backend.agents.executor import execute_plan

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        cache = CacheService(mock_redis)

        tool_executor = AsyncMock(return_value=ToolResult(
            status="ok", data={"ticker": "AAPL", "score": 8.5}
        ))
        steps = [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}]
        result = await execute_plan(steps, tool_executor, cache=cache, session_id="sess-123")

        tool_executor.assert_called_once()
        mock_redis.set.assert_awaited()  # stored in cache

    @pytest.mark.asyncio
    async def test_uncacheable_tool_always_executes(self) -> None:
        """Tools not in CACHEABLE_TOOLS should always execute."""
        from backend.agents.executor import execute_plan

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        cache = CacheService(mock_redis)

        tool_executor = AsyncMock(return_value=ToolResult(
            status="ok", data={"results": []}
        ))
        steps = [{"tool": "search_stocks", "params": {"query": "tech"}}]
        result = await execute_plan(steps, tool_executor, cache=cache, session_id="sess-123")

        tool_executor.assert_called_once()
        # Should NOT cache search_stocks
        mock_redis.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_cache_no_session_still_works(self) -> None:
        """Executor without cache or session_id should work as before."""
        from backend.agents.executor import execute_plan

        tool_executor = AsyncMock(return_value=ToolResult(
            status="ok", data={"ticker": "AAPL"}
        ))
        steps = [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}]
        result = await execute_plan(steps, tool_executor)
        tool_executor.assert_called_once()
```

- [ ] **Step 2: Add cache + session_id params to execute_plan**

In `backend/agents/executor.py`, update the signature:

```python
from backend.services.cache import CacheService, CacheTier

# Cacheable tools (data doesn't change within a session)
CACHEABLE_TOOLS = {
    "analyze_stock", "get_fundamentals", "get_forecast",
    "get_analyst_targets", "get_earnings_history", "get_company_profile",
    "compare_stocks", "get_recommendation_scorecard",
    "dividend_sustainability", "risk_narrative",
}


async def execute_plan(
    steps: list[dict[str, Any]],
    tool_executor: Any,
    on_step: Any | None = None,
    collector: ObservabilityCollector | None = None,
    cache: CacheService | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
```

Inside the step loop, before the retry block, add cache check:

```python
        tool_name = step["tool"]
        raw_params = step.get("params", {})
        params = _resolve_params(raw_params, results)

        # Session cache check (cacheable tools only)
        cache_key = None
        if cache and session_id and tool_name in CACHEABLE_TOOLS:
            param_hash = hash(json.dumps(params, sort_keys=True, default=str))
            cache_key = f"session:{session_id}:tool:{tool_name}:{param_hash}"
            cached = await cache.get(cache_key)
            if cached:
                import json as _json
                cached_data = _json.loads(cached)
                results.append(cached_data)
                tool_calls += 1
                if on_step:
                    try:
                        await on_step(i, tool_name, cached_data.get("status", "ok"))
                    except Exception:
                        pass
                continue  # skip execution

        # Execute with retry (existing code)
        tool_start = time.monotonic()
        result: ToolResult | None = None
        ...
```

After the existing collector recording block, add cache store:

```python
        # Store in session cache (successful cacheable tools only)
        if cache_key and validated["status"] == "ok":
            await cache.set(cache_key, json.dumps(validated, default=str), CacheTier.SESSION)
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/agents/test_executor_cache.py tests/unit/agents/test_executor_observability.py tests/unit/agents/test_executor.py -v
```

- [ ] **Step 4: Update main.py to pass cache + session_id to executor**

In `backend/main.py`, update the `execute_fn` lambda to include cache and session_id:

```python
        app.state.agent_graph = build_agent_graph(
            plan_fn=_plan_fn,
            execute_fn=lambda steps, tool_executor, on_step=None: execute_plan(
                steps, tool_executor, on_step=on_step, collector=collector,
                cache=cache_service,
            ),
            ...
        )
```

Note: `session_id` comes from the graph state (`query_id`), so it needs to be passed from the graph node. In `backend/agents/graph.py` `execute_node`, update the `execute_fn` call to pass `session_id=state.get("query_id")` — but this requires changing the function signature in `build_agent_graph`. For now, use `query_id` from ContextVar instead:

In `executor.py`, at the top of `execute_plan`, read from ContextVar if session_id not provided:

```python
    if session_id is None:
        from backend.request_context import current_query_id
        qid = current_query_id.get()
        if qid:
            session_id = str(qid)
```

- [ ] **Step 5: Commit**

```bash
git add backend/agents/executor.py backend/main.py tests/unit/agents/test_executor_cache.py
git commit -m "feat(cache): agent tool result session cache in executor"
```

---

### Task 7: Cache Warmup + Nightly Invalidation

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/tasks/__init__.py`

- [ ] **Step 1: Add warmup to lifespan**

After `cache_service` initialization in `main.py`:

```python
    # Cache warmup — indexes + top tickers
    try:
        async with async_session_factory() as warmup_db:
            from backend.models.stock import Stock, StockIndex
            from sqlalchemy import select

            # Warm index data
            idx_result = await warmup_db.execute(select(StockIndex))
            indexes = idx_result.scalars().all()
            if indexes:
                import json
                idx_data = json.dumps([{"ticker": i.ticker, "name": i.name} for i in indexes])
                await cache_service.set("app:indexes", idx_data, CacheTier.STABLE)
                logger.info("Warmed %d index entries in cache", len(indexes))
    except Exception:
        logger.warning("Cache warmup failed — will lazy-load", exc_info=True)
```

- [ ] **Step 2: Add cache invalidation to nightly pipeline**

In `backend/tasks/__init__.py`, in the nightly chain (or wherever the batch runs), add at the start:

```python
import redis

def _invalidate_stale_cache() -> None:
    """Clear stale app-wide cache before nightly recomputation."""
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    cursor = 0
    deleted = 0
    while True:
        cursor, keys = r.scan(cursor=cursor, match="app:screener:*", count=100)
        if keys:
            r.delete(*keys)
            deleted += len(keys)
        if cursor == 0:
            break
    cursor = 0
    while True:
        cursor, keys = r.scan(cursor=cursor, match="app:sectors:*", count=100)
        if keys:
            r.delete(*keys)
            deleted += len(keys)
        if cursor == 0:
            break
    logger.info("Invalidated %d stale cache keys before nightly run", deleted)
    r.close()
```

Call this at the start of the nightly chain task.

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/unit/ tests/api/ -q --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add backend/main.py backend/tasks/__init__.py
git commit -m "feat(cache): warmup on startup + nightly invalidation"
```

---

### Task 8: Documentation + Final Verification

**Files:**
- Modify: `docs/TDD.md`
- Modify: `project-plan.md`

- [ ] **Step 1: Update TDD.md §4.3 Caching Strategy**

Replace the aspirational caching section with the implemented design (3-tier namespace, TTL tiers, CacheService).

- [ ] **Step 2: Update project-plan.md**

Mark KAN-148 as complete.

- [ ] **Step 3: Final test run**

```bash
uv run pytest tests/unit/ tests/api/ -q --tb=short
uv run ruff check backend/ tests/
```

- [ ] **Step 4: Commit**

```bash
git add docs/TDD.md project-plan.md
git commit -m "docs: update TDD caching strategy + mark KAN-148 complete"
```

---

## Execution Summary

| Task | Description | New Tests | Files |
|------|-------------|-----------|-------|
| 1 | Shared Redis pool + blocklist refactor | 3 | 4 |
| 2 | CacheService core | 8 | 2 |
| 3 | Wire in main.py | 0 | 1 |
| 4 | Cache stock endpoints | 0 | 1 |
| 5 | Cache sectors + forecasts + portfolio | 0 | 3 |
| 6 | Agent tool result session cache | 4 | 3 |
| 7 | Cache warmup + nightly invalidation | 0 | 2 |
| 8 | Documentation | 0 | 2 |
| **Total** | | **~15** | **18** |
