# Service Layer Extraction + Router Split — Design Spec

**Date:** 2026-03-27
**JIRA:** KAN-172 (service layer), KAN-173 (router split)
**Phase:** 7.5 (deferred tech debt)
**Scope:** stocks.py + portfolio.py routers, tools/ proto-services
**Estimated effort:** ~15h across 3-4 sessions

---

## 1. Problem Statement

Business logic is scattered across three layers with no single source of truth:

| Logic | Router (HTTP) | Tool (Agent) | Task (Celery) |
|-------|--------------|--------------|----------------|
| Signal computation | `stocks.py:758-761` | `compute_signals_tool.py` → `signals.py` | `market_data.py:37-38` |
| Recommendation gen | `stocks.py:809-815` | `recommendations_tool.py` → `recommendations.py` | `recommendations.py:113-114` |
| Portfolio health | `portfolio.py` → `PortfolioHealthTool` | `portfolio_health.py` | `portfolio.py:snapshot_health_task` |
| Position queries | `portfolio.py` (16 DB ops) | `portfolio_exposure.py` → `portfolio.py` | `portfolio.py:_snapshot_all_portfolios` |

**Consequences:**
- Same computation implemented 2-3 times → divergence risk
- `stocks.py` is 1,216 lines with 17 endpoints and 45 direct DB operations — painful to navigate, review, and test
- Business logic can't be reused without importing from HTTP routers or LLM tool wrappers
- Adding new entry points (multi-agent, MCP HTTP, webhooks) requires duplicating logic again

## 2. Architecture Target

### Current (coupled)
```
Router → direct DB queries + inline logic
Tool   → own DB queries + ToolResult wrapping
Task   → duplicates subset of router/tool logic
Agent  → calls tools (which have their own DB logic)
```

### Target (service layer)
```
Router (HTTP)      Tool (Agent)       Task (Celery)
    ↓                  ↓                  ↓
    └──────────────────┼──────────────────┘
                       ↓
                Service Layer
         (stateless async functions)
                       ↓
                   Models / DB
```

**Dependency rules (enforced by convention, no cycles):**
- `services/` → `models/`, `schemas/`, `database.py`, `config.py` only
- `routers/` → `services/`, `schemas/`, `dependencies.py`
- `tools/` → `services/`, `schemas/`, `tools/base.py`
- `tasks/` → `services/`
- `agents/` → `services/` (via `user_context.py`)
- NEVER: `services/` → `routers/`, `tools/`, `tasks/`, `agents/`

## 3. Service Layer Design

### 3.1 Module structure

```
backend/services/
├── __init__.py
├── stock_data.py         # Price fetching, stock CRUD, fundamentals persistence
├── signals.py            # Signal computation, storage, history queries
├── recommendations.py    # Recommendation generation and retrieval
├── watchlist.py          # Watchlist CRUD, acknowledge, refresh orchestration
├── portfolio.py          # Positions (FIFO), summary, health, rebalancing, dividends
├── pipelines.py          # Orchestrators: ingest_ticker, refresh_all_tickers
├── cache.py              # (existing — no change)
├── redis_pool.py         # (existing — no change)
└── token_blocklist.py    # (existing — no change)
```

### 3.2 Service function signatures

All service functions follow the same pattern:
```python
async def function_name(
    # Domain params (ticker, user_id, portfolio_id, etc.)
    # db: AsyncSession — always passed, never created internally
    # Optional: cache_service for cache-aware functions
) -> DomainType | PydanticModel:
    """Google-style docstring."""
    ...
```

**Key conventions:**
- Pure async functions, no classes
- `db: AsyncSession` always injected (testable, no hidden session creation)
- Return domain objects or Pydantic schemas from `backend/schemas/`
- Raise domain exceptions (e.g., `StockNotFoundError`) — callers translate to HTTP 404 or ToolResult error
- No ToolResult, no HTTPException, no LLM formatting inside services
- Stateless — no module-level mutable state

### 3.3 Service modules — function inventory

#### `services/stock_data.py`
Migrated from: `tools/market_data.py`, `tools/fundamentals.py`, `routers/stocks.py`

