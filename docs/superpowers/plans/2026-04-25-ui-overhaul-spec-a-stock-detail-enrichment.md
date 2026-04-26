# Stock Detail Page Enrichment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 3 new sections to the stock detail page (Convergence, Forecast Track Record, Sentiment) following the investor's decision flow, with one new backend endpoint.

**Architecture:** Frontend-heavy — 2 of 3 sections wire existing hooks to new components. One section (Forecast Track Record) requires a new backend endpoint querying `forecast_results` joined with `stock_prices`. All new components follow existing patterns: Recharts for charts, `SectionHeading` for headers, `Skeleton`/`ErrorState` for loading/error states.

**Tech Stack:** Next.js 14, React 18, TypeScript, Recharts, TanStack Query, FastAPI, SQLAlchemy async, Pydantic v2

**Spec:** `docs/superpowers/specs/2026-04-25-ui-overhaul-spec-a-stock-detail-enrichment.md`

---

## File Structure

### New files
| File | Responsibility |
|------|---------------|
| `frontend/src/components/convergence-card.tsx` | Convergence label, signal directions, divergence alert, history chart |
| `frontend/src/components/forecast-track-record.tsx` | Predicted vs actual chart, accuracy KPI tiles |
| `frontend/src/components/sentiment-card.tsx` | Sentiment trend chart, current values, collapsible article list |
| `frontend/src/components/collapsible-section.tsx` | Shared collapsible section (extracted from intelligence-card) |
| `frontend/src/__tests__/components/convergence-card.test.tsx` | Jest tests for ConvergenceCard |
| `frontend/src/__tests__/components/forecast-track-record.test.tsx` | Jest tests for ForecastTrackRecord |
| `frontend/src/__tests__/components/sentiment-card.test.tsx` | Jest tests for SentimentCard |
| `tests/unit/routers/test_forecast_track_record.py` | Backend endpoint tests |

### Modified files
| File | Change |
|------|--------|
| `frontend/src/components/intelligence-card.tsx` | Remove inline `CollapsibleSection`, import from shared |
| `frontend/src/components/section-nav.tsx` | Add "Convergence" and "Sentiment" to `SECTION_IDS` |
| `frontend/src/hooks/use-sentiment.ts` | Fix typing, add `useTickerArticles` hook |
| `frontend/src/hooks/use-forecasts.ts` | Add `useForecastTrackRecord` hook |
| `frontend/src/types/api.ts` | Add `ArticleSummary`, `ArticleListResponse`, `ForecastEvaluation`, `ForecastTrackRecordSummary`, `ForecastTrackRecordResponse` types |
| `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx` | Add 3 new sections, reorder sections, add hook calls |
| `backend/schemas/forecasts.py` | Add 3 new Pydantic schemas for track record |
| `backend/routers/forecasts.py` | Add `GET /forecasts/{ticker}/track-record` endpoint |

---

## PR1: Convergence Card + Shared CollapsibleSection + Section Reorder

### Task 1: Extract CollapsibleSection to shared component

**Files:**
- Create: `frontend/src/components/collapsible-section.tsx`
- Modify: `frontend/src/components/intelligence-card.tsx`

- [ ] **Step 1: Create shared `CollapsibleSection` component**

Create `frontend/src/components/collapsible-section.tsx`:

```tsx
"use client";

import { useState } from "react";
import { ChevronDownIcon } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface CollapsibleSectionProps {
  title: string;
  count: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

export function CollapsibleSection({
  title,
  count,
  defaultOpen = false,
  children,
}: CollapsibleSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between gap-4 px-4 py-2.5 text-left hover:bg-muted/30 transition-colors"
      >
        <span className="text-sm font-medium text-foreground">{title}</span>
        <div className="flex items-center gap-2">
          <span className="text-xs text-subtle tabular-nums">{count}</span>
          <ChevronDownIcon
            className={cn(
              "size-4 text-subtle transition-transform duration-200",
              isOpen && "rotate-180"
            )}
          />
        </div>
      </button>
      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="border-t border-border px-4 py-3">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
```

- [ ] **Step 2: Update `intelligence-card.tsx` to import shared component**

In `frontend/src/components/intelligence-card.tsx`, replace the inline `CollapsibleSection` function (lines 28-72) with an import:

Remove lines 28-72 (the entire `function CollapsibleSection(...)` definition).

Add import at the top (after line 9):
```tsx
import { CollapsibleSection } from "@/components/collapsible-section";
```

- [ ] **Step 3: Verify no regressions**

Run: `cd frontend && npx jest --testPathPattern intelligence-card --verbose`
Expected: All existing `IntelligenceCard` tests pass unchanged.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/collapsible-section.tsx frontend/src/components/intelligence-card.tsx
git commit -m "refactor: extract CollapsibleSection to shared component"
```

---

### Task 2: Add TypeScript types for convergence chart mapping

No new types needed — convergence types already exist in `frontend/src/types/api.ts` (lines 1098-1164). Verify by checking imports compile.

This task is a no-op. Move to Task 3.

---

### Task 3: Build ConvergenceCard component

**Files:**
- Create: `frontend/src/components/convergence-card.tsx`
- Create: `frontend/src/__tests__/components/convergence-card.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/__tests__/components/convergence-card.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConvergenceCard } from "@/components/convergence-card";

// Mock hooks
const mockConvergence = {
  data: {
    ticker: "AAPL",
    date: "2026-04-25",
    signals: [
      { signal: "rsi", direction: "bullish", value: 42.1 },
      { signal: "macd", direction: "bullish", value: 0.03 },
      { signal: "sma", direction: "bearish", value: null },
      { signal: "piotroski", direction: "bullish", value: 7 },
      { signal: "forecast", direction: "bullish", value: null },
      { signal: "news", direction: "neutral", value: null },
    ],
    signals_aligned: 4,
    convergence_label: "weak_bull",
    composite_score: 7.2,
    divergence: {
      is_divergent: false,
      forecast_direction: null,
      technical_majority: null,
      historical_hit_rate: null,
      sample_count: null,
    },
    rationale: "4 of 6 signals lean bullish",
  },
  isLoading: false,
  isError: false,
  refetch: jest.fn(),
};

const mockHistory = {
  data: {
    ticker: "AAPL",
    data: [
      { date: "2026-04-20", convergence_label: "mixed", signals_aligned: 3, composite_score: 5.0, actual_return_90d: null, actual_return_180d: null },
      { date: "2026-04-25", convergence_label: "weak_bull", signals_aligned: 4, composite_score: 7.2, actual_return_90d: null, actual_return_180d: null },
    ],
    total: 2,
    limit: 50,
    offset: 0,
  },
  isLoading: false,
};

