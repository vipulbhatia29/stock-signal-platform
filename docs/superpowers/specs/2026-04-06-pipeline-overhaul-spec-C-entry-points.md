# Spec C: Entry Point Unification

**Status:** Draft
**Date:** 2026-04-06
**Authors:** Platform team (KAN-408 pipeline overhaul)
**Epic:** Pipeline Overhaul (Specs A → B → C → D → E/F/G)
**Depends on:** Spec A (PipelineRunner contract + run tracking), Spec B (ingest_ticker extended to cover news + convergence)
**Blocks:** Spec G (frontend progress UI polish)

---

## Problem Statement

The canonical ingestion pipeline `backend/services/pipelines.py::ingest_ticker` (lines 40–152) exists and correctly composes every atomic step: `ensure_stock_exists` → `fetch_prices_delta` → `load_prices_df` → fundamentals/analyst/earnings → `compute_signals` + `store_signal_snapshot` → forecast dispatch → optional recommendation. It is the only place in the codebase where the full ingest sequence is written down.

It has exactly **one caller**: `backend/routers/stocks/data.py::ingest_stock` (the explicit `POST /stocks/{ticker}/ingest` endpoint — the "Run Analysis" button on the stock detail page). Every other UX path that introduces a new ticker reimplements a partial, buggy subset of the pipeline:

1. **Watchlist add is strictly broken for unknown tickers.**
   `backend/services/watchlist.py:114-140` — `add_to_watchlist` does `SELECT stock WHERE ticker = upper(ticker)` and raises `StockNotFoundError` if the row is missing. `backend/routers/stocks/watchlist.py:76-81` catches it and returns HTTP 404 with message *"Stock 'XYZ' not found. Make sure the ticker is correct and has been added to the system."* — a message that is factually wrong for any valid Yahoo ticker the system has simply never seen before. The frontend papers over this with a two-phase hack in `frontend/src/app/(authenticated)/layout.tsx:24-41`: it calls `ingestTicker.mutateAsync(ticker)` first, then `addToWatchlist.mutate(ticker)`. That hack is only reachable from the topbar search — every other watchlist add path (chat suggestions, deep links, programmatic adds) hits the 404 bug.

2. **Portfolio transaction creates a Stock row but skips price fetch.**
   `backend/routers/portfolio.py:112-118` calls `await ensure_stock_exists(ticker_upper, db)` only. `ensure_stock_exists` creates the `Stock` row (company metadata) but does not call `fetch_prices_delta`, does not call `compute_signals`, does not dispatch the forecast task. The user who logs a `BUY AAPL` at 10:05am then visits the AAPL stock detail page sees blank charts, `null` signals, and the message "No signals computed" until the next intraday refresh (up to 30 minutes later) or the nightly batch. The portfolio position row itself works (FIFO runs against the transaction table), but every secondary surface the user expects — price sparkline, composite score, "is this a buy?" recommendation — is empty.

3. **Chat `analyze_stock` computes signals but does not persist them.**
   `backend/tools/analyze_stock.py:62-84` — if `load_prices_df` returns empty, the tool calls `ensure_stock_exists` + `fetch_prices_delta` inline, then `compute_signals(ticker, df)` and returns the signal fields in the tool response. It never calls `store_signal_snapshot`. The user sees the composite score in chat, clicks through to the stock detail page, and sees "No signals computed" because nothing was written to the `signal_snapshots` table. The chat answer and the stock page disagree.

4. **Stock detail `is_stale` flag is display-only and nothing refreshes.**
   `backend/routers/stocks/data.py:138-212` — `get_signals` computes `is_stale = age > 24h` from `snapshot.computed_at` (lines 176-179) and returns it in `SignalResponse`. The frontend (`frontend/src/components/signal-cards.tsx`, `stock-header.tsx`) does not render the flag anywhere. `frontend/src/hooks/use-stocks.ts:190-196` — `useSignals` has no `refetchInterval`. A user who lands on a stock detail page with a 3-day-old snapshot sees 3-day-old data forever, unless they click "Run Analysis" manually.

5. **Bulk portfolio CSV upload does not exist.**
   A user migrating from another broker must log transactions one at a time through `LogTransactionDialog`. `frontend/src/lib/api.ts:42` hardcodes `Content-Type: application/json` — there is no `postMultipart` helper. A 40-trade import is 40 round trips, each one leaving the ticker half-ingested (Spec C.2 fixes the latter).

The common root cause is that ingestion is not a *contract* — it is a pattern that every caller hand-assembles. Spec C makes every user-facing entry point that introduces a new ticker go through `ingest_ticker` exactly once, and then layers stale-data refresh, CSV bulk import, and frontend cleanup on top.

---

## Goals

1. Every UX path that can introduce a ticker unknown to the database drives it through the canonical `ingest_ticker` pipeline exactly once.
2. The two-phase ingest+watchlist hack in the frontend layout is removed. Frontend just calls `addToWatchlist.mutate(ticker)`.
3. Portfolio transaction for a new ticker returns with full price history, fundamentals, and at least one signal snapshot already stored — so the next navigation to `/stocks/{ticker}` is not blank.
4. Chat `analyze_stock` uses `ingest_ticker` and persists signal snapshots so chat and stock pages agree.
5. Stock detail signals endpoint fires a debounced background refresh when `is_stale=True` and the frontend renders a "Refreshing…" indicator with auto-poll.
6. Users can bulk-import a CSV of transactions through a new `POST /portfolio/transactions/bulk` endpoint that parallelizes ingestion with bounded concurrency.
7. `ticker-search.tsx` and the topbar "Add" flow are simplified post-C1 with no regression in the "in_db / external" rendering.

## Non-Goals

- Redesigning `ingest_ticker` itself — Spec B covers the news + convergence extensions.
- Streaming progress updates over WebSocket — Spec G will add a "fetching…" overlay fed by task IDs; for now we use synchronous request + spinner.
- Splitting `ingest_ticker` into foreground-fast vs background-slow legs — out of scope; latency tradeoff is explicit in rollout section.
- Editing existing transactions (only create + bulk create).
- CSV export format — already exists in `frontend/src/lib/csv-export.ts`.
- Granular permissions on bulk CSV upload size beyond a flat cap.

---

## Design

### C1. Watchlist auto-ingest

#### Current state

`backend/services/watchlist.py:114-140`:

```python
async def add_to_watchlist(user_id, ticker, db) -> dict:
    ticker = ticker.upper()
    stock_result = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = stock_result.scalar_one_or_none()
    if stock is None:
        raise StockNotFoundError(ticker)  # ← returns 404 to user
    ...
```

`backend/routers/stocks/watchlist.py:74-81` catches the exception and returns 404.

`frontend/src/app/(authenticated)/layout.tsx:24-41`:

```tsx
const handleAddTicker = useCallback(async (ticker) => {
    ...
    await ingestTicker.mutateAsync(ticker);   // phase 1 — only reachable from topbar
    addToWatchlist.mutate(ticker);            // phase 2
}, [watchlist, ingestTicker, addToWatchlist]);
```

