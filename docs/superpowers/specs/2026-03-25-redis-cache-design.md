# Redis Cache Layer — Design Spec

**Date**: 2026-03-25
**Phase**: 7 (KAN-148)
**Status**: Draft
**Depends on**: Phase 6B (Observability — for cache hit tracking)

---

## 1. Problem Statement

Every API request hits the database directly. With stock data that changes at most every 5 minutes (prices) or daily (signals, fundamentals), we're doing redundant DB queries. The agent pipeline also re-executes identical tool calls within and across sessions.

**Goals:**
- Reduce DB load for frequently accessed stock data
- Cache agent tool results to avoid redundant LLM-triggered tool execution
- Support per-user cached data (portfolio summaries, recommendations)
- Lay groundwork for multi-user scaling (Phase 8)

---

## 2. Architecture

### 2.1 Cache-Aside Pattern

The application controls both reads and writes:

```
Request → Check Redis → HIT → return cached
                      → MISS → query DB → store in Redis → return
```

No write-through or write-behind — too complex for our current volume. Cache-aside gives us explicit control over what enters cache and when.

### 2.2 Three-Tier Key Namespace

```
app:{entity}:{identifier}          — shared across all users
user:{user_id}:{entity}:{id}      — per-user data
session:{session_id}:{entity}:{id} — per-chat-session data
```

**Examples:**
```
app:signals:AAPL                    → latest signal snapshot for AAPL
app:price:AAPL                      → current price for AAPL
app:fundamentals:AAPL               → fundamentals data for AAPL
app:screener:a3f8b2c1               → screener results (hash of filters)
app:sectors:summary                 → sector summary data
app:forecast:AAPL                   → forecast data for AAPL

user:abc123:portfolio:summary       → portfolio KPIs for user abc123
user:abc123:recommendations         → latest recommendations

session:def456:tool:analyze_stock:AAPL → tool result cache within session
session:def456:tool:get_forecast:MSFT  → tool result cache within session
```

### 2.3 TTL Tiers

| Tier | TTL | Jitter | Data Types |
|------|-----|--------|------------|
| `volatile` | 5 min | ±30s | prices, portfolio summary |
| `standard` | 30 min | ±3 min | signals, screener, sectors, fundamentals |
| `stable` | 24h | ±1h | company profiles, index membership |
| `session` | 2h (or session close) | none | agent tool results, entity registry |

**TTL jitter** (±10%) prevents cache stampede when many keys expire simultaneously.

---

## 3. Cache Service

### 3.1 `CacheService` Class

New module: `backend/services/cache.py`

```python
class CacheTier(str, Enum):
    VOLATILE = "volatile"    # 5 min
    STANDARD = "standard"    # 30 min
    STABLE = "stable"        # 24h
    SESSION = "session"      # 2h

class CacheService:
    """Async Redis cache with namespaced keys and TTL tiers."""

    def __init__(self, redis: Redis) -> None: ...

    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, tier: CacheTier) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def delete_pattern(self, pattern: str) -> int: ...
    async def invalidate_ticker(self, ticker: str) -> int: ...
    async def invalidate_user(self, user_id: str) -> int: ...
```

**Key design decisions:**
- Values stored as JSON strings (Pydantic `.model_dump_json()` / `.model_validate_json()`)
- `delete_pattern` uses `SCAN` + `DEL` (not `KEYS *` — safe for production)
- `invalidate_ticker(ticker)` deletes `app:*:{ticker}` — called after ingest
- `invalidate_user(user_id)` deletes `user:{user_id}:*` — called on portfolio change

### 3.2 Connection Management

Reuse the existing `redis.asyncio` connection from `token_blocklist.py`. Add a shared Redis pool in `backend/services/redis_pool.py`:

```python
_pool: Redis | None = None

async def get_redis() -> Redis:
    """Get shared async Redis connection."""
    global _pool
    if _pool is None:
        _pool = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _pool

async def close_redis() -> None:
    """Close Redis pool on shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
```

Token blocklist refactored to use this shared pool instead of its own.

---

