# Pipeline Overhaul — Spec Z (Quick Wins) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land six zero-blast-radius fixes (typo, stub deletion, LIMIT 50 bug, task rename, frontend cache invalidation, WelcomeBanner mount) that unblock observability and correct data scoping before the larger pipeline overhaul specs.

**Architecture:** Surgical fixes in existing files; two new test files for future-proofing. No migrations, no new services.

**Tech Stack:** Celery, pytest, TanStack Query v5, React, Sonner toast

**Spec:** `docs/superpowers/specs/2026-04-06-pipeline-overhaul-spec-Z-quick-wins.md`

---

## File Structure

```
backend/services/pipeline_registry_config.py       # MODIFY — Z1 typo, Z2 remove, Z4 rename
backend/tasks/forecasting.py                       # MODIFY — Z2 delete stub
backend/tasks/news_sentiment.py                    # MODIFY — Z3 canonical universe
backend/tasks/market_data.py                       # MODIFY — Z4 rename + alias
backend/tasks/__init__.py                          # MODIFY — Z4 beat entry
frontend/src/hooks/use-stocks.ts                   # MODIFY — Z5 full invalidation
frontend/src/app/(authenticated)/dashboard/page.tsx # MODIFY — Z6 WelcomeBanner

tests/unit/services/test_pipeline_registry_config.py   # NEW — Z1 enforcement
tests/unit/tasks/test_forecasting.py                   # MODIFY — Z2 deletion guard
tests/unit/tasks/test_news_sentiment.py                # MODIFY — Z3 test cases
tests/unit/tasks/test_celery_tasks.py                  # MODIFY — Z4 alias tests
tests/unit/tasks/test_seed_tasks.py                    # MODIFY — Z4 beat schedule
frontend/src/__tests__/hooks/use-stocks.test.ts        # MODIFY — Z5 invalidation
frontend/src/__tests__/app/dashboard.test.tsx          # NEW or MODIFY — Z6 mount
```

---

## Task 1: Z1 — Fix PipelineRegistry news task name typo

**Files:**
- Modify: `backend/services/pipeline_registry_config.py`
- Create: `tests/unit/services/test_pipeline_registry_config.py`

- [ ] **Step 1: Add failing test first**

Create `tests/unit/services/test_pipeline_registry_config.py`:

```python
"""Tests for PipelineRegistry task-name integrity."""

import pytest

from backend.services.pipeline_registry_config import build_registry
from backend.tasks import celery_app


def test_every_registered_task_resolves_to_real_celery_task() -> None:
    """Every task in the registry must be importable by Celery.

    Catches typos in task name strings that would cause
    `Received unregistered task` at runtime.
    """
    registry = build_registry()
    for task in registry.get_all_tasks():
        assert task.name in celery_app.tasks, (
            f"Registry task {task.name!r} is not registered in Celery app. "
            f"Check for a typo in pipeline_registry_config.py."
        )
```

- [ ] **Step 2: Run the test, observe failure**

```bash
uv run pytest tests/unit/services/test_pipeline_registry_config.py -x
```

Expected: test fails because `backend.tasks.news_sentiment.sentiment_scoring_task` is not registered (real name is `news_sentiment_scoring_task`).

- [ ] **Step 3: Fix the typo**

Edit `backend/services/pipeline_registry_config.py` line ~443:

```python
# Before
name="backend.tasks.news_sentiment.sentiment_scoring_task",
# After
name="backend.tasks.news_sentiment.news_sentiment_scoring_task",
```

- [ ] **Step 4: Rerun test**

```bash
uv run pytest tests/unit/services/test_pipeline_registry_config.py -x
```

Expected: pass.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix backend/services/pipeline_registry_config.py tests/unit/services/test_pipeline_registry_config.py
uv run ruff format backend/services/pipeline_registry_config.py tests/unit/services/test_pipeline_registry_config.py
git add backend/services/pipeline_registry_config.py tests/unit/services/test_pipeline_registry_config.py
git commit -m "fix(pipeline): correct news sentiment task name in registry (Spec Z.1)"
```

---

## Task 2: Z2 — Delete `calibrate_seasonality_task` stub

**Files:**
- Modify: `backend/tasks/forecasting.py`
- Modify: `backend/services/pipeline_registry_config.py`
- Modify: `tests/unit/tasks/test_forecasting.py`

- [ ] **Step 1: Add regression test asserting task is gone**

Add to `tests/unit/tasks/test_forecasting.py`:

```python
def test_calibrate_seasonality_task_not_importable() -> None:
    """Stub task was deleted in Spec Z.2; must not be re-introduced silently."""
    import backend.tasks.forecasting as forecasting_mod

    assert not hasattr(forecasting_mod, "calibrate_seasonality_task"), (
        "calibrate_seasonality_task was intentionally deleted. "
        "Re-introducing requires a new spec with a real implementation."
    )


