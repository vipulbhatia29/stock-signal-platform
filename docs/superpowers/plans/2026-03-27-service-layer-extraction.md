# Service Layer Extraction + Router Split — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract business logic from routers and tools into a canonical `backend/services/` layer, split `stocks.py` into focused sub-routers.

**Architecture:** Plain async functions in `backend/services/` modules. Routers, tools, and tasks all call services. Services depend only on models/schemas/database/config. Two tiers: atomic services (granular) and pipeline services (orchestrators).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Pydantic v2, pytest

**Spec:** `docs/superpowers/specs/2026-03-27-service-layer-extraction-design.md`

---

## File Structure

### New files
```
backend/constants.py                         # SECTOR_ETF_MAP (extracted from forecasts.py)
backend/services/exceptions.py               # Domain exceptions
backend/services/stock_data.py               # Price, stock CRUD, fundamentals
backend/services/signals.py                  # Signal computation + queries
backend/services/recommendations.py          # Recommendation generation + queries
backend/services/watchlist.py                # Watchlist CRUD
backend/services/portfolio.py                # Positions, summary, health, transactions
backend/services/pipelines.py                # ingest_ticker orchestrator
backend/routers/stocks/__init__.py           # Package router combining sub-routers
backend/routers/stocks/data.py               # Stock data read endpoints
backend/routers/stocks/watchlist.py          # Watchlist endpoints
backend/routers/stocks/search.py             # Search + ingest endpoints
backend/routers/stocks/recommendations.py    # Recommendations + bulk signals
tests/unit/services/test_stock_data.py
tests/unit/services/test_signals.py
tests/unit/services/test_recommendations.py
tests/unit/services/test_watchlist.py
tests/unit/services/test_portfolio_service.py
tests/unit/services/test_pipelines.py
tests/unit/services/__init__.py
```

### Modified files
```
backend/routers/forecasts.py                 # Import SECTOR_ETF_MAP from constants
backend/tools/risk_narrative.py              # Import SECTOR_ETF_MAP from constants
backend/tools/market_data.py                 # Delegate to services/stock_data.py
backend/tools/signals.py                     # Delegate to services/signals.py
backend/tools/recommendations.py             # Delegate to services/recommendations.py
backend/tools/portfolio.py                   # Delegate to services/portfolio.py
backend/tools/fundamentals.py                # Delegate to services/stock_data.py
backend/routers/portfolio.py                 # Replace inline DB with service calls
backend/tasks/market_data.py                 # Update imports to services
backend/tasks/recommendations.py             # Update imports to services
backend/tasks/portfolio.py                   # Update imports to services
backend/agents/user_context.py               # Update imports to services
```

### Deleted files
```
backend/routers/stocks.py                    # Replaced by backend/routers/stocks/ package
```

---

## Task 1: Fix circular import blocker — extract SECTOR_ETF_MAP

**Files:**
- Create: `backend/constants.py`
- Modify: `backend/routers/forecasts.py:32-47`
- Modify: `backend/tools/risk_narrative.py:101`

- [ ] **Step 1: Create `backend/constants.py`**

Read `backend/routers/forecasts.py` lines 32-47 to get the exact `SECTOR_ETF_MAP` dict. Create `backend/constants.py`:

```python
"""Shared constants used across routers, tools, and services."""

SECTOR_ETF_MAP: dict[str, str] = {
    # Copy exact contents from forecasts.py:32-47
}
```

- [ ] **Step 2: Update `backend/routers/forecasts.py`**

Replace the `SECTOR_ETF_MAP` definition (lines 32-47) with:
```python
from backend.constants import SECTOR_ETF_MAP
```

Keep the usage at line 293 (`etf_ticker = SECTOR_ETF_MAP.get(sector.lower())`) unchanged.

- [ ] **Step 3: Update `backend/tools/risk_narrative.py`**

Replace the lazy import at line 101:
```python
# OLD:
from backend.routers.forecasts import SECTOR_ETF_MAP
# NEW:
from backend.constants import SECTOR_ETF_MAP
```

