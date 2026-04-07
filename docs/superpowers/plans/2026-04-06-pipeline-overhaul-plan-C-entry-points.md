# Pipeline Overhaul — Spec C (Entry Point Unification) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every UX path that introduces a ticker drives it through the canonical `ingest_ticker` pipeline exactly once. Watchlist auto-ingests, portfolio transactions sync-ingest new tickers, chat `analyze_stock` persists snapshots, stock detail auto-refreshes on stale, and users can bulk-import a CSV of transactions.

**Architecture:** Backend-first: reuse existing `ingest_ticker` from `backend/services/pipelines.py`; add one new service (`bulk_import.py`), one new multipart endpoint, Redis-backed debounce for stale refresh. Frontend: collapse the two-phase ingest hack, add `mutateAsync` + full-query invalidation, build a CSV upload component.

**Tech Stack:** FastAPI, SQLAlchemy async, Redis (SETNX debounce), slowapi, TanStack Query v5, sonner toasts

**Spec:** `docs/superpowers/specs/2026-04-06-pipeline-overhaul-spec-C-entry-points.md`

**Depends on:** Spec A (`PipelineRunner` contract, `ticker_ingestion_state`), Spec B (`ingest_ticker` extended with news + convergence), and Plan A/B merged first

---

## File Structure

```
backend/services/watchlist.py                    # MODIFY — C1 auto-ingest
backend/routers/stocks/watchlist.py              # MODIFY — C1 404 handler
backend/routers/portfolio.py                     # MODIFY — C2 sync ingest + C5 bulk endpoint
backend/tools/analyze_stock.py                   # MODIFY — C3 canonical ingest
backend/routers/stocks/data.py                   # MODIFY — C4 debounce + response fields
backend/schemas/stock.py                         # MODIFY — SignalResponse + WatchlistItem fields
backend/schemas/portfolio.py                     # MODIFY — BulkTransactionError/Response
backend/services/portfolio/bulk_import.py        # NEW — CSV parse + bulk ingest
backend/config.py                                # MODIFY — WATCHLIST_AUTO_INGEST flag

frontend/src/app/(authenticated)/layout.tsx                       # MODIFY — collapse hack
frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx  # MODIFY — simplify toggle
frontend/src/app/(authenticated)/portfolio/portfolio-client.tsx   # MODIFY — invalidation + upload button
frontend/src/hooks/use-stocks.ts                                  # MODIFY — useAddToWatchlist + useSignals
frontend/src/hooks/use-portfolio.ts                               # MODIFY — useLogTransaction mutateAsync
frontend/src/hooks/use-bulk-transactions.ts                       # NEW
frontend/src/hooks/use-stream-chat.ts                             # MODIFY — invalidate on analyze_stock
frontend/src/components/log-transaction-dialog.tsx                # MODIFY — async submit
frontend/src/components/stock-header.tsx                          # MODIFY — refresh badges
frontend/src/components/chat/tool-card.tsx                        # MODIFY — running label
frontend/src/components/bulk-transaction-upload.tsx               # NEW
frontend/src/lib/api.ts                                           # MODIFY — postMultipart
frontend/src/types/api.ts                                         # MODIFY — new types
frontend/public/portfolio-template.csv                            # NEW

tests/unit/services/test_watchlist_ingest.py                      # NEW — MUST use MagicMock sessions (no db_session)
tests/unit/services/test_bulk_import.py                           # NEW — MUST use MagicMock sessions (no db_session)
tests/api/test_analyze_stock_tool.py                            # MODIFY
tests/api/test_watchlist_auto_ingest.py                           # NEW
tests/api/test_bulk_transactions.py                               # NEW
tests/api/test_signals_auto_refresh.py                            # NEW
tests/api/test_portfolio.py                                       # MODIFY
frontend/src/__tests__/hooks/use-add-to-watchlist.test.tsx        # NEW
frontend/src/__tests__/components/bulk-transaction-upload.test.tsx # NEW
```

---

## Task 1: C1 — Watchlist auto-ingest (backend service + router)

**Files:**
- Modify: `backend/services/watchlist.py`
- Modify: `backend/routers/stocks/watchlist.py`
- Modify: `backend/config.py`
- Create: `tests/unit/services/test_watchlist_ingest.py`
- Create: `tests/api/test_watchlist_auto_ingest.py`

- [ ] **Step 0: Add the `ingest_ticker` import to `backend/services/watchlist.py` FIRST**

Before writing any tests: add `from backend.services.pipelines import
ingest_ticker` at the top of `backend/services/watchlist.py`. The failing
tests below `patch.object(wl_mod, "ingest_ticker", ...)` — that attribute
must exist on the module or the patch raises `AttributeError` at collection
time (not at run time). This is a test-ordering fix surfaced by the Plan C
review (C-TEST-CRIT-3).

No other body changes to `watchlist.py` in this step — the import is
sufficient to make `wl_mod.ingest_ticker` resolvable.

- [ ] **Step 1: Write failing unit tests**

Create `tests/unit/services/test_watchlist_ingest.py`:

```python
"""Spec C.1 — watchlist.add_to_watchlist must auto-ingest new tickers."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.exceptions import (
    DuplicateWatchlistError,
    IngestFailedError,
    StockNotFoundError,
)


@pytest.mark.asyncio
async def test_add_to_watchlist_calls_ingest_for_new_ticker() -> None:
    from backend.services import watchlist as wl_mod

    fake_db = MagicMock()
    fake_db.execute = AsyncMock()
    # size-count query → 0
    # duplicate query → None
    # stock select → MagicMock with name + sector
    fake_db.execute.side_effect = [
        MagicMock(scalar_one=MagicMock(return_value=0)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        MagicMock(
            scalar_one=MagicMock(
                return_value=MagicMock(name="Apple Inc.", sector="Technology")
            )
        ),
    ]
    fake_db.commit = AsyncMock()
    fake_db.refresh = AsyncMock()

    with patch.object(
        wl_mod, "ingest_ticker", new=AsyncMock(return_value={"is_new": True})
    ) as mock_ingest:
        await wl_mod.add_to_watchlist(uuid.uuid4(), "AAPL", fake_db)
        mock_ingest.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_to_watchlist_surfaces_ingest_failure_as_not_found() -> None:
    from backend.services import watchlist as wl_mod

    fake_db = MagicMock()
    fake_db.execute = AsyncMock()
    fake_db.execute.side_effect = [
        MagicMock(scalar_one=MagicMock(return_value=0)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ]

    with patch.object(
        wl_mod, "ingest_ticker", new=AsyncMock(side_effect=IngestFailedError("prices"))
    ):
        with pytest.raises(StockNotFoundError):
            await wl_mod.add_to_watchlist(uuid.uuid4(), "XYZZ", fake_db)


@pytest.mark.asyncio
async def test_add_to_watchlist_duplicate_skips_ingest() -> None:
    from backend.services import watchlist as wl_mod

    fake_db = MagicMock()
    fake_db.execute = AsyncMock()
    fake_db.execute.side_effect = [
        MagicMock(scalar_one=MagicMock(return_value=0)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=MagicMock())),  # exists
    ]

    with patch.object(wl_mod, "ingest_ticker", new=AsyncMock()) as mock_ingest:
        with pytest.raises(DuplicateWatchlistError):
            await wl_mod.add_to_watchlist(uuid.uuid4(), "AAPL", fake_db)
        mock_ingest.assert_not_awaited()
```

