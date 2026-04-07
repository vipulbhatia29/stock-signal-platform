# Pipeline Overhaul — Spec G (Frontend Polish) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rich ingest-progress feedback, auto-polling for freshly-added tickers, ticker search in the transaction dialog, stale badges across stock detail, and cold-start guidance via WelcomeBanner.

**Architecture:** One new backend read-only endpoint (`GET /stocks/{ticker}/ingest-state`) that reads from `ticker_ingestion_state` (Spec A). Frontend gets two new components (IngestProgressToast, StalenessBadge), one new hook (`useIngestProgress`), and wiring into 5+ existing components.

**Tech Stack:** FastAPI, Pydantic, TanStack Query v5, React, shadcn/ui, sonner

**Spec:** `docs/superpowers/specs/2026-04-06-pipeline-overhaul-spec-G-frontend-polish.md`

**Depends on:** Spec A (`ticker_ingestion_state`), Spec C2/C4 (sync portfolio ingest + stale auto-refresh), Spec D3 (staleness SLA constants). Spec Z.5 and Z.6 already land the `useIngestTicker` invalidation and `WelcomeBanner` mount; G5/G6 are restated here for completeness.

---

## File Structure

```
backend/routers/stocks/data.py                                # MODIFY — add /ingest-state endpoint
backend/schemas/stock.py                                      # MODIFY — IngestStateResponse, StageInfo, StageStatus
backend/schemas/portfolio.py                                  # MODIFY — add ingestion_status to PositionWithAlerts
backend/services/portfolio/fifo.py                            # MODIFY — join ticker_ingestion_state in get_positions_with_pnl

frontend/src/types/api.ts                                     # MODIFY — IngestState, StageInfo, StageStatus, Position.ingestion_status
frontend/src/hooks/use-ingest-progress.ts                     # NEW
frontend/src/hooks/use-stocks.ts                              # MODIFY — refetchInterval on useSignals + usePositions
frontend/src/components/ingest-progress-toast.tsx             # NEW
frontend/src/components/staleness-badge.tsx                   # NEW
frontend/src/components/log-transaction-dialog.tsx            # MODIFY — TickerSearch replaces Input
frontend/src/components/signal-cards.tsx                      # MODIFY — render StalenessBadge
frontend/src/components/stock-header.tsx                      # MODIFY — render StalenessBadge
frontend/src/components/score-bar.tsx                         # MODIFY — opacity + tooltip when stale
frontend/src/components/forecast-card.tsx                     # MODIFY — age subtitle
frontend/src/components/news-card.tsx                         # MODIFY — age footer
frontend/src/app/(authenticated)/layout.tsx                   # MODIFY — use IngestProgressToast
frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx # MODIFY — IngestProgressToast on Run Analysis

tests/api/test_stock_ingest_state.py                          # NEW
frontend/src/__tests__/components/ingest-progress-toast.test.tsx # NEW
frontend/src/__tests__/components/staleness-badge.test.tsx       # NEW
frontend/src/__tests__/hooks/use-ingest-progress.test.ts         # NEW
```

---

## Task 1: G1 — Backend `/stocks/{ticker}/ingest-state` endpoint

**Files:**
- Modify: `backend/schemas/stock.py`
- Modify: `backend/routers/stocks/data.py`
- Create: `tests/api/test_stock_ingest_state.py`

- [ ] **Step 1: Add Pydantic schemas**

Append to `backend/schemas/stock.py`:

```python
from enum import Enum
from datetime import datetime


class StageStatus(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    PENDING = "pending"
    MISSING = "missing"


class StageInfo(BaseModel):
    updated_at: datetime | None = None
    status: StageStatus


class IngestStateStages(BaseModel):
    prices: StageInfo
    signals: StageInfo
    fundamentals: StageInfo
    forecast: StageInfo
    news: StageInfo
    sentiment: StageInfo
    convergence: StageInfo


class IngestStateResponse(BaseModel):
    ticker: str
    stages: IngestStateStages
    overall_status: Literal["ready", "ingesting", "stale", "missing"]
    completion_pct: int
```

- [ ] **Step 2: Add the endpoint**

Edit `backend/routers/stocks/data.py`. Add near the existing stock detail endpoints:

