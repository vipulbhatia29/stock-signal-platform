# KAN-228: Stock Detail Page Enrichment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire 4 existing backend endpoints (news, intelligence, benchmark, candlestick OHLC) into the stock detail page with 5 new components, 4 hooks, sticky section nav, and progressive loading.

**Architecture:** All backend work is done. This is pure frontend: add missing TS types, create TanStack Query hooks with progressive `enabled` gating, build components using existing design system primitives (`SectionHeading`, `ChartTooltip`, `useChartColors`, `ErrorState`, `SectorAccordion` pattern), lazy-load `lightweight-charts` for candlestick toggle, add sticky section nav for scroll navigation.

**Tech Stack:** Next.js 14, TanStack Query, Recharts, lightweight-charts (new dep), framer-motion, shadcn/ui Table, Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-03-29-stock-detail-enrichment.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `frontend/src/types/api.ts` | Add `BenchmarkSeries`, `BenchmarkComparisonResponse` |
| Modify | `frontend/src/lib/format.ts` | Add `formatPctChange()` |
| Create | `frontend/src/lib/lightweight-chart-theme.ts` | `useLightweightChartTheme()` — CSS vars → ChartOptions |
| Modify | `frontend/src/hooks/use-stocks.ts` | Add 4 hooks: `useStockNews`, `useStockIntelligence`, `useBenchmark`, `useOHLC` |
| Create | `frontend/src/components/news-card.tsx` | News article list |
| Create | `frontend/src/components/intelligence-card.tsx` | Collapsible intelligence sub-sections |
| Create | `frontend/src/components/benchmark-chart.tsx` | Multi-line % change Recharts chart |
| Create | `frontend/src/components/candlestick-chart.tsx` | lightweight-charts wrapper |
| Create | `frontend/src/components/section-nav.tsx` | Sticky scroll navigation pills |
| Modify | `frontend/src/components/price-chart.tsx` | Line/Candle toggle + lazy import |
| Modify | `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx` | Wire everything + section `id` attrs |
| Create | `frontend/src/__tests__/components/news-card.test.tsx` | NewsCard tests |
| Create | `frontend/src/__tests__/components/intelligence-card.test.tsx` | IntelligenceCard tests |
| Create | `frontend/src/__tests__/components/benchmark-chart.test.tsx` | BenchmarkChart tests |
| Create | `frontend/src/__tests__/components/candlestick-chart.test.tsx` | CandlestickChart tests |
| Create | `frontend/src/__tests__/components/section-nav.test.tsx` | SectionNav tests |
| Create | `frontend/src/__tests__/components/price-chart.test.tsx` | PriceChart toggle tests |

---

## Task 1: Install dependency + add missing types

**Files:**
- Modify: `frontend/package.json` (via npm install)
- Modify: `frontend/src/types/api.ts` (~line 920, after `OHLCResponse`)

- [ ] **Step 1: Install lightweight-charts**

```bash
cd frontend && npm install lightweight-charts
```

- [ ] **Step 2: Add BenchmarkSeries and BenchmarkComparisonResponse to types/api.ts**

Add after the `OHLCResponse` interface (line ~920):

```ts
// ── Benchmark ─────────────────────────────────────────────────────────────────

export interface BenchmarkSeries {
  ticker: string;
  name: string;
  dates: string[];
  pct_change: number[];
}

export interface BenchmarkComparisonResponse {
  ticker: string;
  period: string;
  series: BenchmarkSeries[];
}
```

- [ ] **Step 3: Add formatPctChange to lib/format.ts**

Add at the end of `frontend/src/lib/format.ts`:

```ts
export function formatPctChange(value: number | null | undefined): string {
  if (value == null) return "—";
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}
```

- [ ] **Step 4: Verify types compile**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/types/api.ts frontend/src/lib/format.ts
git commit -m "feat(KAN-228): add lightweight-charts dep, benchmark types, formatPctChange"
```

---

## Task 2: Add 4 new hooks with progressive loading

**Files:**
- Modify: `frontend/src/hooks/use-stocks.ts` (add after `useDividends`, line ~240)

- [ ] **Step 1: Add import for new types**

At the top of `frontend/src/hooks/use-stocks.ts`, add to the existing type imports:

```ts
import type {
  // ... existing imports ...
  StockNewsResponse,
  StockIntelligenceResponse,
  BenchmarkComparisonResponse,
  OHLCResponse,
} from "@/types/api";
```

- [ ] **Step 2: Add useStockNews hook**

Add after the `useDividends` function (~line 240):

```ts
// ── Stock News ──────────────────────────────────────────────────────────────

export function useStockNews(ticker: string, enabled = true) {
  return useQuery({
    queryKey: ["stock-news", ticker],
    queryFn: () => get<StockNewsResponse>(`/stocks/${ticker}/news`),
    staleTime: 5 * 60 * 1000,
    enabled,
    retry: 1,
  });
}
```

- [ ] **Step 3: Add useStockIntelligence hook**

```ts
// ── Stock Intelligence ──────────────────────────────────────────────────────

export function useStockIntelligence(ticker: string, enabled = true) {
  return useQuery({
    queryKey: ["stock-intelligence", ticker],
    queryFn: () =>
      get<StockIntelligenceResponse>(`/stocks/${ticker}/intelligence`),
    staleTime: 5 * 60 * 1000,
    enabled,
    retry: 1,
  });
}
```

- [ ] **Step 4: Add useBenchmark hook with select transform**

```ts
// ── Benchmark Comparison ────────────────────────────────────────────────────

export interface BenchmarkDataPoint {
  date: string;
  [seriesName: string]: string | number;
}

export function useBenchmark(
  ticker: string,
  period: PricePeriod,
  enabled = true
) {
  return useQuery({
    queryKey: ["benchmark", ticker, period],
    queryFn: () =>
      get<BenchmarkComparisonResponse>(
        `/stocks/${ticker}/benchmark?period=${period}`
      ),
    staleTime: 5 * 60 * 1000,
    enabled,
    retry: 1,
    select: (data): BenchmarkDataPoint[] => {
      if (!data.series.length) return [];

      // Find common date set — use the stock's dates as base
      const stockSeries = data.series.find(
        (s) => s.ticker.toUpperCase() === ticker.toUpperCase()
      );
      if (!stockSeries) return [];

      // Build lookup maps for each series
      const seriesMaps = data.series.map((s) => {
        const map = new Map<string, number>();
        s.dates.forEach((d, i) => {
          const dateKey = d.split("T")[0]; // normalize to YYYY-MM-DD
          map.set(dateKey, s.pct_change[i]);
        });
        return { name: s.name, map };
      });

      // Build Recharts-friendly array from stock dates
      return stockSeries.dates.map((d, i) => {
        const dateKey = d.split("T")[0];
        const point: BenchmarkDataPoint = { date: dateKey };
        for (const { name, map } of seriesMaps) {
          const val = map.get(dateKey);
          if (val !== undefined) point[name] = val;
        }
        return point;
      });
    },
  });
}
```

- [ ] **Step 5: Add useOHLC hook**

```ts
// ── OHLC (Candlestick) ─────────────────────────────────────────────────────