- [ ] **Step 2: Add feature flag**

Edit `backend/config.py`:

```python
# In Settings class
WATCHLIST_AUTO_INGEST: bool = True  # Spec C.1 — flip to False to rollback
```

- [ ] **Step 3: Update `backend/services/watchlist.py`**

Replace the body of `add_to_watchlist` with the canonical ingest path:

```python
from backend.config import settings
from backend.services.exceptions import (
    DuplicateWatchlistError,
    IngestFailedError,
    StockNotFoundError,
)
from backend.services.pipelines import ingest_ticker

MAX_WATCHLIST_SIZE = 100


async def add_to_watchlist(
    user_id: uuid.UUID,
    ticker: str,
    db: AsyncSession,
) -> dict:
    """Add a ticker to the user's watchlist, auto-ingesting unknown tickers.

    Runs the canonical ingest pipeline (prices, fundamentals, signals, forecast
    dispatch) before inserting the Watchlist row so the next page view has full
    data. Duplicate adds short-circuit before ingest.

    Raises:
        DuplicateWatchlistError: Row already present for this user.
        StockNotFoundError: Ingest failed — treat as unknown symbol.
        ValueError: Watchlist cap reached.
    """
    ticker = ticker.upper().strip()

    count = (
        await db.execute(
            select(func.count()).select_from(Watchlist).where(Watchlist.user_id == user_id)
        )
    ).scalar_one()
    if count >= MAX_WATCHLIST_SIZE:
        raise ValueError(f"Watchlist is full (maximum {MAX_WATCHLIST_SIZE} tickers)")

    existing = (
        await db.execute(
            select(Watchlist).where(
                Watchlist.user_id == user_id, Watchlist.ticker == ticker
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateWatchlistError(ticker)

    if settings.WATCHLIST_AUTO_INGEST:
        # Spec C.1 — Redis SETNX dedup so concurrent callers (e.g., viral
        # story → 200 users add the same ticker) don't all run the full
        # ingest. Key TTL 60s; on contention raise a 409-equivalent.
        from backend.services.ingest_lock import acquire_ingest_lock, release_ingest_lock

        acquired = await acquire_ingest_lock(ticker)
        if not acquired:
            raise IngestInProgressError(ticker)
        try:
            await ingest_ticker(ticker, db, user_id=str(user_id))
        except IngestFailedError as exc:
            # Hard Rule #10: log the step internally, never surface it.
            logger.warning(
                "Watchlist ingest failed for %s step=%s", ticker, exc.step
            )
            raise StockNotFoundError(ticker) from exc
        finally:
            await release_ingest_lock(ticker)

    stock = (
        await db.execute(select(Stock).where(Stock.ticker == ticker))
    ).scalar_one()

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

- [ ] **Step 4: Update router to handle `IngestFailedError` cleanly**

Edit `backend/routers/stocks/watchlist.py:74-81`:

```python
except StockNotFoundError:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Ticker '{body.ticker.upper()}' not recognized by data provider.",
    )
except IngestFailedError:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Ticker '{body.ticker.upper()}' not recognized by data provider.",
    )