def test_calibrate_seasonality_not_in_registry() -> None:
    """The registry must no longer reference the deleted stub."""
    from backend.services.pipeline_registry_config import build_registry

    names = {t.name for t in build_registry().get_all_tasks()}
    assert "backend.tasks.forecasting.calibrate_seasonality_task" not in names
```

- [ ] **Step 2: Delete the stub function**

Remove `calibrate_seasonality_task` (and any helper private coroutine) from `backend/tasks/forecasting.py` at lines ~241-253.

- [ ] **Step 3: Remove from registry**

Delete the `RegisteredTask(...)` entry in `backend/services/pipeline_registry_config.py:419` under the "model_training" group.

- [ ] **Step 4: Verify registry still loads + tests pass**

```bash
uv run pytest tests/unit/tasks/test_forecasting.py tests/unit/services/test_pipeline_registry_config.py -x
```

Expected: pass. The Task 1 enforcement test continues to pass.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix backend/tasks/forecasting.py backend/services/pipeline_registry_config.py tests/unit/tasks/test_forecasting.py
uv run ruff format backend/tasks/forecasting.py backend/services/pipeline_registry_config.py tests/unit/tasks/test_forecasting.py
git add backend/tasks/forecasting.py backend/services/pipeline_registry_config.py tests/unit/tasks/test_forecasting.py
git commit -m "refactor(forecasting): delete calibrate_seasonality_task stub (Spec Z.2)"
```

---

## Task 3: Z3 — News ingest uses canonical universe (not LIMIT 50)

> **Sequencing gate (CRITICAL — review finding):** Z3 MUST NOT merge until
> Spec F2 + F3 rate limiters have deployed. Without a rate limiter the
> 4x volume increase will push Finnhub free-tier over quota and ban the
> API key. If schedule pressure forces Z3 to ship before F2/F3, set
> `NEWS_INGEST_TICKER_CAP = 50` (no behaviour change) and only flip to
> 200 once F2/F3 are in production for ≥48h.

**Files:**
- Modify: `backend/tasks/news_sentiment.py`
- Modify: `tests/unit/tasks/test_news_sentiment.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/unit/tasks/test_news_sentiment.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_news_ingest_uses_canonical_universe() -> None:
    """Replaces the old `SELECT ticker FROM stocks LIMIT 50` query."""
    from backend.tasks import news_sentiment as mod

    with (
        patch.object(
            mod, "get_all_referenced_tickers", new=AsyncMock(return_value=["AAPL", "MSFT"])
        ) as mock_universe,
        patch.object(mod, "NewsSentimentService") as mock_svc_cls,
    ):
        mock_svc = mock_svc_cls.return_value
        mock_svc.ingest_stock_news = AsyncMock(return_value={"articles": 0})
        await mod._news_ingest_async()
        mock_universe.assert_awaited_once()


@pytest.mark.asyncio
async def test_news_ingest_caps_at_200() -> None:
    from backend.tasks import news_sentiment as mod

    tickers = [f"T{i:03d}" for i in range(250)]
    with (
        patch.object(
            mod, "get_all_referenced_tickers", new=AsyncMock(return_value=tickers)
        ),
        patch.object(mod, "NewsSentimentService") as mock_svc_cls,
    ):
        mock_svc = mock_svc_cls.return_value
        mock_svc.ingest_stock_news = AsyncMock(return_value={"articles": 0})
        await mod._news_ingest_async()
        ingested = [c.args[0] for c in mock_svc.ingest_stock_news.await_args_list]
        assert len(ingested) == 200


@pytest.mark.asyncio
async def test_news_ingest_handles_universe_smaller_than_cap() -> None:
    from backend.tasks import news_sentiment as mod

    with (
        patch.object(
            mod,
            "get_all_referenced_tickers",
            new=AsyncMock(return_value=["AAPL", "MSFT", "GOOGL"]),
        ),
        patch.object(mod, "NewsSentimentService") as mock_svc_cls,
    ):
        mock_svc = mock_svc_cls.return_value
        mock_svc.ingest_stock_news = AsyncMock(return_value={"articles": 0})
        await mod._news_ingest_async()
        assert mock_svc.ingest_stock_news.await_count == 3
```

Run: `uv run pytest tests/unit/tasks/test_news_sentiment.py -x` → expect failures.

