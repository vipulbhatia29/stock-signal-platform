# Screener Grid View Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a card-based grid view to the screener that renders each stock as a chart-first card (full-width sparkline + ticker + signal badges + score), toggled alongside the existing table view.

**Architecture:** Extend the existing `GET /api/v1/stocks/signals/bulk` endpoint to include `price_history` (last 30 daily `adj_close` values per ticker) via a correlated subquery. Add a `screener-grid.tsx` component consuming `Sparkline`. Add a `viewMode` toggle to `screener/page.tsx` that swaps between `ScreenerTable` and `ScreenerGrid`.

**Tech Stack:** Python/FastAPI/SQLAlchemy (backend), Next.js/TypeScript/Tailwind/Recharts (frontend), pytest/httpx (tests)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/schemas/stock.py` | Modify | Add `price_history: list[float] \| None = None` to `BulkSignalItem` |
| `backend/routers/stocks.py` | Modify | Add correlated subquery for price_history; populate field in mapping |
| `tests/api/test_bulk_signals.py` | Modify | Add test asserting `price_history` is returned with correct length |
| `frontend/src/types/api.ts` | Modify | Add `price_history: number[] \| null` to `BulkSignalItem` |
| `frontend/src/hooks/use-container-width.ts` | Create | `useContainerWidth` hook — ResizeObserver for dynamic card widths |
| `frontend/src/components/screener-grid.tsx` | Create | Grid of C2-style stock cards using `Sparkline`, `ScoreBadge`, `SignalBadge` |
| `frontend/src/app/(authenticated)/screener/page.tsx` | Modify | Add `viewMode` state + `LayoutGrid`/`LayoutList` toggle; conditionally render grid vs table |

---

## Chunk 1: Backend — price_history field

### Task 1: Add `price_history` to `BulkSignalItem` schema

**Files:**
- Modify: `backend/schemas/stock.py:233-249`

- [ ] **Step 1: Add the field to the schema**

Open `backend/schemas/stock.py`. After line 248 (`is_stale: bool = False`), add:

```python
price_history: list[float] | None = None
```

The full `BulkSignalItem` class should now end:

```python
class BulkSignalItem(BaseModel):
    """A single stock's signal summary for the screener table."""

    ticker: str
    name: str
    sector: str | None = None
    composite_score: float | None = None
    rsi_value: float | None = None
    rsi_signal: str | None = None
    macd_signal: str | None = None
    sma_signal: str | None = None
    bb_position: str | None = None
    annual_return: float | None = None
    volatility: float | None = None
    sharpe_ratio: float | None = None
    computed_at: datetime | None = None
    is_stale: bool = False
    price_history: list[float] | None = None