```python
from backend.schemas.stock import (
    IngestStateResponse,
    IngestStateStages,
    StageInfo,
    StageStatus,
)
from backend.config import settings

STAGE_SLA_HOURS: dict[str, int] = {
    "prices": 24,
    "signals": 24,
    "fundamentals": 168,
    "forecast": 48,
    "news": 12,
    "sentiment": 24,
    "convergence": 24,
}


def _classify_stage(updated_at: datetime | None, sla_hours: int) -> StageStatus:
    if updated_at is None:
        return StageStatus.MISSING
    age = datetime.now(timezone.utc) - updated_at
    if age.total_seconds() <= sla_hours * 3600:
        return StageStatus.FRESH
    if age.total_seconds() <= 2 * sla_hours * 3600:
        return StageStatus.STALE
    return StageStatus.PENDING


@router.get("/{ticker}/ingest-state", response_model=IngestStateResponse)
async def get_ingest_state(
    ticker: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> IngestStateResponse:
    """Return per-stage ingest freshness for one ticker.

    Non-admin read-only endpoint backing the ingest-progress toast and
    staleness badges on the stock detail page.
    """
    ticker = ticker.upper()
    row = (
        await db.execute(
            select(TickerIngestionState).where(TickerIngestionState.ticker == ticker)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Ticker not found")

    def _stage(attr: str, sla: int) -> StageInfo:
        ts = getattr(row, f"{attr}_updated_at", None)
        return StageInfo(updated_at=ts, status=_classify_stage(ts, sla))

    stages = IngestStateStages(
        prices=_stage("prices", STAGE_SLA_HOURS["prices"]),
        signals=_stage("signals", STAGE_SLA_HOURS["signals"]),
        fundamentals=_stage("fundamentals", STAGE_SLA_HOURS["fundamentals"]),
        forecast=_stage("forecast", STAGE_SLA_HOURS["forecast"]),
        news=_stage("news", STAGE_SLA_HOURS["news"]),
        sentiment=_stage("sentiment", STAGE_SLA_HOURS["sentiment"]),
        convergence=_stage("convergence", STAGE_SLA_HOURS["convergence"]),
    )
    fresh_count = sum(
        1 for s in stages.model_dump().values() if s["status"] == "fresh"
    )
    completion = round(fresh_count / 7 * 100)
    if fresh_count == 7:
        overall: Literal["ready", "ingesting", "stale", "missing"] = "ready"
    elif any(s["status"] == "pending" or s["status"] == "missing" for s in stages.model_dump().values()):
        overall = "ingesting"
    else:
        overall = "stale"
    return IngestStateResponse(
        ticker=ticker,
        stages=stages,
        overall_status=overall,
        completion_pct=completion,
    )
```

- [ ] **Step 3: Write API tests**

Create `tests/api/test_stock_ingest_state.py`:

```python
"""Spec G.1 — GET /stocks/{ticker}/ingest-state tests."""

from datetime import datetime, timezone, timedelta

import pytest


@pytest.mark.asyncio
async def test_ingest_state_returns_all_7_stages(authenticated_client, seed_ticker_state):
    await seed_ticker_state("AAPL", all_fresh=True)
    r = await authenticated_client.get("/api/v1/stocks/AAPL/ingest-state")
    assert r.status_code == 200
    body = r.json()
    assert set(body["stages"].keys()) == {
        "prices", "signals", "fundamentals", "forecast", "news", "sentiment", "convergence"
    }
    assert body["overall_status"] == "ready"
    assert body["completion_pct"] == 100


@pytest.mark.asyncio
async def test_ingest_state_404_for_unknown_ticker(authenticated_client):
    r = await authenticated_client.get("/api/v1/stocks/NOPE/ingest-state")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_ingest_state_overall_ingesting_when_missing_stages(
    authenticated_client, seed_ticker_state
):
    await seed_ticker_state("AAPL", stages={"prices": "fresh", "signals": None})
    r = await authenticated_client.get("/api/v1/stocks/AAPL/ingest-state")
    body = r.json()
    assert body["overall_status"] == "ingesting"
    assert body["completion_pct"] < 100
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/api/test_stock_ingest_state.py -x
```