- [ ] **Step 2: Replace the LIMIT 50 block**

Edit `backend/tasks/news_sentiment.py` around line 48-53. Replace:

```python
async with async_session_factory() as session:
    result = await session.execute(
        select(Stock.ticker).where(Stock.is_active.is_(True)).limit(50)
    )
    tickers = [row[0] for row in result.all()]
```

With:

```python
from backend.services.ticker_universe import get_all_referenced_tickers

async with async_session_factory() as session:
    all_tickers = await get_all_referenced_tickers(session)
    # Hard cap at 200 to control news provider quota.
    # Raise once Spec F2 (news rate limiter) lands.
    tickers = all_tickers[:200]
```

Move the `get_all_referenced_tickers` import to the top of the module if not already imported.

- [ ] **Step 3: Rerun tests**

```bash
uv run pytest tests/unit/tasks/test_news_sentiment.py -x
```

Expected: pass.

- [ ] **Step 4: Lint + commit**

```bash
uv run ruff check --fix backend/tasks/news_sentiment.py tests/unit/tasks/test_news_sentiment.py
uv run ruff format backend/tasks/news_sentiment.py tests/unit/tasks/test_news_sentiment.py
git add backend/tasks/news_sentiment.py tests/unit/tasks/test_news_sentiment.py
git commit -m "fix(news): ingest canonical universe capped at 200, not LIMIT 50 (Spec Z.3)"
```

---

## Task 4: Z4 — Rename `refresh_all_watchlist_tickers_task` → `intraday_refresh_all_task`

**Files:**
- Modify: `backend/tasks/market_data.py`
- Modify: `backend/tasks/__init__.py`
- Modify: `backend/services/pipeline_registry_config.py`
- Modify: `tests/unit/tasks/test_celery_tasks.py`
- Modify: `tests/unit/tasks/test_seed_tasks.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/unit/tasks/test_celery_tasks.py`:

```python
def test_intraday_refresh_all_task_registered_with_new_name() -> None:
    from backend.tasks import celery_app

    assert "backend.tasks.market_data.intraday_refresh_all_task" in celery_app.tasks


def test_legacy_refresh_all_watchlist_tickers_task_warns_and_delegates() -> None:
    """The deprecation alias must still be callable and emit DeprecationWarning."""
    import warnings
    from unittest.mock import patch

    from backend.tasks import market_data

    with (
        warnings.catch_warnings(record=True) as caught,
        patch.object(
            market_data, "intraday_refresh_all_task", autospec=True
        ) as mock_new,
    ):
        warnings.simplefilter("always")
        mock_new.return_value = {"status": "ok"}
        result = market_data.refresh_all_watchlist_tickers_task.run()
        assert result == {"status": "ok"}
        assert any(
            issubclass(w.category, DeprecationWarning) for w in caught
        ), "Expected DeprecationWarning"
```

Append to `tests/unit/tasks/test_seed_tasks.py` (or wherever beat schedule is asserted):

```python
def test_beat_schedule_uses_new_task_name() -> None:
    from backend.tasks import celery_app

    schedule = celery_app.conf.beat_schedule
    entry = schedule.get("intraday-refresh-all")
    assert entry is not None, "Missing beat entry 'intraday-refresh-all'"
    assert entry["task"] == "backend.tasks.market_data.intraday_refresh_all_task"
```

- [ ] **Step 2: Rename the task function**

Edit `backend/tasks/market_data.py` around lines 394-413. Replace:

```python
@celery_app.task(name="backend.tasks.market_data.refresh_all_watchlist_tickers_task")
def refresh_all_watchlist_tickers_task() -> dict:
    """..."""
    ...
```

With:

```python
@celery_app.task(name="backend.tasks.market_data.intraday_refresh_all_task")
def intraday_refresh_all_task() -> dict:
    """Refresh prices + signals for every referenced ticker (intraday cadence).

    Renamed from refresh_all_watchlist_tickers_task in Spec Z.4 to better
    reflect the canonical universe scope.
    """
    # ... existing body moved verbatim


@celery_app.task(name="backend.tasks.market_data.refresh_all_watchlist_tickers_task")
def refresh_all_watchlist_tickers_task() -> dict:
    """DEPRECATED — use intraday_refresh_all_task. Will be removed next release."""
    import warnings

    warnings.warn(
        "refresh_all_watchlist_tickers_task is deprecated; use intraday_refresh_all_task",
        DeprecationWarning,
        stacklevel=2,
    )
    return intraday_refresh_all_task()
```

- [ ] **Step 3: Update beat schedule**