```

- [ ] **Step 2: Verify no import changes needed**

`list[float]` uses built-in types only — no new imports needed. Confirm `from __future__ import annotations` is not required (Pydantic v2 handles this natively).

---

### Task 2: Add price_history correlated subquery to bulk signals endpoint

**Files:**
- Modify: `backend/routers/stocks.py:562-642`

`★ Insight ─────────────────────────────────────`
The existing query uses a `row_number()` window function as a subquery to get the latest signal snapshot per ticker. We add a second correlated subquery that selects the last 30 `adj_close` values per ticker from `stock_prices`, sorted by `time DESC`, then aggregates them into an array with `array_agg`. The outer query calls `array_agg` with `ORDER BY time ASC` to return chronological order for the sparkline.
`─────────────────────────────────────────────────`

- [ ] **Step 1: Write the failing test first** (see Task 3 below — write the test, then come back here)

- [ ] **Step 2: Add imports** to `backend/routers/stocks.py`

Check the existing `from sqlalchemy import ...` line — `func` and `select` are already there. Add `Float`:

```python
from sqlalchemy import delete, Float, func, select
```

Also check whether `StockPrice` is already imported. If not, add:

```python
from backend.models.price import StockPrice
```

Also add the PostgreSQL-specific `aggregate_order_by` helper (needed for ordered `array_agg`):

```python
from sqlalchemy.dialects.postgresql import aggregate_order_by
```

- [ ] **Step 3: Build the price_history correlated subquery**

In `get_bulk_signals` (around line 562), after `latest = latest.subquery("latest")` and before `query = select(latest).where(latest.c.rn == 1)`, add:

```python
# Correlated subquery: last 30 adj_close values per ticker (chronological ASC).
# Uses a nested subquery to pick the 30 most-recent dates (DESC limit),
# then array_agg with aggregate_order_by to return them sorted ASC.
_last_30_times = (
    select(StockPrice.time)
    .where(StockPrice.ticker == latest.c.ticker)
    .order_by(StockPrice.time.desc())
    .limit(30)
    .correlate(latest)
    .subquery()
)
price_sub = (
    select(
        func.array_agg(
            aggregate_order_by(
                StockPrice.adj_close.cast(Float),
                StockPrice.time.asc(),
            )
        ).label("price_history")
    )
    .where(StockPrice.ticker == latest.c.ticker)
    .where(StockPrice.time.in_(select(_last_30_times)))
    .correlate(latest)
    .scalar_subquery()
)
```

Key points:
- `_last_30_times` is a plain `.subquery()` (not `.scalar_subquery()`) — it returns multiple rows, used inside `.in_()`
- `aggregate_order_by(col, order)` is the correct SQLAlchemy construct for `array_agg(col ORDER BY order)` in PostgreSQL — guarantees chronological order
- `.scalar_subquery()` on the outer `select(func.array_agg(...))` is correct — that query returns exactly one value (the array)

- [ ] **Step 4: Add price_history to the main select**

Change:

```python
query = select(latest).where(latest.c.rn == 1)
```

To:

```python
query = select(latest, price_sub).where(latest.c.rn == 1)
```

- [ ] **Step 5: Map price_history in the BulkSignalItem constructor**

In the `items = [BulkSignalItem(...) for row in rows]` block (around line 618), add `price_history=row.price_history` to the constructor:

```python
items = [
    BulkSignalItem(
        ticker=row.ticker,
        name=row.name,
        sector=row.stock_sector,
        composite_score=row.composite_score,
        rsi_value=row.rsi_value,
        rsi_signal=row.rsi_signal,
        macd_signal=row.macd_signal_label,
        sma_signal=row.sma_signal,
        bb_position=row.bb_position,
        annual_return=row.annual_return,
        volatility=row.volatility,
        sharpe_ratio=row.sharpe_ratio,
        computed_at=row.computed_at,
        is_stale=(
            row.computed_at.replace(tzinfo=timezone.utc) < stale_cutoff
            if row.computed_at
            else True
        ),
        price_history=row.price_history,
    )
    for row in rows
]
```

- [ ] **Step 6: Run linting**

```bash
uv run ruff check backend/ --fix && uv run ruff format backend/
```

Expected: zero errors.

---

### Task 3: Add price_history test to bulk signals test suite

**Files:**
- Modify: `tests/api/test_bulk_signals.py`

- [ ] **Step 1: Write the failing test**

Add this test method to the `TestBulkSignals` class in `tests/api/test_bulk_signals.py`:

```python
async def test_bulk_signals_includes_price_history(
    self, authenticated_client: AsyncClient, db_url: str
) -> None:
    """price_history field contains up to 30 chronological adj_close floats."""
    from datetime import timedelta

    engine = create_async_engine(db_url, echo=False)
    factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory_() as session:
        stock = StockFactory.build(ticker="PH01", name="Price History Test")
        session.add(stock)
        await session.flush()

        signal = SignalSnapshotFactory.build(ticker="PH01", composite_score=7.0)
        session.add(signal)

        base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for i in range(35):
            price = StockPriceFactory.build(
                ticker="PH01",
                time=base_time + timedelta(days=i),
                adj_close=float(100 + i),
            )
            session.add(price)
        await session.commit()
    await engine.dispose()

    response = await authenticated_client.get("/api/v1/stocks/signals/bulk")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    ph = items[0]
    assert ph["ticker"] == "PH01"
    assert ph["price_history"] is not None
    # 35 rows inserted, limit is 30 — must return exactly 30
    assert len(ph["price_history"]) == 30
    # Values should be floats
    assert all(isinstance(v, float) for v in ph["price_history"])
    # Must be in chronological (ascending) order — sparkline depends on this
    assert ph["price_history"] == sorted(ph["price_history"])