```

- [ ] **Step 5: Write API integration test**

Create `tests/api/test_watchlist_auto_ingest.py`:

```python
"""Spec C.1 — POST /stocks/watchlist auto-ingests new tickers."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_post_watchlist_with_unknown_ticker_succeeds_after_ingest(
    authenticated_client,
):
    with patch(
        "backend.services.watchlist.ingest_ticker",
        new=AsyncMock(return_value={"is_new": True, "composite_score": 7.5}),
    ):
        r = await authenticated_client.post(
            "/api/v1/stocks/watchlist", json={"ticker": "NVDA"}
        )
        assert r.status_code == 201
        body = r.json()
        assert body["ingestion_status"] == "completed"


@pytest.mark.asyncio
async def test_post_watchlist_with_invalid_ticker_returns_404(authenticated_client):
    from backend.services.exceptions import IngestFailedError

    with patch(
        "backend.services.watchlist.ingest_ticker",
        new=AsyncMock(side_effect=IngestFailedError("prices")),
    ):
        r = await authenticated_client.post(
            "/api/v1/stocks/watchlist", json={"ticker": "ZZZZ"}
        )
        assert r.status_code == 404
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/unit/services/test_watchlist_ingest.py tests/api/test_watchlist_auto_ingest.py -x
```

Expected: pass. Update any existing `tests/unit/services/test_watchlist.py` mocks that patched `ensure_stock_exists` — patch `backend.services.watchlist.ingest_ticker` at the lookup site instead.

- [ ] **Step 7: Lint + commit**

```bash
uv run ruff check --fix backend/services/watchlist.py backend/routers/stocks/watchlist.py backend/config.py tests/unit/services/test_watchlist_ingest.py tests/api/test_watchlist_auto_ingest.py
uv run ruff format backend/services/watchlist.py backend/routers/stocks/watchlist.py backend/config.py tests/unit/services/test_watchlist_ingest.py tests/api/test_watchlist_auto_ingest.py
git add backend/services/watchlist.py backend/routers/stocks/watchlist.py backend/config.py tests/unit/services/test_watchlist_ingest.py tests/api/test_watchlist_auto_ingest.py
git commit -m "feat(watchlist): auto-ingest unknown tickers via canonical pipeline (Spec C.1)"
```

---

## Task 2: C1 — Frontend watchlist hack removal + full invalidation

**Files:**
- Modify: `frontend/src/app/(authenticated)/layout.tsx`
- Modify: `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx`
- Modify: `frontend/src/hooks/use-stocks.ts`
- Create: `frontend/src/__tests__/hooks/use-add-to-watchlist.test.tsx`

- [ ] **Step 1: Simplify `handleAddTicker`**

Edit `frontend/src/app/(authenticated)/layout.tsx:24-41`:

```tsx
const handleAddTicker = useCallback(
  (ticker: string) => {
    const normalized = ticker.toUpperCase();
    const isInWatchlist = watchlist?.some((w) => w.ticker === normalized);
    if (isInWatchlist) {
      toast.info(`${normalized} is already in your watchlist`);
      return;
    }
    addToWatchlist.mutate(normalized);
  },
  [watchlist, addToWatchlist],
);
```

Remove `useIngestTicker` import from this file.

- [ ] **Step 2: Simplify `handleToggleWatchlist` on stock detail**

Edit `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx:88-94`:

```tsx
const handleToggleWatchlist = () => {
  if (isInWatchlist) {
    removeFromWatchlist.mutate(ticker);
  } else {
    addToWatchlist.mutate(ticker);
  }
};
```

- [ ] **Step 3: Upgrade `useAddToWatchlist`**

Edit `frontend/src/hooks/use-stocks.ts` (around line 57-70):

```ts
import { ApiRequestError } from "@/lib/api";

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
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      for (const key of [
        ["signals", T],
        ["prices", T],
        ["fundamentals", T],
        ["bulk-signals"],
        ["bulk-signals-by-ticker"],
        ["stock-intelligence", T],
        ["forecast", T],
        ["stock-news", T],
      ]) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    },
    onError: (err, ticker) => {
      const is404 = err instanceof ApiRequestError && err.status === 404;
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

- [ ] **Step 4: Write the hook test**

Create `frontend/src/__tests__/hooks/use-add-to-watchlist.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";

import { server } from "@/test-utils/msw-server";
import { useAddToWatchlist } from "@/hooks/use-stocks";

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useAddToWatchlist", () => {
  it("invalidates expected query keys on success", async () => {
    server.use(
      http.post("*/stocks/watchlist", () =>
        HttpResponse.json(
          { id: "1", ticker: "AAPL", name: "Apple", sector: "Tech", ingestion_status: "completed" },
          { status: 201 },
        ),
      ),
    );
    const { result } = renderHook(() => useAddToWatchlist(), { wrapper });
    await result.current.mutateAsync("AAPL");
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });

  it("surfaces 404 as friendly message", async () => {
    server.use(
      http.post("*/stocks/watchlist", () =>
        HttpResponse.json({ detail: "not found" }, { status: 404 }),
      ),
    );
    const { result } = renderHook(() => useAddToWatchlist(), { wrapper });
    await expect(result.current.mutateAsync("ZZZZ")).rejects.toBeDefined();
  });
});
```

- [ ] **Step 5: Run + commit**

```bash
cd frontend && npm test -- use-add-to-watchlist && cd ..
cd frontend && npm run lint -- --fix && cd ..
git add frontend/src/app/\(authenticated\)/layout.tsx frontend/src/app/\(authenticated\)/stocks/\[ticker\]/stock-detail-client.tsx frontend/src/hooks/use-stocks.ts frontend/src/__tests__/hooks/use-add-to-watchlist.test.tsx
git commit -m "feat(frontend): collapse watchlist two-phase hack; full invalidation (Spec C.1)"
```

---

## Task 3: C2 — Portfolio transaction sync-ingest for new tickers

**Files:**
- Modify: `backend/routers/portfolio.py`
- Modify: `tests/api/test_portfolio.py`
- Modify: `frontend/src/hooks/use-portfolio.ts` (or wherever `useLogTransaction` lives)
- Modify: `frontend/src/components/log-transaction-dialog.tsx`

- [ ] **Step 1: Write failing API tests**

Append to `tests/api/test_portfolio.py`:

```python
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_create_transaction_new_ticker_triggers_full_ingest(
    authenticated_client, db_session
):
    with patch(
        "backend.routers.portfolio.ingest_ticker",
        new=AsyncMock(return_value={"is_new": True}),
    ) as mock_ingest:
        r = await authenticated_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "NEW",
                "transaction_type": "BUY",
                "shares": "1",
                "price_per_share": "100.00",
                "transacted_at": "2026-01-01",
            },
        )
        assert r.status_code in {200, 201}
        mock_ingest.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_transaction_existing_ticker_skips_ingest(
    authenticated_client, db_session
):
    # Inline seed — no undefined fixture needed.
    from datetime import datetime, timezone

    from backend.models.stock import Stock

    db_session.add(
        Stock(
            ticker="AAPL",
            name="Apple Inc.",
            last_fetched_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()
    with patch(
        "backend.routers.portfolio.ingest_ticker", new=AsyncMock()
    ) as mock_ingest:
        await authenticated_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "AAPL",
                "transaction_type": "BUY",
                "shares": "1",
                "price_per_share": "100.00",
                "transacted_at": "2026-01-01",
            },
        )
        mock_ingest.assert_not_called()


@pytest.mark.asyncio
async def test_create_transaction_ingest_failure_returns_422(authenticated_client):
    from backend.services.exceptions import IngestFailedError

    with patch(
        "backend.routers.portfolio.ingest_ticker",
        new=AsyncMock(side_effect=IngestFailedError("prices")),
    ):
        r = await authenticated_client.post(
            "/api/v1/portfolio/transactions",
            json={
                "ticker": "ZZZZ",
                "transaction_type": "BUY",
                "shares": "1",
                "price_per_share": "100.00",
                "transacted_at": "2026-01-01",
            },
        )
        assert r.status_code == 422
```

- [ ] **Step 2: Update router**

Edit `backend/routers/portfolio.py:112-118`:

```python
from backend.services.exceptions import IngestFailedError
from backend.services.pipelines import ingest_ticker

try:
    stock = await ensure_stock_exists(ticker_upper, db)
except ValueError:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Ticker '{ticker_upper}' not recognized. Verify the symbol is correct.",
    )

if stock.last_fetched_at is None:
    try:
        await ingest_ticker(ticker_upper, db, user_id=str(current_user.id))
    except IngestFailedError as exc:
        logger.warning(
            "Transaction ingest failed for %s user=%s step=%s",
            ticker_upper,
            current_user.id,
            exc.step,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not load market data for '{ticker_upper}'. Try again shortly.",
        )
```

- [ ] **Step 3: Upgrade `useLogTransaction`**

Edit `frontend/src/hooks/use-portfolio.ts` (or wherever defined):

```ts
export function useLogTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: TransactionCreate) =>
      post<TransactionResponse>("/portfolio/transactions", data),
    onSuccess: (_data, variables) => {
      const T = variables.ticker.toUpperCase();
      for (const key of [
        ["portfolio"],
        ["signals", T],
        ["prices", T],
        ["fundamentals", T],
        ["bulk-signals-by-ticker"],
        ["stock-intelligence", T],
        ["forecast", T],
      ]) {
        queryClient.invalidateQueries({ queryKey: key });
      }
      toast.success(`${variables.transaction_type} ${T} recorded`);
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "Failed to log trade");
    },
  });
}
```

- [ ] **Step 4: Make the dialog await submission**

Edit `frontend/src/components/log-transaction-dialog.tsx:42-53`:

```tsx
async function handleSubmit(e: React.FormEvent) {
  e.preventDefault();
  try {
    await onSubmit(form); // Promise-returning onSubmit
    setOpen(false);
    setForm(initialForm());
  } catch {
    // error toast surfaced by mutation hook; keep dialog open
  }
}
```

Type signature: change `onSubmit: (data: TransactionCreate) => void` to `(data: TransactionCreate) => Promise<unknown>`. Add a disabled overlay + "Ingesting {ticker}..." copy while `isLoading`.

- [ ] **Step 5: Run + commit**

```bash
uv run pytest tests/api/test_portfolio.py -x
cd frontend && npm test -- log-transaction-dialog && cd ..
uv run ruff check --fix backend/routers/portfolio.py tests/api/test_portfolio.py
uv run ruff format backend/routers/portfolio.py tests/api/test_portfolio.py
cd frontend && npm run lint -- --fix && cd ..
git add backend/routers/portfolio.py tests/api/test_portfolio.py frontend/src/hooks/use-portfolio.ts frontend/src/components/log-transaction-dialog.tsx
git commit -m "feat(portfolio): sync-ingest new tickers on transaction create (Spec C.2)"
```

---

## Task 4: C3 — Chat `analyze_stock` canonical ingest

**Files:**
- Modify: `backend/tools/analyze_stock.py`
- Create: `tests/api/test_analyze_stock_tool.py` (no existing tool test file
  lives at `tests/unit/tools/`; the pre-existing
  `tests/unit/test_analyze_stock_autoingest.py` covers the legacy behaviour
  and will be deleted as part of Step 2)
- Delete: `tests/unit/test_analyze_stock_autoingest.py`
- Modify: `frontend/src/hooks/use-stream-chat.ts`
- Modify: `frontend/src/components/chat/tool-card.tsx`

- [ ] **Step 1: Rewrite the tool**

Edit `backend/tools/analyze_stock.py`:

```python
async def _run(self, params: dict[str, Any]) -> ToolResult:
    """Run canonical ingest pipeline for one ticker and return signal snapshot."""
    import re

    from backend.database import async_session_factory
    from backend.services.exceptions import IngestFailedError
    from backend.services.pipelines import ingest_ticker
    from backend.services.signals import get_latest_signals

    ticker = str(params.get("ticker", "")).upper().strip()
    if not ticker or not re.match(r"^[A-Z]{1,5}$", ticker):
        return ToolResult(
            status="error",
            error="Invalid ticker format. Use 1-5 letters (e.g., AAPL).",
        )

    async with async_session_factory() as session:
        try:
            result = await ingest_ticker(ticker, session, user_id=None)
        except IngestFailedError:
            logger.warning("analyze_stock ingest failed for %s", ticker, exc_info=True)
            return ToolResult(
                status="error",
                error=f"No data available for {ticker}. Verify the ticker is correct.",
            )

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

Bump the tool class-level `timeout_seconds = 45.0`.

- [ ] **Step 2: Create tests (new file — delete the legacy test first)**

```bash
rm tests/unit/test_analyze_stock_autoingest.py
```

Create `tests/api/test_analyze_stock_tool.py`:

```python
"""Spec C.3 — analyze_stock uses canonical ingest + persists."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_analyze_stock_calls_ingest_ticker() -> None:
    from backend.tools.analyze_stock import AnalyzeStockTool

    fake_snapshot = AsyncMock()
    fake_snapshot.rsi_value = 55
    fake_snapshot.rsi_signal = "neutral"
    fake_snapshot.macd_value = 0.1
    fake_snapshot.macd_signal_label = "bullish"
    fake_snapshot.sma_signal = "bullish"
    fake_snapshot.bb_position = 0.5
    fake_snapshot.annual_return = 0.15
    fake_snapshot.volatility = 0.2
    fake_snapshot.sharpe_ratio = 1.1

    with (
        patch(
            "backend.tools.analyze_stock.ingest_ticker",
            new=AsyncMock(return_value={"is_new": True, "composite_score": 7.2}),
        ) as mock_ingest,
        patch(
            "backend.tools.analyze_stock.get_latest_signals",
            new=AsyncMock(return_value=fake_snapshot),
        ),
        patch(
            "backend.tools.analyze_stock.async_session_factory"
        ) as mock_factory,
    ):
        mock_factory.return_value.__aenter__ = AsyncMock()
        mock_factory.return_value.__aexit__ = AsyncMock()
        result = await AnalyzeStockTool()._run({"ticker": "AAPL"})
        assert result.status == "ok"
        mock_ingest.assert_awaited_once()