Expected: pass.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix backend/schemas/stock.py backend/routers/stocks/data.py tests/api/test_stock_ingest_state.py
uv run ruff format backend/schemas/stock.py backend/routers/stocks/data.py tests/api/test_stock_ingest_state.py
git add backend/schemas/stock.py backend/routers/stocks/data.py tests/api/test_stock_ingest_state.py
git commit -m "feat(api): GET /stocks/{ticker}/ingest-state endpoint (Spec G.1)"
```

---

## Task 2: G1 — Frontend `useIngestProgress` hook + IngestProgressToast

**Files:**
- Modify: `frontend/src/types/api.ts`
- Create: `frontend/src/hooks/use-ingest-progress.ts`
- Create: `frontend/src/components/ingest-progress-toast.tsx`
- Create: `frontend/src/__tests__/hooks/use-ingest-progress.test.ts`
- Create: `frontend/src/__tests__/components/ingest-progress-toast.test.tsx`

- [ ] **Step 1: Add TypeScript types**

Append to `frontend/src/types/api.ts`:

```ts
export type StageStatus = "fresh" | "stale" | "pending" | "missing";

export interface StageInfo {
  updated_at: string | null;
  status: StageStatus;
}

export interface IngestState {
  ticker: string;
  stages: {
    prices: StageInfo;
    signals: StageInfo;
    fundamentals: StageInfo;
    forecast: StageInfo;
    news: StageInfo;
    sentiment: StageInfo;
    convergence: StageInfo;
  };
  overall_status: "ready" | "ingesting" | "stale" | "missing";
  completion_pct: number;
}
```

- [ ] **Step 2: Create the hook**

Create `frontend/src/hooks/use-ingest-progress.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import type { IngestState } from "@/types/api";

/**
 * Poll the backend ingest-state endpoint every 2s while status is "ingesting".
 * Stops polling once overall_status === "ready".
 */
export function useIngestProgress(ticker: string | null, enabled: boolean) {
  return useQuery<IngestState>({
    queryKey: ["ingest-state", ticker],
    queryFn: () => get<IngestState>(`/stocks/${ticker}/ingest-state`),
    enabled: enabled && !!ticker,
    refetchInterval: (q) => {
      const data = q.state.data;
      if (!data) return 2000;
      if (data.overall_status === "ready") return false;
      return 2000;
    },
    staleTime: 0,
  });
}
```

- [ ] **Step 3: Create the toast component**

Create `frontend/src/components/ingest-progress-toast.tsx`:

```tsx
"use client";

import { useEffect } from "react";
import { Check, Loader2, AlertCircle } from "lucide-react";

import { useIngestProgress } from "@/hooks/use-ingest-progress";
import type { StageInfo, StageStatus } from "@/types/api";

interface IngestProgressToastProps {
  ticker: string;
  onComplete?: () => void;
}

const STAGES = [
  "prices",
  "signals",
  "fundamentals",
  "forecast",
  "news",
  "sentiment",
  "convergence",
] as const;

function StageIcon({ status }: { status: StageStatus }) {
  if (status === "fresh") return <Check className="h-3 w-3 text-green-500" />;
  if (status === "pending" || status === "missing")
    return <Loader2 className="h-3 w-3 animate-spin text-blue-500" />;
  return <AlertCircle className="h-3 w-3 text-yellow-500" />;
}

