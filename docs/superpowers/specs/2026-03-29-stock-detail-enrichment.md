# KAN-228: Stock Detail Page Enrichment — Spec

**Epic:** KAN-226 (Phase B.5 Frontend Catch-Up)
**Story:** KAN-228 (BU-2)
**Date:** 2026-03-29
**Status:** Draft — pending PM review

---

## 1. Goal

Wire 4 existing backend endpoints into the stock detail page. All backend work is done — this is purely frontend: hooks, types, components, layout integration.

## 2. Decisions (from brainstorm + self-review)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Layout | Hybrid stacking + sticky section nav | Candlestick is a chart mode. Benchmark in analysis group. Section nav prevents scroll fatigue (11 sections). |
| Intelligence | Single collapsible card with sub-sections | Compact, one heading, most-important data always visible |
| Candlestick | lightweight-charts (TradingView OSS), lazy-loaded on toggle | Best-in-class candlestick lib. Dynamic import avoids 45KB penalty for line-only users. |
| News | 5-8 articles, compact list, publisher + relative time | No source indicator (internal concern). No images (RSS rarely has usable thumbnails). |
| Benchmark | Separate multi-line % chart in analysis group | Different Y-axis (% change vs absolute $), shared period selector |
| Loading | Progressive — news/intel/benchmark wait for signals | Prevents 8 simultaneous skeleton pop-ins |

## 3. Backend Endpoints (all exist, authenticated)

| Endpoint | Router | Response Schema |
|----------|--------|----------------|
| `GET /stocks/{ticker}/news` | `stocks/data.py:get_stock_news` | `StockNewsResponse` → `NewsItem[]` |
| `GET /stocks/{ticker}/intelligence` | `stocks/data.py:get_stock_intelligence` | `StockIntelligenceResponse` |
| `GET /stocks/{ticker}/benchmark?period=` | `stocks/data.py:get_benchmark` | `BenchmarkComparisonResponse` → `BenchmarkSeries[]` |
| `GET /stocks/{ticker}/prices?period=&format=ohlc` | `stocks/data.py:get_prices` | `OHLCResponse` |

## 4. Frontend Types Gap

**Already in `types/api.ts`:** `NewsItem`, `StockNewsResponse`, `UpgradeDowngrade`, `InsiderTransaction`, `ShortInterest`, `StockIntelligenceResponse`, `OHLCResponse`

**Missing — must add:**
- `BenchmarkSeries` — `{ ticker: string; name: string; dates: string[]; pct_change: number[] }`
- `BenchmarkComparisonResponse` — `{ ticker: string; period: string; series: BenchmarkSeries[] }`

## 5. New Hooks (`hooks/use-stocks.ts`)

```ts
useStockNews(ticker: string)         // GET /stocks/{ticker}/news, staleTime 5min
                                     // enabled: !!signals (progressive load)

useStockIntelligence(ticker: string) // GET /stocks/{ticker}/intelligence, staleTime 5min
                                     // enabled: !!signals (progressive load)

useBenchmark(ticker: string, period: PricePeriod)
                                     // GET /stocks/{ticker}/benchmark?period=
                                     // queryKey: ["benchmark", ticker, period]
                                     // enabled: !!signals (progressive load)

useOHLC(ticker: string, period: PricePeriod)
                                     // GET /stocks/{ticker}/prices?period=&format=ohlc
                                     // queryKey: ["ohlc", ticker, period]
                                     // CRITICAL: must NOT collide with usePrices queryKey ["prices", ticker, period]
```

All use TanStack Query via `lib/api.ts` `get<T>()`.

## 6. New Components

### 6.0 SectionNav (`components/section-nav.tsx`) — NEW
- Sticky horizontal pill bar below StockHeader
- One pill per page section with `id` anchors
- `scrollIntoView({ behavior: "smooth" })` on click
- Active pill tracks scroll position via `IntersectionObserver`
- Pills: Price | Signals | History | Benchmark | Risk | Fundamentals | Forecast | Intelligence | News | Dividends
- Styling: navy-800 bg, same pill style as period selector

### 6.1 CandlestickChart (`components/candlestick-chart.tsx`)
- Uses `lightweight-charts` (`createChart`, `addCandlestickSeries`)
- **MUST be dynamically imported** with `{ ssr: false }` — lightweight-charts uses `document.createElement('canvas')` internally. SSR will cause hydration mismatch (same issue as KAN-98).
- **MUST theme to match design system** — navy background (`--navy-950`), grid color (`--navy-800`), gain/loss colors from CSS vars, Sora font. Create `useLightweightChartTheme()` helper that reads CSS vars → returns `ChartOptions`.
- Props: `data: OHLCResponse`, `period`, `onPeriodChange`
- Self-contained — creates its own chart container, handles resize via `ResizeObserver`
- Volume as histogram below candles (built into lightweight-charts)