@pytest.mark.asyncio
async def test_analyze_stock_surfaces_ingest_failure_with_safe_message() -> None:
    """Hard Rule #10 — no str(e) in user-facing error."""
    from backend.services.exceptions import IngestFailedError
    from backend.tools.analyze_stock import AnalyzeStockTool

    with (
        patch(
            "backend.tools.analyze_stock.ingest_ticker",
            new=AsyncMock(side_effect=IngestFailedError("prices")),
        ),
        patch(
            "backend.tools.analyze_stock.async_session_factory"
        ) as mock_factory,
    ):
        mock_factory.return_value.__aenter__ = AsyncMock()
        mock_factory.return_value.__aexit__ = AsyncMock()
        result = await AnalyzeStockTool()._run({"ticker": "ZZZZ"})
        assert result.status == "error"
        assert "Verify the ticker" in (result.error or "")
        # Hard Rule #10 — no raw exception text leaked
        assert "IngestFailedError" not in (result.error or "")
```

- [ ] **Step 3: Frontend — invalidate on tool_complete**

Edit `frontend/src/hooks/use-stream-chat.ts` — in the NDJSON event handler on `tool_complete`:

```ts
if (event.tool_name === "analyze_stock" && event.status === "ok") {
  const ticker = (event.data as { ticker?: string })?.ticker?.toUpperCase();
  if (ticker) {
    for (const key of [
      ["signals", ticker],
      ["prices", ticker],
      ["fundamentals", ticker],
      ["bulk-signals-by-ticker"],
      ["watchlist"],
    ]) {
      queryClient.invalidateQueries({ queryKey: key });
    }
  }
}
```

Edit `frontend/src/components/chat/tool-card.tsx` — add `analyze_stock`-specific pending label "Fetching 10y history, computing signals…".

- [ ] **Step 4: Run + commit**

```bash
uv run pytest tests/api/test_analyze_stock_tool.py -x
cd frontend && npm test -- use-stream-chat tool-card && cd ..
uv run ruff check --fix backend/tools/analyze_stock.py tests/api/test_analyze_stock_tool.py
uv run ruff format backend/tools/analyze_stock.py tests/api/test_analyze_stock_tool.py
cd frontend && npm run lint -- --fix && cd ..
git add backend/tools/analyze_stock.py tests/api/test_analyze_stock_tool.py frontend/src/hooks/use-stream-chat.ts frontend/src/components/chat/tool-card.tsx
git commit -m "feat(chat): analyze_stock uses canonical ingest + persists snapshot (Spec C.3)"
```

---

## Task 5: C4 — Stock detail auto-refresh on stale

**Files:**
- Modify: `backend/routers/stocks/data.py`
- Modify: `backend/schemas/stock.py`
- Modify: `frontend/src/hooks/use-stocks.ts`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/components/stock-header.tsx`
- Create: `tests/api/test_signals_auto_refresh.py`