export function IngestProgressToast({ ticker, onComplete }: IngestProgressToastProps) {
  const { data } = useIngestProgress(ticker, true);

  useEffect(() => {
    if (data?.overall_status === "ready") {
      const t = setTimeout(() => onComplete?.(), 5000);
      return () => clearTimeout(t);
    }
  }, [data?.overall_status, onComplete]);

  if (!data) return <div className="text-sm">Starting ingest for {ticker}…</div>;

  return (
    <div className="space-y-2 text-sm" data-testid="ingest-progress-toast">
      <div className="font-medium">
        {ticker} — {data.completion_pct}% complete
      </div>
      <div className="space-y-1">
        {STAGES.map((stage) => {
          const info: StageInfo = data.stages[stage];
          return (
            <div key={stage} className="flex items-center gap-2">
              <StageIcon status={info.status} />
              <span className="text-xs capitalize">{stage}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Write tests**

Create `frontend/src/__tests__/components/ingest-progress-toast.test.tsx`:

```tsx
// Jest is the test runner in this repo (see frontend/package.json jest config).
// `describe`/`it`/`expect` are globals. Use `jest.fn()` / `jest.useFakeTimers()`
// / `jest.spyOn` — do NOT import from "vitest".
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";

import { server } from "@/test-utils/msw-server";
import { IngestProgressToast } from "@/components/ingest-progress-toast";

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("IngestProgressToast", () => {
  it("renders 7 stage rows", async () => {
    server.use(
      http.get("*/stocks/AAPL/ingest-state", () =>
        HttpResponse.json({
          ticker: "AAPL",
          stages: {
            prices: { status: "fresh", updated_at: null },
            signals: { status: "pending", updated_at: null },
            fundamentals: { status: "pending", updated_at: null },
            forecast: { status: "pending", updated_at: null },
            news: { status: "pending", updated_at: null },
            sentiment: { status: "pending", updated_at: null },
            convergence: { status: "pending", updated_at: null },
          },
          overall_status: "ingesting",
          completion_pct: 14,
        }),
      ),
    );
    renderWithClient(<IngestProgressToast ticker="AAPL" />);
    await waitFor(() => {
      expect(screen.getByText(/AAPL/)).toBeInTheDocument();
      expect(screen.getAllByText(/prices|signals|fundamentals/i)).toHaveLength(3);
    });
  });

  it("calls onComplete 5s after reaching ready state", async () => {
    jest.useFakeTimers();
    const onComplete = jest.fn();
    server.use(
      http.get("*/stocks/AAPL/ingest-state", () =>
        HttpResponse.json({
          ticker: "AAPL",
          stages: {
            prices: { status: "fresh", updated_at: "2026-04-06T20:00:00Z" },
            signals: { status: "fresh", updated_at: "2026-04-06T20:00:00Z" },
            fundamentals: { status: "fresh", updated_at: "2026-04-06T20:00:00Z" },
            forecast: { status: "fresh", updated_at: "2026-04-06T20:00:00Z" },
            news: { status: "fresh", updated_at: "2026-04-06T20:00:00Z" },
            sentiment: { status: "fresh", updated_at: "2026-04-06T20:00:00Z" },
            convergence: { status: "fresh", updated_at: "2026-04-06T20:00:00Z" },
          },
          overall_status: "ready",
          completion_pct: 100,
        }),
      ),
    );
    renderWithClient(<IngestProgressToast ticker="AAPL" onComplete={onComplete} />);
    await jest.advanceTimersByTimeAsync(6000);
    expect(onComplete).toHaveBeenCalled();
    jest.useRealTimers();
  });
});
```

- [ ] **Step 5: Run tests**

```bash
cd frontend && npm test -- ingest-progress-toast use-ingest-progress
```

- [ ] **Step 6: Commit**

```bash
cd frontend && npm run lint -- --fix && cd ..
git add frontend/src/types/api.ts frontend/src/hooks/use-ingest-progress.ts frontend/src/components/ingest-progress-toast.tsx frontend/src/__tests__/components/ingest-progress-toast.test.tsx frontend/src/__tests__/hooks/use-ingest-progress.test.ts
git commit -m "feat(frontend): IngestProgressToast + useIngestProgress hook (Spec G.1)"
```

---

## Task 3: G2 — Polling on useSignals and usePositions

**Files:**
- Modify: `backend/schemas/portfolio.py`
- Modify: `backend/services/portfolio/fifo.py`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/hooks/use-stocks.ts`

- [ ] **Step 1: Backend — add ingestion_status to positions response**

Edit `backend/schemas/portfolio.py` — add field to `PositionWithAlerts`:

```python
class PositionWithAlerts(BaseModel):
    ...
    ingestion_status: Literal["ready", "ingesting", "stale", "missing"] | None = None
```

Edit `backend/services/portfolio/fifo.py:get_positions_with_pnl` — LEFT JOIN `ticker_ingestion_state` and map to `ingestion_status`. Use the same `_classify_stage` helper from the stock data router (import or move to a shared utility module `backend/services/staleness.py`).

- [ ] **Step 2: Frontend types**

Edit `frontend/src/types/api.ts` — add to `Position`:

```ts
export interface Position {
  ...
  ingestion_status?: "ready" | "ingesting" | "stale" | "missing";
}
```

- [ ] **Step 3: refetchInterval on `useSignals`**

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

(The `is_refreshing` field comes from Spec C4.)

- [ ] **Step 4: refetchInterval on `usePositions`**

In the same file (or `use-portfolio.ts`):

```ts
export function usePositions() {
  return useQuery<Position[]>({
    queryKey: ["positions"],
    queryFn: () => get<Position[]>("/portfolio/positions"),
    refetchInterval: (q) => {
      const positions = q.state.data;
      if (!positions) return false;
      return positions.some((p) => p.ingestion_status === "ingesting") ? 5000 : false;
    },
  });
}
```

- [ ] **Step 5: Tests**

Update `frontend/src/__tests__/hooks/use-stocks.test.ts` to cover:
- `useSignals` refetches every 5s while `is_refreshing: true`
- `usePositions` refetches every 5s while any position has `ingestion_status: "ingesting"`

- [ ] **Step 6: Run + commit**

```bash
uv run pytest tests/api/test_portfolio.py -x
cd frontend && npm test -- use-stocks && cd ..
uv run ruff check --fix backend/schemas/portfolio.py backend/services/portfolio/
uv run ruff format backend/schemas/portfolio.py backend/services/portfolio/
cd frontend && npm run lint -- --fix && cd ..
git add backend/schemas/portfolio.py backend/services/portfolio/fifo.py frontend/src/types/api.ts frontend/src/hooks/use-stocks.ts frontend/src/__tests__/hooks/use-stocks.test.ts
git commit -m "feat(frontend): poll signals + positions while ingesting (Spec G.2)"
```

---

## Task 4: G3 — TickerSearch in LogTransactionDialog

**Files:**
- Modify: `frontend/src/components/log-transaction-dialog.tsx`
- Modify: `frontend/src/__tests__/components/log-transaction-dialog.test.tsx`

- [ ] **Step 1: Replace the Input**

Edit `frontend/src/components/log-transaction-dialog.tsx` around lines 68-78:

```tsx
import { TickerSearch } from "@/components/ticker-search";

// ... inside the form JSX, replace the existing ticker <Input>:
<div className="space-y-2">
  <Label htmlFor="ticker">Ticker</Label>
  <TickerSearch
    onSelect={(ticker) => setForm({ ...form, ticker })}
    initialValue={form.ticker}
    placeholder="Search ticker or company name..."
  />
</div>
```

- [ ] **Step 2: Update the test**

Edit `frontend/src/__tests__/components/log-transaction-dialog.test.tsx` — replace the `Input` interaction with a `TickerSearch` interaction. Mock `TickerSearch` to a stub that exposes an `onSelect` prop for test drivers.

- [ ] **Step 3: Run + commit**

```bash
cd frontend && npm test -- log-transaction-dialog && cd ..
cd frontend && npm run lint -- --fix && cd ..
git add frontend/src/components/log-transaction-dialog.tsx frontend/src/__tests__/components/log-transaction-dialog.test.tsx
git commit -m "feat(frontend): TickerSearch in LogTransactionDialog (Spec G.3)"
```

---

## Task 5: G4 — StalenessBadge component + integration

**Files:**
- Create: `frontend/src/components/staleness-badge.tsx`
- Create: `frontend/src/__tests__/components/staleness-badge.test.tsx`
- Modify: `frontend/src/components/signal-cards.tsx`
- Modify: `frontend/src/components/stock-header.tsx`
- Modify: `frontend/src/components/score-bar.tsx`
- Modify: `frontend/src/components/forecast-card.tsx`
- Modify: `frontend/src/components/news-card.tsx`

- [ ] **Step 1: Create StalenessBadge**

Create `frontend/src/components/staleness-badge.tsx`:

```tsx
import { Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";

interface StalenessBadgeProps {
  lastUpdated: string | null;
  slaHours: number;
  refreshing?: boolean;
}

/**
 * Render a stale/refreshing badge. Returns null when within SLA.
 *
 * - Within SLA → null
 * - Over SLA, under 2x → "Stale (Nh old)" warning
 * - Over 2x SLA → "Very stale" destructive
 * - refreshing=true → "Refreshing" spinner
 */
export function StalenessBadge({ lastUpdated, slaHours, refreshing }: StalenessBadgeProps) {
  if (refreshing) {
    return (
      <Badge variant="default" data-testid="staleness-badge-refreshing">
        <Loader2 className="mr-1 h-3 w-3 animate-spin" />
        Refreshing
      </Badge>
    );
  }
  if (!lastUpdated) {
    return (
      <Badge variant="outline" data-testid="staleness-badge-none">
        No data
      </Badge>
    );
  }
  const ageHours = (Date.now() - new Date(lastUpdated).getTime()) / 3_600_000;
  if (ageHours > slaHours * 2) {
    return (
      <Badge variant="destructive" data-testid="staleness-badge-very-stale">
        Very stale ({Math.round(ageHours)}h old)
      </Badge>
    );
  }
  if (ageHours > slaHours) {
    return (
      <Badge variant="secondary" data-testid="staleness-badge-stale">
        Stale ({Math.round(ageHours)}h old)
      </Badge>
    );
  }
  return null;
}
```

- [ ] **Step 2: Unit tests**

Create `frontend/src/__tests__/components/staleness-badge.test.tsx`:

```tsx
// Jest runner — no "vitest" import. `describe`/`it`/`expect`/`beforeEach`
// are globals; use `jest.useFakeTimers()` / `jest.setSystemTime()`.
import { render, screen } from "@testing-library/react";

import { StalenessBadge } from "@/components/staleness-badge";

describe("StalenessBadge", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date("2026-04-06T20:00:00Z"));
  });

  it("returns null when within SLA", () => {
    const recent = new Date("2026-04-06T19:00:00Z").toISOString();
    const { container } = render(<StalenessBadge lastUpdated={recent} slaHours={24} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders warning when stale", () => {
    const old = new Date("2026-04-05T00:00:00Z").toISOString(); // 44h old
    render(<StalenessBadge lastUpdated={old} slaHours={24} />);
    expect(screen.getByTestId("staleness-badge-stale")).toBeInTheDocument();
  });

  it("renders destructive when 2x stale", () => {
    const veryOld = new Date("2026-04-03T00:00:00Z").toISOString(); // 92h old
    render(<StalenessBadge lastUpdated={veryOld} slaHours={24} />);
    expect(screen.getByTestId("staleness-badge-very-stale")).toBeInTheDocument();
  });

  it("renders no-data when lastUpdated is null", () => {
    render(<StalenessBadge lastUpdated={null} slaHours={24} />);
    expect(screen.getByTestId("staleness-badge-none")).toBeInTheDocument();
  });

  it("renders refreshing when refreshing=true", () => {
    render(<StalenessBadge lastUpdated={null} slaHours={24} refreshing />);
    expect(screen.getByTestId("staleness-badge-refreshing")).toBeInTheDocument();
  });

  it("calculates age hours correctly", () => {
    const twelveHoursAgo = new Date("2026-04-06T08:00:00Z").toISOString();
    const { container } = render(
      <StalenessBadge lastUpdated={twelveHoursAgo} slaHours={6} />,
    );
    expect(container.textContent).toContain("12h");
  });
});
```

- [ ] **Step 3: Integrate into 5 components**

For each of `signal-cards.tsx`, `stock-header.tsx`, `score-bar.tsx`, `forecast-card.tsx`, `news-card.tsx`:

```tsx
import { StalenessBadge } from "@/components/staleness-badge";

// Inside render, next to the relevant data point:
<StalenessBadge lastUpdated={signals.computed_at} slaHours={24} refreshing={signals.is_refreshing} />
```

Per-component details:
- `signal-cards.tsx` — badge next to each card header, sla=24
- `stock-header.tsx` — badge next to score badge, sla=24
- `score-bar.tsx` — wrap in `<div className={cn(isStale && "opacity-60")}>` + badge tooltip
- `forecast-card.tsx` — sla=168 (7 days), uses `forecast.created_at`
- `news-card.tsx` — sla=6, uses max `published_at` from articles

- [ ] **Step 4: Run tests**

```bash
cd frontend && npm test -- staleness-badge signal-cards stock-header && cd ..
```

- [ ] **Step 5: Commit**

```bash
cd frontend && npm run lint -- --fix && cd ..
git add frontend/src/components/staleness-badge.tsx frontend/src/components/signal-cards.tsx frontend/src/components/stock-header.tsx frontend/src/components/score-bar.tsx frontend/src/components/forecast-card.tsx frontend/src/components/news-card.tsx frontend/src/__tests__/components/staleness-badge.test.tsx
git commit -m "feat(frontend): StalenessBadge component + stock-detail integration (Spec G.4)"
```

---

## Task 6: G1 integration — IngestProgressToast on Run Analysis + topbar

**Files:**
- Modify: `frontend/src/app/(authenticated)/layout.tsx`
- Modify: `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx`

- [ ] **Step 1: Topbar `handleAddTicker` — swap toast.loading for IngestProgressToast**

Edit `frontend/src/app/(authenticated)/layout.tsx`:

```tsx
import { toast } from "sonner";
import { IngestProgressToast } from "@/components/ingest-progress-toast";

// inside handleAddTicker, after the addToWatchlist.mutateAsync succeeds:
const toastId = toast.custom(
  (t) => (
    <IngestProgressToast
      ticker={ticker.toUpperCase()}
      onComplete={() => toast.dismiss(t)}
    />
  ),
  { duration: Infinity },
);
```

- [ ] **Step 2: Stock detail "Run Analysis"**

Edit `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx:96-110` — replace existing loading toast with the same `IngestProgressToast` custom toast, after `useIngestTicker` mutation fires.

- [ ] **Step 3: Commit**

```bash
cd frontend && npm run lint -- --fix && npm test -- layout stock-detail-client && cd ..
git add frontend/src/app/(authenticated)/layout.tsx frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx
git commit -m "feat(frontend): IngestProgressToast wired into topbar add + Run Analysis (Spec G.1)"
```

---

## Task 7: G5 + G6 — Verify Spec Z items landed

G5 (full cache invalidation in `useIngestTicker`) and G6 (WelcomeBanner mount) are implemented in Plan Z, Tasks 5 and 6. No new work in Plan G.

- [ ] **Step 1: Confirm Z.5 is in `develop`**

```bash
uv run grep -n "intelligence" frontend/src/hooks/use-stocks.ts
```

Expected: matches the full-invalidation block from Plan Z.

- [ ] **Step 2: Confirm Z.6 is in `develop`**

```bash
uv run grep -n "WelcomeBanner" frontend/src/app/\(authenticated\)/dashboard/page.tsx
```

Expected: matches `WelcomeBanner` mount.

- [ ] **Step 3: If either is missing, open a follow-up ticket** and reference this task number.

---

## Task 8: Final full-suite sweep

- [ ] **Step 1: Backend API tests**

```bash
uv run pytest tests/api/test_stock_ingest_state.py tests/api/test_portfolio.py -q
```

- [ ] **Step 2: Frontend tests**

```bash
cd frontend && npm test && cd ..
```

- [ ] **Step 3: Lint + type check**

```bash
uv run ruff check backend/
cd frontend && npm run lint && npm run typecheck && cd ..
```

Expected: zero errors.

---

## Done Criteria

- [ ] `GET /stocks/{ticker}/ingest-state` returns 7 stages with per-stage status + overall_status + completion_pct
- [ ] `useIngestProgress` polls every 2s while ingesting, stops on ready
- [ ] `IngestProgressToast` shown on topbar add and stock-detail Run Analysis
- [ ] `useSignals` auto-refetches every 5s while `is_refreshing` is true
- [ ] `usePositions` auto-refetches every 5s while any position is `ingesting`
- [ ] `LogTransactionDialog` uses `TickerSearch` instead of free-text `Input`
- [ ] `StalenessBadge` renders in `signal-cards`, `stock-header`, `score-bar`, `forecast-card`, `news-card`
- [ ] All 26 new/modified test cases pass