| Function | Source | Callers |
|----------|--------|---------|
| `ensure_stock_exists(ticker, db)` | `tools/market_data.py` | routers, tools, tasks |
| `fetch_prices_delta(ticker, db)` | `tools/market_data.py` | pipelines, ingest tool |
| `get_prices(ticker, db, days)` | `routers/stocks.py` inline | router, tools |
| `fetch_fundamentals(ticker)` | `tools/fundamentals.py` | pipelines, fundamentals tool |
| `fetch_analyst_data(ticker)` | `tools/fundamentals.py` | pipelines |
| `fetch_earnings_history(ticker)` | `tools/fundamentals.py` | pipelines |
| `persist_fundamentals(ticker, data, db)` | `tools/fundamentals.py` | pipelines |
| `persist_analyst_data(ticker, data, db)` | `tools/fundamentals.py` | pipelines |
| `persist_earnings(ticker, data, db)` | `tools/fundamentals.py` | pipelines |

#### `services/signals.py`
Migrated from: `tools/signals.py`, `routers/stocks.py`

| Function | Source | Callers |
|----------|--------|---------|
| `compute_signals(ticker, db, piotroski_score?)` | `tools/signals.py` | pipelines, compute tool |
| `get_latest_signals(ticker, db)` | `routers/stocks.py` inline | router, analyze tool |
| `get_signal_history(ticker, db, days)` | `routers/stocks.py` inline | router |
| `get_bulk_signals(db, filters, pagination)` | `routers/stocks.py` inline | router, screen tool |

#### `services/recommendations.py`
Migrated from: `tools/recommendations.py`, `routers/stocks.py`

| Function | Source | Callers |
|----------|--------|---------|
| `generate_recommendation(ticker, user_id, db)` | `tools/recommendations.py` | pipelines, rec tool, tasks |
| `get_recommendations(user_id, db, filters)` | `routers/stocks.py` inline | router |

#### `services/watchlist.py`
Migrated from: `routers/stocks.py` (pure extraction, no existing tool equivalent)

| Function | Source | Callers |
|----------|--------|---------|
| `get_watchlist(user_id, db)` | `routers/stocks.py` inline | router |
| `add_to_watchlist(user_id, ticker, db)` | `routers/stocks.py` inline | router, search tool |
| `remove_from_watchlist(user_id, ticker, db)` | `routers/stocks.py` inline | router |
| `acknowledge_price(user_id, ticker, db)` | `routers/stocks.py` inline | router |

#### `services/portfolio.py`
Migrated from: `tools/portfolio.py`, `routers/portfolio.py`

| Function | Source | Callers |
|----------|--------|---------|
| `get_or_create_portfolio(user_id, db)` | `tools/portfolio.py` | router, tools, tasks, agents |
| `get_positions_with_pnl(portfolio_id, db)` | `tools/portfolio.py` | router, tools, tasks, agents |
| `get_portfolio_summary(user_id, db)` | `routers/portfolio.py` inline | router, tasks |
| `compute_portfolio_health(user_id, db)` | `tools/portfolio_health.py` (partial) | router, tools, tasks |
| `get_rebalancing(user_id, db)` | `routers/portfolio.py` inline | router |
| `get_dividends(user_id, ticker, db)` | `routers/portfolio.py` inline | router |
| `get_health_history(user_id, db)` | `routers/portfolio.py` inline | router |
| `create_transaction(user_id, data, db)` | `routers/portfolio.py` inline | router |
| `list_transactions(user_id, db, pagination)` | `routers/portfolio.py` inline | router |
| `delete_transaction(user_id, txn_id, db)` | `routers/portfolio.py` inline | router |

#### `services/pipelines.py`
New orchestrator — composes atomic services into transactional sequences.

| Function | Composes | Callers |
|----------|----------|---------|
| `ingest_ticker(ticker, user_id, db)` | `ensure_stock_exists` → `fetch_prices_delta` → `fetch_fundamentals` → `persist_*` → `compute_signals` → `generate_recommendation` | router (`POST /ingest`), ingest tool, tasks |
| `refresh_all_tickers(tickers, db)` | batch `ingest_ticker` with concurrency limit | tasks (nightly pipeline) |

## 4. Router Split — stocks.py

`backend/routers/stocks.py` (1,216 lines, 17 endpoints) → package with 4 submodules:

```
backend/routers/stocks/
├── __init__.py            # Combines sub-routers, exports `router` for main.py compatibility
├── data.py                # GET /{ticker}/prices, /{ticker}/signals, /{ticker}/fundamentals,
│                          #     /{ticker}/news, /{ticker}/intelligence  (~5 endpoints)
├── watchlist.py           # GET /watchlist, POST /watchlist, DELETE /watchlist/{ticker},
│                          #     PATCH /watchlist/{ticker}/acknowledge, POST /watchlist/refresh  (~5 endpoints)
├── search.py              # GET /search, POST /{ticker}/ingest  (~2 endpoints)
└── recommendations.py     # GET /recommendations, GET /signals/bulk, GET /{ticker}/signals/history  (~3 endpoints)
```

Each submodule:
- Has its own `router = APIRouter()` with appropriate tags
- `__init__.py` includes all sub-routers: `router.include_router(data.router)`, etc.
- `main.py` import unchanged: `from backend.routers.stocks import router`
- Target: each file under 250 lines

`portfolio.py` stays as a single file (567 lines, 10 endpoints) — already domain-focused, no split needed. Just extract DB logic to `services/portfolio.py`.

## 5. Proto-Service Migration (tools/ → services/)

### Files that lose business logic (become thin wrappers)

| Tool file | Functions moving to services/ | What remains |
|-----------|------------------------------|-------------|
| `tools/market_data.py` | `fetch_prices_delta()`, `ensure_stock_exists()`, `load_prices_df()` | Tool class wrapper |
| `tools/fundamentals.py` | `fetch_fundamentals()`, `fetch_analyst_data()`, `fetch_earnings_history()`, `persist_*()` | Stays as sync fetch (called via `run_in_executor`) — see note |
| `tools/signals.py` | `compute_signals()`, `SignalResult`, `store_signal_snapshot()` | Dataclass stays (shared type) |
| `tools/recommendations.py` | `generate_recommendation()`, `store_recommendation()` | Tool class wrapper |
| `tools/portfolio.py` | `get_or_create_portfolio()`, `get_positions_with_pnl()`, `_run_fifo()` | Empty (all logic moves) |

**Note on `tools/fundamentals.py`:** `fetch_fundamentals()` is synchronous (yfinance is blocking). It's called via `asyncio.to_thread()` / `run_in_executor()` by callers. The service version will remain sync for the fetch, with async wrappers where needed. The `persist_*()` functions are async (DB writes).

### Files that need import updates (9 files)

| File | Current import | New import |
|------|---------------|------------|
| `routers/stocks.py` (all submodules) | `from backend.tools.fundamentals import fetch_fundamentals` | `from backend.services.stock_data import fetch_fundamentals` |
| `routers/portfolio.py` | `from backend.tools.portfolio import get_or_create_portfolio, get_positions_with_pnl` | `from backend.services.portfolio import ...` |
| `routers/chat.py` | `from backend.tools.chat_session import ...` | No change (chat not in scope) |
| `routers/forecasts.py` | None direct, but uses tools via endpoints | Minimal changes |
| `tasks/market_data.py` | `from backend.tools.market_data import ...` | `from backend.services.stock_data import ...` |
| `tasks/recommendations.py` | `from backend.tools.recommendations import ...` | `from backend.services.recommendations import ...` |
| `tasks/portfolio.py` | `from backend.tools.portfolio import ...` | `from backend.services.portfolio import ...` |
| `tasks/forecasting.py` | `from backend.tools.forecasting import ...` | No change (forecasting not in scope) |
| `agents/user_context.py` | `from backend.tools.portfolio import get_or_create_portfolio, get_positions_with_pnl` | `from backend.services.portfolio import ...` |

## 6. Blocker: Circular Import

`backend/tools/risk_narrative.py` (line 101) imports `SECTOR_ETF_MAP` from `backend/routers/forecasts.py` (line 32). This is a `tools/ → routers/` dependency that violates the target dependency graph.

**Fix (prerequisite step):** Extract `SECTOR_ETF_MAP` to `backend/constants.py`. Update both `risk_narrative.py` and `forecasts.py` to import from `constants.py`.

## 7. Error Handling Pattern

Services raise domain-specific exceptions. Callers translate:

```python
# backend/services/exceptions.py (new file)
class StockNotFoundError(Exception): ...
class PortfolioNotFoundError(Exception): ...
class DuplicateWatchlistError(Exception): ...
class IngestFailedError(Exception): ...
```