### 6.2 PriceChart update (`components/price-chart.tsx`)
- Add `chartMode` state: `"line" | "candle"` (default `"line"`)
- Toggle pill in `SectionHeading` action bar (next to period selector)
- When `candle`: render `<CandlestickChart>` via **lazy import** inside `<Suspense fallback={<Skeleton />}>` — lightweight-charts only loads on first toggle
- Pass `period` and `onPeriodChange` through
- Fetch OHLC data via `useOHLC()` only when `chartMode === "candle"` (`enabled: chartMode === "candle"`)

### 6.3 BenchmarkChart (`components/benchmark-chart.tsx`)
- Recharts `LineChart` with up to 3 lines (stock, S&P 500, NASDAQ)
- Y-axis: percentage change (not absolute $), formatted as `+12.3%`
- Legend with color-coded labels — use existing `useChartColors()`: `colors.price` (stock), `colors.chart1` (S&P 500), `colors.chart2` (NASDAQ). No new CSS vars needed.
- Uses shared `period` state from parent (already lifted)
- **Data transformation in hook, not component**: `useBenchmark` converts parallel-array shape (`dates[]`, `pct_change[]` per series) into Recharts-friendly `{ date: string, [seriesName]: number }[]` array via a `select` transform in the query config
- Skeleton loading state
- **Error state**: `<ErrorState>` with retry button (benchmark depends on index data which can be stale)
- Handles graceful degradation (if an index is unavailable, fewer lines)

### 6.4 IntelligenceCard (`components/intelligence-card.tsx`)
- Collapsible card with `SectionHeading`
- Summary row always visible: next earnings date, short % of float
- Sub-sections (each collapsible, reuse pattern from `SectorAccordion`):
  - **Analyst Ratings**: table of `UpgradeDowngrade[]` (firm, action, to_grade, date)
  - **Insider Transactions**: table of `InsiderTransaction[]` (name, type, shares, value, date)
  - **Short Interest**: `short_percent_of_float`, `short_ratio`, `shares_short`
- Empty state per sub-section if no data
- **Error state**: `<ErrorState>` with retry (yfinance intelligence endpoints are flaky)

### 6.5 NewsCard (`components/news-card.tsx`)
- `SectionHeading` with "News" title
- Compact list of `NewsItem[]`:
  - Title as external link (`target="_blank" rel="noopener noreferrer"`)
  - Publisher name + relative time (no source indicator — internal concern)
- Max 8 articles displayed
- Empty state if no articles
- **Error state**: `<ErrorState>` with retry (Google News RSS can be blocked)

## 7. Page Layout (updated section order)

```
StockHeader
SectionNav (sticky)          ← NEW — scroll navigation
PriceChart                   ← + Line/Candle toggle
Signal Breakdown
Signal History
BenchmarkChart               ← NEW (analysis group, after signals)
Risk & Return
Fundamentals
Forecast
IntelligenceCard             ← NEW
NewsCard                     ← NEW
Dividends
```

Each `<section>` gets an `id` attribute for SectionNav anchor scrolling.

**Rationale for benchmark placement:** Price → Signals → Signal History → "How does this compare to market?" (Benchmark) → Risk → Fundamentals flows as a natural decision funnel. Putting benchmark between PriceChart and Signals broke this flow.

## 8. Style Guide Compliance — MUST USE existing primitives

Every new component MUST reuse the project's established patterns. Do NOT invent new styling approaches.

### Layout & Structure
- **`SectionHeading`** (`components/section-heading.tsx`) — every card section uses this for its title. Supports `action` slot for inline controls (period selector, toggles). Pattern: `<SectionHeading action={...}>Title</SectionHeading>`
- **Card wrapper** — `<div className="space-y-4">` wrapping `SectionHeading` + content. See `DividendCard`, `FundamentalsCard` for reference.
- **Loading skeleton** — `<Skeleton className="h-20 rounded-lg" />` in grid. Copy exact pattern from `FundamentalsCard` / `DividendCard`.
- **Empty state** — plain `<p className="text-sm text-muted-foreground">` for "no data". See `DividendCard` line 37-44.
- **Error state** — `<ErrorState error="..." onRetry={refetch} />` from `components/error-state.tsx`. Already has destructive icon, retry button.