- [ ] **Step 4: Lint and test**

```bash
uv run ruff check --fix backend/constants.py backend/routers/forecasts.py backend/tools/risk_narrative.py
uv run ruff format backend/constants.py backend/routers/forecasts.py backend/tools/risk_narrative.py
uv run pytest tests/unit/ -q --tb=short -x
```
Expected: All tests pass, zero lint errors.

- [ ] **Step 5: Commit**

```bash
git add backend/constants.py backend/routers/forecasts.py backend/tools/risk_narrative.py
git commit -m "refactor: extract SECTOR_ETF_MAP to constants.py — fix tools→routers circular import"
```

---

## Task 2: Create domain exceptions

**Files:**
- Create: `backend/services/exceptions.py`

- [ ] **Step 1: Create `backend/services/exceptions.py`**

```python
"""Domain exceptions for the service layer.

Services raise these; callers (routers, tools, tasks) catch and translate
to their own error format (HTTPException, ToolResult, log + retry).
"""


class ServiceError(Exception):
    """Base exception for all service-layer errors."""


class StockNotFoundError(ServiceError):
    """Raised when a ticker is not in the stocks table."""

    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        super().__init__(f"Stock not found: {ticker}")


class PortfolioNotFoundError(ServiceError):
    """Raised when a user has no portfolio."""

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        super().__init__(f"Portfolio not found for user: {user_id}")


class DuplicateWatchlistError(ServiceError):
    """Raised when adding a ticker already on the watchlist."""

    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        super().__init__(f"Already on watchlist: {ticker}")


class IngestFailedError(ServiceError):
    """Raised when the ingest pipeline fails for a ticker."""

    def __init__(self, ticker: str, step: str) -> None:
        self.ticker = ticker
        self.step = step
        super().__init__(f"Ingest failed for {ticker} at step: {step}")
```

- [ ] **Step 2: Ensure `backend/services/__init__.py` exists**

Read `backend/services/__init__.py` — it should already exist (cache, redis_pool, token_blocklist). If it does, no changes. If it's empty, leave it empty.

- [ ] **Step 3: Lint**

```bash
uv run ruff check --fix backend/services/exceptions.py && uv run ruff format backend/services/exceptions.py
```

- [ ] **Step 4: Commit**

```bash
git add backend/services/exceptions.py
git commit -m "feat(services): add domain exception classes for service layer"
```

---

## Task 3: Create `services/stock_data.py` — price + stock CRUD

**Files:**
- Create: `backend/services/stock_data.py`
- Create: `tests/unit/services/__init__.py`
- Create: `tests/unit/services/test_stock_data.py`
- Modify: `backend/tools/market_data.py` (update to delegate)

- [ ] **Step 1: Read source functions**

Read these files to understand the exact function signatures and logic:
- `backend/tools/market_data.py` — `ensure_stock_exists()`, `fetch_prices_delta()`, `get_latest_price()`, `load_prices_df()`
- `backend/tools/fundamentals.py` — `fetch_fundamentals()`, `fetch_analyst_data()`, `fetch_earnings_history()`, `persist_fundamentals()`, `persist_analyst_data()`, `persist_earnings()`
- `backend/routers/stocks.py` — inline price query (find the `get_prices` endpoint, extract DB query)

- [ ] **Step 2: Create `backend/services/stock_data.py`**

Move the pure business logic functions from `tools/market_data.py` and `tools/fundamentals.py` into this file. Keep exact same function signatures (parameter names, types, return types). Add `from backend.services.exceptions import StockNotFoundError` and raise it where appropriate instead of returning None.