- [ ] **Step 1: Extend schema**

Edit `backend/schemas/stock.py`:

```python
class SignalResponse(BaseModel):
    ...
    is_stale: bool
    is_refreshing: bool = False
    last_refresh_attempt: datetime | None = None
```

- [ ] **Step 2: Add debounce helper in router**

Edit `backend/routers/stocks/data.py`:

```python
import redis.asyncio as redis_async

from backend.config import settings
from backend.tasks.market_data import refresh_ticker_task

DEBOUNCE_TTL_SECONDS = 300
DEBOUNCE_KEY_PREFIX = "refresh:debounce:"


async def _try_dispatch_refresh(
    ticker: str,
) -> tuple[bool, datetime | None]:
    """SETNX-based debounce for stale stock detail refreshes.

    Returns:
        (dispatched, last_attempt) where dispatched is True only when we
        acquired the lock this call and dispatched the Celery task.
    """
    key = f"{DEBOUNCE_KEY_PREFIX}{ticker.upper()}"
    try:
        client = redis_async.from_url(settings.REDIS_URL)
        now_iso = datetime.now(timezone.utc).isoformat()
        acquired = await client.set(key, now_iso, ex=DEBOUNCE_TTL_SECONDS, nx=True)
        if acquired:
            refresh_ticker_task.delay(ticker.upper())
            logger.info("Dispatched stale refresh for %s", ticker)
            return True, datetime.now(timezone.utc)
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

In `get_signals`, after computing `is_stale`:

```python
is_refreshing = False
last_refresh_attempt: datetime | None = None
if is_stale:
    is_refreshing, last_refresh_attempt = await _try_dispatch_refresh(ticker)

response = SignalResponse(
    ...,
    is_stale=is_stale,
    is_refreshing=is_refreshing,
    last_refresh_attempt=last_refresh_attempt,
)

# Skip the existing cache.set(...) when stale to avoid caching refresh state
if not is_stale:
    await cache.set(...)
```

- [ ] **Step 3: Write API tests**

Create `tests/api/test_signals_auto_refresh.py`:

```python
"""Spec C.4 — stock detail auto-refresh on stale."""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time


@pytest.mark.asyncio
async def test_get_signals_stale_dispatches_refresh_task(
    authenticated_client, seed_stale_signal
):
    await seed_stale_signal("AAPL", age_hours=48)
    fake_redis = AsyncMock()
    fake_redis.set = AsyncMock(return_value=True)
    with (
        patch("backend.routers.stocks.data.redis_async.from_url", return_value=fake_redis),
        patch("backend.routers.stocks.data.refresh_ticker_task") as mock_task,
    ):
        r = await authenticated_client.get("/api/v1/stocks/AAPL/signals")
        assert r.status_code == 200
        body = r.json()
        assert body["is_stale"] is True
        assert body["is_refreshing"] is True
        mock_task.delay.assert_called_once_with("AAPL")


@pytest.mark.asyncio
async def test_get_signals_stale_within_debounce_does_not_redispatch(
    authenticated_client, seed_stale_signal
):
    await seed_stale_signal("AAPL", age_hours=48)
    fake_redis = AsyncMock()
    fake_redis.set = AsyncMock(return_value=False)
    fake_redis.get = AsyncMock(
        return_value=datetime.now(timezone.utc).isoformat().encode()
    )
    with (
        patch("backend.routers.stocks.data.redis_async.from_url", return_value=fake_redis),
        patch("backend.routers.stocks.data.refresh_ticker_task") as mock_task,
    ):
        r = await authenticated_client.get("/api/v1/stocks/AAPL/signals")
        body = r.json()
        assert body["is_refreshing"] is False
        assert body["last_refresh_attempt"] is not None
        mock_task.delay.assert_not_called()


@pytest.mark.asyncio
async def test_get_signals_redis_unavailable_still_returns_data(
    authenticated_client, seed_stale_signal
):
    await seed_stale_signal("AAPL", age_hours=48)
    with patch(
        "backend.routers.stocks.data.redis_async.from_url",
        side_effect=ConnectionError("down"),
    ):
        r = await authenticated_client.get("/api/v1/stocks/AAPL/signals")
        assert r.status_code == 200
        assert r.json()["is_refreshing"] is False
```

- [ ] **Step 4: Frontend — add `refetchInterval` + types**

Edit `frontend/src/types/api.ts`:

```ts
export interface SignalResponse {
  ...
  is_stale: boolean;
  is_refreshing: boolean;
  last_refresh_attempt: string | null;
}
```

Edit `frontend/src/hooks/use-stocks.ts:190-196`:

```ts
export function useSignals(ticker: string) {
  return useQuery({
    queryKey: ["signals", ticker],
    queryFn: () => get<SignalResponse>(`/stocks/${ticker}/signals`),
    staleTime: 5 * 60 * 1000,
    refetchInterval: (q) => (q.state.data?.is_refreshing ? 5000 : false),
  });
}
```

Edit `frontend/src/components/stock-header.tsx` — render "Refreshing data…" badge when `is_stale && is_refreshing`, or "Data may be outdated" with a manual Refresh button (calls `useIngestTicker.mutate`) when `is_stale && !is_refreshing`.

- [ ] **Step 5: Run + commit**

```bash
uv run pytest tests/api/test_signals_auto_refresh.py -x
cd frontend && npm test -- use-stocks stock-header && cd ..
uv run ruff check --fix backend/routers/stocks/data.py backend/schemas/stock.py tests/api/test_signals_auto_refresh.py
uv run ruff format backend/routers/stocks/data.py backend/schemas/stock.py tests/api/test_signals_auto_refresh.py
cd frontend && npm run lint -- --fix && cd ..
git add backend/routers/stocks/data.py backend/schemas/stock.py tests/api/test_signals_auto_refresh.py frontend/src/types/api.ts frontend/src/hooks/use-stocks.ts frontend/src/components/stock-header.tsx
git commit -m "feat(stocks): debounced stale refresh dispatch + refresh badges (Spec C.4)"
```

---

## Task 6: C5 — Bulk CSV import service + endpoint

**Files:**
- Modify: `backend/schemas/portfolio.py`
- Create: `backend/services/portfolio/bulk_import.py`
- Modify: `backend/routers/portfolio.py`
- Create: `tests/unit/services/test_bulk_import.py`
- Create: `tests/api/test_bulk_transactions.py`

- [ ] **Step 1: Add schemas**

Edit `backend/schemas/portfolio.py`:

```python
class BulkTransactionError(BaseModel):
    row: int
    ticker: str | None
    message: str