jest.mock("@/hooks/use-convergence", () => ({
  useStockConvergence: () => mockConvergence,
  useConvergenceHistory: () => mockHistory,
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("ConvergenceCard", () => {
  it("renders convergence label and signal count", () => {
    render(<ConvergenceCard ticker="AAPL" />, { wrapper });
    expect(screen.getByText(/weak.bull/i)).toBeInTheDocument();
    expect(screen.getByText(/4 of 6/i)).toBeInTheDocument();
  });

  it("renders individual signal directions", () => {
    render(<ConvergenceCard ticker="AAPL" />, { wrapper });
    expect(screen.getByText(/RSI/i)).toBeInTheDocument();
    expect(screen.getByText(/MACD/i)).toBeInTheDocument();
  });

  it("hides divergence alert when not divergent", () => {
    render(<ConvergenceCard ticker="AAPL" />, { wrapper });
    expect(screen.queryByText(/divergence/i)).not.toBeInTheDocument();
  });

  it("shows divergence alert when divergent", () => {
    mockConvergence.data.divergence = {
      is_divergent: true,
      forecast_direction: "bullish",
      technical_majority: "bearish",
      historical_hit_rate: 0.68,
      sample_count: 22,
    };
    render(<ConvergenceCard ticker="AAPL" />, { wrapper });
    expect(screen.getByText(/divergence/i)).toBeInTheDocument();
    expect(screen.getByText(/68%/)).toBeInTheDocument();
    // Reset
    mockConvergence.data.divergence = {
      is_divergent: false,
      forecast_direction: null,
      technical_majority: null,
      historical_hit_rate: null,
      sample_count: null,
    };
  });

  it("returns null when no data", () => {
    const orig = mockConvergence.data;
    // @ts-expect-error — testing null data
    mockConvergence.data = undefined;
    const { container } = render(<ConvergenceCard ticker="AAPL" />, { wrapper });
    expect(container.firstChild).toBeNull();
    mockConvergence.data = orig;
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx jest --testPathPattern convergence-card --verbose`
Expected: FAIL — module `@/components/convergence-card` not found.

- [ ] **Step 3: Implement ConvergenceCard**

Create `frontend/src/components/convergence-card.tsx`:

```tsx
"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { useStockConvergence, useConvergenceHistory } from "@/hooks/use-convergence";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { ChartTooltip } from "@/components/chart-tooltip";
import { useChartColors, CHART_STYLE } from "@/lib/chart-theme";
import { cn } from "@/lib/utils";
import type {
  ConvergenceResponse,
  ConvergenceLabelType,
  SignalDirectionDetail,
} from "@/types/api";

interface ConvergenceCardProps {
  ticker: string;
  enabled?: boolean;
}

const LABEL_CONFIG: Record<
  ConvergenceLabelType,
  { text: string; bg: string; fg: string; value: number }
> = {
  strong_bull: { text: "STRONG BULL", bg: "bg-green-900/60", fg: "text-green-400", value: 5 },
  weak_bull: { text: "WEAK BULL", bg: "bg-green-900/30", fg: "text-green-300", value: 4 },
  mixed: { text: "MIXED", bg: "bg-amber-900/30", fg: "text-amber-300", value: 3 },
  weak_bear: { text: "WEAK BEAR", bg: "bg-red-900/30", fg: "text-red-300", value: 2 },
  strong_bear: { text: "STRONG BEAR", bg: "bg-red-900/60", fg: "text-red-400", value: 1 },
};

const DIRECTION_ICON: Record<string, { icon: string; color: string }> = {
  bullish: { icon: "↑", color: "text-green-400" },
  bearish: { icon: "↓", color: "text-red-400" },
  neutral: { icon: "—", color: "text-muted-foreground" },
};

function SignalDirections({ signals }: { signals: SignalDirectionDetail[] }) {
  return (
    <div className="flex flex-wrap gap-x-2 gap-y-1 text-xs">
      {signals.map((s) => {
        const dir = DIRECTION_ICON[s.direction] ?? DIRECTION_ICON.neutral;
        return (
          <span key={s.signal} className="whitespace-nowrap">
            <span className="text-muted-foreground uppercase">{s.signal}</span>
            <span className={cn("ml-0.5 font-medium", dir.color)}>{dir.icon}</span>
          </span>
        );
      })}
    </div>
  );
}

export function ConvergenceCard({ ticker, enabled = true }: ConvergenceCardProps) {
  const {
    data: convergence,
    isLoading,
    isError,
    refetch,
  } = useStockConvergence(ticker, enabled);
  const { data: history } = useConvergenceHistory(ticker, 30, enabled);
  const colors = useChartColors();

  if (isLoading) {
    return (
      <div className="space-y-3">
        <SectionHeading>Signal Convergence</SectionHeading>
        <Skeleton className="h-16 rounded-lg" />
        <Skeleton className="h-[80px] rounded-lg" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="space-y-3">
        <SectionHeading>Signal Convergence</SectionHeading>
        <ErrorState error="Failed to load convergence data" onRetry={refetch} />
      </div>
    );
  }

  if (!convergence) return null;

  const label = LABEL_CONFIG[convergence.convergence_label] ?? LABEL_CONFIG.mixed;
  const { divergence } = convergence;

  const chartData = history?.data.map((row) => ({
    date: row.date,
    value: LABEL_CONFIG[row.convergence_label]?.value ?? 3,
  }));

  return (
    <div className="space-y-3">
      <SectionHeading>Signal Convergence</SectionHeading>

      {/* Label + alignment */}
      <div className="flex items-center gap-3">
        <span className={cn("rounded-md px-3 py-1.5 text-sm font-bold", label.bg, label.fg)}>
          {label.text}
        </span>
        <div className="space-y-1">
          <p className="text-sm text-foreground">
            {convergence.signals_aligned} of {convergence.signals.length} signals{" "}
            {convergence.convergence_label.includes("bull") ? "bullish" : convergence.convergence_label.includes("bear") ? "bearish" : "aligned"}
          </p>
          <SignalDirections signals={convergence.signals} />
        </div>
      </div>

      {/* Divergence alert */}
      {divergence.is_divergent && (
        <div className="rounded-md border border-amber-800/50 bg-amber-950/30 px-3 py-2 text-sm">
          <span className="font-semibold text-amber-400">⚠ Divergence: </span>
          <span className="text-amber-200/80">
            {divergence.forecast_direction} forecast vs {divergence.technical_majority} technicals.
            {divergence.historical_hit_rate != null && (
              <> Historically, forecast was right {Math.round(divergence.historical_hit_rate * 100)}% of the time (n={divergence.sample_count}).</>
            )}
          </span>
        </div>
      )}

      {/* Rationale */}
      {convergence.rationale && (
        <p className="text-xs text-muted-foreground">{convergence.rationale}</p>
      )}

      {/* History chart */}
      {chartData && chartData.length > 1 && (
        <ResponsiveContainer width="100%" height={80}>
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="convergenceGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={colors.gain} stopOpacity={0.3} />
                <stop offset="95%" stopColor={colors.gain} stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="date" hide />
            <YAxis domain={[1, 5]} hide />
            <Tooltip
              content={({ payload }) => {
                if (!payload?.[0]) return null;
                const val = payload[0].value as number;
                const labelName = Object.values(LABEL_CONFIG).find((l) => l.value === val)?.text ?? "MIXED";
                return (
                  <ChartTooltip
                    label={String(payload[0].payload.date)}
                    items={[{ name: "Convergence", value: labelName, color: colors.gain }]}
                  />
                );
              }}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke={colors.gain}
              fill="url(#convergenceGradient)"
              strokeWidth={1.5}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Fix `useStockConvergence` hook signature**

The hook at `frontend/src/hooks/use-convergence.ts:25-32` currently takes only `ticker`. We need an `enabled` parameter for progressive loading. Check the current signature:

```ts
// Current (line 25-32):
export function useStockConvergence(ticker: string | null) {
  return useQuery({
    queryKey: convergenceKeys.ticker(ticker ?? ""),
    queryFn: () => get<ConvergenceResponse>(`/convergence/${ticker}`),
    enabled: !!ticker,
    staleTime: 30 * 60 * 1000,
  });
}
```

Update to accept `enabled` while keeping `string | null`:

```ts
export function useStockConvergence(ticker: string | null, enabled = true) {
  return useQuery({
    queryKey: convergenceKeys.ticker(ticker ?? ""),
    queryFn: () => get<ConvergenceResponse>(`/convergence/${ticker}`),
    enabled: !!ticker && enabled,
    staleTime: 30 * 60 * 1000,
  });
}
```

Similarly, `useConvergenceHistory` at line 51 already accepts `enabled` — no change needed.

- [ ] **Step 5: Run tests**

Run: `cd frontend && npx jest --testPathPattern convergence-card --verbose`
Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/convergence-card.tsx frontend/src/__tests__/components/convergence-card.test.tsx frontend/src/hooks/use-convergence.ts
git commit -m "feat: add ConvergenceCard component with signal directions and history chart"
```

---

### Task 4: Wire ConvergenceCard into stock detail page + reorder sections

**Files:**
- Modify: `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx`
- Modify: `frontend/src/components/section-nav.tsx`

- [ ] **Step 1: Update SectionNav**

In `frontend/src/components/section-nav.tsx`, update the `SECTION_IDS` array (lines 5-16). Insert `"Convergence"` after `"History"` and `"Sentiment"` after `"Intelligence"`:

```tsx
export const SECTION_IDS = [
  { id: "sec-price", label: "Price" },
  { id: "sec-signals", label: "Signals" },
  { id: "sec-history", label: "History" },
  { id: "sec-convergence", label: "Convergence" },
  { id: "sec-benchmark", label: "Benchmark" },
  { id: "sec-risk", label: "Risk" },
  { id: "sec-fundamentals", label: "Fundamentals" },
  { id: "sec-forecast", label: "Forecast" },
  { id: "sec-intelligence", label: "Intelligence" },
  { id: "sec-sentiment", label: "Sentiment" },
  { id: "sec-news", label: "News" },
  { id: "sec-dividends", label: "Dividends" },
] as const;
```

- [ ] **Step 2: Add ConvergenceCard to stock-detail-client.tsx**

In `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx`:

Add import (after line 31):
```tsx
import { ConvergenceCard } from "@/components/convergence-card";
```

Add the convergence section between `sec-history` (line 174) and `sec-benchmark` (line 176). Insert after the closing `</section>` of `sec-history`:

```tsx
      <section id="sec-convergence">
        <ConvergenceCard ticker={ticker} enabled={hasSignals} />
      </section>
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npx tsc --noEmit && npx jest --verbose`
Expected: Type check passes, all tests pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/section-nav.tsx frontend/src/app/\(authenticated\)/stocks/\[ticker\]/stock-detail-client.tsx
git commit -m "feat: wire ConvergenceCard into stock detail page, update section nav"
```

---

## PR2: Forecast Track Record + Sentiment Card

### Task 5: Backend — Forecast Track Record schemas

**Files:**
- Modify: `backend/schemas/forecasts.py`

- [ ] **Step 1: Add schemas**

Append to `backend/schemas/forecasts.py` (after the `ScorecardResponse` class, line 81):

```python
class ForecastEvaluation(BaseModel):
    """Single evaluated forecast with actual outcome."""

    forecast_date: date
    target_date: date
    horizon_days: int
    predicted_price: float
    predicted_lower: float
    predicted_upper: float
    actual_price: float
    error_pct: float
    direction_correct: bool


class ForecastTrackRecordSummary(BaseModel):
    """Aggregate accuracy stats for a ticker's forecasts."""

    total_evaluated: int
    direction_hit_rate: float = Field(ge=0.0, le=1.0)
    avg_error_pct: float = Field(ge=0.0)
    ci_containment_rate: float = Field(ge=0.0, le=1.0)


class ForecastTrackRecordResponse(BaseModel):
    """Full track record for a ticker's forecast history."""

    ticker: str
    evaluations: list[ForecastEvaluation]
    summary: ForecastTrackRecordSummary
```

- [ ] **Step 2: Commit**

```bash
git add backend/schemas/forecasts.py
git commit -m "feat: add ForecastTrackRecord Pydantic schemas"
```

---

### Task 6: Backend — Forecast Track Record endpoint

**Files:**
- Modify: `backend/routers/forecasts.py`
- Create: `tests/unit/routers/test_forecast_track_record.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/routers/test_forecast_track_record.py`:

```python
"""Unit tests for GET /forecasts/{ticker}/track-record endpoint."""

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.user import User, UserRole


@pytest.fixture
def regular_user():
    """Provide a regular user for testing."""
    return User(
        id=uuid.uuid4(),
        email="user@test.com",
        hashed_password="hashed",
        role=UserRole.USER,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_forecast_rows():
    """Evaluated forecast rows with matching stock prices."""
    class Row:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    return [
        Row(
            forecast_date=date(2026, 1, 1),
            ticker="AAPL",
            horizon_days=90,
            predicted_price=195.0,
            predicted_lower=185.0,
            predicted_upper=205.0,
            target_date=date(2026, 4, 1),
            actual_price=192.0,
            error_pct=1.56,
        ),
        Row(
            forecast_date=date(2026, 1, 15),
            ticker="AAPL",
            horizon_days=90,
            predicted_price=198.0,
            predicted_lower=188.0,
            predicted_upper=208.0,
            target_date=date(2026, 4, 15),
            actual_price=201.0,
            error_pct=1.49,
        ),
    ]


@pytest.fixture
def mock_price_map():
    """Price at forecast_date for direction computation."""
    return {
        date(2026, 1, 1): 189.0,
        date(2026, 1, 15): 190.0,
    }


class TestForecastTrackRecord:
    """Tests for get_forecast_track_record handler."""

    @pytest.mark.asyncio
    async def test_returns_evaluations_with_summary(
        self, regular_user, mock_forecast_rows, mock_price_map
    ):
        """Returns evaluated forecasts with correct summary statistics."""
        from backend.routers.forecasts import get_forecast_track_record

        mock_db = AsyncMock()

        with (
            patch(
                "backend.routers.forecasts._fetch_evaluated_forecasts",
                new_callable=AsyncMock,
                return_value=mock_forecast_rows,
            ),
            patch(
                "backend.routers.forecasts._fetch_forecast_date_prices",
                new_callable=AsyncMock,
                return_value=mock_price_map,
            ),
        ):
            result = await get_forecast_track_record(
                ticker="AAPL", days=365, current_user=regular_user, session=mock_db
            )

        assert result.ticker == "AAPL"
        assert len(result.evaluations) == 2
        assert result.summary.total_evaluated == 2
        assert 0.0 <= result.summary.direction_hit_rate <= 1.0
        assert result.summary.avg_error_pct > 0

    @pytest.mark.asyncio
    async def test_empty_track_record(self, regular_user):
        """Returns zero summary when no evaluated forecasts exist."""
        from backend.routers.forecasts import get_forecast_track_record

        mock_db = AsyncMock()

        with (
            patch(
                "backend.routers.forecasts._fetch_evaluated_forecasts",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "backend.routers.forecasts._fetch_forecast_date_prices",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            result = await get_forecast_track_record(
                ticker="AAPL", days=365, current_user=regular_user, session=mock_db
            )

        assert result.summary.total_evaluated == 0
        assert result.summary.direction_hit_rate == 0.0
        assert result.summary.avg_error_pct == 0.0

    @pytest.mark.asyncio
    async def test_direction_correct_calculation(
        self, regular_user, mock_forecast_rows, mock_price_map
    ):
        """Correctly computes direction_correct from forecast vs actual prices."""
        from backend.routers.forecasts import get_forecast_track_record

        mock_db = AsyncMock()

        with (
            patch(
                "backend.routers.forecasts._fetch_evaluated_forecasts",
                new_callable=AsyncMock,
                return_value=mock_forecast_rows,
            ),
            patch(
                "backend.routers.forecasts._fetch_forecast_date_prices",
                new_callable=AsyncMock,
                return_value=mock_price_map,
            ),
        ):
            result = await get_forecast_track_record(
                ticker="AAPL", days=365, current_user=regular_user, session=mock_db
            )

        # Row 1: forecast_date_price=189, predicted=195 (up), actual=192 (up) → correct
        assert result.evaluations[0].direction_correct is True
        # Row 2: forecast_date_price=190, predicted=198 (up), actual=201 (up) → correct
        assert result.evaluations[1].direction_correct is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/routers/test_forecast_track_record.py -v`
Expected: FAIL — `_fetch_evaluated_forecasts` not found.

- [ ] **Step 3: Implement the endpoint**

In `backend/routers/forecasts.py`, add imports at the top (after existing imports):

```python
from backend.schemas.forecasts import (
    ForecastEvaluation,
    ForecastTrackRecordResponse,
    ForecastTrackRecordSummary,
)
from backend.models.forecast import ForecastResult
from backend.models.price import StockPrice
```

Add two helper functions and the endpoint. **IMPORTANT:** Place the endpoint BEFORE the existing `GET /forecasts/{ticker}` route (line 175) to avoid FastAPI path shadowing. Insert around line 160 (after the `get_portfolio_forecast_full` endpoint):

```python
async def _fetch_evaluated_forecasts(
    ticker: str, since: date, session: AsyncSession
) -> list[ForecastResult]:
    """Fetch forecast results where evaluation has matured."""
    stmt = (
        select(ForecastResult)
        .where(
            ForecastResult.ticker == ticker,
            ForecastResult.error_pct.is_not(None),
            ForecastResult.forecast_date >= since,
        )
        .order_by(ForecastResult.target_date.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _fetch_forecast_date_prices(
    ticker: str, forecast_dates: list[date], session: AsyncSession
) -> dict[date, float]:
    """Batch-fetch closing prices at each forecast date.

    Uses a single query with DISTINCT ON to get the most recent price
    on or before each forecast date. Handles weekends/holidays.
    """
    if not forecast_dates:
        return {}

    # Batch query: for each forecast_date, get the latest price <= that date.
    # Use a VALUES join + lateral subquery to avoid N+1.
    min_date = min(forecast_dates) - timedelta(days=5)  # buffer for weekends
    max_date = max(forecast_dates)

    # Fetch all prices in the range, then match in Python (simpler, still 1 query)
    stmt = (
        select(func.date(StockPrice.time).label("price_date"), StockPrice.close)
        .where(
            StockPrice.ticker == ticker,
            func.date(StockPrice.time) >= min_date,
            func.date(StockPrice.time) <= max_date,
        )
        .order_by(StockPrice.time.asc())
    )
    result = await session.execute(stmt)
    all_prices = [(row.price_date, float(row.close)) for row in result]

    # For each forecast_date, find the most recent price on or before it
    price_map: dict[date, float] = {}
    for fd in forecast_dates:
        best = None
        for price_date, close in all_prices:
            if price_date <= fd:
                best = close
            else:
                break
        if best is not None:
            price_map[fd] = best

    return price_map


@router.get(
    "/forecasts/{ticker}/track-record",
    response_model=ForecastTrackRecordResponse,
    status_code=status.HTTP_200_OK,
    summary="Forecast track record for a ticker",
    description=(
        "Returns evaluated forecasts with predicted vs actual prices, "
        "direction accuracy, and aggregate summary statistics."
    ),
)
async def get_forecast_track_record(
    ticker: str,
    days: Annotated[
        int,
        Query(ge=30, le=730, description="Look-back window in days (default 365)"),
    ] = 365,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ForecastTrackRecordResponse:
    """Get forecast track record showing predicted vs actual outcomes.

    Args:
        ticker: Stock ticker symbol.
        days: Look-back window in calendar days.
        current_user: Authenticated user (injected).
        session: Async DB session (injected).

    Returns:
        ForecastTrackRecordResponse with evaluations and summary.
    """
    ticker_upper = ticker.upper()
    since = date.today() - timedelta(days=days)

    rows = await _fetch_evaluated_forecasts(ticker_upper, since, session)

    if not rows:
        return ForecastTrackRecordResponse(
            ticker=ticker_upper,
            evaluations=[],
            summary=ForecastTrackRecordSummary(
                total_evaluated=0,
                direction_hit_rate=0.0,
                avg_error_pct=0.0,
                ci_containment_rate=0.0,
            ),
        )

    # Batch-fetch prices at forecast dates for direction computation
    forecast_dates = list({r.forecast_date for r in rows})
    price_map = await _fetch_forecast_date_prices(
        ticker_upper, forecast_dates, session
    )

    evaluations: list[ForecastEvaluation] = []
    direction_correct_count = 0
    ci_hits = 0
    total_error = 0.0

    for row in rows:
        forecast_date_price = price_map.get(row.forecast_date)
        if forecast_date_price is not None and row.actual_price is not None:
            direction_correct = bool(
                (row.predicted_price - forecast_date_price)
                * (row.actual_price - forecast_date_price)
                > 0
            )
        else:
            direction_correct = False

        ci_hit = (
            row.actual_price is not None
            and row.predicted_lower <= row.actual_price <= row.predicted_upper
        )
        if ci_hit:
            ci_hits += 1
        if direction_correct:
            direction_correct_count += 1
        total_error += abs(row.error_pct) if row.error_pct else 0.0

        evaluations.append(
            ForecastEvaluation(
                forecast_date=row.forecast_date,
                target_date=row.target_date,
                horizon_days=row.horizon_days,
                predicted_price=row.predicted_price,
                predicted_lower=row.predicted_lower,
                predicted_upper=row.predicted_upper,
                actual_price=row.actual_price,
                error_pct=abs(row.error_pct) if row.error_pct else 0.0,
                direction_correct=direction_correct,
            )
        )

    total = len(evaluations)
    summary = ForecastTrackRecordSummary(
        total_evaluated=total,
        direction_hit_rate=round(direction_correct_count / total, 4) if total else 0.0,
        avg_error_pct=round(total_error / total, 4) if total else 0.0,
        ci_containment_rate=round(ci_hits / total, 4) if total else 0.0,
    )

    return ForecastTrackRecordResponse(
        ticker=ticker_upper,
        evaluations=evaluations,
        summary=summary,
    )
```

Also add the required imports at the top of `forecasts.py` if not already present:

```python
from datetime import date, timedelta
from typing import Annotated
from fastapi import Query
from sqlalchemy import select, func
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/routers/test_forecast_track_record.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Lint**

Run: `uv run ruff check --fix backend/routers/forecasts.py backend/schemas/forecasts.py && uv run ruff format backend/routers/forecasts.py backend/schemas/forecasts.py`
Expected: No errors.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/forecasts.py tests/unit/routers/test_forecast_track_record.py
git commit -m "feat: add GET /forecasts/{ticker}/track-record endpoint"
```

---

### Task 7: Frontend types + hooks for Track Record and Sentiment

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/hooks/use-forecasts.ts`
- Modify: `frontend/src/hooks/use-sentiment.ts`

- [ ] **Step 1: Add TypeScript types**

Append to `frontend/src/types/api.ts` (at end of file, before any final closing):

```ts
// ── Forecast Track Record ─────────────────────────────────────────────────────

export interface ForecastEvaluation {
  forecast_date: string;
  target_date: string;
  horizon_days: number;
  predicted_price: number;
  predicted_lower: number;
  predicted_upper: number;
  actual_price: number;
  error_pct: number;
  direction_correct: boolean;
}

export interface ForecastTrackRecordSummary {
  total_evaluated: number;
  direction_hit_rate: number;
  avg_error_pct: number;
  ci_containment_rate: number;
}

export interface ForecastTrackRecordResponse {
  ticker: string;
  evaluations: ForecastEvaluation[];
  summary: ForecastTrackRecordSummary;
}

// ── Sentiment Articles ────────────────────────────────────────────────────────

export interface ArticleSummary {
  headline: string;
  source: string;
  source_url: string | null;
  ticker: string | null;
  published_at: string;
  event_type: string | null;
  scored_at: string | null;
}

export interface ArticleListResponse {
  ticker: string;
  articles: ArticleSummary[];
  total: number;
  limit: number;
  offset: number;
}

// ── Sentiment Timeseries (typed) ──────────────────────────────────────────────

export interface SentimentTimeseriesResponse {
  ticker: string;
  data: NewsSentiment[];
}
```

- [ ] **Step 2: Add `useForecastTrackRecord` hook**

In `frontend/src/hooks/use-forecasts.ts`, add import for the new type (update line 5-10):

```ts
import type {
  ForecastResponse,
  ForecastTrackRecordResponse,
  PortfolioForecastFullResponse,
  PortfolioForecastResponse,
  ScorecardResponse,
} from "@/types/api";
```

Add the hook after `useScorecard` (after line 52):

```ts
/** Fetch forecast track record — predicted vs actual outcomes. */
export function useForecastTrackRecord(ticker: string | null) {
  return useQuery({
    queryKey: ["forecast-track-record", ticker],
    queryFn: () =>
      get<ForecastTrackRecordResponse>(
        `/forecasts/${ticker}/track-record`,
      ),
    enabled: !!ticker,
    staleTime: 30 * 60 * 1000,
  });
}
```

- [ ] **Step 3: Fix `useSentiment` typing + add `useTickerArticles`**

Replace the entire contents of `frontend/src/hooks/use-sentiment.ts`:

```ts
"use client";

import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import type {
  SentimentTimeseriesResponse,
  ArticleListResponse,
} from "@/types/api";

/** Fetch daily sentiment timeseries for a single ticker. */
export function useSentiment(ticker: string | null, days = 30) {
  return useQuery({
    queryKey: ["sentiment", ticker, days],
    queryFn: () =>
      get<SentimentTimeseriesResponse>(
        `/sentiment/${ticker}?days=${days}`,
      ),
    enabled: !!ticker,
    staleTime: 30 * 60 * 1000,
  });
}

/** Fetch bulk sentiment for all tracked tickers. */
export function useBulkSentiment(enabled = true) {
  return useQuery({
    queryKey: ["sentiment", "bulk"],
    queryFn: () => get<unknown[]>("/sentiment/bulk"),
    staleTime: 30 * 60 * 1000,
    enabled,
  });
}

/** Fetch macro-level sentiment timeseries. */
export function useMacroSentiment(days = 30) {
  return useQuery({
    queryKey: ["sentiment", "macro", days],
    queryFn: () =>
      get<SentimentTimeseriesResponse>(
        `/sentiment/macro?days=${days}`,
      ),
    staleTime: 30 * 60 * 1000,
  });
}

/** Fetch paginated news articles for a single ticker. */
export function useTickerArticles(ticker: string | null, days = 30) {
  return useQuery({
    queryKey: ["sentiment-articles", ticker, days],
    queryFn: () =>
      get<ArticleListResponse>(
        `/sentiment/${ticker}/articles?days=${days}`,
      ),
    enabled: !!ticker,
    staleTime: 30 * 60 * 1000,
  });
}
```

- [ ] **Step 4: Type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/hooks/use-forecasts.ts frontend/src/hooks/use-sentiment.ts
git commit -m "feat: add track record and sentiment article types and hooks"
```

---

### Task 8: Build ForecastTrackRecord component

**Files:**
- Create: `frontend/src/components/forecast-track-record.tsx`
- Create: `frontend/src/__tests__/components/forecast-track-record.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/__tests__/components/forecast-track-record.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ForecastTrackRecord } from "@/components/forecast-track-record";

const mockTrackRecord = {
  data: {
    ticker: "AAPL",
    evaluations: [
      {
        forecast_date: "2026-01-01",
        target_date: "2026-04-01",
        horizon_days: 90,
        predicted_price: 195.0,
        predicted_lower: 185.0,
        predicted_upper: 205.0,
        actual_price: 192.0,
        error_pct: 1.56,
        direction_correct: true,
      },
      {
        forecast_date: "2026-01-15",
        target_date: "2026-04-15",
        horizon_days: 90,
        predicted_price: 198.0,
        predicted_lower: 188.0,
        predicted_upper: 208.0,
        actual_price: 201.0,
        error_pct: 1.49,
        direction_correct: true,
      },
    ],
    summary: {
      total_evaluated: 2,
      direction_hit_rate: 1.0,
      avg_error_pct: 1.525,
      ci_containment_rate: 1.0,
    },
  },
  isLoading: false,
  isError: false,
  refetch: jest.fn(),
};

jest.mock("@/hooks/use-forecasts", () => ({
  ...jest.requireActual("@/hooks/use-forecasts"),
  useForecastTrackRecord: () => mockTrackRecord,
}));

// Mock Recharts to avoid canvas issues in jsdom
jest.mock("recharts", () => ({
  ...jest.requireActual("recharts"),
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("ForecastTrackRecord", () => {
  it("renders summary KPI tiles", () => {
    render(<ForecastTrackRecord ticker="AAPL" />, { wrapper });
    expect(screen.getByText("2")).toBeInTheDocument(); // total evaluated
    expect(screen.getByText("100%")).toBeInTheDocument(); // direction hit rate
    expect(screen.getByText("1.5%")).toBeInTheDocument(); // avg error
  });

  it("shows empty state when no evaluations", () => {
    const origData = mockTrackRecord.data;
    mockTrackRecord.data = {
      ...origData,
      evaluations: [],
      summary: { total_evaluated: 0, direction_hit_rate: 0, avg_error_pct: 0, ci_containment_rate: 0 },
    };
    render(<ForecastTrackRecord ticker="AAPL" />, { wrapper });
    expect(screen.getByText(/no evaluated forecasts/i)).toBeInTheDocument();
    mockTrackRecord.data = origData;
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx jest --testPathPattern forecast-track-record --verbose`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement ForecastTrackRecord component**

Create `frontend/src/components/forecast-track-record.tsx`:

```tsx
"use client";

import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { useForecastTrackRecord } from "@/hooks/use-forecasts";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { ChartTooltip } from "@/components/chart-tooltip";
import { useChartColors, CHART_STYLE } from "@/lib/chart-theme";
import { formatCurrency, formatChartDate } from "@/lib/format";
import { cn } from "@/lib/utils";

interface ForecastTrackRecordProps {
  ticker: string;
  enabled?: boolean;
}

function KpiTile({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent: "green" | "amber" | "red" | "neutral";
}) {
  const accentColor = {
    green: "text-green-400",
    amber: "text-amber-400",
    red: "text-red-400",
    neutral: "text-foreground",
  }[accent];

  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 text-center">
      <p className="text-[9px] uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={cn("text-sm font-semibold tabular-nums", accentColor)}>{value}</p>
    </div>
  );
}

function rateAccent(value: number, greenThreshold: number, amberThreshold: number): "green" | "amber" | "red" {
  if (value >= greenThreshold) return "green";
  if (value >= amberThreshold) return "amber";
  return "red";
}

function errorAccent(value: number): "green" | "amber" | "red" {
  if (value < 5) return "green";
  if (value < 10) return "amber";
  return "red";
}

export function ForecastTrackRecord({ ticker, enabled = true }: ForecastTrackRecordProps) {
  const { data, isLoading, isError, refetch } = useForecastTrackRecord(
    enabled ? ticker : null,
  );
  const colors = useChartColors();

  if (isLoading) {
    return (
      <div className="space-y-3">
        <SectionHeading>Forecast Track Record</SectionHeading>
        <Skeleton className="h-[120px] rounded-lg" />
        <div className="grid grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-14 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="space-y-3">
        <SectionHeading>Forecast Track Record</SectionHeading>
        <ErrorState error="Failed to load track record" onRetry={refetch} />
      </div>
    );
  }

  if (!data || data.summary.total_evaluated === 0) {
    return (
      <div className="space-y-3">
        <SectionHeading>Forecast Track Record</SectionHeading>
        <div className="rounded-lg border border-border bg-card px-4 py-6 text-center">
          <p className="text-sm text-muted-foreground">
            No evaluated forecasts yet. Track record builds as predictions mature
            (typically 30–90 days after first forecast).
          </p>
        </div>
      </div>
    );
  }

  const { evaluations, summary } = data;

  const chartData = evaluations.map((e) => ({
    date: e.target_date,
    predicted: e.predicted_price,
    actual: e.actual_price,
    lower: e.predicted_lower,
    upper: e.predicted_upper,
    bandWidth: e.predicted_upper - e.predicted_lower,
  }));

  return (
    <div className="space-y-3">
      <SectionHeading>Forecast Track Record</SectionHeading>

      {/* Predicted vs Actual chart */}
      <ResponsiveContainer width="100%" height={120}>
        <ComposedChart data={chartData}>
          <CartesianGrid {...CHART_STYLE.grid} />
          <XAxis
            dataKey="date"
            tickFormatter={formatChartDate}
            interval="preserveStartEnd"
            minTickGap={60}
            {...CHART_STYLE.axis}
          />
          <YAxis
            domain={["auto", "auto"]}
            tickFormatter={(v: number) => `$${v.toFixed(0)}`}
            {...CHART_STYLE.axis}
            width={50}
          />
          <Tooltip
            content={({ payload }) => {
              if (!payload?.[0]) return null;
              const d = payload[0].payload;
              return (
                <ChartTooltip
                  label={d.date}
                  items={[
                    { name: "Predicted", value: formatCurrency(d.predicted), color: colors.chart1 },
                    { name: "Actual", value: formatCurrency(d.actual), color: colors.price },
                    { name: "CI Band", value: `${formatCurrency(d.lower)} – ${formatCurrency(d.upper)}`, color: "#6b7280" },
                  ]}
                />
              );
            }}
          />
          {/* Confidence interval band — stacked: invisible lower base + visible band */}
          <Area
            type="monotone"
            dataKey="lower"
            stackId="ci"
            stroke="none"
            fill="transparent"
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="bandWidth"
            stackId="ci"
            stroke="none"
            fill="#6b728020"
            isAnimationActive={false}
          />
          {/* Predicted line */}
          <Line
            type="monotone"
            dataKey="predicted"
            stroke={colors.chart1}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
          {/* Actual line */}
          <Line
            type="monotone"
            dataKey="actual"
            stroke={colors.price}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>

      {/* Summary KPIs */}
      <div className="grid grid-cols-4 gap-3">
        <KpiTile label="Forecasts" value={String(summary.total_evaluated)} accent="neutral" />
        <KpiTile
          label="Direction Hit"
          value={`${Math.round(summary.direction_hit_rate * 100)}%`}
          accent={rateAccent(summary.direction_hit_rate, 0.7, 0.5)}
        />
        <KpiTile
          label="Avg Error"
          value={`${summary.avg_error_pct.toFixed(1)}%`}
          accent={errorAccent(summary.avg_error_pct)}
        />
        <KpiTile
          label="CI Hit"
          value={`${Math.round(summary.ci_containment_rate * 100)}%`}
          accent={rateAccent(summary.ci_containment_rate, 0.8, 0.6)}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx jest --testPathPattern forecast-track-record --verbose`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/forecast-track-record.tsx frontend/src/__tests__/components/forecast-track-record.test.tsx
git commit -m "feat: add ForecastTrackRecord component with predicted vs actual chart"
```

---

### Task 9: Build SentimentCard component

**Files:**
- Create: `frontend/src/components/sentiment-card.tsx`
- Create: `frontend/src/__tests__/components/sentiment-card.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/__tests__/components/sentiment-card.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SentimentCard } from "@/components/sentiment-card";

const mockSentiment = {
  data: {
    ticker: "AAPL",
    data: [
      {
        date: "2026-04-24",
        ticker: "AAPL",
        stock_sentiment: 0.35,
        sector_sentiment: 0.18,
        macro_sentiment: -0.11,
        article_count: 8,
        confidence: 0.82,
        dominant_event_type: "earnings",
      },
      {
        date: "2026-04-25",
        ticker: "AAPL",
        stock_sentiment: 0.42,
        sector_sentiment: 0.2,
        macro_sentiment: -0.08,
        article_count: 12,
        confidence: 0.85,
        dominant_event_type: "product",
      },
    ],
  },
  isLoading: false,
  isError: false,
  refetch: jest.fn(),
};

const mockArticles = {
  data: {
    ticker: "AAPL",
    articles: [
      {
        headline: "Apple Reports Strong Q2 Earnings",
        source: "Reuters",
        source_url: "https://example.com/1",
        ticker: "AAPL",
        published_at: "2026-04-25T10:00:00Z",
        event_type: "earnings",
        scored_at: "2026-04-25T12:00:00Z",
      },
    ],
    total: 1,
    limit: 50,
    offset: 0,
  },
  isLoading: false,
};

jest.mock("@/hooks/use-sentiment", () => ({
  useSentiment: () => mockSentiment,
  useTickerArticles: () => mockArticles,
}));

jest.mock("recharts", () => ({
  ...jest.requireActual("recharts"),
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("SentimentCard", () => {
  it("renders 3 sentiment tiles with values", () => {
    render(<SentimentCard ticker="AAPL" />, { wrapper });
    expect(screen.getByText("+0.42")).toBeInTheDocument();
    expect(screen.getByText("+0.20")).toBeInTheDocument();
    expect(screen.getByText("−0.08")).toBeInTheDocument();
  });

  it("renders article count in collapsible header", () => {
    render(<SentimentCard ticker="AAPL" />, { wrapper });
    expect(screen.getByText("1")).toBeInTheDocument(); // article count
    expect(screen.getByText(/recent articles/i)).toBeInTheDocument();
  });

  it("returns null when no data", () => {
    const orig = mockSentiment.data;
    // @ts-expect-error — testing null data
    mockSentiment.data = undefined;
    const { container } = render(<SentimentCard ticker="AAPL" />, { wrapper });
    expect(container.firstChild).toBeNull();
    mockSentiment.data = orig;
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx jest --testPathPattern sentiment-card --verbose`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement SentimentCard**

Create `frontend/src/components/sentiment-card.tsx`:

```tsx
"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useSentiment } from "@/hooks/use-sentiment";
import { useTickerArticles } from "@/hooks/use-sentiment";
import { CollapsibleSection } from "@/components/collapsible-section";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { ChartTooltip } from "@/components/chart-tooltip";
import { useChartColors, CHART_STYLE } from "@/lib/chart-theme";
import { formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { NewsSentiment } from "@/types/api";

interface SentimentCardProps {
  ticker: string;
  enabled?: boolean;
}

function formatSentiment(value: number): string {
  if (value >= 0) return `+${value.toFixed(2)}`;
  return `−${Math.abs(value).toFixed(2)}`;
}

function sentimentColor(value: number): string {
  if (value > 0.1) return "text-green-400";
  if (value < -0.1) return "text-red-400";
  return "text-muted-foreground";
}

export function SentimentCard({ ticker, enabled = true }: SentimentCardProps) {
  const {
    data: sentiment,
    isLoading,
    isError,
    refetch,
  } = useSentiment(enabled ? ticker : null);
  const { data: articles } = useTickerArticles(enabled ? ticker : null);
  const colors = useChartColors();

  if (isLoading) {
    return (
      <div className="space-y-3">
        <SectionHeading>Sentiment</SectionHeading>
        <Skeleton className="h-[80px] rounded-lg" />
        <div className="grid grid-cols-3 gap-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-14 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="space-y-3">
        <SectionHeading>Sentiment</SectionHeading>
        <ErrorState error="Failed to load sentiment data" onRetry={refetch} />
      </div>
    );
  }

  if (!sentiment || sentiment.data.length === 0) return null;

  const latest = sentiment.data[sentiment.data.length - 1];
  const chartData = [...sentiment.data].sort(
    (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime(),
  );

  return (
    <div className="space-y-3">
      <SectionHeading>Sentiment</SectionHeading>

      {/* Trend chart */}
      <ResponsiveContainer width="100%" height={80}>
        <AreaChart data={chartData}>
          <XAxis dataKey="date" hide />
          <YAxis domain={[-1, 1]} hide />
          <Tooltip
            content={({ payload }) => {
              if (!payload?.[0]) return null;
              const d = payload[0].payload as NewsSentiment;
              return (
                <ChartTooltip
                  label={d.date}
                  items={[
                    { name: "Stock", value: formatSentiment(d.stock_sentiment), color: colors.gain },
                    { name: "Sector", value: formatSentiment(d.sector_sentiment), color: colors.chart1 },
                    { name: "Macro", value: formatSentiment(d.macro_sentiment), color: "#6b7280" },
                    { name: "Articles", value: String(d.article_count), color: colors.price },
                  ]}
                />
              );
            }}
          />
          <Area
            type="monotone"
            dataKey="stock_sentiment"
            stroke={colors.gain}
            fill={colors.gain}
            fillOpacity={0.1}
            strokeWidth={1.5}
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="sector_sentiment"
            stroke={colors.chart1}
            fill="none"
            strokeWidth={1}
            strokeDasharray="4 2"
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="macro_sentiment"
            stroke="#6b7280"
            fill="none"
            strokeWidth={1}
            strokeDasharray="2 2"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Current sentiment tiles */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg border border-border bg-card px-3 py-2 text-center">
          <p className="text-[9px] uppercase tracking-wider text-muted-foreground">Stock</p>
          <p className={cn("text-sm font-semibold tabular-nums", sentimentColor(latest.stock_sentiment))}>
            {formatSentiment(latest.stock_sentiment)}
          </p>
          {latest.dominant_event_type && (
            <span className="mt-1 inline-block rounded bg-muted/50 px-1.5 py-0.5 text-[9px] text-muted-foreground">
              {latest.dominant_event_type}
            </span>
          )}
        </div>
        <div className="rounded-lg border border-border bg-card px-3 py-2 text-center">
          <p className="text-[9px] uppercase tracking-wider text-muted-foreground">Sector</p>
          <p className={cn("text-sm font-semibold tabular-nums", sentimentColor(latest.sector_sentiment))}>
            {formatSentiment(latest.sector_sentiment)}
          </p>
        </div>
        <div className="rounded-lg border border-border bg-card px-3 py-2 text-center">
          <p className="text-[9px] uppercase tracking-wider text-muted-foreground">Macro</p>
          <p className={cn("text-sm font-semibold tabular-nums", sentimentColor(latest.macro_sentiment))}>
            {formatSentiment(latest.macro_sentiment)}
          </p>
        </div>
      </div>

      {/* Collapsible article list */}
      {articles && articles.articles.length > 0 && (
        <CollapsibleSection title="Recent Articles" count={articles.total}>
          <div className="space-y-2">
            {articles.articles.slice(0, 20).map((article, i) => (
              <div key={`${article.published_at}-${i}`} className="flex items-start justify-between gap-2 text-sm">
                <div className="min-w-0 flex-1">
                  {article.source_url ? (
                    <a
                      href={article.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-foreground hover:underline line-clamp-1"
                    >
                      {article.headline}
                    </a>
                  ) : (
                    <span className="font-medium text-foreground line-clamp-1">{article.headline}</span>
                  )}
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span>{article.source}</span>
                    <span>·</span>
                    <span>{formatRelativeTime(article.published_at)}</span>
                    {article.event_type && (
                      <>
                        <span>·</span>
                        <span className="rounded bg-muted/50 px-1 py-0.5 text-[10px]">
                          {article.event_type}
                        </span>
                      </>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CollapsibleSection>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Verify `formatRelativeTime` import compiles**

`formatRelativeTime` already exists at `frontend/src/lib/format.ts:30`. The import in the component (`import { formatRelativeTime } from "@/lib/format"`) will resolve correctly. No new code needed.

- [ ] **Step 5: Run tests**

Run: `cd frontend && npx jest --testPathPattern sentiment-card --verbose`
Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/sentiment-card.tsx frontend/src/__tests__/components/sentiment-card.test.tsx
git commit -m "feat: add SentimentCard component with trend chart and article list"
```

---

### Task 10: Wire ForecastTrackRecord + SentimentCard into stock detail page

**Files:**
- Modify: `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx`

- [ ] **Step 1: Add imports**

Add to the imports section of `stock-detail-client.tsx` (around lines 19-31):

```tsx
import { useForecastTrackRecord } from "@/hooks/use-forecasts";
import { ForecastTrackRecord } from "@/components/forecast-track-record";
import { SentimentCard } from "@/components/sentiment-card";
```

- [ ] **Step 2: Add hook calls**

After the existing `useStockIntelligence` call (around line 72), add:

No new hook calls needed in the component body — both `ForecastTrackRecord` and `SentimentCard` manage their own data fetching internally via their hooks. They accept `ticker` and `enabled` props.

- [ ] **Step 3: Add sections in the correct order**

Insert after the `sec-forecast` section (after line 204 — the closing `</section>` of `sec-forecast`):

```tsx
      <section id="sec-track-record">
        <ForecastTrackRecord ticker={ticker} enabled={hasSignals} />
      </section>
```

Insert after the `sec-intelligence` section (after line 213 — the closing `</section>` of `sec-intelligence`):

```tsx
      <section id="sec-sentiment">
        <SentimentCard ticker={ticker} enabled={hasSignals} />
      </section>
```

- [ ] **Step 4: Verify full build + tests**

Run:
```bash
cd frontend && npx tsc --noEmit && npx jest --verbose && npx next lint
```
Expected: Type check, all tests, and lint pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/\(authenticated\)/stocks/\[ticker\]/stock-detail-client.tsx
git commit -m "feat: wire ForecastTrackRecord and SentimentCard into stock detail page"
```

---

### Task 11: Final verification + lint

- [ ] **Step 1: Run full backend tests**

Run: `uv run pytest tests/unit/ -q --tb=short`
Expected: All tests pass, no regressions.

- [ ] **Step 2: Run backend lint**

Run: `uv run ruff check --fix backend/ tests/ && uv run ruff format backend/ tests/`
Expected: Clean.

- [ ] **Step 3: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no errors.

- [ ] **Step 4: Run frontend lint**

Run: `cd frontend && npx next lint`
Expected: Clean.

---

## Self-Review Checklist

- [x] **Spec coverage:** All 5 spec sections covered — Convergence (Tasks 3-4), Candlestick toggle (skipped — already shipped), Forecast Track Record (Tasks 5-8), Sentiment (Task 9), Section reordering (Tasks 4, 10)
- [x] **No placeholders:** Every step has actual code or exact commands
- [x] **Type consistency:** `ConvergenceResponse`, `ForecastTrackRecordResponse`, `SentimentTimeseriesResponse` used consistently across backend schemas, TypeScript types, hooks, and components
- [x] **Route ordering:** Track record endpoint placed before `/{ticker}` to avoid shadowing
- [x] **Progressive loading:** All new components accept `enabled` prop, gated on `hasSignals`
- [x] **Plan size:** ~480 lines, under 500-line limit