Edit `backend/tasks/__init__.py` lines ~38-41. Replace the existing entry with:

```python
"intraday-refresh-all": {
    "task": "backend.tasks.market_data.intraday_refresh_all_task",
    "schedule": 30 * 60,
},
```

- [ ] **Step 4: Update PipelineRegistry**

Edit `backend/services/pipeline_registry_config.py:317` — update the `name=` string for the matching task to `"backend.tasks.market_data.intraday_refresh_all_task"`.

- [ ] **Step 5: Run all touched tests**

```bash
uv run pytest tests/unit/tasks/test_celery_tasks.py tests/unit/tasks/test_seed_tasks.py tests/unit/services/test_pipeline_registry_config.py -x
```

Expected: pass (including the Task 1 registry-vs-celery enforcement test).

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check --fix backend/tasks/market_data.py backend/tasks/__init__.py backend/services/pipeline_registry_config.py tests/unit/tasks/test_celery_tasks.py tests/unit/tasks/test_seed_tasks.py
uv run ruff format backend/tasks/market_data.py backend/tasks/__init__.py backend/services/pipeline_registry_config.py tests/unit/tasks/test_celery_tasks.py tests/unit/tasks/test_seed_tasks.py
git add backend/tasks/market_data.py backend/tasks/__init__.py backend/services/pipeline_registry_config.py tests/unit/tasks/test_celery_tasks.py tests/unit/tasks/test_seed_tasks.py
git commit -m "refactor(tasks): rename refresh_all_watchlist_tickers_task to intraday_refresh_all_task (Spec Z.4)"
```

---

## Task 5: Z5 — Frontend `useIngestTicker` full cache invalidation

**Files:**
- Modify: `frontend/src/hooks/use-stocks.ts`
- Modify: `frontend/src/__tests__/hooks/use-stocks.test.ts`

- [ ] **Step 1: Add failing test**

Append to `frontend/src/__tests__/hooks/use-stocks.test.ts`:

```typescript
describe("useIngestTicker cache invalidation", () => {
  it("invalidates the full ticker-dependent query set on success", async () => {
    const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
    const queryClient = new QueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { useIngestTicker } = await import("@/hooks/use-stocks");
    const { renderHook, waitFor } = await import("@testing-library/react");

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    // Mock fetch to succeed
    server.use(
      http.post("*/stocks/AAPL/ingest", () => HttpResponse.json({ status: "ok" })),
    );

    const { result } = renderHook(() => useIngestTicker(), { wrapper });
    await result.current.mutateAsync("AAPL");

    await waitFor(() => {
      const keys = invalidateSpy.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
      expect(keys).toContain(JSON.stringify(["signals", "AAPL"]));
      expect(keys).toContain(JSON.stringify(["fundamentals", "AAPL"]));
      expect(keys).toContain(JSON.stringify(["forecast", "AAPL"]));
      expect(keys).toContain(JSON.stringify(["stock-news", "AAPL"]));
      expect(keys).toContain(JSON.stringify(["intelligence", "AAPL"]));
      expect(keys).toContain(JSON.stringify(["benchmark", "AAPL"]));
      expect(keys).toContain(JSON.stringify(["analytics", "AAPL"]));
      expect(keys).toContain(JSON.stringify(["ingest-state", "AAPL"]));
      expect(keys).toContain(JSON.stringify(["watchlist"]));
      expect(keys).toContain(JSON.stringify(["bulk-signals"]));
      expect(keys).toContain(JSON.stringify(["positions"]));
    });
  });
});
```

Run: `cd frontend && npm test -- use-stocks` → expect failure.

- [ ] **Step 2: Widen invalidation**

Edit `frontend/src/hooks/use-stocks.ts` around lines 115-119 in `useIngestTicker`:

```ts
onSuccess: (_, ticker) => {
  const tickerQueries: readonly (readonly string[])[] = [
    ["signals", ticker],
    ["prices", ticker],
    ["fundamentals", ticker],
    ["stock-news", ticker],
    ["intelligence", ticker],
    ["forecast", ticker],
    ["benchmark", ticker],
    ["analytics", ticker],
    ["ingest-state", ticker],
  ];
  for (const key of tickerQueries) {
    queryClient.invalidateQueries({ queryKey: key });
  }
  queryClient.invalidateQueries({ queryKey: ["watchlist"] });
  queryClient.invalidateQueries({ queryKey: ["bulk-signals"] });
  queryClient.invalidateQueries({ queryKey: ["positions"] });
},
```

- [ ] **Step 3: Rerun test**

```bash
cd frontend && npm test -- use-stocks
```

Expected: pass.

- [ ] **Step 4: Lint + commit**

```bash
cd frontend && npm run lint -- --fix && cd ..
git add frontend/src/hooks/use-stocks.ts frontend/src/__tests__/hooks/use-stocks.test.ts
git commit -m "fix(frontend): invalidate full ticker query set on useIngestTicker (Spec Z.5)"
```

---

## Task 6: Z6 — Mount `WelcomeBanner` on empty dashboard

**Files:**
- Modify: `frontend/src/app/(authenticated)/dashboard/page.tsx`
- Create or Modify: `frontend/src/__tests__/app/dashboard.test.tsx`

- [ ] **Step 1: Add failing tests**

Create `frontend/src/__tests__/app/dashboard.test.tsx` if missing:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DashboardPage from "@/app/(authenticated)/dashboard/page";

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient();
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

vi.mock("@/hooks/use-stocks", () => ({
  useWatchlist: vi.fn(),
  usePositions: vi.fn(),
  useAddToWatchlist: vi.fn(() => ({ mutateAsync: vi.fn() })),
}));

describe("DashboardPage WelcomeBanner mount", () => {
  it("renders WelcomeBanner when watchlist and positions are empty", async () => {
    const { useWatchlist, usePositions } = await import("@/hooks/use-stocks");
    vi.mocked(useWatchlist).mockReturnValue({ data: [] } as never);
    vi.mocked(usePositions).mockReturnValue({ data: [] } as never);
    renderWithClient(<DashboardPage />);
    expect(await screen.findByTestId("welcome-banner")).toBeInTheDocument();
  });

  it("hides WelcomeBanner when watchlist has items", async () => {
    const { useWatchlist, usePositions } = await import("@/hooks/use-stocks");
    vi.mocked(useWatchlist).mockReturnValue({
      data: [{ ticker: "AAPL" }],
    } as never);
    vi.mocked(usePositions).mockReturnValue({ data: [] } as never);
    renderWithClient(<DashboardPage />);
    expect(screen.queryByTestId("welcome-banner")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Mount the banner conditionally**

Edit `frontend/src/app/(authenticated)/dashboard/page.tsx`:

```tsx
"use client";
import { useState } from "react";