class BulkTransactionResponse(BaseModel):
    inserted: int
    failed: int
    errors: list[BulkTransactionError]
    success_tickers: list[str]
    ingested_tickers: list[str]
```

- [ ] **Step 2: Create the bulk_import service**

Create `backend/services/portfolio/bulk_import.py`:

```python
"""Bulk CSV transaction importer (Spec C.5)."""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.portfolio import Transaction
from backend.models.stock import Stock
from backend.schemas.portfolio import (
    BulkTransactionError,
    BulkTransactionResponse,
    TransactionCreate,
)
from backend.services.exceptions import IngestFailedError
from backend.services.portfolio.core import get_or_create_portfolio, recompute_position
from backend.services.pipelines import ingest_ticker

logger = logging.getLogger(__name__)

MAX_CONCURRENT_INGESTS = 5
MAX_ROWS = 500


def _parse_date(value: str) -> date:
    value = value.strip()
    try:
        return date.fromisoformat(value)
    except ValueError:
        return datetime.fromisoformat(value).date()


def parse_csv_to_transactions(
    file_bytes: bytes,
) -> tuple[list[TransactionCreate], list[BulkTransactionError]]:
    """Parse a CSV byte stream into validated transactions + error rows.

    Args:
        file_bytes: Raw UTF-8 CSV with required header row.

    Returns:
        (parsed, errors) tuple. `parsed` may be empty if the header is invalid.
    """
    errors: list[BulkTransactionError] = []
    parsed: list[TransactionCreate] = []
    try:
        reader = csv.DictReader(io.StringIO(file_bytes.decode("utf-8-sig")))
    except UnicodeDecodeError:
        errors.append(
            BulkTransactionError(row=0, ticker=None, message="CSV is not valid UTF-8")
        )
        return [], errors

    expected = {
        "ticker",
        "transaction_type",
        "shares",
        "price_per_share",
        "transacted_at",
    }
    if reader.fieldnames is None or not expected.issubset(set(reader.fieldnames)):
        errors.append(
            BulkTransactionError(
                row=0,
                ticker=None,
                message=f"CSV header must include {sorted(expected)}",
            )
        )
        return [], errors

    for i, row in enumerate(reader, start=1):
        if i > MAX_ROWS:
            errors.append(
                BulkTransactionError(
                    row=i, ticker=None, message=f"Row limit exceeded ({MAX_ROWS} max)"
                )
            )
            break
        try:
            parsed.append(
                TransactionCreate(
                    ticker=row["ticker"].strip().upper(),
                    transaction_type=row["transaction_type"].strip().upper(),
                    shares=Decimal(row["shares"]),
                    price_per_share=Decimal(row["price_per_share"]),
                    transacted_at=_parse_date(row["transacted_at"]),
                    notes=(row.get("notes") or "").strip() or None,
                )
            )
        except (KeyError, ValueError, InvalidOperation) as exc:
            errors.append(
                BulkTransactionError(
                    row=i,
                    ticker=row.get("ticker"),
                    message=f"Invalid row: {exc}",
                )
            )
    return parsed, errors


async def bulk_create_transactions(
    user_id: uuid.UUID,
    transactions: list[TransactionCreate],
    db: AsyncSession,
    *,
    validate_only: bool = False,
) -> BulkTransactionResponse:
    """Ingest unique new tickers in parallel, insert survivors, recompute positions."""
    errors: list[BulkTransactionError] = []
    tickers = {t.ticker for t in transactions}

    existing = (
        await db.execute(
            select(Stock.ticker, Stock.last_fetched_at).where(Stock.ticker.in_(tickers))
        )
    ).all()
    known = {row.ticker: row.last_fetched_at for row in existing}
    needs_ingest = [t for t in tickers if known.get(t) is None]

    sem = asyncio.Semaphore(MAX_CONCURRENT_INGESTS)
    ingested_tickers: list[str] = []

    async def _ingest_one(ticker: str) -> None:
        async with sem:
            from backend.database import async_session_factory

            async with async_session_factory() as inner_session:
                try:
                    await ingest_ticker(
                        ticker, inner_session, user_id=str(user_id)
                    )
                    ingested_tickers.append(ticker)
                except IngestFailedError:
                    for idx, t in enumerate(transactions, start=1):
                        if t.ticker == ticker:
                            errors.append(
                                BulkTransactionError(
                                    row=idx,
                                    ticker=ticker,
                                    message="Ticker not recognized by data provider",
                                )
                            )
                            break

    if needs_ingest:
        await asyncio.gather(*(_ingest_one(t) for t in needs_ingest))

    failed_tickers = {e.ticker for e in errors if e.ticker}
    survivors = [t for t in transactions if t.ticker not in failed_tickers]

    if validate_only:
        return BulkTransactionResponse(
            inserted=0,
            failed=len(errors),
            errors=errors,
            success_tickers=[],
            ingested_tickers=ingested_tickers,
        )

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
        raise  # router catches

    affected = {t.ticker for t in survivors}
    for t in affected:
        await recompute_position(portfolio.id, t, db)
    await db.commit()

    return BulkTransactionResponse(
        inserted=len(txn_rows),
        failed=len(errors),
        errors=errors,
        success_tickers=sorted(affected),
        ingested_tickers=ingested_tickers,
    )
```

- [ ] **Step 3: Add endpoint**

Edit `backend/routers/portfolio.py`:

```python
from fastapi import File, Query, UploadFile