#### New backend implementation

Modify `backend/services/watchlist.py::add_to_watchlist` to call `ingest_ticker` synchronously before the existing duplicate-check and insert. On `IngestFailedError`, surface as `StockNotFoundError(ticker)` so the existing 404 message stays consistent for genuinely invalid tickers. **Error messages never include `exc.step` or other internal detail — only a generic "not recognized / temporarily unavailable" string (Hard Rule #10).**

#### Concurrent-user dedup (Redis SETNX)

A viral story can drive many users to add the same unknown ticker within
seconds. Without coordination, every caller runs the full ingest pipeline
(10-year price fetch + signals + forecast dispatch) — crushing Finnhub
rate limits and wasting work.

Before invoking `ingest_ticker`, `add_to_watchlist` acquires a Redis
SETNX lock:

```python
IN_FLIGHT_KEY = "ingest:in_flight:{ticker}"  # TTL 60s
LOCK_TTL_SECONDS = 60

async def _acquire_ingest_lock(ticker: str) -> bool:
    return bool(
        await redis_client.set(
            IN_FLIGHT_KEY.format(ticker=ticker),
            "1",
            ex=LOCK_TTL_SECONDS,
            nx=True,
        )
    )
```

Behaviour:

- **First caller** acquires the lock and runs `ingest_ticker`. On
  success or failure the key is `DEL`'d so subsequent requests go
  through fast paths.
- **Concurrent callers** (SETNX returns False) either:
  - **Option A (default):** Return 409 Conflict with a generic message
    `"Ingestion already in progress for this ticker, please retry in ~30s."`
    — no internal detail leaked.
  - **Option B:** Poll the ticker's `last_fetched_at` column for up to
    30s and return the successful response when the first caller
    finishes. Implementations may ship Option A first and upgrade later.

The watchlist router, portfolio-transaction router, and stock-detail
auto-refresh path all go through the same lock helper so a single in-flight
ingest is reused across all entry points.

```python
from backend.services.exceptions import (
    DuplicateWatchlistError,
    IngestFailedError,
    StockNotFoundError,
)
from backend.services.pipelines import ingest_ticker

async def add_to_watchlist(
    user_id: uuid.UUID,
    ticker: str,
    db: AsyncSession,
) -> dict:
    """Add a ticker to the user's watchlist (auto-ingests if unknown).

    The ticker is ingested through the canonical pipeline (ensure_stock +
    fetch prices + fundamentals + signals + forecast dispatch) before the
    watchlist row is inserted, so the next page view has full data.
    """
    ticker = ticker.upper().strip()

    # Size limit check (avoid wasted ingest work if user is already at cap)
    count_result = await db.execute(
        select(func.count()).select_from(Watchlist).where(Watchlist.user_id == user_id)
    )
    if count_result.scalar_one() >= MAX_WATCHLIST_SIZE:
        raise ValueError(f"Watchlist is full (maximum {MAX_WATCHLIST_SIZE} tickers)")

    # Duplicate check BEFORE ingest (idempotent: avoid re-fetching for an existing add)
    existing_wl = await db.execute(
        select(Watchlist).where(
            Watchlist.user_id == user_id,
            Watchlist.ticker == ticker,
        )
    )
    if existing_wl.scalar_one_or_none() is not None:
        raise DuplicateWatchlistError(ticker)

    # Canonical ingest — creates Stock row, fetches prices, computes signals
    try:
        await ingest_ticker(ticker, db, user_id=str(user_id))
    except IngestFailedError as exc:
        logger.warning("Watchlist ingest failed for %s: %s", ticker, exc.step)
        raise StockNotFoundError(ticker) from exc

    # Stock row is now guaranteed to exist
    stock_result = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = stock_result.scalar_one()

    entry = Watchlist(user_id=user_id, ticker=ticker)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    return {
        "id": entry.id,
        "ticker": entry.ticker,
        "name": stock.name,
        "sector": stock.sector,
        "added_at": entry.added_at,
        "ingestion_status": "completed",
    }
```

Notes on the shape change:
- The `ingest_ticker` call inside `add_to_watchlist` receives its own `db` session. `ingest_ticker` already performs multiple internal commits (it calls `persist_enriched_fundamentals`, `store_signal_snapshot`, `update_last_fetched_at`, and these commit independently), so by the time we insert the `Watchlist` row we are already past the point of rollback for the ingest work. This is acceptable: an ingest followed by a failed watchlist insert leaves the ingest data in place (no harm — it will be used by other users or a later retry). The user-visible behavior is "the next attempt succeeds instantly because the Stock row exists".
- `DuplicateWatchlistError` is raised before `ingest_ticker` so repeat adds of a ticker the user already has do not re-fetch.

Router (`backend/routers/stocks/watchlist.py`) grows one new exception handler:

```python
except IngestFailedError:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Ticker '{body.ticker.upper()}' not recognized by data provider.",
    )
```

#### Frontend changes

1. `frontend/src/app/(authenticated)/layout.tsx:24-41` — collapse `handleAddTicker` to a single mutation:

```tsx
const handleAddTicker = useCallback(
  (ticker: string) => {
    const isInWatchlist = watchlist?.some((w) => w.ticker === ticker);
    if (isInWatchlist) {
      toast.info(`${ticker} is already in your watchlist`);
      return;
    }
    addToWatchlist.mutate(ticker);
  },
  [watchlist, addToWatchlist],
);
```

`useIngestTicker` is no longer imported here. It remains exported from `use-stocks.ts` for the explicit "Run Analysis" button on the stock detail page (Spec C6).

2. `frontend/src/hooks/use-stocks.ts:57-70` — `useAddToWatchlist` gains:
   - Pending-state friendly loading toast with an ID matched to the success/error handlers (so the "Fetching…" toast is replaced by "Added" or "Failed").
   - Full query-set invalidation for the new ticker on success (the ticker now has fresh signals, prices, fundamentals, bulk-signals, forecast, news, intelligence).
   - 404 detection for a user-friendly message.

```ts
export function useAddToWatchlist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ticker: string) =>
      post<WatchlistItem>("/stocks/watchlist", { ticker }),
    onMutate: (ticker) => {
      toast.loading(`Fetching data for ${ticker.toUpperCase()}...`, {
        id: `add-${ticker}`,
      });
    },
    onSuccess: (_data, ticker) => {
      const T = ticker.toUpperCase();
      toast.success(`${T} added to watchlist`, { id: `add-${ticker}` });
      // Full invalidation so every surface on /stocks/T sees the new data
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      queryClient.invalidateQueries({ queryKey: ["signals", T] });
      queryClient.invalidateQueries({ queryKey: ["prices", T] });
      queryClient.invalidateQueries({ queryKey: ["fundamentals", T] });
      queryClient.invalidateQueries({ queryKey: ["bulk-signals"] });
      queryClient.invalidateQueries({ queryKey: ["bulk-signals-by-ticker"] });
      queryClient.invalidateQueries({ queryKey: ["stock-intelligence", T] });
      queryClient.invalidateQueries({ queryKey: ["forecast", T] });
      queryClient.invalidateQueries({ queryKey: ["stock-news", T] });
    },
    onError: (err, ticker) => {
      const is404 =
        err instanceof ApiRequestError && err.status === 404;
      const msg = is404
        ? `${ticker.toUpperCase()} not recognized. Check the symbol.`
        : err instanceof Error
        ? err.message
        : "Failed to add";
      toast.error(msg, { id: `add-${ticker}` });
    },
  });
}
```

3. `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx:88-94` — `handleToggleWatchlist` simplifies to the single mutation (no pre-ingest).

4. `frontend/src/components/ticker-search.tsx` — no direct change here. This component only calls `props.onSelect(ticker)` and the caller (`Topbar` → `handleAddTicker`) is the piece that simplifies. After C1, the external ("Add from market") branch still works identically because `onSelect → handleAddTicker → addToWatchlist` now ingests transparently.

### C2. Portfolio transaction sync ingest for new tickers

#### Current state

`backend/routers/portfolio.py:112-118`:

```python
try:
    await ensure_stock_exists(ticker_upper, db)
except ValueError:
    raise HTTPException(422, ...)
```

No prices, no signals, no forecast.

#### New backend implementation

After `ensure_stock_exists` returns, inspect `stock.last_fetched_at`. If `None`, this is a truly new ticker for the platform; call the full `ingest_ticker` pipeline synchronously. If it already has a `last_fetched_at`, trust the existing intraday refresh and skip the expensive path.

```python
from backend.services.pipelines import ingest_ticker
from backend.services.exceptions import IngestFailedError

try:
    stock = await ensure_stock_exists(ticker_upper, db)
except ValueError:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Ticker '{ticker_upper}' not recognized. Verify the symbol is correct.",
    )

if stock.last_fetched_at is None:
    # New ticker — run canonical ingest synchronously. Latency ~5-15s.
    try:
        await ingest_ticker(ticker_upper, db, user_id=str(current_user.id))
    except IngestFailedError as exc:
        logger.warning(
            "Transaction ingest failed for %s user=%s step=%s",
            ticker_upper, current_user.id, exc.step,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not load market data for '{ticker_upper}'. Try again shortly.",
        )
```

Implementation nuance: `ensure_stock_exists` creates the Stock row if missing. We observe `last_fetched_at` on the returned object *after* `ensure_stock_exists` returns but *before* `ingest_ticker` mutates it. A fresh row will have `last_fetched_at=None`; an existing row will have a timestamp. This is the same check `ingest_ticker` uses internally (via `is_new = stock.last_fetched_at is None`) — we rely on it as the cheap de-dup signal to avoid re-fetching 10 years of price data every time a user logs a second transaction.

Response schema is unchanged (`TransactionResponse`). The latency contract changes for new tickers only: from ~200ms to ~5-15s. This is called out in the rollout section.

#### Frontend changes

1. `frontend/src/components/log-transaction-dialog.tsx:42-53` — `handleSubmit` currently closes the dialog unconditionally. Change to:

```tsx
async function handleSubmit(e: React.FormEvent) {
  e.preventDefault();
  try {
    await onSubmit(form);       // hook returns the mutation result promise
    setOpen(false);
    setForm(initialForm());
  } catch {
    // error toast is surfaced by the mutation hook — keep dialog open
  }
}
```

`onSubmit` typing moves from `(data: TransactionCreate) => void` to `(data: TransactionCreate) => Promise<unknown>`. Add a disabled+spinner overlay on the dialog content while `isLoading` is true. Overlay copy: *"Ingesting {ticker}…"* with a small sub-line *"Fetching 10 years of history, computing signals"*.

2. `frontend/src/app/(authenticated)/portfolio/portfolio-client.tsx:62-75` — `useLogTransaction` currently invalidates `["portfolio"]` only. Extend it to invalidate the full query set for the ticker on success, and convert the exposed mutate to `mutateAsync` so the dialog can `await` it.

```ts
export function useLogTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: TransactionCreate) =>
      post<TransactionResponse>("/portfolio/transactions", data),
    onSuccess: (_data, variables) => {
      const T = variables.ticker.toUpperCase();
      queryClient.invalidateQueries({ queryKey: ["portfolio"] });
      queryClient.invalidateQueries({ queryKey: ["signals", T] });
      queryClient.invalidateQueries({ queryKey: ["prices", T] });
      queryClient.invalidateQueries({ queryKey: ["fundamentals", T] });
      queryClient.invalidateQueries({ queryKey: ["bulk-signals-by-ticker"] });
      queryClient.invalidateQueries({ queryKey: ["stock-intelligence", T] });
      queryClient.invalidateQueries({ queryKey: ["forecast", T] });
      toast.success(`${variables.transaction_type} ${T} recorded`);
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "Failed to log trade");
    },
  });
}
```

3. Optional but recommended: replace the free-text ticker `Input` in `LogTransactionDialog` with `TickerSearch`. This kills typo-driven ingest failures. Gated behind a follow-up JIRA; do not block C2 on it.

### C3. Chat `analyze_stock` canonical ingest

#### Current state

`backend/tools/analyze_stock.py:40-100` — lightweight path. Signals computed inline, never stored.

#### New implementation

Replace the `_run` body with a direct `ingest_ticker` call.

```python
async def _run(self, params: dict[str, Any]) -> ToolResult:
    """Run the canonical ingest pipeline for a single ticker."""
    import re

    ticker = str(params.get("ticker", "")).upper().strip()
    if not ticker or not re.match(r"^[A-Z]{1,5}$", ticker):
        return ToolResult(
            status="error",
            error="Invalid ticker format. Use 1-5 letters (e.g., AAPL).",
        )

    from backend.database import async_session_factory
    from backend.services.exceptions import IngestFailedError
    from backend.services.pipelines import ingest_ticker
    from backend.services.signals import get_latest_signals

    async with async_session_factory() as session:
        try:
            result = await ingest_ticker(ticker, session, user_id=None)
        except IngestFailedError:
            logger.warning("analyze_stock ingest failed for %s", ticker, exc_info=True)
            return ToolResult(
                status="error",
                error=f"No data available for {ticker}. Verify the ticker is correct.",
            )

        # Reload the persisted snapshot so the tool response mirrors what the
        # stock detail page will serve on the very next click
        snapshot = await get_latest_signals(ticker, session)
        if snapshot is None:
            return ToolResult(
                status="error",
                error=f"Could not compute signals for {ticker}.",
            )

        return ToolResult(
            status="ok",
            data={
                "ticker": ticker,
                "composite_score": result["composite_score"],
                "rsi_value": snapshot.rsi_value,
                "rsi_signal": snapshot.rsi_signal,
                "macd_value": snapshot.macd_value,
                "macd_signal": snapshot.macd_signal_label,
                "sma_signal": snapshot.sma_signal,
                "bb_position": snapshot.bb_position,
                "annual_return": snapshot.annual_return,
                "volatility": snapshot.volatility,
                "sharpe_ratio": snapshot.sharpe_ratio,
                "is_new": result["is_new"],
            },
        )
```

`timeout_seconds` on the tool is bumped from `15.0` to `45.0` to accommodate a cold-cache full ingest (10 years of price history + fundamentals). Cold paths are rare (new tickers only); warm paths are sub-second.

#### Frontend cache invalidation

The chat tool now persists data that other tabs display. The streaming chat loop in `frontend/src/hooks/use-stream-chat.ts` needs to invalidate query keys when an `analyze_stock` tool-complete event arrives:

```ts
// inside the NDJSON event handler, on tool_complete
if (event.tool_name === "analyze_stock" && event.status === "ok") {
  const ticker = (event.data as { ticker?: string })?.ticker?.toUpperCase();
  if (ticker) {
    queryClient.invalidateQueries({ queryKey: ["signals", ticker] });
    queryClient.invalidateQueries({ queryKey: ["prices", ticker] });
    queryClient.invalidateQueries({ queryKey: ["fundamentals", ticker] });
    queryClient.invalidateQueries({ queryKey: ["bulk-signals-by-ticker"] });
    queryClient.invalidateQueries({ queryKey: ["watchlist"] });
  }
}
```

`queryClient` is already available in the hook via `useQueryClient()`; if not, inject it there.

`frontend/src/components/chat/tool-card.tsx` gains an `analyze_stock`-specific running-state label: *"Fetching 10y history, computing signals…"* while the tool is pending. Plain text swap; no structural change.

### C4. Stock detail auto-refresh on stale

#### Current state

`backend/routers/stocks/data.py:176-179` — computes `is_stale`, returns it, does nothing else. `frontend/src/hooks/use-stocks.ts:190-196` — `useSignals` has no `refetchInterval`.

#### New backend implementation

Inside `get_signals`, after computing `is_stale`, fire-and-forget a Celery refresh with a Redis-backed 5-minute debounce. Also expose two new response fields so the frontend can render the refresh state.

```python
import redis.asyncio as redis_async
from backend.config import settings
from backend.tasks.market_data import refresh_ticker_task

DEBOUNCE_TTL_SECONDS = 300
DEBOUNCE_KEY_PREFIX = "refresh:debounce:"

async def _try_dispatch_refresh(ticker: str) -> tuple[bool, datetime | None]:
    """SETNX-based debounce. Returns (dispatched, last_attempt_at)."""
    key = f"{DEBOUNCE_KEY_PREFIX}{ticker.upper()}"
    try:
        client = redis_async.from_url(settings.REDIS_URL)
        now_iso = datetime.now(timezone.utc).isoformat()
        acquired = await client.set(key, now_iso, ex=DEBOUNCE_TTL_SECONDS, nx=True)
        if acquired:
            refresh_ticker_task.delay(ticker.upper())
            logger.info("Dispatched stale refresh for %s", ticker)
            return True, datetime.now(timezone.utc)
        # Not acquired — read the existing value for last_attempt
        existing = await client.get(key)
        if existing:
            try:
                return False, datetime.fromisoformat(existing.decode("utf-8"))
            except Exception:
                return False, None
        return False, None
    except Exception:
        logger.warning("Redis debounce unavailable for %s", ticker, exc_info=True)
        return False, None
```

Wire into `get_signals` right after the existing `is_stale` block:

```python
is_refreshing = False
last_refresh_attempt: datetime | None = None
if is_stale:
    is_refreshing, last_refresh_attempt = await _try_dispatch_refresh(ticker)
```

Add both fields to `SignalResponse` (Pydantic schema in `backend/schemas/stock.py`):

```python
class SignalResponse(BaseModel):
    ...
    is_stale: bool
    is_refreshing: bool = False
    last_refresh_attempt: datetime | None = None
```

Cache key bust: since cached responses now carry mutable refresh state, lower the `STANDARD` TTL is overkill. Instead, do not cache the response when `is_stale=True` — the branch above unconditionally goes to Redis for debounce, and a re-entry 2 seconds later should not see a stale cached response missing the `is_refreshing` flag. Implementation: wrap the existing `cache.set` in `if not is_stale:`.

#### Frontend changes

1. `frontend/src/types/api.ts:104-114` — extend `SignalResponse`:

```ts
export interface SignalResponse {
  ticker: string;
  computed_at: string | null;
  rsi: RSISignal;
  macd: MACDSignal;
  sma: SMASignal;
  bollinger: BollingerSignal;
  returns: ReturnsMetrics;
  composite_score: number | null;
  is_stale: boolean;
  is_refreshing: boolean;
  last_refresh_attempt: string | null;
}
```

2. `frontend/src/hooks/use-stocks.ts:190-196` — add conditional `refetchInterval`:

```ts
export function useSignals(ticker: string) {
  return useQuery({
    queryKey: ["signals", ticker],
    queryFn: () => get<SignalResponse>(`/stocks/${ticker}/signals`),
    staleTime: 5 * 60 * 1000,
    refetchInterval: (q) =>
      q.state.data?.is_refreshing ? 5000 : false,
  });
}
```

TanStack Query v5 `refetchInterval` accepts a function receiving the query object; poll every 5s while a refresh is in flight, stop once the server returns `is_refreshing=false`.

3. `frontend/src/components/stock-header.tsx` — render a small badge next to the ticker when `is_stale && is_refreshing` ("Refreshing data…") and a different badge when `is_stale && !is_refreshing` ("Data may be outdated" with a manual Refresh button wired to the existing `useIngestTicker` mutation).

### C5. Bulk portfolio CSV upload

#### Current state

No bulk endpoint. `frontend/src/lib/api.ts` has no multipart helper. `frontend/src/lib/csv-export.ts` exists for export only.

#### New endpoint design

```
POST /api/v1/portfolio/transactions/bulk
  Content-Type: multipart/form-data
  field: file (text/csv)

200 OK  BulkTransactionResponse
4xx     HTTPException with safe detail
```

CSV format (strict — header must match exactly):

```
ticker,transaction_type,shares,price_per_share,transacted_at,notes
AAPL,BUY,10,182.50,2025-11-15,Q3 dip
MSFT,BUY,5,420.00,2025-12-01,
GOOGL,SELL,3,195.10,2026-01-20,Tax harvest
```

Rules:
- Max 500 rows per upload.
- Max file size 256 KB (enforced before parse).
- `transacted_at` accepts `YYYY-MM-DD` or ISO8601.
- `notes` optional.
- Dry-run mode if `?validate_only=true` query param — returns the same response shape with `inserted=0` and `errors` populated but no DB writes.

Schemas in `backend/schemas/portfolio.py`:

```python
class BulkTransactionError(BaseModel):
    row: int  # 1-based, header is row 0
    ticker: str | None
    message: str

class BulkTransactionResponse(BaseModel):
    inserted: int
    failed: int
    errors: list[BulkTransactionError]
    success_tickers: list[str]
    ingested_tickers: list[str]  # subset that went through ingest_ticker
```

Router endpoint (new file stub inside existing `backend/routers/portfolio.py` or a submodule if the router has grown past ~500 lines):

```python
from fastapi import File, UploadFile

@router.post(
    "/transactions/bulk",
    response_model=BulkTransactionResponse,
    status_code=status.HTTP_200_OK,
    summary="Bulk import transactions from CSV",
)
async def bulk_create_transactions_endpoint(
    request: Request,
    file: UploadFile = File(...),
    validate_only: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> BulkTransactionResponse:
    require_verified_email(current_user)
    if file.content_type not in ("text/csv", "application/vnd.ms-excel", "application/octet-stream"):
        raise HTTPException(415, "Upload must be a CSV file")
    raw = await file.read()
    if len(raw) > 256 * 1024:
        raise HTTPException(413, "CSV file exceeds 256 KB limit")

    from backend.services.portfolio.bulk_import import (
        parse_csv_to_transactions,
        bulk_create_transactions,
    )
    parsed, parse_errors = parse_csv_to_transactions(raw)
    if not parsed and parse_errors:
        return BulkTransactionResponse(
            inserted=0, failed=len(parse_errors), errors=parse_errors,
            success_tickers=[], ingested_tickers=[],
        )

    result = await bulk_create_transactions(
        user_id=current_user.id,
        transactions=parsed,
        db=db,
        validate_only=validate_only,
    )
    # Prepend any parse-time errors to the service-level errors
    result.errors = parse_errors + result.errors
    result.failed += len(parse_errors)
    return result
```

#### Service layer

New file `backend/services/portfolio/bulk_import.py` (or `backend/services/bulk_transactions.py` if the portfolio service is still a flat module). Keep it under 400 lines.

Key functions:

```python
import asyncio
import csv
import io
from decimal import Decimal, InvalidOperation

MAX_CONCURRENT_INGESTS = 5

def parse_csv_to_transactions(
    file_bytes: bytes,
) -> tuple[list[TransactionCreate], list[BulkTransactionError]]:
    """Parse a CSV byte stream. Returns (valid rows, error rows)."""
    errors: list[BulkTransactionError] = []
    parsed: list[TransactionCreate] = []
    reader = csv.DictReader(io.StringIO(file_bytes.decode("utf-8-sig")))
    expected = {"ticker", "transaction_type", "shares", "price_per_share", "transacted_at"}
    if reader.fieldnames is None or not expected.issubset(set(reader.fieldnames)):
        errors.append(BulkTransactionError(
            row=0, ticker=None,
            message=f"CSV header must include {sorted(expected)}",
        ))
        return [], errors
    for i, row in enumerate(reader, start=1):
        if i > 500:
            errors.append(BulkTransactionError(
                row=i, ticker=None, message="Row limit exceeded (500 max)",
            ))
            break
        try:
            parsed.append(TransactionCreate(
                ticker=row["ticker"].strip().upper(),
                transaction_type=row["transaction_type"].strip().upper(),
                shares=Decimal(row["shares"]),
                price_per_share=Decimal(row["price_per_share"]),
                transacted_at=_parse_date(row["transacted_at"]),
                notes=(row.get("notes") or "").strip() or None,
            ))
        except (KeyError, ValueError, InvalidOperation) as exc:
            errors.append(BulkTransactionError(
                row=i, ticker=row.get("ticker"), message=f"Invalid row: {exc}",
            ))
    return parsed, errors


async def bulk_create_transactions(
    user_id: uuid.UUID,
    transactions: list[TransactionCreate],
    db: AsyncSession,
    *,
    validate_only: bool = False,
) -> BulkTransactionResponse:
    """Ingest unique new tickers in parallel, insert all transactions in one commit,
    then recompute every affected position."""
    errors: list[BulkTransactionError] = []
    tickers = {t.ticker for t in transactions}

    # Classify new vs existing
    existing_rows = await db.execute(
        select(Stock.ticker, Stock.last_fetched_at).where(Stock.ticker.in_(tickers))
    )
    known = {row.ticker: row.last_fetched_at for row in existing_rows.all()}
    needs_ingest = [t for t in tickers if known.get(t) is None]

    # Parallel ingest with a semaphore
    sem = asyncio.Semaphore(MAX_CONCURRENT_INGESTS)
    ingested_tickers: list[str] = []

    async def _ingest_one(ticker: str) -> None:
        async with sem:
            # Each ingest gets its own session — shared AsyncSession is not concurrent-safe
            from backend.database import async_session_factory
            async with async_session_factory() as inner_session:
                try:
                    await ingest_ticker(ticker, inner_session, user_id=str(user_id))
                    ingested_tickers.append(ticker)
                except IngestFailedError as exc:
                    for idx, t in enumerate(transactions, start=1):
                        if t.ticker == ticker:
                            errors.append(BulkTransactionError(
                                row=idx, ticker=ticker,
                                message="Ticker not recognized by data provider",
                            ))
                            break

    if needs_ingest:
        await asyncio.gather(*(_ingest_one(t) for t in needs_ingest))

    # Drop transactions whose ticker failed ingest
    failed_tickers = {e.ticker for e in errors if e.ticker}
    survivors = [t for t in transactions if t.ticker not in failed_tickers]

    if validate_only:
        return BulkTransactionResponse(
            inserted=0, failed=len(errors), errors=errors,
            success_tickers=[], ingested_tickers=ingested_tickers,
        )

    # Insert + recompute positions
    from backend.models.portfolio import Transaction
    portfolio = await get_or_create_portfolio(user_id, db)
    txn_rows = [
        Transaction(
            portfolio_id=portfolio.id,
            ticker=t.ticker,
            transaction_type=t.transaction_type,
            shares=t.shares,
            price_per_share=t.price_per_share,
            transacted_at=t.transacted_at,
            notes=t.notes,
        )
        for t in survivors
    ]
    db.add_all(txn_rows)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        logger.exception("Bulk transaction insert failed")
        raise HTTPException(422, "Bulk insert failed integrity check") from exc

    affected_tickers = {t.ticker for t in survivors}
    for t in affected_tickers:
        await recompute_position(portfolio.id, t, db)
    await db.commit()

    return BulkTransactionResponse(
        inserted=len(txn_rows),
        failed=len(errors),
        errors=errors,
        success_tickers=sorted(affected_tickers),
        ingested_tickers=ingested_tickers,
    )
```

Concurrency note: each `ingest_ticker` gets its own `AsyncSession` via `async_session_factory()` because SQLAlchemy AsyncSession is not concurrent-safe across `asyncio.gather`. The outer `db` session is reused only for the single bulk insert and position recomputation.

SELL pre-validation: for v1 we skip the per-row SELL guard that `create_transaction` does. Document that bulk import is primarily for historical BUY lots; a SELL that exceeds holdings will surface as an IntegrityError on the position recompute and roll back the whole batch. A future refinement (post-C5) is per-row SELL validation with a FIFO dry-run.

#### Frontend changes

1. `frontend/src/lib/api.ts` — add a multipart helper that bypasses the `Content-Type: application/json` default:

```ts
export async function postMultipart<T>(
  path: string,
  formData: FormData,
): Promise<T> {
  const url = `${API_BASE}${path}`;
  let res = await fetch(url, {
    method: "POST",
    credentials: "include",
    body: formData, // browser sets boundary automatically
  });
  if (res.status === 401) {
    const refreshed = await refreshToken();
    if (refreshed) {
      res = await fetch(url, {
        method: "POST",
        credentials: "include",
        body: formData,
      });
    }
  }
  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`;
    try {
      const body: ApiError = await res.json();
      detail = body.detail || detail;
    } catch { /* non-JSON */ }
    throw new ApiRequestError(res.status, detail);
  }
  return res.json() as Promise<T>;
}
```

2. New file `frontend/src/hooks/use-bulk-transactions.ts`:

```ts
export function useBulkUploadTransactions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return postMultipart<BulkTransactionResponse>(
        "/portfolio/transactions/bulk",
        fd,
      );
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["portfolio"] });
      for (const T of data.success_tickers) {
        queryClient.invalidateQueries({ queryKey: ["signals", T] });
        queryClient.invalidateQueries({ queryKey: ["prices", T] });
        queryClient.invalidateQueries({ queryKey: ["fundamentals", T] });
      }
      queryClient.invalidateQueries({ queryKey: ["bulk-signals-by-ticker"] });
      toast.success(`${data.inserted} transactions imported`);
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "Upload failed");
    },
  });
}
```

3. New file `frontend/src/components/bulk-transaction-upload.tsx` — drag-and-drop zone, inline CSV preview table, per-row validation errors surfaced from the response, submit button, link to download `/portfolio-template.csv`. Uses the hook above. Implementation hits the `validate_only` endpoint first for the preview, then submits for real on confirm.

4. `frontend/src/app/(authenticated)/portfolio/portfolio-client.tsx:362-373` — add an "Upload CSV" button next to the existing `<LogTransactionDialog>` inside the same flex container. Opens the new bulk upload dialog.

5. New static file `frontend/public/portfolio-template.csv`:

```csv
ticker,transaction_type,shares,price_per_share,transacted_at,notes
AAPL,BUY,10,182.50,2025-11-15,Example buy
```

6. New types in `frontend/src/types/api.ts`:

```ts
export interface BulkTransactionError {
  row: number;
  ticker: string | null;
  message: string;
}