### Charts (Recharts)
- **`useChartColors()`** (`lib/chart-theme.ts`) — resolves CSS vars to literal strings for Recharts. ALL chart colors must come from here.
- **`CHART_STYLE`** (`lib/chart-theme.ts`) — shared grid, axis, tooltip cursor styles. Pass via spread: `<CartesianGrid {...CHART_STYLE.grid} />`, `<XAxis {...CHART_STYLE.axis} />`.
- **`ChartTooltip`** (`components/chart-tooltip.tsx`) — reusable tooltip with `items: { name, value, color }[]`. Never write inline tooltip renderers.
- **BenchmarkChart** must use `useChartColors()` + `CHART_STYLE` + `ChartTooltip`. Benchmark line colors: use `colors.chart1` (S&P), `colors.chart2` (NASDAQ), `colors.price` (stock). No new CSS vars needed — existing palette is sufficient.

### Charts (lightweight-charts for candlestick)
- **`useLightweightChartTheme()`** — NEW helper to create. Must read from `CSS_VARS` (`lib/design-tokens.ts`) via `readCssVar()` pattern from `chart-theme.ts`. Map to lightweight-charts `ChartOptions`: `layout.background` → `--card`, `layout.textColor` → `--foreground`, `grid.vertLines/horzLines` → `--border` at 50% opacity, `upColor` → `--gain`, `downColor` → `--loss`.

### Data Formatting
- **`formatCurrency()`**, **`formatPercent()`**, **`formatNumber()`**, **`formatVolume()`**, **`formatRelativeTime()`**, **`formatDate()`** — all in `lib/format.ts`. Use these. Never write inline formatting.
- News: `formatRelativeTime(article.published)` for relative timestamps.
- Intelligence: `formatDate(upgrade.date)` for analyst rating dates, `formatCurrency(txn.value)` for insider transaction values.
- Benchmark: `+${pct.toFixed(1)}%` for Y-axis — add `formatPctChange()` to `lib/format.ts` if not present.

### Tables
- Use shadcn `Table` / `TableBody` / `TableHead` / `TableHeader` / `TableRow` / `TableCell` from `components/ui/table`. See `DividendCard` for reference.
- Intelligence sub-section tables (upgrades, insider) follow this exact pattern.

### Collapsible Sections
- Reuse the `SectorAccordion` pattern (`components/sector-accordion.tsx`): `ChevronDownIcon` rotation, `framer-motion` `AnimatePresence`, `motion.div` for expand/collapse. Same card border/bg (`rounded-lg border border-border bg-card`).

### Design Tokens
- All colors via Tailwind classes (`text-foreground`, `text-muted-foreground`, `text-subtle`, `bg-card`, `bg-card2`, `border-border`) or `CSS_VARS` constants for programmatic access.
- Financial semantic: `text-gain` / `text-loss` for positive/negative values.
- Never hardcode hex/oklch values in components.

## 9. Dependencies

- `npm install lightweight-charts` (frontend, ~45KB gzip, lazy-loaded)
- BU-1 (KAN-227) must be merged first — done

## 10. Technical Gotchas

| # | Gotcha | Mitigation |
|---|--------|------------|
| 1 | lightweight-charts uses DOM APIs → SSR hydration mismatch | `dynamic(() => import(...), { ssr: false })` |
| 2 | `usePrices` queryKey `["prices", ticker, period]` vs `useOHLC` | `useOHLC` must use `["ohlc", ticker, period]` — distinct key |
| 3 | BenchmarkSeries `dates` are ISO datetime strings from backend | Parse in `useBenchmark` `select` transform, not in component |
| 4 | lightweight-charts has own theming, doesn't inherit CSS vars | `useLightweightChartTheme()` reads CSS vars → ChartOptions |
| 5 | 8 parallel API calls on page load → skeleton cascade | Progressive: news/intel/benchmark use `enabled: !!signals` |
| 6 | Intelligence/News depend on flaky external APIs | `<ErrorState>` with retry button on each section |

## 11. Testing

- **Hook tests**: `useStockNews`, `useStockIntelligence`, `useBenchmark`, `useOHLC` — mock API, verify query keys, verify `enabled` gating
- **IntelligenceCard** — renders with data, empty state per sub-section, collapsible behavior, error state
- **NewsCard** — renders articles, empty state, external links have `rel="noopener noreferrer"`, error state
- **BenchmarkChart** — renders with 1/2/3 series, loading skeleton, error state with retry
- **CandlestickChart** — mock `lightweight-charts` module in jsdom, verify mount/unmount cleanup
- **PriceChart** — toggle between line/candle modes, verify lazy import triggers
- **SectionNav** — renders all pills, click triggers scroll

## 12. Out of Scope

- Backend changes (all endpoints exist)
- Portfolio analytics upgrade (separate Epic KAN-246)
- News sentiment analysis
- Real-time price updates / WebSocket
- SectionNav active-state scroll tracking (nice-to-have, can add later)