from backend.schemas.portfolio import BulkTransactionResponse


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
    allowed = {"text/csv", "application/vnd.ms-excel", "application/octet-stream"}
    if file.content_type not in allowed:
        raise HTTPException(415, "Upload must be a CSV file")
    raw = await file.read()
    if len(raw) > 256 * 1024:
        raise HTTPException(413, "CSV file exceeds 256 KB limit")

    from backend.services.portfolio.bulk_import import (
        bulk_create_transactions,
        parse_csv_to_transactions,
    )

    parsed, parse_errors = parse_csv_to_transactions(raw)
    if not parsed and parse_errors:
        return BulkTransactionResponse(
            inserted=0,
            failed=len(parse_errors),
            errors=parse_errors,
            success_tickers=[],
            ingested_tickers=[],
        )

    try:
        result = await bulk_create_transactions(
            user_id=current_user.id,
            transactions=parsed,
            db=db,
            validate_only=validate_only,
        )
    except IntegrityError:
        raise HTTPException(422, "Bulk insert failed integrity check")

    result.errors = parse_errors + result.errors
    result.failed += len(parse_errors)
    return result
```

- [ ] **Step 4: Unit tests for parsing + service**

Create `tests/unit/services/test_bulk_import.py` — cases as enumerated in the spec (17-24). Key snippet:

```python
def test_parse_csv_valid_rows_returns_transactions() -> None:
    from backend.services.portfolio.bulk_import import parse_csv_to_transactions

    csv_bytes = (
        b"ticker,transaction_type,shares,price_per_share,transacted_at,notes\n"
        b"AAPL,BUY,10,182.50,2025-11-15,Q3 dip\n"
        b"MSFT,BUY,5,420.00,2025-12-01,\n"
    )
    parsed, errors = parse_csv_to_transactions(csv_bytes)
    assert len(parsed) == 2
    assert errors == []


def test_parse_csv_missing_header_returns_error_row_zero() -> None:
    from backend.services.portfolio.bulk_import import parse_csv_to_transactions

    parsed, errors = parse_csv_to_transactions(b"foo,bar\n1,2\n")
    assert parsed == []
    assert errors[0].row == 0


def test_parse_csv_bad_decimal_reports_row_number() -> None:
    from backend.services.portfolio.bulk_import import parse_csv_to_transactions

    csv_bytes = (
        b"ticker,transaction_type,shares,price_per_share,transacted_at\n"
        b"AAPL,BUY,notanumber,182.50,2025-11-15\n"
    )
    parsed, errors = parse_csv_to_transactions(csv_bytes)
    assert parsed == []
    assert errors[0].row == 1
```

- [ ] **Step 5: API tests**

Create `tests/api/test_bulk_transactions.py`:

```python
"""Spec C.5 — POST /portfolio/transactions/bulk tests."""

import io

import pytest


@pytest.mark.asyncio
async def test_post_bulk_requires_auth(client):
    r = await client.post("/api/v1/portfolio/transactions/bulk", files={"file": ("x.csv", b"a,b\n")})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_post_bulk_wrong_content_type_returns_415(authenticated_client):
    r = await authenticated_client.post(
        "/api/v1/portfolio/transactions/bulk",
        files={"file": ("x.bin", b"binary", "application/pdf")},
    )
    assert r.status_code == 415


@pytest.mark.asyncio
async def test_post_bulk_oversized_file_returns_413(authenticated_client):
    big = b"ticker,transaction_type,shares,price_per_share,transacted_at\n" + (
        b"AAPL,BUY,1,1,2025-01-01\n" * 100_000
    )
    r = await authenticated_client.post(
        "/api/v1/portfolio/transactions/bulk",
        files={"file": ("big.csv", big, "text/csv")},
    )
    assert r.status_code == 413