export function useOHLC(ticker: string, period: PricePeriod, enabled = true) {
  return useQuery({
    queryKey: ["ohlc", ticker, period],
    queryFn: () =>
      get<OHLCResponse>(`/stocks/${ticker}/prices?period=${period}&format=ohlc`),
    staleTime: 5 * 60 * 1000,
    enabled,
  });
}
```

- [ ] **Step 6: Verify types compile**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/use-stocks.ts
git commit -m "feat(KAN-228): add useStockNews, useStockIntelligence, useBenchmark, useOHLC hooks"
```

---

## Task 3: NewsCard component + tests

**Files:**
- Create: `frontend/src/components/news-card.tsx`
- Create: `frontend/src/__tests__/components/news-card.test.tsx`

- [ ] **Step 1: Write the test file**

Create `frontend/src/__tests__/components/news-card.test.tsx`:

```tsx
import React from "react";
import { render, screen } from "@testing-library/react";
import { NewsCard } from "@/components/news-card";
import type { StockNewsResponse } from "@/types/api";

const mockNews: StockNewsResponse = {
  ticker: "AAPL",
  articles: [
    {
      title: "Apple announces new iPhone",
      link: "https://example.com/article1",
      publisher: "Reuters",
      published: new Date(Date.now() - 3600_000).toISOString(), // 1 hour ago
      source: "yfinance",
    },
    {
      title: "Apple beats earnings estimates",
      link: "https://example.com/article2",
      publisher: "Bloomberg",
      published: new Date(Date.now() - 86400_000).toISOString(), // 1 day ago
      source: "google_news",
    },
  ],
  fetched_at: new Date().toISOString(),
};

test("renders article titles as links", () => {
  render(<NewsCard news={mockNews} isLoading={false} />);
  const link1 = screen.getByText("Apple announces new iPhone");
  expect(link1.closest("a")).toHaveAttribute("href", "https://example.com/article1");
  expect(link1.closest("a")).toHaveAttribute("target", "_blank");
  expect(link1.closest("a")).toHaveAttribute("rel", "noopener noreferrer");
});

test("renders publisher names", () => {
  render(<NewsCard news={mockNews} isLoading={false} />);
  expect(screen.getByText("Reuters")).toBeInTheDocument();
  expect(screen.getByText("Bloomberg")).toBeInTheDocument();
});

test("renders loading skeleton", () => {
  const { container } = render(<NewsCard news={undefined} isLoading={true} />);
  expect(container.querySelectorAll("[data-slot='skeleton']").length).toBeGreaterThan(0);
});

test("renders empty state when no articles", () => {
  const emptyNews: StockNewsResponse = {
    ticker: "AAPL",
    articles: [],
    fetched_at: new Date().toISOString(),
  };
  render(<NewsCard news={emptyNews} isLoading={false} />);
  expect(screen.getByText(/no news/i)).toBeInTheDocument();
});

test("renders error state with retry", () => {
  const onRetry = jest.fn();
  render(<NewsCard news={undefined} isLoading={false} isError={true} onRetry={onRetry} />);
  expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
  expect(screen.getByText(/try again/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd frontend && npx jest --testPathPattern=news-card --verbose 2>&1 | head -20
```

Expected: FAIL — module `@/components/news-card` not found.

- [ ] **Step 3: Implement NewsCard**

Create `frontend/src/components/news-card.tsx`:

```tsx
"use client";

import { ExternalLinkIcon } from "lucide-react";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { formatRelativeTime } from "@/lib/format";
import type { StockNewsResponse } from "@/types/api";

const MAX_ARTICLES = 8;

interface NewsCardProps {
  news: StockNewsResponse | undefined;
  isLoading: boolean;
  isError?: boolean;
  onRetry?: () => void;
}

export function NewsCard({ news, isLoading, isError, onRetry }: NewsCardProps) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        <SectionHeading>News</SectionHeading>
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-12 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="space-y-4">
        <SectionHeading>News</SectionHeading>
        <ErrorState error="Failed to load news" onRetry={onRetry} />
      </div>
    );
  }

  if (!news || news.articles.length === 0) {
    return (
      <div className="space-y-4">
        <SectionHeading>News</SectionHeading>
        <p className="text-sm text-muted-foreground">
          No news available for this ticker.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <SectionHeading>News</SectionHeading>
      <ul className="space-y-2">
        {news.articles.slice(0, MAX_ARTICLES).map((article, i) => (
          <li
            key={`${article.link}-${i}`}
            className="flex items-start gap-3 rounded-lg border border-border bg-card px-3 py-2.5"
          >
            <div className="min-w-0 flex-1">
              <a
                href={article.link}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-medium text-foreground hover:text-primary transition-colors line-clamp-2"
              >
                {article.title}
              </a>
              <div className="mt-1 flex items-center gap-2 text-xs text-subtle">
                {article.publisher && (
                  <span className="font-medium text-muted-foreground">
                    {article.publisher}
                  </span>
                )}
                {article.published && (
                  <span>{formatRelativeTime(article.published)}</span>
                )}
              </div>
            </div>
            <ExternalLinkIcon className="mt-0.5 size-3.5 shrink-0 text-subtle" />
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 4: Run test — verify it passes**

```bash
cd frontend && npx jest --testPathPattern=news-card --verbose
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/news-card.tsx frontend/src/__tests__/components/news-card.test.tsx
git commit -m "feat(KAN-228): add NewsCard component with tests"
```

---

## Task 4: IntelligenceCard component + tests

**Files:**
- Create: `frontend/src/components/intelligence-card.tsx`
- Create: `frontend/src/__tests__/components/intelligence-card.test.tsx`

- [ ] **Step 1: Write the test file**

Create `frontend/src/__tests__/components/intelligence-card.test.tsx`:

```tsx
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { IntelligenceCard } from "@/components/intelligence-card";
import type { StockIntelligenceResponse } from "@/types/api";

// Mock framer-motion
jest.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => (
      <div {...props}>{children}</div>
    ),
  },
  AnimatePresence: ({ children }: React.PropsWithChildren) => <>{children}</>,
}));

const mockIntelligence: StockIntelligenceResponse = {
  ticker: "AAPL",
  upgrades_downgrades: [
    {
      firm: "Goldman Sachs",
      to_grade: "Buy",
      from_grade: "Hold",
      action: "Upgrade",
      date: "2026-03-20",
    },
  ],
  insider_transactions: [
    {
      insider_name: "Tim Cook",
      relation: "CEO",
      transaction_type: "Sale",
      shares: 50000,
      value: 9500000,
      date: "2026-03-15",
    },
  ],
  next_earnings_date: "2026-04-25",
  eps_revisions: null,
  short_interest: {
    short_percent_of_float: 0.72,
    short_ratio: 1.5,
    shares_short: 120000000,
  },
  fetched_at: new Date().toISOString(),
};

test("renders summary row with earnings date and short interest", () => {
  render(<IntelligenceCard intelligence={mockIntelligence} isLoading={false} />);
  expect(screen.getByText(/apr 25, 2026/i)).toBeInTheDocument();
  expect(screen.getByText(/0.72%/)).toBeInTheDocument();
});