```

- [ ] **Step 2: Add missing imports to test file**

At the top of `tests/api/test_bulk_signals.py`, add `StockPriceFactory` to the existing import from `tests.conftest` and add `datetime`, `timezone`:

```python
from datetime import datetime, timezone

from tests.conftest import (
    SignalSnapshotFactory,
    StockFactory,
    StockIndexFactory,
    StockIndexMembershipFactory,
    StockPriceFactory,
)
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/api/test_bulk_signals.py::TestBulkSignals::test_bulk_signals_includes_price_history -v
```

Expected: FAIL — `price_history` is `None` (field not yet added to query).

- [ ] **Step 4: Implement Task 2 (the backend query change) now**

Return to Task 2 and complete it.

- [ ] **Step 5: Run the new test to verify it passes**

```bash
uv run pytest tests/api/test_bulk_signals.py::TestBulkSignals::test_bulk_signals_includes_price_history -v
```

Expected: PASS

- [ ] **Step 6: Run the full bulk signals test suite**

```bash
uv run pytest tests/api/test_bulk_signals.py -v
```

Expected: all tests PASS (≥7 tests).

- [ ] **Step 7: Commit**

```bash
git add backend/schemas/stock.py backend/routers/stocks.py tests/api/test_bulk_signals.py
git commit -m "feat: add price_history to bulk signals endpoint (last 30 adj_close per ticker)"
```

---

## Chunk 2: Frontend — type, grid component, page toggle

### Task 4: Extend `BulkSignalItem` TypeScript type

**Files:**
- Modify: `frontend/src/types/api.ts:152-167`

- [ ] **Step 1: Add `price_history` to the interface**

In `frontend/src/types/api.ts`, find the `BulkSignalItem` interface and add the field after `is_stale`:

```typescript
export interface BulkSignalItem {
  ticker: string;
  name: string;
  sector: string | null;
  composite_score: number | null;
  rsi_value: number | null;
  rsi_signal: string | null;
  macd_signal: string | null;
  sma_signal: string | null;
  bb_position: string | null;
  annual_return: number | null;
  volatility: number | null;
  sharpe_ratio: number | null;
  computed_at: string | null;
  is_stale: boolean;
  price_history: number[] | null;
}
```

- [ ] **Step 2: Verify TypeScript build passes**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: no new type errors.

---

### Task 5: Create `screener-grid.tsx` component

**Files:**
- Create: `frontend/src/components/screener-grid.tsx`

`★ Insight ─────────────────────────────────────`
The C2 card layout places the full-width Sparkline as the top half of the card (borderless, no padding), and the meta section below it. The Sparkline component takes a fixed `width` and `height` prop — but the grid cards need the chart to fill the card width. To achieve full-width rendering without a fixed pixel width, wrap the Sparkline in a `w-full` container and use `useRef` + `ResizeObserver` to read the container's actual pixel width, passing it to `<Sparkline width={...} />`. This pattern avoids hardcoded widths that break at different breakpoints.
`─────────────────────────────────────────────────`

- [ ] **Step 1: Create the container-width hook**

Create `frontend/src/hooks/use-container-width.ts`:

```typescript
import { useRef, useState, useEffect } from "react";

/**
 * Returns the current pixel width of a DOM element via ResizeObserver.
 * Uses lazy useState initializer for the first read to avoid calling
 * setState synchronously inside useEffect (ESLint react-hooks/set-state-in-effect).
 */
export function useContainerWidth(
  ref: React.RefObject<HTMLDivElement | null>
): number {
  const [width, setWidth] = useState(() => {
    if (typeof window === "undefined") return 160;
    return ref.current?.getBoundingClientRect().width ?? 160;
  });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      setWidth(entry.contentRect.width);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);

  return width;
}
```

- [ ] **Step 2: Create the screener-grid component**

Create `frontend/src/components/screener-grid.tsx`:

```typescript
"use client";

import { useRef } from "react";
import { useRouter } from "next/navigation";
import { Skeleton } from "@/components/ui/skeleton";
import { ScoreBadge } from "@/components/score-badge";
import { SignalBadge } from "@/components/signal-badge";
import { Sparkline } from "@/components/sparkline";
import { formatPercent } from "@/lib/format";
import { scoreToSentiment } from "@/lib/signals";
import { useContainerWidth } from "@/hooks/use-container-width";
import { cn } from "@/lib/utils";
import type { BulkSignalItem } from "@/types/api";