```python
# Router translates to HTTP
try:
    signals = await get_latest_signals(ticker, db)
except StockNotFoundError:
    raise HTTPException(status_code=404, detail="Stock not found")

# Tool translates to ToolResult
try:
    signals = await get_latest_signals(ticker, db)
except StockNotFoundError:
    return ToolResult(status="error", error="Stock not found. Try searching first.")
```

## 8. Test Strategy

### New tests (services)
- `tests/unit/services/test_stock_data.py` — price queries, stock CRUD
- `tests/unit/services/test_signals.py` — compute + retrieve signals
- `tests/unit/services/test_recommendations.py` — generate + retrieve recs
- `tests/unit/services/test_watchlist.py` — watchlist CRUD
- `tests/unit/services/test_portfolio.py` — positions, summary, health, transactions
- `tests/unit/services/test_pipelines.py` — ingest_ticker orchestration

All use mocked `AsyncSession` — fast, isolated, no DB needed.

### Existing tests
- **API tests** (`tests/api/`): unchanged — still hit HTTP endpoints, validate full stack
- **Tool tests** (`tests/unit/tools/`): update imports, verify ToolResult formatting still works
- **Task tests** (`tests/unit/pipeline/`): update imports

### Coverage target
- Every public service function has ≥1 unit test
- Happy path + error path (StockNotFoundError, etc.)
- Pipeline tests verify correct sequencing (ingest calls fetch → compute → store in order)

## 9. Shared Schemas

These Pydantic models are used by routers, tools, AND will be used by services. No changes needed — services return the same types:

- `schemas/stock.py` — `StockSearchResponse`, `SignalResponse`, `BulkSignalResponse`
- `schemas/portfolio.py` — `PortfolioSummaryResponse`, `PositionResponse`, `SectorAllocation`
- `schemas/portfolio_health.py` — `PortfolioHealthResponse`, `HealthComponent`
- `schemas/recommend.py` — `RecommendationResponse`

## 10. What's NOT in scope

- **Chat/session services** — `tools/chat_session.py` is already well-isolated, not duplicated
- **Forecast services** — `tools/forecasting.py` (Prophet) is specialized, not duplicated in routers
- **Scorecard services** — `tools/scorecard.py` is tool-only, no router equivalent
- **Auth services** — `dependencies.py` is already the auth service layer
- **Sectors/indexes routers** — not large enough to warrant extraction this round
- **Multi-agent architecture** — separate initiative (KAN-189), but this refactor is its prerequisite
- **Intent-based tool filtering** — separate story (KAN-188), depends on cleaner tool boundaries from this work

## 11. Migration Sequence

Ordered to minimize breakage and allow incremental commits:

1. **Pre-requisite:** Extract `SECTOR_ETF_MAP` to `backend/constants.py` (circular import fix)
2. **Create `services/exceptions.py`** — domain exception classes
3. **Create `services/stock_data.py`** — migrate from `tools/market_data.py` + `tools/fundamentals.py`
4. **Create `services/signals.py`** — migrate from `tools/signals.py` + router inline queries
5. **Create `services/recommendations.py`** — migrate from `tools/recommendations.py` + router inline
6. **Create `services/watchlist.py`** — extract from `routers/stocks.py` (pure new extraction)
7. **Create `services/portfolio.py`** — migrate from `tools/portfolio.py` + router inline queries
8. **Create `services/pipelines.py`** — compose existing services into ingest pipeline
9. **Split `routers/stocks.py`** → `routers/stocks/` package (4 submodules)
10. **Update `routers/portfolio.py`** — replace inline DB with service calls
11. **Update tool imports** — all tool files that imported proto-services
12. **Update task imports** — all Celery task files
13. **Update `agents/user_context.py`** import
14. **Write service unit tests**
15. **Run full test suite** — verify zero regressions

Each step is independently committable and testable.

## 12. Success Criteria

- Zero direct DB operations in `routers/stocks/` and `routers/portfolio.py` (all go through services)
- `stocks.py` eliminated — replaced by 4 sub-router files, each under 250 lines
- Every proto-service function in `tools/` has moved to `services/` — tools are thin wrappers
- No circular imports (verified by `ruff check`)
- All existing tests pass (API, unit, integration, frontend)
- New service unit tests for every public function in `services/`
- Dependency graph is clean: services depend only on models/schemas/database/config