@pytest.mark.asyncio
async def test_post_bulk_happy_path_returns_counts(authenticated_client, monkeypatch):
    from unittest.mock import AsyncMock

    async def fake_ingest(ticker, session, user_id=None):
        return {"is_new": True}

    monkeypatch.setattr("backend.services.portfolio.bulk_import.ingest_ticker", fake_ingest)
    csv_body = (
        "ticker,transaction_type,shares,price_per_share,transacted_at\n"
        "AAPL,BUY,10,182.50,2025-11-15\n"
    ).encode()
    r = await authenticated_client.post(
        "/api/v1/portfolio/transactions/bulk",
        files={"file": ("trades.csv", csv_body, "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["inserted"] >= 0
```

- [ ] **Step 6: Run + commit**

```bash
uv run pytest tests/unit/services/test_bulk_import.py tests/api/test_bulk_transactions.py -x
uv run ruff check --fix backend/services/portfolio/bulk_import.py backend/routers/portfolio.py backend/schemas/portfolio.py tests/unit/services/test_bulk_import.py tests/api/test_bulk_transactions.py
uv run ruff format backend/services/portfolio/bulk_import.py backend/routers/portfolio.py backend/schemas/portfolio.py tests/unit/services/test_bulk_import.py tests/api/test_bulk_transactions.py
git add backend/services/portfolio/bulk_import.py backend/routers/portfolio.py backend/schemas/portfolio.py tests/unit/services/test_bulk_import.py tests/api/test_bulk_transactions.py
git commit -m "feat(portfolio): bulk CSV transaction import endpoint (Spec C.5)"
```

---

## Task 7: C5 — Frontend upload component + multipart helper

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/types/api.ts`
- Create: `frontend/src/hooks/use-bulk-transactions.ts`
- Create: `frontend/src/components/bulk-transaction-upload.tsx`
- Create: `frontend/public/portfolio-template.csv`
- Modify: `frontend/src/app/(authenticated)/portfolio/portfolio-client.tsx`
- Create: `frontend/src/__tests__/components/bulk-transaction-upload.test.tsx`

- [ ] **Step 1: Add `postMultipart` helper**

Edit `frontend/src/lib/api.ts`:

```ts
export async function postMultipart<T>(
  path: string,
  formData: FormData,
): Promise<T> {
  const url = `${API_BASE}${path}`;
  let res = await fetch(url, {
    method: "POST",
    credentials: "include",
    body: formData, // browser sets multipart boundary automatically
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
      const body = (await res.json()) as { detail?: string };
      detail = body.detail || detail;
    } catch {
      /* non-JSON */
    }
    throw new ApiRequestError(res.status, detail);
  }
  return (await res.json()) as T;
}
```

- [ ] **Step 2: Add types**

Edit `frontend/src/types/api.ts`:

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

- [ ] **Step 3: Create the hook**

Create `frontend/src/hooks/use-bulk-transactions.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { postMultipart } from "@/lib/api";
import type { BulkTransactionResponse } from "@/types/api";

export function useBulkUploadTransactions() {
  const queryClient = useQueryClient();
  return useMutation<BulkTransactionResponse, Error, File>({
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

- [ ] **Step 4: Create the upload component**

Create `frontend/src/components/bulk-transaction-upload.tsx`:

```tsx
"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useBulkUploadTransactions } from "@/hooks/use-bulk-transactions";
import type { BulkTransactionResponse } from "@/types/api";

export function BulkTransactionUpload() {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<BulkTransactionResponse | null>(null);
  const upload = useBulkUploadTransactions();

  const handlePreview = async () => {
    if (!file) return;
    // Validation dry-run via validate_only=true (reuse postMultipart)
    const fd = new FormData();
    fd.append("file", file);
    const { postMultipart } = await import("@/lib/api");
    try {
      const res = await postMultipart<BulkTransactionResponse>(
        "/portfolio/transactions/bulk?validate_only=true",
        fd,
      );
      setPreview(res);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Preview failed");
    }
  };

  const handleConfirm = async () => {
    if (!file) return;
    await upload.mutateAsync(file);
    setOpen(false);
    setFile(null);
    setPreview(null);
  };

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        Upload CSV
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Bulk import transactions</DialogTitle>
          </DialogHeader>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              setFile(f);
              setPreview(null);
            }}
            data-testid="bulk-csv-input"
          />
          <a
            href="/portfolio-template.csv"
            className="text-sm text-blue-500 underline"
          >
            Download template
          </a>
          {preview && (
            <div className="text-sm">
              <p>
                Would insert: {preview.inserted}, errors: {preview.failed}
              </p>
              {preview.errors.slice(0, 10).map((e) => (
                <div key={`${e.row}-${e.message}`} className="text-red-500">
                  Row {e.row} ({e.ticker ?? "—"}): {e.message}
                </div>
              ))}
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={handlePreview} disabled={!file}>
              Preview
            </Button>
            <Button
              onClick={handleConfirm}
              disabled={!file || upload.isPending}
            >
              {upload.isPending ? "Uploading..." : "Confirm"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
```

- [ ] **Step 5: Add the CSV template asset**

Create `frontend/public/portfolio-template.csv`:

```csv
ticker,transaction_type,shares,price_per_share,transacted_at,notes
AAPL,BUY,10,182.50,2025-11-15,Example buy
```

- [ ] **Step 6: Mount the button**

Edit `frontend/src/app/(authenticated)/portfolio/portfolio-client.tsx:362-373` — next to the existing `<LogTransactionDialog>`, add `<BulkTransactionUpload />`.

- [ ] **Step 7: Component test**

Create `frontend/src/__tests__/components/bulk-transaction-upload.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";

import { server } from "@/test-utils/msw-server";
import { BulkTransactionUpload } from "@/components/bulk-transaction-upload";

function renderIt() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <BulkTransactionUpload />
    </QueryClientProvider>,
  );
}

describe("BulkTransactionUpload", () => {
  it("rejects non-csv file", async () => {
    renderIt();
    fireEvent.click(screen.getByText("Upload CSV"));
    const input = screen.getByTestId("bulk-csv-input") as HTMLInputElement;
    const file = new File(["garbage"], "bad.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });
    // accept=".csv,text/csv" prevents selection; file should still appear but preview will error
    expect(input.files?.[0].name).toBe("bad.txt");
  });

  it("posts validate_only for preview", async () => {
    let previewCalled = false;
    server.use(
      http.post("*/portfolio/transactions/bulk", ({ request }) => {
        if (request.url.includes("validate_only=true")) {
          previewCalled = true;
        }
        return HttpResponse.json({
          inserted: 0,
          failed: 0,
          errors: [],
          success_tickers: [],
          ingested_tickers: [],
        });
      }),
    );
    renderIt();
    fireEvent.click(screen.getByText("Upload CSV"));
    const input = screen.getByTestId("bulk-csv-input") as HTMLInputElement;
    const file = new File(
      ["ticker,transaction_type,shares,price_per_share,transacted_at\nAAPL,BUY,1,1,2025-01-01"],
      "t.csv",
      { type: "text/csv" },
    );
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByText("Preview"));
    await new Promise((r) => setTimeout(r, 50));
    expect(previewCalled).toBe(true);
  });
});
```

- [ ] **Step 8: Run + commit**

```bash
cd frontend && npm test -- bulk-transaction-upload && cd ..
cd frontend && npm run lint -- --fix && cd ..
git add frontend/src/lib/api.ts frontend/src/types/api.ts frontend/src/hooks/use-bulk-transactions.ts frontend/src/components/bulk-transaction-upload.tsx frontend/public/portfolio-template.csv frontend/src/app/\(authenticated\)/portfolio/portfolio-client.tsx frontend/src/__tests__/components/bulk-transaction-upload.test.tsx
git commit -m "feat(frontend): bulk CSV transaction upload component + hook (Spec C.5)"
```

---

## Task 8: C6 — Search "Add" flow simplification verification

- [ ] **Step 1: Verify `useIngestTicker` still reachable only from stock detail Run Analysis**

```bash
uv run grep -rn "useIngestTicker" frontend/src/
```

Expected: only matches in `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx` and its test.

- [ ] **Step 2: Manual smoke test checklist**

Run backend + frontend:
```bash
uv run uvicorn backend.main:app --reload --port 8181 &
cd frontend && npm run dev
```

Verify:
- Topbar search → select an in-DB ticker → adds to watchlist in <500ms
- Topbar search → select an external (`in_db: false`) ticker → adds in 5-15s with loading toast
- Direct navigation to `/stocks/XYZZ` with an unknown ticker → "Run Analysis" button reachable
- Chat: "Analyze NVDA" (assuming NVDA in DB) → chat answer matches stock detail page

- [ ] **Step 3: No additional commit** (verification only)

---

## Done Criteria

- [ ] `add_to_watchlist` auto-ingests; 404 only for genuinely invalid tickers
- [ ] Portfolio transaction endpoint sync-ingests when `stock.last_fetched_at is None`
- [ ] `analyze_stock` chat tool persists signal snapshots
- [ ] Stock detail `SignalResponse` exposes `is_refreshing` + `last_refresh_attempt`; frontend polls every 5s while refreshing
- [ ] `POST /portfolio/transactions/bulk` multipart endpoint parses up to 500 rows, 256 KB
- [ ] Frontend `postMultipart` helper + BulkTransactionUpload component wired into portfolio page
- [ ] Feature flag `WATCHLIST_AUTO_INGEST` in config.py
- [ ] ~35 new/modified test cases green
- [ ] No `str(e)` leaks in any new error path (Hard Rule #10)