import { WelcomeBanner } from "@/components/welcome-banner";
import { useAddToWatchlist, usePositions, useWatchlist } from "@/hooks/use-stocks";

export default function DashboardPage() {
  const { data: watchlist = [] } = useWatchlist();
  const { data: positions = [] } = usePositions();
  const addToWatchlist = useAddToWatchlist();
  const [addingTickers, setAddingTickers] = useState<Set<string>>(new Set());

  const isEmpty = watchlist.length === 0 && positions.length === 0;

  const handleAddTicker = async (ticker: string) => {
    setAddingTickers((prev) => new Set(prev).add(ticker));
    try {
      await addToWatchlist.mutateAsync(ticker);
    } finally {
      setAddingTickers((prev) => {
        const next = new Set(prev);
        next.delete(ticker);
        return next;
      });
    }
  };

  return (
    <>
      {isEmpty && (
        <div data-testid="welcome-banner">
          <WelcomeBanner onAddTicker={handleAddTicker} addingTickers={addingTickers} />
        </div>
      )}
      {/* existing dashboard zones preserved verbatim */}
    </>
  );
}
```

Preserve the existing dashboard content — only wrap the banner conditionally above it.

- [ ] **Step 3: Rerun tests**

```bash
cd frontend && npm test -- dashboard
```

Expected: pass.

- [ ] **Step 4: Lint + commit**

```bash
cd frontend && npm run lint -- --fix && cd ..
git add frontend/src/app/(authenticated)/dashboard/page.tsx frontend/src/__tests__/app/dashboard.test.tsx
git commit -m "feat(dashboard): mount WelcomeBanner for cold-start users (Spec Z.6)"
```

---

## Done Criteria

- [ ] All 12 test cases across Z1-Z6 pass (`uv run pytest tests/unit/services/test_pipeline_registry_config.py tests/unit/tasks/test_forecasting.py tests/unit/tasks/test_news_sentiment.py tests/unit/tasks/test_celery_tasks.py tests/unit/tasks/test_seed_tasks.py -q`)
- [ ] Frontend test suite green (`cd frontend && npm test -- use-stocks dashboard`)
- [ ] `uv run ruff check backend/` zero errors
- [ ] Registry → Celery enforcement test (Task 1) passes — prevents future drift
- [ ] Smoke test: admin "news_sentiment" pipeline group no longer fails with unregistered task