test("renders analyst upgrade", () => {
  render(<IntelligenceCard intelligence={mockIntelligence} isLoading={false} />);
  // Expand the Analyst Ratings section
  const analystButton = screen.getByText(/analyst ratings/i);
  fireEvent.click(analystButton);
  expect(screen.getByText("Goldman Sachs")).toBeInTheDocument();
  expect(screen.getByText("Buy")).toBeInTheDocument();
});

test("renders insider transaction", () => {
  render(<IntelligenceCard intelligence={mockIntelligence} isLoading={false} />);
  const insiderButton = screen.getByText(/insider transactions/i);
  fireEvent.click(insiderButton);
  expect(screen.getByText("Tim Cook")).toBeInTheDocument();
  expect(screen.getByText("Sale")).toBeInTheDocument();
});

test("renders loading skeleton", () => {
  const { container } = render(
    <IntelligenceCard intelligence={undefined} isLoading={true} />
  );
  expect(container.querySelectorAll("[data-slot='skeleton']").length).toBeGreaterThan(0);
});

test("renders empty sub-sections gracefully", () => {
  const empty: StockIntelligenceResponse = {
    ...mockIntelligence,
    upgrades_downgrades: [],
    insider_transactions: [],
    short_interest: null,
    next_earnings_date: null,
  };
  render(<IntelligenceCard intelligence={empty} isLoading={false} />);
  expect(screen.getByText(/no upcoming earnings/i)).toBeInTheDocument();
});