## 4. Endpoint Integration

### 4.1 Endpoints to Cache (app-wide)

| Endpoint | Cache Key | Tier | Invalidation |
|----------|-----------|------|-------------|
| `GET /stocks/{ticker}/signals` | `app:signals:{ticker}` | standard | On ingest |
| `GET /stocks/{ticker}/prices` | `app:price:{ticker}` | volatile | On ingest |
| `GET /stocks/{ticker}/fundamentals` | `app:fundamentals:{ticker}` | standard | On ingest |
| `GET /stocks/signals/bulk` | `app:screener:{filter_hash}` | standard | On nightly batch |
| `GET /sectors/summary` | `app:sectors:summary` | standard | On nightly batch |
| `GET /sectors/{sector}/stocks` | `app:sectors:{sector}:stocks` | standard | On nightly batch |
| `GET /forecasts/{ticker}` | `app:forecast:{ticker}` | standard | On forecast run |
| `GET /indexes` | `app:indexes` | stable | On nightly sync |

### 4.2 Endpoints to Cache (per-user)

| Endpoint | Cache Key | Tier | Invalidation |
|----------|-----------|------|-------------|
| `GET /portfolio/summary` | `user:{uid}:portfolio:summary` | volatile | On transaction |
| `GET /portfolio/recommendations` | `user:{uid}:recommendations` | standard | On recompute |

### 4.3 Endpoints NOT Cached

| Endpoint | Reason |
|----------|--------|
| `GET /portfolio/positions` | Frequent writes, always needs fresh data |
| `POST /chat/stream` | Streaming, real-time |
| `POST /stocks/{ticker}/ingest` | Write operation |
| `GET /admin/*` | Low traffic, always fresh |
| `GET /alerts` | Must be real-time for user |

### 4.4 Implementation Pattern

Use a decorator or inline pattern at the router level:

```python
@router.get("/stocks/{ticker}/signals")
async def get_signals(
    ticker: str,
    cache: CacheService = Depends(get_cache),
    db: AsyncSession = Depends(get_async_session),
):
    # 1. Check cache
    cached = await cache.get(f"app:signals:{ticker.upper()}")
    if cached:
        return SignalResponse.model_validate_json(cached)

    # 2. Query DB
    result = await _fetch_signals(db, ticker)
    response = SignalResponse.model_validate(result)

    # 3. Store in cache
    await cache.set(f"app:signals:{ticker.upper()}", response.model_dump_json(), CacheTier.STANDARD)

    return response
```

---

## 5. Agent Tool Result Caching

### 5.1 Per-Session Tool Cache

When the agent executes a tool during a chat session, cache the result so repeated questions about the same ticker don't re-query.

**Key:** `session:{session_id}:tool:{tool_name}:{param_hash}`
**TTL:** 2 hours (CacheTier.SESSION)
**Invalidation:** Session close or explicit clear

### 5.2 Integration Point

In `backend/agents/executor.py`, before executing a tool:

```python
# Check session cache
cache_key = f"session:{session_id}:tool:{tool_name}:{hash(params)}"
cached_result = await cache.get(cache_key)
if cached_result:
    return ToolResult.from_json(cached_result)  # cache hit

# Execute tool
result = await tool_executor(tool_name, params)

# Cache result (if successful)
if result.status == "ok":
    await cache.set(cache_key, result.to_json(), CacheTier.SESSION)
```

### 5.3 Tools to Cache vs Skip

| Cache | Tools | Reason |
|-------|-------|--------|
| Yes | `analyze_stock`, `get_fundamentals`, `get_forecast`, `get_analyst_targets`, `get_earnings_history`, `get_company_profile`, `compare_stocks`, `get_recommendation_scorecard`, `dividend_sustainability`, `risk_narrative` | Data doesn't change within a session |
| No | `search_stocks`, `ingest_stock`, `get_portfolio_exposure`, `web_search`, `get_geopolitical_events` | Dynamic, user-specific, or external real-time |

---

## 6. Cache Warmup

### 6.1 On Startup

In `main.py` lifespan, after registry + providers are initialized:

```python
# Warm app-wide caches
await cache_service.warm_indexes(db)       # index membership
await cache_service.warm_top_tickers(db)   # top-10 by composite score
```

### 6.2 On User Login

Not implemented initially — TTL-based lazy loading sufficient for single user.

### 6.3 After Nightly Pipeline

Celery `nightly_chain` calls `cache.delete_pattern("app:*")` at the start, then signal/forecast computations naturally re-warm via cache-aside.

---

## 7. Invalidation Strategy

| Trigger | Keys Invalidated | Method |
|---------|-----------------|--------|
| `POST /stocks/{ticker}/ingest` | `app:*:{ticker}` | `invalidate_ticker()` |
| Portfolio transaction | `user:{uid}:portfolio:*` | `invalidate_user()` |
| Nightly batch start | `app:screener:*`, `app:sectors:*` | `delete_pattern()` |
| Forecast recomputation | `app:forecast:{ticker}` | Single key delete |
| Chat session close | `session:{sid}:*` | `delete_pattern()` |

---

## 8. Observability Integration

Set `cache_hit = True` on `ToolExecutionLog` when a tool result is served from cache. The ObservabilityCollector can optionally track:
- `cache_hits_by_key_prefix` counter (app/user/session)
- `cache_miss_rate` — for tuning TTLs

---

## 9. Files Changed

| Action | File |
|--------|------|
| **Create** | `backend/services/cache.py` — CacheService + CacheTier |
| **Create** | `backend/services/redis_pool.py` — shared Redis connection pool |
| **Modify** | `backend/services/token_blocklist.py` — use shared pool |
| **Modify** | `backend/routers/stocks.py` — cache signals, prices, fundamentals |
| **Modify** | `backend/routers/sectors.py` — cache sector summary + stocks |
| **Modify** | `backend/routers/forecasts.py` — cache forecast data |
| **Modify** | `backend/routers/portfolio.py` — cache portfolio summary, invalidate on write |
| **Modify** | `backend/agents/executor.py` — tool result session cache |
| **Modify** | `backend/main.py` — init CacheService, inject as dependency, warmup |
| **Modify** | `backend/tasks/__init__.py` — invalidate cache in nightly pipeline |
| **Create** | `tests/unit/services/test_cache.py` — CacheService unit tests |
| **Create** | `tests/unit/services/test_redis_pool.py` — pool tests |

---

## 10. Success Criteria

- [ ] All cacheable endpoints return cached data on second call (verify via response time)
- [ ] `invalidate_ticker()` clears all data for a ticker after ingest
- [ ] Agent tool results cached per-session — same question in same session doesn't re-execute tools
- [ ] Cache warmup loads indexes + top tickers on startup
- [ ] Nightly pipeline invalidates stale data before recomputing
- [ ] `ToolExecutionLog.cache_hit` is True for cached tool results
- [ ] No regressions — all existing tests pass
- [ ] TTL jitter applied — no cache stampede risk

---

## 11. Out of Scope

- Semantic caching (vector similarity for LLM queries) — requires Redis Stack, deferred
- LangGraph `RedisSaver` checkpointer — future replacement for in-DB chat history
- Cross-session agent memory (user-level learning) — Phase 8
- Cache metrics admin endpoint — can be added later via ObservabilityCollector
- Write-through or write-behind patterns — unnecessary at current volume

---

## 12. References

- [Redis Real-Time Trading Platform](https://redis.io/blog/real-time-trading-platform-with-redis-enterprise/)
- [LangGraph + Redis Agent Memory](https://redis.io/blog/langgraph-redis-build-smarter-ai-agents-with-memory-persistence/)
- [Financial API TTL Strategy](https://medium.com/@digvijay17july/increase-financial-api-response-time-using-redis-cache-techniques-and-ttl-97098b5721c6)
- [Cache-Aside Pattern with Redis](https://redis.io/tutorials/howtos/solutions/microservices/caching/)
- [Redis Agent Memory Server](https://redis.github.io/agent-memory-server/memory-lifecycle/)