Key functions to include:
- `ensure_stock_exists(ticker, db)` — from `tools/market_data.py`
- `fetch_prices_delta(ticker, db)` — from `tools/market_data.py`
- `get_latest_price(ticker, db)` — from `tools/market_data.py`
- `load_prices_df(ticker, db, days)` — from `tools/market_data.py`
- `fetch_fundamentals(ticker)` — from `tools/fundamentals.py` (sync, yfinance)
- `fetch_analyst_data(ticker)` — from `tools/fundamentals.py` (sync)
- `fetch_earnings_history(ticker)` — from `tools/fundamentals.py` (sync)
- `persist_fundamentals(ticker, data, db)` — from `tools/fundamentals.py`
- `persist_analyst_data(ticker, data, db)` — from `tools/fundamentals.py`
- `persist_earnings(ticker, data, db)` — from `tools/fundamentals.py`

- [ ] **Step 3: Write tests in `tests/unit/services/test_stock_data.py`**

Create `tests/unit/services/__init__.py` (empty). Then write tests with mocked AsyncSession:
- `test_ensure_stock_exists_creates_when_missing` — mock DB returning None, verify `db.add()` called
- `test_ensure_stock_exists_returns_existing` — mock DB returning Stock, verify no add
- `test_get_latest_price_returns_most_recent` — mock DB returning price row
- `test_get_latest_price_stock_not_found` — mock DB returning None, verify `StockNotFoundError`

- [ ] **Step 4: Update `backend/tools/market_data.py`**

Replace function bodies with delegation to services. Keep the function names as re-exports for backward compatibility during migration:

```python
# At top of file, add:
from backend.services.stock_data import (
    ensure_stock_exists as ensure_stock_exists,
    fetch_prices_delta as fetch_prices_delta,
    get_latest_price as get_latest_price,
    load_prices_df as load_prices_df,
)
```

Remove the old function bodies. Keep any tool-class wrappers that exist in this file.

- [ ] **Step 5: Update `backend/tools/fundamentals.py`**

Same pattern — delegate to `services/stock_data.py`:

```python
from backend.services.stock_data import (
    fetch_fundamentals as fetch_fundamentals,
    fetch_analyst_data as fetch_analyst_data,
    fetch_earnings_history as fetch_earnings_history,
    persist_fundamentals as persist_fundamentals,
    persist_analyst_data as persist_analyst_data,
    persist_earnings as persist_earnings,
)
```

Remove old function bodies.

- [ ] **Step 6: Run tests**