export interface BulkTransactionResponse {
  inserted: number;
  failed: number;
  errors: BulkTransactionError[];
  success_tickers: string[];
  ingested_tickers: string[];
}
```

### C6. Search "Add" flow simplification

Post-C1 state: `frontend/src/components/ticker-search.tsx` is unchanged in this spec. The change is that its single `onSelect(ticker)` callback no longer needs to be double-wrapped in the caller. Verification steps:

1. Search → select a dbResult → `handleAddTicker` → `addToWatchlist.mutate` → backend ingest (no-op fast path for known tickers) → 201 Created → watchlist updated.
2. Search → select an externalResult (`in_db: false`) → same path → backend ingest does real work → 201 Created.
3. The explicit "Run Analysis" button on `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx` still uses `useIngestTicker()` — this is the **one** legitimate caller left and covers the "I want to force a fresh fetch right now" case that C4's debounced background refresh intentionally rate-limits.

Acceptance check for C6: delete `useIngestTicker` import from `layout.tsx`, run the frontend unit tests and manual smoke on topbar search, stock detail "Run Analysis", and direct `/stocks/{unknown-ticker}` deep link → confirms the ingest endpoint is still reachable.

---

## Files Created

Backend:
- `backend/services/portfolio/bulk_import.py` (new, or `backend/services/bulk_transactions.py` if portfolio service is still flat — pick whichever matches the current layout)

Frontend:
- `frontend/src/components/bulk-transaction-upload.tsx`
- `frontend/src/hooks/use-bulk-transactions.ts`
- `frontend/public/portfolio-template.csv`

Tests:
- `tests/unit/services/test_watchlist_ingest.py`
- `tests/unit/services/test_bulk_import.py`
- `tests/api/test_bulk_transactions.py`
- `tests/api/test_watchlist_auto_ingest.py`
- `tests/api/test_signals_auto_refresh.py`
- `frontend/src/__tests__/hooks/use-add-to-watchlist.test.tsx`
- `frontend/src/__tests__/components/bulk-transaction-upload.test.tsx`

## Files Modified

Backend:
- `backend/services/watchlist.py` — `add_to_watchlist` calls `ingest_ticker`
- `backend/routers/stocks/watchlist.py` — add `IngestFailedError` handler
- `backend/routers/portfolio.py` — `create_transaction` sync-ingests new tickers; adds bulk endpoint
- `backend/tools/analyze_stock.py` — replace lightweight path with `ingest_ticker`; bump `timeout_seconds` to 45.0
- `backend/routers/stocks/data.py` — `get_signals` debounced refresh dispatch, new response fields, skip cache on `is_stale`
- `backend/schemas/stock.py` — `SignalResponse` gains `is_refreshing`, `last_refresh_attempt`; `WatchlistItemResponse` gains optional `ingestion_status`
- `backend/schemas/portfolio.py` — add `BulkTransactionError`, `BulkTransactionResponse`
- `backend/services/exceptions.py` — no changes expected; `IngestFailedError` already exists

Frontend:
- `frontend/src/app/(authenticated)/layout.tsx:24-41` — drop two-phase hack
- `frontend/src/hooks/use-stocks.ts:57-70` — `useAddToWatchlist` full invalidation + 404 handling
- `frontend/src/hooks/use-stocks.ts:190-196` — `useSignals` conditional `refetchInterval`
- `frontend/src/hooks/use-portfolio.ts` (or wherever `useLogTransaction` lives) — switch to `mutateAsync`, full invalidation
- `frontend/src/components/log-transaction-dialog.tsx` — async submit, no auto-close, loading overlay
- `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx:88-94` — simplify `handleToggleWatchlist`
- `frontend/src/app/(authenticated)/portfolio/portfolio-client.tsx:62-75, 362-373` — invalidation + "Upload CSV" button
- `frontend/src/components/stock-header.tsx` — render refresh badges
- `frontend/src/components/chat/tool-card.tsx` — `analyze_stock` running label
- `frontend/src/hooks/use-stream-chat.ts` — invalidate on `analyze_stock` tool_complete
- `frontend/src/lib/api.ts` — add `postMultipart` helper
- `frontend/src/types/api.ts` — `SignalResponse`, `WatchlistItem`, `BulkTransactionRequest`, `BulkTransactionResponse`, `BulkTransactionError`

---

## API Contract Changes

| Endpoint | Change | Schema impact |
|---|---|---|
| `POST /api/v1/stocks/watchlist` | Now auto-ingests on add. 404 still fires for tickers the data provider doesn't recognize. Latency: 200ms → 5-15s for new tickers. | `WatchlistItem` adds optional `ingestion_status: "completed"` |
| `POST /api/v1/portfolio/transactions` | Sync-ingests new tickers (detected via `stock.last_fetched_at is None`). Latency: 200ms → 5-15s for new tickers. | None (response shape unchanged) |
| `POST /api/v1/portfolio/transactions/bulk` | **NEW** multipart CSV endpoint. Max 500 rows, 256 KB. `?validate_only=true` for dry run. | New: `BulkTransactionResponse`, `BulkTransactionError` |
| `GET /api/v1/stocks/{ticker}/signals` | Fires debounced background refresh when `is_stale=True`. Response cache bypassed when stale. | `SignalResponse` adds `is_refreshing: bool`, `last_refresh_attempt: datetime \| null` |
| Chat tool `analyze_stock` | Now drives the canonical pipeline — persists signal snapshot. Timeout bumped to 45s. | No schema change; response still returns flat signal dict |

---

## Frontend Impact

### Routes & components modified

- `frontend/src/app/(authenticated)/layout.tsx` (line 24-41)
- `frontend/src/app/(authenticated)/portfolio/portfolio-client.tsx` (line 62-75, 362-373)
- `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx` (line 88-94)
- `frontend/src/components/log-transaction-dialog.tsx` (whole submit handler)
- `frontend/src/components/stock-header.tsx`
- `frontend/src/components/chat/tool-card.tsx`
- `frontend/src/components/ticker-search.tsx` — verified unchanged

### Hooks modified

- `frontend/src/hooks/use-stocks.ts` — `useAddToWatchlist`, `useSignals`
- `frontend/src/hooks/use-portfolio.ts` — `useLogTransaction`
- `frontend/src/hooks/use-stream-chat.ts` — tool-complete invalidation

### Hooks created

- `frontend/src/hooks/use-bulk-transactions.ts`

### Components created

- `frontend/src/components/bulk-transaction-upload.tsx`

### Static assets created

- `frontend/public/portfolio-template.csv`

### TypeScript type changes (`frontend/src/types/api.ts`)

- **Modify** `SignalResponse`: add `is_refreshing: boolean`, `last_refresh_attempt: string | null`
- **Modify** `WatchlistItem`: add optional `ingestion_status?: "completed"`
- **New** `BulkTransactionError`, `BulkTransactionResponse`

---

## Test Impact

### Existing test files affected

Search outputs to audit (run during implementation):
- `tests/unit/services/test_watchlist.py` — `add_to_watchlist` mocks need to mock `ingest_ticker` too
- `tests/api/test_stocks_watchlist.py` — POST /watchlist tests must not rely on pre-existing Stock row; either seed it or assert the ingest happens
- `tests/api/test_portfolio.py` — `create_transaction` tests must mock `ingest_ticker` at the lookup site (`backend.routers.portfolio.ingest_ticker`)
- `tests/unit/tools/test_analyze_stock.py` — replace inline `ensure_stock_exists` + `fetch_prices_delta` mocks with an `ingest_ticker` mock
- `tests/api/test_stocks_data.py` (or wherever `get_signals` is covered) — add `is_refreshing`, `last_refresh_attempt` to assertions; patch Redis client
- `frontend/src/__tests__/hooks/use-stocks.test.tsx` — MSW handlers for watchlist POST, extra invalidation assertions
- `frontend/src/__tests__/components/log-transaction-dialog.test.tsx` — async submit flow

Follow `global/debugging/mock-patching-gotchas`: patch `ingest_ticker` at the lookup site (inside the module that imports it), not at `backend.services.pipelines.ingest_ticker`.

### New test files and specific cases

**`tests/unit/services/test_watchlist_ingest.py`**
1. `add_to_watchlist_calls_ingest_for_new_ticker` — mock `ingest_ticker` returns fake result; assert called once with `(ticker, db, user_id=str(uuid))`; assert Watchlist row inserted.
2. `add_to_watchlist_surfaces_ingest_failure_as_not_found` — mock raises `IngestFailedError`; assert `StockNotFoundError` raised, no Watchlist row written.
3. `add_to_watchlist_duplicate_skips_ingest` — seed existing Watchlist row; assert `ingest_ticker` NOT called and `DuplicateWatchlistError` raised.
4. `add_to_watchlist_size_limit_skips_ingest` — seed 100 entries; assert `ValueError` raised before ingest.

**`tests/api/test_watchlist_auto_ingest.py`**
5. `post_watchlist_with_unknown_ticker_succeeds_after_ingest` — mock `ingest_ticker` success; assert 201 response with `ingestion_status: "completed"`.
6. `post_watchlist_with_invalid_ticker_returns_404` — mock `ingest_ticker` raises `IngestFailedError`; assert 404.

**`tests/api/test_portfolio.py` (extend)**
7. `create_transaction_new_ticker_triggers_full_ingest` — assert `ingest_ticker` called once when `stock.last_fetched_at is None`.
8. `create_transaction_existing_ticker_skips_ingest` — assert `ingest_ticker` NOT called when `last_fetched_at` is set.
9. `create_transaction_ingest_failure_returns_422` — mock raises `IngestFailedError`; assert 422, no transaction row.

**`tests/unit/tools/test_analyze_stock.py` (rewrite)**
10. `analyze_stock_calls_ingest_ticker` — assert call arguments and return shape.
11. `analyze_stock_reloads_snapshot_after_ingest` — verify tool response pulls from persisted snapshot, not in-memory compute.
12. `analyze_stock_surfaces_ingest_failure` — assert `status="error"` and generic message (no `str(e)` leak — Hard Rule #10).

**`tests/api/test_signals_auto_refresh.py`**
13. `get_signals_stale_dispatches_refresh_task` — freezegun 48 hours after `computed_at`; mock Redis `set` with `nx=True` returning True; assert `refresh_ticker_task.delay` called once, `is_refreshing=True` in response.
14. `get_signals_stale_within_debounce_does_not_redispatch` — mock Redis `set` returning False; assert `refresh_ticker_task.delay` NOT called, `is_refreshing=False`, `last_refresh_attempt` populated.
15. `get_signals_not_stale_does_not_dispatch` — assert Redis not touched, response `is_refreshing=False`.
16. `get_signals_redis_unavailable_still_returns_data` — mock Redis raises ConnectionError; assert 200 response with `is_refreshing=False`, logged warning.

**`tests/unit/services/test_bulk_import.py`**
17. `parse_csv_valid_rows_returns_transactions` — happy path, 3 rows.
18. `parse_csv_missing_header_returns_error_row_zero`.
19. `parse_csv_bad_decimal_reports_row_number`.
20. `parse_csv_row_limit_exceeded_returns_error`.
21. `bulk_create_ingests_unique_new_tickers_in_parallel` — mock `ingest_ticker` to track concurrent calls; assert `MAX_CONCURRENT_INGESTS=5` semaphore honored.
22. `bulk_create_skips_ingest_for_existing_stocks` — seed 2 existing stocks, 3 new; assert `ingest_ticker` called exactly 3 times.
23. `bulk_create_ingest_failure_drops_ticker_rows` — one ticker fails ingest; assert its rows are in `errors`, survivors are inserted.
24. `bulk_create_validate_only_writes_nothing` — assert no transaction rows committed.

**`tests/api/test_bulk_transactions.py`**
25. `post_bulk_requires_auth` — 401 when unauthenticated.
26. `post_bulk_requires_verified_email` — 403 when unverified.
27. `post_bulk_happy_path_returns_counts`.
28. `post_bulk_wrong_content_type_returns_415`.
29. `post_bulk_oversized_file_returns_413`.
30. `post_bulk_validate_only_returns_dry_run`.

### Frontend test cases

**`frontend/src/__tests__/hooks/use-add-to-watchlist.test.tsx`**
31. `invalidates_expected_query_keys_on_success`.
32. `surfaces_404_as_friendly_message`.

**`frontend/src/__tests__/components/bulk-transaction-upload.test.tsx`**
33. `rejects_non_csv_file`.
34. `posts_validate_only_for_preview`.
35. `renders_per_row_errors_from_response`.

Target: ~35 new or modified test cases. Existing baseline (~1906 backend unit + ~439 frontend) moves up accordingly.

---

## Migration / Rollout

1. **Feature flag.** `WATCHLIST_AUTO_INGEST` (default `True`) in `backend/config.py`. If `False`, `add_to_watchlist` falls back to the current "must already exist" behavior. Gives us a one-env-var rollback for C1 without a redeploy.
2. **No DB migration.** Every field added (`is_refreshing`, `last_refresh_attempt`, bulk schemas) is response-only. No Alembic changes.
3. **Deployment order.** Backend first (adds new fields with safe defaults), frontend second (reads the new fields). Any temporary drift between the two produces `undefined` values that the frontend already null-guards.
4. **C5 is strictly additive.** A new endpoint, a new component, a new hook. Zero impact on existing flows if disabled via a `BULK_UPLOAD_ENABLED` flag (optional — the endpoint simply isn't referenced from any UI until the button is wired).
5. **Post-deploy smoke.**
   - `curl -X POST /api/v1/stocks/watchlist -d '{"ticker":"NVDA"}'` for a user that's never seen NVDA → expect 201 in 5-10s, stock detail page loaded on next navigation.
   - Log a `BUY` on a ticker not in the DB → expect 201 in 5-15s, stock detail page has signals and a forecast dispatched.
   - Call `GET /stocks/AAPL/signals` with a snapshot older than 24h → expect `is_refreshing=True` on first call, `False` on second within 5 minutes.
   - Bulk upload a 5-row CSV with 4 valid + 1 invalid → expect 200 response, `inserted=4, failed=1`.

---

## Risk + Rollback

| Risk | Mitigation | Rollback |
|---|---|---|
| **C1 latency regression** — watchlist add now blocks on ingest (5-15s for new tickers). | Loading toast in UI. New tickers are rare (most users add established names already in DB; fast path is <500ms). | Flip `WATCHLIST_AUTO_INGEST=False`. |
| **C1 transactional integrity** — ingest performs internal commits; a failed Watchlist insert after a successful ingest leaves Stock + prices persisted. | Acceptable: data is reusable, not user-scoped, not harmful. Retry succeeds fast. | No rollback needed. |
| **C2 portfolio transaction latency** — 5-15s for new tickers. | Dialog stays open with spinner so user knows it's working. Return 422 on ingest failure mirrors existing error path. | Revert `backend/routers/portfolio.py:create_transaction` block. |
| **C3 chat tool latency** — `analyze_stock` now 5-15s on cold paths. | Bumped `timeout_seconds=45`. Tool frame in chat shows progress label. | Revert `tools/analyze_stock.py`. |
| **C4 Redis pressure** — debounce keys add ~1 SETNX per stale stock page view. At 300s TTL per ticker and <5k unique tickers, max ~5k keys ≤ 500 KB. | Negligible. Keys auto-expire. | Revert `data.py` dispatch block. |
| **C5 parallel ingest fanout** — a 50-ticker CSV triggers 50 parallel yfinance calls capped at 5 concurrent. | Semaphore limits fanout; each yfinance call is already rate-limited by the existing stock_data layer. | Revert endpoint; C5 is additive. |
| **Mocked test drift** — existing tests patching `ensure_stock_exists` directly break when the service now calls `ingest_ticker`. | Audit via the grep enumeration above; update mocks to patch at the lookup site per `global/debugging/mock-patching-gotchas`. | N/A — fix tests as the code changes. |
| **Hard Rule #10 (no `str(e)`)** violations in new error paths | Spec deliberately uses fixed messages ("Ticker not recognized by data provider") and logs exceptions with `logger.exception`. | N/A — caught in expert review. |

---

## Open Questions

1. **Acceptable sync latency on C1/C2?** The alternative is a two-phase ingest: return 202 immediately, poll for completion. My recommendation: ship the synchronous version behind a toast/overlay. If user feedback flags it as painful, Spec G will layer in a task-ID streaming approach.
2. **Strict or flexible CSV format?** My recommendation: strict — header must match exactly, errors cite row numbers. A flexible parser hides bugs. Provide `portfolio-template.csv` as the canonical starting point.
3. **Should C4 also expose a "force refresh" mutation?** The explicit `POST /stocks/{ticker}/ingest` already does this. No new endpoint needed — reuse it from the stock-header "Refresh" button.
4. **Should the bulk endpoint accept JSON as well as CSV?** Out of scope for C5. JSON would need a different schema and different error shape. Revisit if a client needs it.

---

## Dependencies

- **Blocks:** Spec G (frontend progress UI) needs these hooks and components before it can layer in polish.
- **Depends on:** Spec A (`PipelineRunner` run-tracking contract — all calls to `ingest_ticker` need to carry a run_id for observability; the current `ingest_ticker` signature does not take one, so Spec A adds it and Spec C threads it through).
- **Depends on:** Spec B (`ingest_ticker` must cover news persistence and convergence dispatch for new tickers, otherwise C1/C2 still leave surfaces empty).
- Coordinates with Spec D (admin observability dashboard reads `PipelineRun` rows from the new contract — C's five new call sites become five new rows per request).