test("renders error state with retry", () => {
  const onRetry = jest.fn();
  render(
    <IntelligenceCard
      intelligence={undefined}
      isLoading={false}
      isError={true}
      onRetry={onRetry}
    />
  );
  expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd frontend && npx jest --testPathPattern=intelligence-card --verbose 2>&1 | head -10
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement IntelligenceCard**

Create `frontend/src/components/intelligence-card.tsx`:

```tsx
"use client";

import { useState } from "react";
import { ChevronDownIcon, CalendarIcon, TrendingDownIcon } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDate, formatCurrency, formatVolume } from "@/lib/format";
import type { StockIntelligenceResponse } from "@/types/api";

interface IntelligenceCardProps {
  intelligence: StockIntelligenceResponse | undefined;
  isLoading: boolean;
  isError?: boolean;
  onRetry?: () => void;
}

function CollapsibleSection({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(false);

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

export function IntelligenceCard({
  intelligence,
  isLoading,
  isError,
  onRetry,
}: IntelligenceCardProps) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        <SectionHeading>Intelligence</SectionHeading>
        <div className="grid grid-cols-2 gap-3">
          {[1, 2].map((i) => (
            <Skeleton key={i} className="h-16 rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-12 rounded-lg" />
        <Skeleton className="h-12 rounded-lg" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="space-y-4">
        <SectionHeading>Intelligence</SectionHeading>
        <ErrorState error="Failed to load intelligence data" onRetry={onRetry} />
      </div>
    );
  }

  if (!intelligence) return null;

  const { upgrades_downgrades, insider_transactions, short_interest, next_earnings_date } =
    intelligence;

  return (
    <div className="space-y-4">
      <SectionHeading>Intelligence</SectionHeading>

      {/* Summary row — always visible */}
      <div className="grid grid-cols-2 gap-3">
        <div className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2.5">
          <CalendarIcon className="size-4 text-subtle" />
          <div>
            <p className="text-[10px] uppercase tracking-wider text-subtle">
              Next Earnings
            </p>
            <p className="text-sm font-medium text-foreground">
              {next_earnings_date
                ? formatDate(next_earnings_date)
                : "No upcoming earnings"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2.5">
          <TrendingDownIcon className="size-4 text-subtle" />
          <div>
            <p className="text-[10px] uppercase tracking-wider text-subtle">
              Short Interest
            </p>
            <p className="text-sm font-medium text-foreground">
              {short_interest
                ? `${short_interest.short_percent_of_float.toFixed(2)}%`
                : "N/A"}
            </p>
          </div>
        </div>
      </div>

      {/* Collapsible sub-sections */}
      <CollapsibleSection
        title="Analyst Ratings"
        count={upgrades_downgrades.length}
      >
        {upgrades_downgrades.length === 0 ? (
          <p className="text-sm text-muted-foreground">No recent analyst activity.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Firm</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Grade</TableHead>
                <TableHead>Date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {upgrades_downgrades.map((u, i) => (
                <TableRow key={`${u.firm}-${u.date}-${i}`}>
                  <TableCell className="font-medium">{u.firm}</TableCell>
                  <TableCell>{u.action}</TableCell>
                  <TableCell>
                    {u.from_grade ? `${u.from_grade} → ` : ""}
                    {u.to_grade}
                  </TableCell>
                  <TableCell className="text-subtle">{formatDate(u.date)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CollapsibleSection>

      <CollapsibleSection
        title="Insider Transactions"
        count={insider_transactions.length}
      >
        {insider_transactions.length === 0 ? (
          <p className="text-sm text-muted-foreground">No recent insider activity.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead className="text-right">Shares</TableHead>
                <TableHead className="text-right">Value</TableHead>
                <TableHead>Date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {insider_transactions.map((t, i) => (
                <TableRow key={`${t.insider_name}-${t.date}-${i}`}>
                  <TableCell className="font-medium">{t.insider_name}</TableCell>
                  <TableCell>{t.transaction_type}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatVolume(t.shares)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {t.value ? formatCurrency(t.value) : "—"}
                  </TableCell>
                  <TableCell className="text-subtle">{formatDate(t.date)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CollapsibleSection>

      {short_interest && (short_interest.short_ratio || short_interest.shares_short) && (
        <div className="rounded-lg border border-border bg-card px-4 py-3">
          <p className="text-sm font-medium text-foreground mb-2">Short Interest Detail</p>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <p className="text-subtle text-xs">% of Float</p>
              <p className="font-mono tabular-nums">{short_interest.short_percent_of_float.toFixed(2)}%</p>
            </div>
            {short_interest.short_ratio && (
              <div>
                <p className="text-subtle text-xs">Short Ratio</p>
                <p className="font-mono tabular-nums">{short_interest.short_ratio.toFixed(1)}</p>
              </div>
            )}
            {short_interest.shares_short && (
              <div>
                <p className="text-subtle text-xs">Shares Short</p>
                <p className="font-mono tabular-nums">{formatVolume(short_interest.shares_short)}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test — verify it passes**

```bash
cd frontend && npx jest --testPathPattern=intelligence-card --verbose
```

Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/intelligence-card.tsx frontend/src/__tests__/components/intelligence-card.test.tsx
git commit -m "feat(KAN-228): add IntelligenceCard component with collapsible sub-sections"
```

---

## Task 5: BenchmarkChart component + tests

**Files:**
- Create: `frontend/src/components/benchmark-chart.tsx`
- Create: `frontend/src/__tests__/components/benchmark-chart.test.tsx`

- [ ] **Step 1: Write the test file**

Create `frontend/src/__tests__/components/benchmark-chart.test.tsx`:

```tsx
import React from "react";
import { render, screen } from "@testing-library/react";
import { BenchmarkChart } from "@/components/benchmark-chart";
import type { BenchmarkDataPoint } from "@/hooks/use-stocks";

// Mock Recharts — jsdom doesn't have SVG layout engine
jest.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: React.PropsWithChildren) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  LineChart: ({ children }: React.PropsWithChildren) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => <div data-testid="line" />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  Tooltip: () => <div />,
  Legend: () => <div />,
  CartesianGrid: () => <div />,
}));

const mockData: BenchmarkDataPoint[] = [
  { date: "2025-01-02", AAPL: 0, "S&P 500": 0, "NASDAQ Composite": 0 },
  { date: "2025-06-15", AAPL: 15.2, "S&P 500": 8.1, "NASDAQ Composite": 12.3 },
  { date: "2025-12-31", AAPL: 25.3, "S&P 500": 14.5, "NASDAQ Composite": 18.7 },
];

test("renders chart container when data is present", () => {
  render(
    <BenchmarkChart data={mockData} isLoading={false} seriesNames={["AAPL", "S&P 500", "NASDAQ Composite"]} />
  );
  expect(screen.getByTestId("responsive-container")).toBeInTheDocument();
});

test("renders section heading", () => {
  render(
    <BenchmarkChart data={mockData} isLoading={false} seriesNames={["AAPL"]} />
  );
  expect(screen.getByText(/benchmark/i)).toBeInTheDocument();
});

test("renders loading skeleton", () => {
  const { container } = render(
    <BenchmarkChart data={undefined} isLoading={true} seriesNames={[]} />
  );
  expect(container.querySelectorAll("[data-slot='skeleton']").length).toBeGreaterThan(0);
});

test("renders error state with retry", () => {
  const onRetry = jest.fn();
  render(
    <BenchmarkChart
      data={undefined}
      isLoading={false}
      isError={true}
      onRetry={onRetry}
      seriesNames={[]}
    />
  );
  expect(screen.getByText(/try again/i)).toBeInTheDocument();
});

test("renders empty state when no data", () => {
  render(
    <BenchmarkChart data={[]} isLoading={false} seriesNames={[]} />
  );
  expect(screen.getByText(/no benchmark data/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd frontend && npx jest --testPathPattern=benchmark-chart --verbose 2>&1 | head -10
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement BenchmarkChart**

Create `frontend/src/components/benchmark-chart.tsx`:

```tsx
"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { ChartTooltip } from "@/components/chart-tooltip";
import { useChartColors, CHART_STYLE } from "@/lib/chart-theme";
import { formatChartDate, formatPctChange } from "@/lib/format";
import type { BenchmarkDataPoint } from "@/hooks/use-stocks";

// Map series index to chart color key
const SERIES_COLOR_KEYS = ["price", "chart1", "chart2"] as const;

interface BenchmarkChartProps {
  data: BenchmarkDataPoint[] | undefined;
  isLoading: boolean;
  isError?: boolean;
  onRetry?: () => void;
  seriesNames: string[];
}

export function BenchmarkChart({
  data,
  isLoading,
  isError,
  onRetry,
  seriesNames,
}: BenchmarkChartProps) {
  const colors = useChartColors();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <SectionHeading>Benchmark Comparison</SectionHeading>
        <Skeleton className="h-[250px] w-full sm:h-[350px]" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="space-y-4">
        <SectionHeading>Benchmark Comparison</SectionHeading>
        <ErrorState error="Failed to load benchmark data" onRetry={onRetry} />
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="space-y-4">
        <SectionHeading>Benchmark Comparison</SectionHeading>
        <p className="text-sm text-muted-foreground">No benchmark data available.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <SectionHeading>Benchmark Comparison</SectionHeading>
      <ResponsiveContainer width="100%" height="100%" minHeight={250} className="sm:min-h-[350px]">
        <LineChart data={data}>
          <CartesianGrid {...CHART_STYLE.grid} />
          <XAxis
            dataKey="date"
            tickFormatter={formatChartDate}
            interval="preserveStartEnd"
            minTickGap={60}
            {...CHART_STYLE.axis}
          />
          <YAxis
            tickFormatter={(v: number) => formatPctChange(v)}
            width={65}
            {...CHART_STYLE.axis}
          />
          <Tooltip
            cursor={CHART_STYLE.tooltip.cursor}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0].payload as BenchmarkDataPoint;
              return (
                <ChartTooltip
                  active={active}
                  label={formatChartDate(d.date)}
                  items={seriesNames.map((name, i) => ({
                    name,
                    value: formatPctChange(
                      typeof d[name] === "number" ? d[name] : null
                    ),
                    color: colors[SERIES_COLOR_KEYS[i] ?? "chart3"],
                  }))}
                />
              );
            }}
          />
          <Legend
            verticalAlign="top"
            height={30}
            wrapperStyle={{ fontSize: "12px" }}
          />
          {seriesNames.map((name, i) => (
            <Line
              key={name}
              type="monotone"
              dataKey={name}
              stroke={colors[SERIES_COLOR_KEYS[i] ?? "chart3"]}
              strokeWidth={i === 0 ? 2 : 1.5}
              dot={false}
              strokeDasharray={i === 0 ? undefined : "5 3"}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 4: Run test — verify it passes**

```bash
cd frontend && npx jest --testPathPattern=benchmark-chart --verbose
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/benchmark-chart.tsx frontend/src/__tests__/components/benchmark-chart.test.tsx
git commit -m "feat(KAN-228): add BenchmarkChart component with Recharts multi-line"
```

---

## Task 6: lightweight-charts theme helper + CandlestickChart + tests

**Files:**
- Create: `frontend/src/lib/lightweight-chart-theme.ts`
- Create: `frontend/src/components/candlestick-chart.tsx`
- Create: `frontend/src/__tests__/components/candlestick-chart.test.tsx`

- [ ] **Step 1: Create the theme helper**

Create `frontend/src/lib/lightweight-chart-theme.ts`:

```ts
"use client";

import { useState, useEffect } from "react";
import { CSS_VARS } from "@/lib/design-tokens";
import type { ChartOptions, DeepPartial } from "lightweight-charts";

function readCssVar(name: string): string {
  if (typeof window === "undefined") return "";
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
}

function resolveTheme(): DeepPartial<ChartOptions> {
  const bg = readCssVar(CSS_VARS.card) || "#0a0e1a";
  const fg = readCssVar(CSS_VARS.foreground) || "#e2e8f0";
  const border = readCssVar(CSS_VARS.border) || "#1e293b";
  const gain = readCssVar(CSS_VARS.gain) || "#22c55e";
  const loss = readCssVar(CSS_VARS.loss) || "#ef4444";

  return {
    layout: {
      background: { color: bg },
      textColor: fg,
      fontFamily: "var(--font-sora), system-ui, sans-serif",
      fontSize: 11,
    },
    grid: {
      vertLines: { color: border, style: 3 }, // dotted
      horzLines: { color: border, style: 3 },
    },
    crosshair: {
      vertLine: { color: fg, width: 1, style: 2 },
      horzLine: { color: fg, width: 1, style: 2 },
    },
    rightPriceScale: {
      borderColor: border,
    },
    timeScale: {
      borderColor: border,
    },
  };
}

export interface LightweightChartColors {
  up: string;
  down: string;
}

function resolveColors(): LightweightChartColors {
  return {
    up: readCssVar(CSS_VARS.gain) || "#22c55e",
    down: readCssVar(CSS_VARS.loss) || "#ef4444",
  };
}

export function useLightweightChartTheme() {
  const [theme, setTheme] = useState<DeepPartial<ChartOptions>>(() =>
    resolveTheme()
  );
  const [candleColors, setCandleColors] = useState<LightweightChartColors>(() =>
    resolveColors()
  );

  useEffect(() => {
    const observer = new MutationObserver(() => {
      setTheme(resolveTheme());
      setCandleColors(resolveColors());
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);

  return { theme, candleColors };
}
```

- [ ] **Step 2: Write the CandlestickChart test**

Create `frontend/src/__tests__/components/candlestick-chart.test.tsx`:

```tsx
import React from "react";
import { render, screen } from "@testing-library/react";

// Mock lightweight-charts — it requires a real DOM canvas
jest.mock("lightweight-charts", () => ({
  createChart: jest.fn(() => ({
    addCandlestickSeries: jest.fn(() => ({
      setData: jest.fn(),
    })),
    addHistogramSeries: jest.fn(() => ({
      setData: jest.fn(),
    })),
    applyOptions: jest.fn(),
    timeScale: jest.fn(() => ({
      fitContent: jest.fn(),
    })),
    remove: jest.fn(),
    resize: jest.fn(),
  })),
}));

// Mock the theme hook
jest.mock("@/lib/lightweight-chart-theme", () => ({
  useLightweightChartTheme: () => ({
    theme: { layout: { background: { color: "#0a0e1a" } } },
    candleColors: { up: "#22c55e", down: "#ef4444" },
  }),
}));

import { CandlestickChart } from "@/components/candlestick-chart";
import type { OHLCResponse } from "@/types/api";

const mockOHLC: OHLCResponse = {
  ticker: "AAPL",
  period: "1y",
  count: 3,
  timestamps: ["2025-01-02T00:00:00Z", "2025-01-03T00:00:00Z", "2025-01-06T00:00:00Z"],
  open: [150.0, 152.0, 151.0],
  high: [155.0, 156.0, 154.0],
  low: [149.0, 151.0, 150.0],
  close: [153.0, 154.0, 152.0],
  volume: [1000000, 1200000, 900000],
};

test("renders chart container", () => {
  render(<CandlestickChart data={mockOHLC} />);
  expect(screen.getByTestId("candlestick-container")).toBeInTheDocument();
});

test("calls createChart on mount", () => {
  const { createChart } = require("lightweight-charts");
  render(<CandlestickChart data={mockOHLC} />);
  expect(createChart).toHaveBeenCalled();
});

test("renders nothing when data is undefined", () => {
  const { container } = render(<CandlestickChart data={undefined} />);
  expect(container.querySelector("[data-testid='candlestick-container']")).toBeNull();
});
```

- [ ] **Step 3: Implement CandlestickChart**

Create `frontend/src/components/candlestick-chart.tsx`:

```tsx
"use client";

import { useRef, useEffect } from "react";
import { createChart } from "lightweight-charts";
import type { IChartApi } from "lightweight-charts";
import { useLightweightChartTheme } from "@/lib/lightweight-chart-theme";
import type { OHLCResponse } from "@/types/api";

interface CandlestickChartProps {
  data: OHLCResponse | undefined;
}

export function CandlestickChart({ data }: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const { theme, candleColors } = useLightweightChartTheme();

  useEffect(() => {
    if (!containerRef.current || !data || data.count === 0) return;

    const chart = createChart(containerRef.current, {
      ...theme,
      width: containerRef.current.clientWidth,
      height: 400,
      autoSize: true,
    });
    chartRef.current = chart;

    const candleSeries = chart.addCandlestickSeries({
      upColor: candleColors.up,
      downColor: candleColors.down,
      borderUpColor: candleColors.up,
      borderDownColor: candleColors.down,
      wickUpColor: candleColors.up,
      wickDownColor: candleColors.down,
    });

    const candles = data.timestamps.map((ts, i) => ({
      time: ts.split("T")[0] as string,
      open: data.open[i],
      high: data.high[i],
      low: data.low[i],
      close: data.close[i],
    }));
    candleSeries.setData(candles);

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    const volumes = data.timestamps.map((ts, i) => ({
      time: ts.split("T")[0] as string,
      value: data.volume[i],
      color:
        data.close[i] >= data.open[i]
          ? `${candleColors.up}40`
          : `${candleColors.down}40`,
    }));
    volumeSeries.setData(volumes);

    chart.timeScale().fitContent();

    // Resize observer
    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.resize(containerRef.current.clientWidth, 400);
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [data, theme, candleColors]);

  if (!data) return null;

  return (
    <div
      ref={containerRef}
      data-testid="candlestick-container"
      className="w-full min-h-[400px]"
    />
  );
}
```

- [ ] **Step 4: Run test — verify it passes**

```bash
cd frontend && npx jest --testPathPattern=candlestick-chart --verbose
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/lightweight-chart-theme.ts frontend/src/components/candlestick-chart.tsx frontend/src/__tests__/components/candlestick-chart.test.tsx
git commit -m "feat(KAN-228): add CandlestickChart with lightweight-charts + theme helper"
```

---

## Task 7: PriceChart — Line/Candle toggle + lazy import

**Files:**
- Modify: `frontend/src/components/price-chart.tsx`
- Create: `frontend/src/__tests__/components/price-chart.test.tsx`

- [ ] **Step 1: Write the test**

Create `frontend/src/__tests__/components/price-chart.test.tsx`:

```tsx
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";

// Mock Recharts
jest.mock("recharts", () => ({
  ComposedChart: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  Area: () => <div />,
  Bar: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  Tooltip: () => <div />,
  ResponsiveContainer: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CartesianGrid: () => <div />,
}));

// Mock use-stocks hooks
jest.mock("@/hooks/use-stocks", () => ({
  usePrices: () => ({
    data: [
      { time: "2025-01-02", close: 150, volume: 1000000 },
      { time: "2025-06-15", close: 175, volume: 1200000 },
    ],
    isLoading: false,
  }),
  useOHLC: () => ({
    data: { ticker: "AAPL", period: "1y", count: 2, timestamps: [], open: [], high: [], low: [], close: [], volume: [] },
    isLoading: false,
  }),
}));

// Mock chart-theme
jest.mock("@/lib/chart-theme", () => ({
  useChartColors: () => ({
    price: "#3b82f6",
    volume: "#6b7280",
    gain: "#22c55e",
    loss: "#ef4444",
    chart1: "#f59e0b",
    chart2: "#8b5cf6",
    chart3: "#ec4899",
    sma50: "#f59e0b",
    sma200: "#ef4444",
    rsi: "#8b5cf6",
  }),
  CHART_STYLE: {
    grid: { strokeDasharray: "3 3" },
    axis: { tick: { fontSize: 11 } },
    tooltip: { cursor: {} },
  },
}));

// Mock the lazy-loaded candlestick (it would be dynamically imported)
jest.mock("@/components/candlestick-chart", () => ({
  CandlestickChart: () => <div data-testid="candlestick-chart">Candlestick</div>,
}));

import { PriceChart } from "@/components/price-chart";

test("renders Line button as active by default", () => {
  render(<PriceChart ticker="AAPL" period="1y" onPeriodChange={() => {}} />);
  const lineBtn = screen.getByRole("button", { name: /line/i });
  expect(lineBtn).toBeInTheDocument();
});

test("renders Candle button", () => {
  render(<PriceChart ticker="AAPL" period="1y" onPeriodChange={() => {}} />);
  expect(screen.getByRole("button", { name: /candle/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test — verify it fails** (PriceChart currently has no toggle)

```bash
cd frontend && npx jest --testPathPattern=price-chart.test --verbose 2>&1 | head -20
```

Expected: FAIL — "Line" button not found.

- [ ] **Step 3: Update PriceChart with toggle**

Modify `frontend/src/components/price-chart.tsx`. The key changes:

1. Add `chartMode` state (`"line" | "candle"`)
2. Add toggle pills next to period selector
3. Lazy-import `CandlestickChart` with `dynamic({ ssr: false })`
4. Conditionally fetch OHLC data
5. Render candlestick or line based on mode

Replace the full file content with:

```tsx
"use client";

import { useState, Suspense, lazy } from "react";
import {
  ComposedChart,
  Area,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { usePrices, useOHLC } from "@/hooks/use-stocks";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { SectionHeading } from "@/components/section-heading";
import { ChartTooltip } from "@/components/chart-tooltip";
import { useChartColors, CHART_STYLE } from "@/lib/chart-theme";
import { formatCurrency, formatVolume, formatChartDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { PricePeriod } from "@/types/api";

const LazyCandlestick = lazy(() =>
  import("@/components/candlestick-chart").then((m) => ({
    default: m.CandlestickChart,
  }))
);

type ChartMode = "line" | "candle";

const PERIODS: { value: PricePeriod; label: string }[] = [
  { value: "1mo", label: "1M" },
  { value: "3mo", label: "3M" },
  { value: "6mo", label: "6M" },
  { value: "1y", label: "1Y" },
  { value: "5y", label: "5Y" },
];

interface PriceChartProps {
  ticker: string;
  period: PricePeriod;
  onPeriodChange: (p: PricePeriod) => void;
}

export function PriceChart({ ticker, period, onPeriodChange }: PriceChartProps) {
  const [chartMode, setChartMode] = useState<ChartMode>("line");
  const { data: prices, isLoading: pricesLoading } = usePrices(ticker, period);
  const { data: ohlc, isLoading: ohlcLoading } = useOHLC(
    ticker,
    period,
    chartMode === "candle"
  );
  const colors = useChartColors();

  const trendColor =
    prices && prices.length >= 2
      ? prices[prices.length - 1].close > prices[0].close
        ? colors.gain
        : prices[prices.length - 1].close < prices[0].close
          ? colors.loss
          : colors.price
      : colors.price;

  const modeToggle = (
    <div className="flex gap-1">
      {(["line", "candle"] as const).map((mode) => (
        <Button
          key={mode}
          variant={chartMode === mode ? "secondary" : "ghost"}
          size="sm"
          className="h-7 px-2.5 text-xs capitalize"
          onClick={() => setChartMode(mode)}
        >
          {mode}
        </Button>
      ))}
    </div>
  );

  const periodSelector = (
    <div className="flex gap-1">
      {PERIODS.map((p) => (
        <Button
          key={p.value}
          variant={period === p.value ? "secondary" : "ghost"}
          size="sm"
          className={cn("h-7 px-2.5 text-xs")}
          onClick={() => onPeriodChange(p.value)}
        >
          {p.label}
        </Button>
      ))}
    </div>
  );

  const actions = (
    <div className="flex items-center gap-3">
      {modeToggle}
      <div className="h-4 w-px bg-border" />
      {periodSelector}
    </div>
  );

  const isLoading = chartMode === "line" ? pricesLoading : ohlcLoading;

  return (
    <div>
      <SectionHeading action={actions}>Price History</SectionHeading>

      {isLoading ? (
        <Skeleton className="h-[250px] w-full sm:h-[400px]" />
      ) : chartMode === "candle" ? (
        <Suspense fallback={<Skeleton className="h-[400px] w-full" />}>
          <LazyCandlestick data={ohlc} />
        </Suspense>
      ) : (
        <ResponsiveContainer width="100%" height="100%" minHeight={250} className="sm:min-h-[400px]">
          <ComposedChart
            data={prices}
            role="img"
            aria-label={`${ticker} price history chart`}
          >
            <defs>
              <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={trendColor} stopOpacity={0.3} />
                <stop offset="95%" stopColor={trendColor} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid {...CHART_STYLE.grid} />
            <XAxis
              dataKey="time"
              tickFormatter={formatChartDate}
              interval="preserveStartEnd"
              minTickGap={60}
              {...CHART_STYLE.axis}
            />
            <YAxis
              yAxisId="price"
              orientation="left"
              tickFormatter={(v: number) => `$${v.toFixed(0)}`}
              width={60}
              domain={["auto", "auto"]}
              {...CHART_STYLE.axis}
            />
            <YAxis
              yAxisId="volume"
              orientation="right"
              tickFormatter={formatVolume}
              width={50}
              {...CHART_STYLE.axis}
            />
            <Tooltip
              cursor={CHART_STYLE.tooltip.cursor}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const d = payload[0].payload as {
                  time: string;
                  close: number;
                  volume: number;
                };
                return (
                  <ChartTooltip
                    active={active}
                    label={formatChartDate(d.time)}
                    items={[
                      { name: "Price", value: formatCurrency(d.close), color: colors.price },
                      { name: "Volume", value: formatVolume(d.volume), color: colors.volume },
                    ]}
                  />
                );
              }}
            />
            <Area
              yAxisId="price"
              type="monotone"
              dataKey="close"
              stroke={colors.price}
              fill="url(#priceGradient)"
              strokeWidth={2}
            />
            <Bar
              yAxisId="volume"
              dataKey="volume"
              fill={colors.volume}
              opacity={0.4}
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test — verify it passes**

```bash
cd frontend && npx jest --testPathPattern=price-chart.test --verbose
```

Expected: 2 tests PASS.

- [ ] **Step 5: Verify types compile**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/price-chart.tsx frontend/src/__tests__/components/price-chart.test.tsx
git commit -m "feat(KAN-228): add Line/Candle toggle to PriceChart with lazy-loaded candlestick"
```

---

## Task 8: SectionNav component + tests

**Files:**
- Create: `frontend/src/components/section-nav.tsx`
- Create: `frontend/src/__tests__/components/section-nav.test.tsx`

- [ ] **Step 1: Write the test**

Create `frontend/src/__tests__/components/section-nav.test.tsx`:

```tsx
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { SectionNav, SECTION_IDS } from "@/components/section-nav";

// Mock scrollIntoView
const mockScrollIntoView = jest.fn();
window.HTMLElement.prototype.scrollIntoView = mockScrollIntoView;

beforeEach(() => {
  mockScrollIntoView.mockClear();
});

test("renders all section pills", () => {
  render(<SectionNav />);
  for (const section of SECTION_IDS) {
    expect(screen.getByText(section.label)).toBeInTheDocument();
  }
});

test("clicking a pill calls scrollIntoView on the target element", () => {
  // Create a target element in the DOM
  const target = document.createElement("div");
  target.id = SECTION_IDS[0].id;
  document.body.appendChild(target);

  render(<SectionNav />);
  fireEvent.click(screen.getByText(SECTION_IDS[0].label));
  expect(target.scrollIntoView).toHaveBeenCalledWith({
    behavior: "smooth",
    block: "start",
  });

  document.body.removeChild(target);
});
```

- [ ] **Step 2: Implement SectionNav**

Create `frontend/src/components/section-nav.tsx`:

```tsx
"use client";

import { cn } from "@/lib/utils";

export const SECTION_IDS = [
  { id: "sec-price", label: "Price" },
  { id: "sec-signals", label: "Signals" },
  { id: "sec-history", label: "History" },
  { id: "sec-benchmark", label: "Benchmark" },
  { id: "sec-risk", label: "Risk" },
  { id: "sec-fundamentals", label: "Fundamentals" },
  { id: "sec-forecast", label: "Forecast" },
  { id: "sec-intelligence", label: "Intelligence" },
  { id: "sec-news", label: "News" },
  { id: "sec-dividends", label: "Dividends" },
] as const;

export function SectionNav() {
  function handleClick(id: string) {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  return (
    <nav className="sticky top-0 z-20 -mx-4 overflow-x-auto bg-navy-900/95 backdrop-blur-sm px-4 py-2 border-b border-border">
      <div className="flex gap-1">
        {SECTION_IDS.map((section) => (
          <button
            key={section.id}
            type="button"
            onClick={() => handleClick(section.id)}
            className={cn(
              "shrink-0 rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              "text-muted-foreground hover:text-foreground hover:bg-muted/30"
            )}
          >
            {section.label}
          </button>
        ))}
      </div>
    </nav>
  );
}
```

- [ ] **Step 3: Run test — verify it passes**

```bash
cd frontend && npx jest --testPathPattern=section-nav --verbose
```

Expected: 2 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/section-nav.tsx frontend/src/__tests__/components/section-nav.test.tsx
git commit -m "feat(KAN-228): add SectionNav sticky scroll navigation"
```

---

## Task 9: Wire everything into stock-detail-client.tsx

**Files:**
- Modify: `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx`

- [ ] **Step 1: Update the stock detail page**

Replace the full file with:

```tsx
"use client";

import { useState } from "react";
import { BarChart3Icon } from "lucide-react";
import {
  useSignals,
  useAddToWatchlist,
  useRemoveFromWatchlist,
  useIsInWatchlist,
  useIngestTicker,
  useStockMeta,
  useFundamentals,
  useDividends,
  useStockNews,
  useStockIntelligence,
  useBenchmark,
} from "@/hooks/use-stocks";
import { useForecast } from "@/hooks/use-forecasts";
import { StockHeader } from "@/components/stock-header";
import { SectionNav } from "@/components/section-nav";
import { PriceChart } from "@/components/price-chart";
import { BenchmarkChart } from "@/components/benchmark-chart";
import { SignalCards } from "@/components/signal-cards";
import { SignalHistoryChart } from "@/components/signal-history-chart";
import { RiskReturnCard } from "@/components/risk-return-card";
import { FundamentalsCard } from "@/components/fundamentals-card";
import { DividendCard } from "@/components/dividend-card";
import { ForecastCard } from "@/components/forecast-card";
import { IntelligenceCard } from "@/components/intelligence-card";
import { NewsCard } from "@/components/news-card";
import { EmptyState } from "@/components/empty-state";
import { SectionHeading } from "@/components/section-heading";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import type { PricePeriod } from "@/types/api";
import { PageTransition } from "@/components/motion-primitives";

interface StockDetailClientProps {
  ticker: string;
}

export function StockDetailClient({ ticker }: StockDetailClientProps) {
  const [period, setPeriod] = useState<PricePeriod>("1y");
  const { data: signals, isLoading: signalsLoading } = useSignals(ticker);
  const { name, sector } = useStockMeta(ticker);
  const isInWatchlist = useIsInWatchlist(ticker);
  const addToWatchlist = useAddToWatchlist();
  const removeFromWatchlist = useRemoveFromWatchlist();
  const ingestTicker = useIngestTicker();
  const { data: fundamentals, isLoading: fundLoading } = useFundamentals(ticker);
  const { data: dividends, isLoading: divLoading } = useDividends(ticker);
  const { data: forecast, isLoading: forecastLoading } = useForecast(ticker);

  // Progressive loading — wait for signals before fetching secondary data
  const hasSignals = !!signals;
  const {
    data: news,
    isLoading: newsLoading,
    isError: newsError,
    refetch: refetchNews,
  } = useStockNews(ticker, hasSignals);
  const {
    data: intelligence,
    isLoading: intelLoading,
    isError: intelError,
    refetch: refetchIntel,
  } = useStockIntelligence(ticker, hasSignals);
  const {
    data: benchmarkData,
    isLoading: benchmarkLoading,
    isError: benchmarkError,
    refetch: refetchBenchmark,
  } = useBenchmark(ticker, period, hasSignals);

  // Extract series names for BenchmarkChart legend
  const benchmarkSeriesNames = benchmarkData?.length
    ? Object.keys(benchmarkData[0]).filter((k) => k !== "date")
    : [];

  function handleToggleWatchlist() {
    if (isInWatchlist) {
      removeFromWatchlist.mutate(ticker);
    } else {
      addToWatchlist.mutate(ticker);
    }
  }

  async function handleIngest() {
    toast.loading(`Fetching data for ${ticker}...`, {
      id: `ingest-${ticker}`,
    });
    try {
      const result = await ingestTicker.mutateAsync(ticker);
      toast.success(`${result.rows_fetched} data points loaded`, {
        id: `ingest-${ticker}`,
      });
    } catch {
      toast.error(`Failed to fetch data for ${ticker}`, {
        id: `ingest-${ticker}`,
      });
    }
  }

  // Show ingest prompt if no signals exist
  if (!signalsLoading && !signals) {
    return (
      <div className="space-y-6">
        <h1 className="font-mono text-2xl font-bold">{ticker}</h1>
        <EmptyState
          icon={BarChart3Icon}
          title="No signals available"
          description="This stock hasn't been analyzed yet"
          action={
            <Button onClick={handleIngest} disabled={ingestTicker.isPending}>
              {ingestTicker.isPending ? "Loading..." : "Run Analysis"}
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <PageTransition className="space-y-8">

      {signalsLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-8 w-32" />
          <Skeleton className="h-5 w-48" />
        </div>
      ) : (
        <StockHeader
          ticker={ticker}
          name={name}
          sector={sector}
          score={signals?.composite_score ?? null}
          isInWatchlist={isInWatchlist}
          onToggleWatchlist={handleToggleWatchlist}
        />
      )}

      <SectionNav />

      <section id="sec-price">
        <PriceChart ticker={ticker} period={period} onPeriodChange={setPeriod} />
      </section>

      <section id="sec-signals">
        <SectionHeading>Signal Breakdown</SectionHeading>
        <SignalCards signals={signals} isLoading={signalsLoading} />
      </section>

      <section id="sec-history">
        <SectionHeading>Signal History (90 days)</SectionHeading>
        <SignalHistoryChart ticker={ticker} />
      </section>

      <section id="sec-benchmark">
        <BenchmarkChart
          data={benchmarkData}
          isLoading={benchmarkLoading}
          isError={benchmarkError}
          onRetry={refetchBenchmark}
          seriesNames={benchmarkSeriesNames}
        />
      </section>

      <section id="sec-risk">
        <RiskReturnCard returns={signals?.returns} />
      </section>

      <section id="sec-fundamentals">
        <FundamentalsCard fundamentals={fundamentals} isLoading={fundLoading} />
      </section>

      <section id="sec-forecast">
        <ForecastCard
          horizons={forecast?.horizons}
          isLoading={forecastLoading}
          currentPrice={undefined}
        />
      </section>

      <section id="sec-intelligence">
        <IntelligenceCard
          intelligence={intelligence}
          isLoading={intelLoading}
          isError={intelError}
          onRetry={refetchIntel}
        />
      </section>

      <section id="sec-news">
        <NewsCard
          news={news}
          isLoading={newsLoading}
          isError={newsError}
          onRetry={refetchNews}
        />
      </section>

      <section id="sec-dividends">
        <DividendCard dividends={dividends} isLoading={divLoading} />
      </section>
    </PageTransition>
  );
}
```

- [ ] **Step 2: Verify types compile**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 3: Run full frontend test suite**

```bash
cd frontend && npx jest --verbose 2>&1 | tail -20
```

Expected: All tests pass (existing + new).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/\(authenticated\)/stocks/\[ticker\]/stock-detail-client.tsx
git commit -m "feat(KAN-228): wire all new components into stock detail page with section nav"
```

---

## Task 10: Lint, build verification, and final commit

- [ ] **Step 1: Run ESLint**

```bash
cd frontend && npm run lint
```

Expected: 0 errors. Fix any warnings.

- [ ] **Step 2: Run TypeScript type check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 3: Run production build**

```bash
cd frontend && npm run build
```

Expected: Build succeeds. This catches SSR issues that `tsc` misses (e.g., `document` usage in server components).

- [ ] **Step 4: Run full test suite**

```bash
cd frontend && npx jest --verbose 2>&1 | tail -30
```

Expected: All tests pass.

- [ ] **Step 5: Final commit if any lint fixes were needed**

```bash
git add -A && git commit -m "chore(KAN-228): lint fixes and build verification"
```

---

## Task 11: Cascading failure analysis + regression fixes

This task catches breakage caused by our changes to shared components.

- [ ] **Step 1: Check that existing PriceChart consumers aren't broken**

`PriceChart` now imports `useOHLC` — verify this doesn't break other pages that import PriceChart. Search:

```bash
cd frontend && grep -rn "PriceChart" src/ --include="*.tsx" | grep -v __tests__ | grep -v node_modules
```

Expected: Only `stock-detail-client.tsx` imports it. If other files import it, verify they pass the correct props (no breaking interface change — `PriceChartProps` is unchanged).

- [ ] **Step 2: Check that `use-stocks.ts` import size hasn't created a circular dep**

New hooks import `BenchmarkComparisonResponse`, `OHLCResponse`, `StockNewsResponse`, `StockIntelligenceResponse` from `types/api.ts`. These types should already be in the file (confirmed in spec). Verify no circular import:

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -i "circular"
```

Expected: No circular dependency warnings.

- [ ] **Step 3: Verify SectionNav sticky doesn't overlap with existing sticky elements**

Topbar is `h-12` but NOT sticky/fixed (it's in normal flow). SectionNav at `sticky top-0` will stick to the top of the scrollable content area, not overlap the topbar. Verify visually in the browser that the nav sticks correctly when scrolling. If the app shell layout changes to make topbar sticky in the future, SectionNav would need `sticky top-12`.

- [ ] **Step 4: Verify lightweight-charts doesn't break the production build (SSR)**

The `CandlestickChart` is lazy-imported via `React.lazy()`. But if any top-level code in `candlestick-chart.tsx` references `window` or `document`, it'll still crash during SSR module resolution. Verify:

```bash
cd frontend && npm run build 2>&1 | grep -i "error\|window\|document"
```

Expected: No SSR errors. If there are, wrap the `import { createChart }` inside the `useEffect` instead of at the top of the file. The current implementation already does this correctly (import is at top but `createChart` is only called in `useEffect`), but `lightweight-charts` module-level code might reference `window`. If build fails, switch to dynamic import:

```tsx
// Replace top-level import with:
// import { createChart } from "lightweight-charts";  // REMOVE
// In useEffect:
const { createChart } = await import("lightweight-charts");
```

- [ ] **Step 5: Check that the `useBenchmark` select transform handles edge cases**

The `select` function in `useBenchmark` does date normalization with `split("T")[0]`. If the backend ever sends dates without the `T` separator (e.g., `"2025-01-02"`), this still works — `"2025-01-02".split("T")[0]` returns `"2025-01-02"`. But if `data.series` is empty, the function should return `[]`. Verify the early return handles this:

```ts
if (!data.series.length) return [];
```

This is already in the implementation — just verify it's there after implementation.

- [ ] **Step 6: Run backend tests to confirm no regression**

```bash
cd /Users/sigmoid/Documents/projects/stockanalysis/stock-signal-platform && uv run pytest tests/unit/ -q --tb=short 2>&1 | tail -5
```

Expected: All passing. We made no backend changes, but this confirms the dev environment is healthy.

- [ ] **Step 7: Commit any fixes from this analysis**

```bash
git add -A && git commit -m "fix(KAN-228): cascading failure fixes from regression analysis"
```

(Skip if no fixes were needed.)

---

## Summary

| Task | Component | New Tests | Estimate |
|------|-----------|-----------|----------|
| 1 | Types + dep + formatPctChange | 0 (type-check only) | ~3 min |
| 2 | 4 hooks with progressive loading | 0 (tested via components) | ~5 min |
| 3 | NewsCard | 5 | ~5 min |
| 4 | IntelligenceCard | 6 | ~8 min |
| 5 | BenchmarkChart | 5 | ~5 min |
| 6 | CandlestickChart + theme | 3 | ~8 min |
| 7 | PriceChart toggle | 2 | ~5 min |
| 8 | SectionNav | 2 | ~3 min |
| 9 | Wire into stock-detail-client | 0 (integration) | ~5 min |
| 10 | Lint + build | 0 | ~3 min |
| 11 | Cascading failure analysis | 0 | ~5 min |

**Total: 11 tasks, 23 new tests, ~55 min estimated**