// ── Stock card ────────────────────────────────────────────────────────────────

function StockCard({ item }: { item: BulkSignalItem }) {
  const router = useRouter();
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chartWidth = useContainerWidth(chartRef);
  const sentiment = scoreToSentiment(item.composite_score);

  return (
    <div
      className="group rounded-lg border bg-card overflow-hidden cursor-pointer hover:border-primary/50 transition-colors"
      onClick={() => router.push(`/stocks/${item.ticker}`)}
      role="button"
      tabIndex={0}
      aria-label={`View ${item.ticker} — ${item.name}`}
      onKeyDown={(e) => e.key === "Enter" && router.push(`/stocks/${item.ticker}`)}
    >
      {/* Sparkline — full-width top half */}
      <div ref={chartRef} className="w-full border-b border-border/50">
        {item.price_history && item.price_history.length >= 2 ? (
          <Sparkline
            data={item.price_history}
            width={chartWidth}
            height={56}
            sentiment={sentiment}
          />
        ) : (
          <div className="h-14 bg-muted/30" />
        )}
      </div>

      {/* Meta row */}
      <div className="px-3 py-2 flex items-center justify-between gap-2">
        {/* Left: ticker + name + signal badges */}
        <div className="min-w-0">
          <div className="flex items-baseline gap-1.5">
            <span className="font-mono font-semibold text-sm tracking-wide">
              {item.ticker}
            </span>
            <span className="text-[10px] text-muted-foreground truncate max-w-[100px]">
              {item.name}
            </span>
          </div>
          <div className="flex gap-1 mt-1 flex-wrap">
            {item.rsi_signal && (
              <SignalBadge signal={item.rsi_signal} type="rsi" />
            )}
            {item.macd_signal && (
              <SignalBadge signal={item.macd_signal} type="macd" />
            )}
            {item.sma_signal && (
              <SignalBadge signal={item.sma_signal} type="sma" />
            )}
          </div>
        </div>

        {/* Right: annual return + score */}
        <div className="text-right flex-shrink-0">
          {item.annual_return !== null && (
            <div
              className={cn(
                "text-[10px] font-medium tabular-nums",
                item.annual_return >= 0 ? "text-gain" : "text-loss"
              )}
            >
              {item.annual_return >= 0 ? "+" : ""}
              {formatPercent(item.annual_return)}
            </div>
          )}
          <div className="mt-0.5">
            <ScoreBadge score={item.composite_score} size="sm" />
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Loading skeleton ──────────────────────────────────────────────────────────

function StockCardSkeleton() {
  return (
    <div className="rounded-lg border bg-card overflow-hidden">
      <Skeleton className="h-14 w-full rounded-none" />
      <div className="px-3 py-2 space-y-2">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-3 w-16" />
      </div>
    </div>
  );
}

// ── Grid ──────────────────────────────────────────────────────────────────────

interface ScreenerGridProps {
  items: BulkSignalItem[];
  isLoading: boolean;
}

export function ScreenerGrid({ items, isLoading }: ScreenerGridProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
        {Array.from({ length: 10 }).map((_, i) => (
          <StockCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
      {items.map((item) => (
        <StockCard key={item.ticker} item={item} />
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Run TypeScript check**

```bash
cd frontend && npm run build 2>&1 | tail -30
```

Expected: no errors.

---

### Task 6: Add view mode toggle to screener page

**Files:**
- Modify: `frontend/src/app/(authenticated)/screener/page.tsx`

- [ ] **Step 1: Update imports**

In `screener/page.tsx`, the existing lucide import at line 5 is:

```typescript
import { FilterIcon, AlignJustifyIcon, LayoutListIcon } from "lucide-react";
```

Add `LayoutGridIcon` to the same import (do not add a second lucide import line):

```typescript
import { FilterIcon, AlignJustifyIcon, LayoutListIcon, LayoutGridIcon } from "lucide-react";
```

Also add the `ScreenerGrid` import:

```typescript
import { ScreenerGrid } from "@/components/screener-grid";
```

- [ ] **Step 2: Add `viewMode` state to `ScreenerContent`**

Inside `ScreenerContent()`, after the `activeTab` state, add:

```typescript
const [viewMode, setViewMode] = useState<"table" | "grid">("table");
```

- [ ] **Step 3: Add `ViewModeToggle` component**

Add this component inside `screener/page.tsx` (alongside `DensityToggle`):

```typescript
function ViewModeToggle({
  viewMode,
  onChange,
}: {
  viewMode: "table" | "grid";
  onChange: (mode: "table" | "grid") => void;
}) {
  return (
    <Button
      variant="ghost"
      size="sm"
      className="h-8 w-8 p-0"
      onClick={() => onChange(viewMode === "table" ? "grid" : "table")}
      aria-label={`Switch to ${viewMode === "table" ? "grid" : "table"} view`}
    >
      {viewMode === "table" ? (
        <LayoutGridIcon className="size-4" />
      ) : (
        <LayoutListIcon className="size-4" />
      )}
    </Button>
  );
}
```

- [ ] **Step 4: Update the header toolbar**

In `ScreenerContent`, change the header `div` from:

```tsx
<div className="flex items-center justify-between">
  <h1 className="text-2xl font-semibold tracking-tight">Screener</h1>
  <DensityToggle />
</div>
```

To:

```tsx
<div className="flex items-center justify-between">
  <h1 className="text-2xl font-semibold tracking-tight">Screener</h1>
  <div className="flex items-center gap-1">
    {viewMode === "table" && <DensityToggle />}
    <ViewModeToggle viewMode={viewMode} onChange={setViewMode} />
  </div>
</div>
```

- [ ] **Step 5: Conditionally render table or grid**

Replace the current render block (where `ScreenerTable` is rendered) with:

```tsx
{!isLoading && data && data.items.length === 0 ? (
  <EmptyState
    icon={FilterIcon}
    title="No stocks match your filters"
    description="Try broadening your search criteria"
  />
) : viewMode === "grid" ? (
  <ScreenerGrid items={data?.items ?? []} isLoading={isLoading} />
) : (
  <>
    <ScreenerTable
      items={data?.items ?? []}
      sortBy={sortBy}
      sortOrder={sortOrder}
      onSort={handleSort}
      isLoading={isLoading}
      activeTab={activeTab}
      onTabChange={setActiveTab}
    />
  </>
)}
{data && data.total > 0 && (
  <PaginationControls
    page={page}
    pageSize={PAGE_SIZE}
    total={data.total}
    onPageChange={handlePageChange}
  />
)}
```

Note: Move `PaginationControls` outside the conditional so it renders in both views. Remove the inner fragment wrapper from the table branch since pagination is now unconditional.

- [ ] **Step 6: Run lint and build**

```bash
cd frontend && npm run lint && npm run build 2>&1 | tail -30
```

Expected: zero errors, all routes generated.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/use-container-width.ts frontend/src/types/api.ts frontend/src/components/screener-grid.tsx frontend/src/app/(authenticated)/screener/page.tsx
git commit -m "feat: add screener grid view with sparkline cards and view mode toggle"
```

---

## Chunk 3: Final verification

### Task 7: Full test suite + PROGRESS.md update

- [ ] **Step 1: Run full backend test suite**

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: all tests pass (≥148 tests, 1 new from Task 3).

- [ ] **Step 2: Run frontend lint + build**

```bash
cd frontend && npm run lint && npm run build
```

Expected: zero errors.

- [ ] **Step 3: Update PROGRESS.md**

Add a Session 11 entry covering:
- Backend: `price_history` field added to bulk signals endpoint + test
- Frontend: `screener-grid.tsx` created, `screener/page.tsx` updated with view toggle
- Test count: 148 backend / 75 frontend unit
- Next: Phase 3 planning (agent/chat interface, portfolio tracking)

- [ ] **Step 4: Update Serena project memory**

Update `project_overview` memory via `edit_memory`:
- Current state: Session 11 complete, chart grid view done, all Phase 2.5 deferred items complete
- Resume point: Phase 3 planning

- [ ] **Step 5: Final commit**

```bash
git add PROGRESS.md
git commit -m "docs: Session 11 progress — screener grid view complete"
```