```bash
uv run ruff check --fix backend/services/stock_data.py backend/tools/market_data.py backend/tools/fundamentals.py tests/unit/services/
uv run ruff format backend/services/stock_data.py backend/tools/market_data.py backend/tools/fundamentals.py tests/unit/services/
uv run pytest tests/unit/ -q --tb=short -x
```
Expected: All existing tests still pass + new service tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/services/stock_data.py backend/tools/market_data.py backend/tools/fundamentals.py tests/unit/services/
git commit -m "feat(services): extract stock_data service from tools/market_data + tools/fundamentals"
```

---

## Task 4: Create `services/signals.py`

**Files:**
- Create: `backend/services/signals.py`
- Create: `tests/unit/services/test_signals.py`
- Modify: `backend/tools/signals.py` (delegate to service)

- [ ] **Step 1: Read source functions**

Read:
- `backend/tools/signals.py` — `compute_signals()`, `store_signal_snapshot()`, `SignalResult`
- `backend/routers/stocks.py` — find inline DB queries for `get_signals`, `get_signal_history`, `get_bulk_signals` endpoints

- [ ] **Step 2: Create `backend/services/signals.py`**

Move from `tools/signals.py`:
- `compute_signals(ticker, db, piotroski_score?)` — computation logic
- `store_signal_snapshot(signal_result, db)` — DB write
- `SignalResult` dataclass — shared type (keep importable from both locations)

Extract from `routers/stocks.py`:
- `get_latest_signals(ticker, db)` — the DB query from the signals endpoint
- `get_signal_history(ticker, db, days)` — the DB query from signal history endpoint
- `get_bulk_signals(db, index_id, filters, limit, offset)` — the complex DISTINCT ON query

- [ ] **Step 3: Write tests in `tests/unit/services/test_signals.py`**

- `test_get_latest_signals_returns_snapshot` — mock DB with signal row
- `test_get_latest_signals_stock_not_found` — verify StockNotFoundError
- `test_get_signal_history_default_90_days` — mock DB, verify date filter
- `test_get_bulk_signals_with_filters` — mock DB, verify query construction

- [ ] **Step 4: Update `backend/tools/signals.py`**

Re-export from services:
```python
from backend.services.signals import (
    compute_signals as compute_signals,
    store_signal_snapshot as store_signal_snapshot,
    SignalResult as SignalResult,
)
```

- [ ] **Step 5: Lint, test, commit**

```bash
uv run ruff check --fix backend/services/signals.py backend/tools/signals.py tests/unit/services/test_signals.py
uv run ruff format backend/services/signals.py backend/tools/signals.py tests/unit/services/test_signals.py
uv run pytest tests/unit/ -q --tb=short -x
git add backend/services/signals.py backend/tools/signals.py tests/unit/services/test_signals.py
git commit -m "feat(services): extract signals service from tools/signals + router inline queries"
```

---

## Task 5: Create `services/recommendations.py`

**Files:**
- Create: `backend/services/recommendations.py`
- Create: `tests/unit/services/test_recommendations.py`
- Modify: `backend/tools/recommendations.py` (delegate)

- [ ] **Step 1: Read source functions**

Read:
- `backend/tools/recommendations.py` — `generate_recommendation()`, `store_recommendation()`, `calculate_position_size()`
- `backend/routers/stocks.py` — inline DB query for `get_recommendations` endpoint

- [ ] **Step 2: Create `backend/services/recommendations.py`**

Move from `tools/recommendations.py`:
- `generate_recommendation(ticker, user_id, db, signal_result?, positions?)` — generation logic
- `store_recommendation(rec, db)` — DB write
- `calculate_position_size(...)` — position sizing math

Extract from `routers/stocks.py`:
- `get_recommendations(user_id, db, action_filter?, limit?, offset?)` — query for user's recs

- [ ] **Step 3: Write tests**

- `test_generate_recommendation_buy_signal` — mock signals with score >= 8, verify BUY
- `test_generate_recommendation_avoid_signal` — mock signals with score < 5, verify AVOID
- `test_get_recommendations_filters_by_action` — mock DB, verify WHERE clause

- [ ] **Step 4: Update `backend/tools/recommendations.py`**

Re-export from services. Keep tool class wrappers.

- [ ] **Step 5: Lint, test, commit**

```bash
uv run pytest tests/unit/ -q --tb=short -x
git add backend/services/recommendations.py backend/tools/recommendations.py tests/unit/services/test_recommendations.py
git commit -m "feat(services): extract recommendations service from tools/recommendations + router"
```

---

## Task 6: Create `services/watchlist.py`

**Files:**
- Create: `backend/services/watchlist.py`
- Create: `tests/unit/services/test_watchlist.py`

- [ ] **Step 1: Read source**

Read `backend/routers/stocks.py` — find all watchlist endpoints: `get_watchlist`, `add_to_watchlist`, `remove_from_watchlist`, `acknowledge_watchlist_price`, `refresh_all_watchlist`. Extract the DB query logic from each.

- [ ] **Step 2: Create `backend/services/watchlist.py`**

Extract from `routers/stocks.py`:
- `get_watchlist(user_id, db)` — query Watchlist + join latest prices/signals
- `add_to_watchlist(user_id, ticker, db)` — insert, raise DuplicateWatchlistError if exists
- `remove_from_watchlist(user_id, ticker, db)` — delete, raise StockNotFoundError if not on list
- `acknowledge_price(user_id, ticker, price, db)` — update acknowledged price
- `get_all_watchlist_tickers(db)` — for batch refresh (used by tasks)

- [ ] **Step 3: Write tests**

- `test_add_to_watchlist_success` — mock DB, verify insert
- `test_add_to_watchlist_duplicate` — mock existing, verify DuplicateWatchlistError
- `test_remove_from_watchlist_not_found` — verify StockNotFoundError
- `test_get_watchlist_returns_enriched_data` — mock DB joins

- [ ] **Step 4: Lint, test, commit**

```bash
uv run pytest tests/unit/ -q --tb=short -x
git add backend/services/watchlist.py tests/unit/services/test_watchlist.py
git commit -m "feat(services): extract watchlist service from routers/stocks.py"
```

---

## Task 7: Create `services/portfolio.py`

**Files:**
- Create: `backend/services/portfolio.py` (the service — distinct from existing `tools/portfolio.py`)
- Create: `tests/unit/services/test_portfolio_service.py`
- Modify: `backend/tools/portfolio.py` (delegate)

- [ ] **Step 1: Read source functions**

Read:
- `backend/tools/portfolio.py` — `get_or_create_portfolio()`, `get_positions_with_pnl()`, `_run_fifo()`, `get_all_portfolio_ids()`, `snapshot_portfolio_value()`
- `backend/routers/portfolio.py` — inline DB logic for all 10 endpoints

- [ ] **Step 2: Create `backend/services/portfolio.py`**

Move from `tools/portfolio.py`:
- `get_or_create_portfolio(user_id, db)`
- `get_positions_with_pnl(portfolio_id, db)`
- `_run_fifo(transactions)` (private helper, still needed)
- `get_all_portfolio_ids(db)`
- `snapshot_portfolio_value(portfolio_id, db)`

Extract from `routers/portfolio.py`:
- `create_transaction(user_id, data, db)`
- `list_transactions(user_id, db, limit, offset)`
- `delete_transaction(user_id, txn_id, db)`
- `get_portfolio_summary(user_id, db)`
- `get_portfolio_history(user_id, db, days)`
- `get_rebalancing(user_id, db)`
- `get_dividends_for_ticker(user_id, ticker, db)`
- `get_health_history(user_id, db, days)`

- [ ] **Step 3: Write tests**

- `test_get_or_create_portfolio_creates_new` — mock no existing, verify db.add
- `test_get_or_create_portfolio_returns_existing` — mock existing
- `test_get_positions_with_pnl_fifo_calculation` — verify FIFO math
- `test_create_transaction_validates_ticker` — mock stock lookup
- `test_delete_transaction_not_found` — verify error

- [ ] **Step 4: Update `backend/tools/portfolio.py`**

Re-export all moved functions from services:
```python
from backend.services.portfolio import (
    get_or_create_portfolio as get_or_create_portfolio,
    get_positions_with_pnl as get_positions_with_pnl,
    get_all_portfolio_ids as get_all_portfolio_ids,
    snapshot_portfolio_value as snapshot_portfolio_value,
)
```

- [ ] **Step 5: Lint, test, commit**

```bash
uv run pytest tests/unit/ -q --tb=short -x
git add backend/services/portfolio.py backend/tools/portfolio.py tests/unit/services/test_portfolio_service.py
git commit -m "feat(services): extract portfolio service from tools/portfolio + routers/portfolio"
```

---

## Task 8: Create `services/pipelines.py`

**Files:**
- Create: `backend/services/pipelines.py`
- Create: `tests/unit/services/test_pipelines.py`

- [ ] **Step 1: Read the ingest endpoint**

Read `backend/routers/stocks.py` — find the `ingest_ticker` endpoint (around line 690-815). This is the orchestration logic: ensure_stock → fetch_prices → fetch_fundamentals → persist → compute_signals → generate_recommendation.

Also read `backend/tasks/market_data.py` — `_refresh_ticker_async()` which does a similar sequence.

- [ ] **Step 2: Create `backend/services/pipelines.py`**

```python
"""Pipeline orchestrators — compose atomic services into transactional sequences.

These are the ONLY place where multi-step business workflows are defined.
Routers, tools, and tasks call pipelines for orchestrated operations.
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.exceptions import IngestFailedError
from backend.services.stock_data import (
    ensure_stock_exists,
    fetch_prices_delta,
    fetch_fundamentals,
    persist_fundamentals,
    fetch_analyst_data,
    persist_analyst_data,
    fetch_earnings_history,
    persist_earnings,
)
from backend.services.signals import compute_signals, store_signal_snapshot

logger = logging.getLogger(__name__)


async def ingest_ticker(ticker: str, db: AsyncSession, user_id=None) -> dict:
    """Full ingest pipeline: fetch → compute → store → recommend.

    Args:
        ticker: Stock ticker symbol.
        db: Async database session.
        user_id: Optional user ID for portfolio-aware recommendations.

    Returns:
        Dict with step results: {prices, signals, recommendation}.

    Raises:
        IngestFailedError: If any critical step fails.
    """
    # Step 1: Ensure stock exists
    stock = await ensure_stock_exists(ticker, db)

    # Step 2: Fetch latest prices
    price_count = await fetch_prices_delta(ticker, db)

    # Step 3: Fetch + persist fundamentals (sync fetch via run_in_executor)
    # ... compose the exact logic from routers/stocks.py ingest endpoint

    # Step 4: Compute signals
    signal_result = await compute_signals(ticker, db)
    await store_signal_snapshot(signal_result, db)

    # Step 5: Generate recommendation (if user_id provided)
    recommendation = None
    if user_id:
        from backend.services.recommendations import generate_recommendation
        # ... portfolio-aware recommendation

    return {"prices": price_count, "signals": signal_result, "recommendation": recommendation}
```

Extract the EXACT logic from the ingest endpoint — don't simplify or rewrite. Match what exists.

- [ ] **Step 3: Write tests**

- `test_ingest_ticker_full_pipeline` — mock all service calls, verify they execute in order
- `test_ingest_ticker_price_fetch_fails` — verify IngestFailedError at step 2
- `test_ingest_ticker_skips_recommendation_without_user` — verify recommendation is None

- [ ] **Step 4: Lint, test, commit**

```bash
uv run pytest tests/unit/ -q --tb=short -x
git add backend/services/pipelines.py tests/unit/services/test_pipelines.py
git commit -m "feat(services): add pipeline orchestrator for ingest_ticker"
```

---

## Task 9: Split `routers/stocks.py` into package

**Files:**
- Create: `backend/routers/stocks/__init__.py`
- Create: `backend/routers/stocks/data.py`
- Create: `backend/routers/stocks/watchlist.py`
- Create: `backend/routers/stocks/search.py`
- Create: `backend/routers/stocks/recommendations.py`
- Delete: `backend/routers/stocks.py` (after creating package)

- [ ] **Step 1: Create `backend/routers/stocks/` directory**

```bash
mkdir -p backend/routers/stocks
```

- [ ] **Step 2: Create `backend/routers/stocks/data.py`**

Move these endpoints from `stocks.py`, replacing inline DB queries with service calls:
- `get_prices(ticker, db, user)` → calls `services.stock_data.get_prices()`
- `get_signals(ticker, db, user)` → calls `services.signals.get_latest_signals()`
- `get_fundamentals(ticker, db, user)` → calls service
- `get_stock_news(ticker, db, user)` → stays as-is (news is already tool-delegated)
- `get_stock_intelligence(ticker, db, user)` → stays as-is

Each endpoint: validate input, call service, return Pydantic response. No direct DB operations.

- [ ] **Step 3: Create `backend/routers/stocks/watchlist.py`**

Move watchlist endpoints, delegate to `services.watchlist`:
- `get_watchlist`, `add_to_watchlist`, `remove_from_watchlist`, `acknowledge_watchlist_price`, `refresh_all_watchlist`

Catch `DuplicateWatchlistError` → 409, `StockNotFoundError` → 404.

- [ ] **Step 4: Create `backend/routers/stocks/search.py`**

Move:
- `search_stocks(query, db, user)` — keep Yahoo search logic (it's HTTP-specific)
- `ingest_ticker(ticker, db, user)` → calls `services.pipelines.ingest_ticker()`

- [ ] **Step 5: Create `backend/routers/stocks/recommendations.py`**

Move:
- `get_recommendations(db, user, filters)` → calls `services.recommendations.get_recommendations()`
- `get_bulk_signals(db, user, filters)` → calls `services.signals.get_bulk_signals()`
- `get_signal_history(ticker, db, user)` → calls `services.signals.get_signal_history()`

- [ ] **Step 6: Create `backend/routers/stocks/__init__.py`**

```python
"""Stock-related API endpoints — split by domain."""

from fastapi import APIRouter

from backend.routers.stocks.data import router as data_router
from backend.routers.stocks.recommendations import router as recommendations_router
from backend.routers.stocks.search import router as search_router
from backend.routers.stocks.watchlist import router as watchlist_router

router = APIRouter()
router.include_router(data_router)
router.include_router(watchlist_router)
router.include_router(search_router)
router.include_router(recommendations_router)
```

- [ ] **Step 7: Delete old `backend/routers/stocks.py`**

Verify `main.py` imports `from backend.routers.stocks import router` — this now resolves to the package `__init__.py`. No main.py changes needed.

```bash
rm backend/routers/stocks.py
```

- [ ] **Step 8: Lint, test, commit**

```bash
uv run ruff check --fix backend/routers/stocks/ && uv run ruff format backend/routers/stocks/
uv run pytest tests/unit/ tests/api/ -q --tb=short -x
git add backend/routers/stocks/ && git rm backend/routers/stocks.py
git commit -m "refactor(routers): split stocks.py (1216 lines) into 4 focused sub-routers"
```

---

## Task 10: Update `routers/portfolio.py` to use services

**Files:**
- Modify: `backend/routers/portfolio.py`

- [ ] **Step 1: Replace inline DB operations with service calls**

Read `backend/routers/portfolio.py`. For each of the 10 endpoints, replace inline DB queries with calls to `backend.services.portfolio`. Update imports at top of file.

Old pattern:
```python
portfolio = await get_or_create_portfolio(user.id, db)  # from tools/portfolio
result = await db.execute(select(...).where(...))  # inline DB
```

New pattern:
```python
from backend.services.portfolio import get_portfolio_summary
summary = await get_portfolio_summary(user.id, db)
```

- [ ] **Step 2: Update error handling**

Catch service exceptions and translate:
```python
from backend.services.exceptions import PortfolioNotFoundError, StockNotFoundError

try:
    result = await get_dividends_for_ticker(user.id, ticker, db)
except StockNotFoundError:
    raise HTTPException(status_code=404, detail="Stock not found")
```

- [ ] **Step 3: Update imports**

Replace all `from backend.tools.portfolio import ...` with `from backend.services.portfolio import ...`.
Replace `from backend.tools.recommendations import calculate_position_size` with `from backend.services.recommendations import calculate_position_size`.

- [ ] **Step 4: Lint, test, commit**

```bash
uv run ruff check --fix backend/routers/portfolio.py && uv run ruff format backend/routers/portfolio.py
uv run pytest tests/unit/ tests/api/ -q --tb=short -x
git add backend/routers/portfolio.py
git commit -m "refactor(routers): portfolio.py delegates to services — zero inline DB ops"
```

---

## Task 11: Update task imports

**Files:**
- Modify: `backend/tasks/market_data.py`
- Modify: `backend/tasks/recommendations.py`
- Modify: `backend/tasks/portfolio.py`

- [ ] **Step 1: Update `backend/tasks/market_data.py`**

Replace imports (lines 12-13 and lazy imports):
```python
# OLD:
from backend.tools.market_data import fetch_prices_delta, load_prices_df
from backend.tools.signals import compute_signals, store_signal_snapshot
# NEW:
from backend.services.stock_data import fetch_prices_delta, load_prices_df
from backend.services.signals import compute_signals, store_signal_snapshot
```

Also update lazy import of `fetch_dividends`, `store_dividends` at line 67 if those moved.

- [ ] **Step 2: Update `backend/tasks/recommendations.py`**

Replace imports (lines 30-32):
```python
# OLD:
from backend.tools.market_data import get_latest_price
from backend.tools.recommendations import generate_recommendation, store_recommendation
from backend.tools.signals import SignalResult
# NEW:
from backend.services.stock_data import get_latest_price
from backend.services.recommendations import generate_recommendation, store_recommendation
from backend.services.signals import SignalResult
```

- [ ] **Step 3: Update `backend/tasks/portfolio.py`**

Replace imports (lines 8 and 84):
```python
# OLD:
from backend.tools.portfolio import get_all_portfolio_ids, snapshot_portfolio_value
from backend.tools.portfolio_health import compute_portfolio_health
# NEW:
from backend.services.portfolio import get_all_portfolio_ids, snapshot_portfolio_value
# portfolio_health stays in tools (orchestrator tool, not pure service) — verify
```

- [ ] **Step 4: Update `backend/agents/user_context.py`**

Replace import (line 90, inside function):
```python
# OLD:
from backend.tools.portfolio import get_or_create_portfolio, get_positions_with_pnl
# NEW:
from backend.services.portfolio import get_or_create_portfolio, get_positions_with_pnl
```

- [ ] **Step 5: Lint, test, commit**

```bash
uv run ruff check --fix backend/tasks/ backend/agents/user_context.py
uv run ruff format backend/tasks/ backend/agents/user_context.py
uv run pytest tests/unit/ -q --tb=short -x
git add backend/tasks/market_data.py backend/tasks/recommendations.py backend/tasks/portfolio.py backend/agents/user_context.py
git commit -m "refactor: update task + agent imports to use services layer"
```

---

## Task 12: Final verification + cleanup

**Files:**
- No new files — verification only

- [ ] **Step 1: Verify zero tools→services leaks**

```bash
# No router should have direct DB operations (except auth, chat, health, admin which are out of scope)
grep -rn "db.execute\|db.add\|select(" backend/routers/stocks/ backend/routers/portfolio.py | grep -v "# service" | head -20
# Should return zero or only comments
```

- [ ] **Step 2: Verify dependency graph**

```bash
# Services should NEVER import from routers, tools, tasks, or agents
grep -rn "from backend.routers\|from backend.tools\|from backend.tasks\|from backend.agents" backend/services/*.py
# Should return zero matches (except cache/redis_pool/token_blocklist which are unchanged)
```

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/unit/ tests/api/ -q --tb=short
```
Expected: All tests pass. Note the new test count.

- [ ] **Step 4: Verify no leftover proto-service function bodies in tools/**

```bash
# tools/portfolio.py, tools/market_data.py, tools/signals.py, tools/recommendations.py
# should only contain re-exports and tool class wrappers — no business logic bodies
wc -l backend/tools/portfolio.py backend/tools/market_data.py backend/tools/signals.py backend/tools/recommendations.py backend/tools/fundamentals.py
# Each should be significantly shorter than before
```

- [ ] **Step 5: Final commit if any cleanup needed**

```bash
git add -A && git status
# If clean: done. If changes: commit with "chore: service layer cleanup"
```

---

## Execution Notes

- **Tasks 1-2** are prerequisites (blocker fix + exceptions). Can be done quickly.
- **Tasks 3-8** (service creation) are independent of each other and can be parallelized with worktree agents. However, Task 8 (pipelines) depends on Tasks 3-5 being complete since it imports from them.
- **Tasks 9-10** (router refactoring) depend on all services being created (Tasks 3-8).
- **Task 11** (import updates) depends on services existing.
- **Task 12** is final verification.

**Recommended parallel batches:**
- Batch 1: Tasks 1-2 (sequential, fast)
- Batch 2: Tasks 3, 4, 5, 6, 7 (parallel — independent service modules)
- Batch 3: Task 8 (pipelines — needs services from batch 2)
- Batch 4: Tasks 9, 10, 11 (can partially parallel — 9 and 10 are independent, 11 needs both)
- Batch 5: Task 12 (verification)
