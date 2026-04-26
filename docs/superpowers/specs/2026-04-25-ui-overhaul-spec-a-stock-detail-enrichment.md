# Spec A: Stock Detail Page Enrichment

**Epic:** KAN-400 (UI Overhaul)
**Date:** 2026-04-25
**Scope:** 3 new sections on the stock detail page + section reordering
**Estimated effort:** ~3-4 days, 2 PRs

---

## Context

Session 134 UI walkthrough identified 11 backend features without frontend UI. This spec covers the stock detail page enrichments — 3 new sections that fill gaps in the investor's decision flow.

The stock detail page currently has 10 sections in a single-scroll layout with `SectionNav` jump links. This spec adds 3 new sections positioned to follow the investor's natural decision-making process, and reorders sections accordingly.

**Correction from gap analysis:** Two items originally listed as gaps are already shipped:
- E-1 (Stock Intelligence Display) — `IntelligenceCard` component exists and renders on stock detail
- Candlestick toggle — `PriceChart` already has a Line/Candle toggle with `useOHLC` wired

---

## Design Principle

> Sentiment is a supporting signal, not the main event. New sections should feel like a subtle "context layer" — something a part-time investor glances at to confirm conviction, not a wall of charts demanding analysis. No new section should overshadow the core signal/forecast flow.

---

## Section 1: Signal Convergence Card

### What it answers
"Are all my signals agreeing or fighting each other?"

### Data source
- `useStockConvergence(ticker)` — hook at `frontend/src/hooks/use-convergence.ts:25-32`
- `useConvergenceHistory(ticker, days)` — hook at `frontend/src/hooks/use-convergence.ts:51-65`
- Backend: `GET /convergence/{ticker}` → `ConvergenceResponse`
- Backend: `GET /convergence/{ticker}/history?days=30` → `ConvergenceHistoryResponse`

### Response schemas (already defined)

**`ConvergenceResponse`** (`backend/schemas/convergence.py:65-80`):
```
ticker: str
date: date
signals: list[SignalDirectionDetail]    # 6 signals: rsi, macd, sma, piotroski, forecast, news
  - signal: str
  - direction: "bullish" | "bearish" | "neutral"
  - value: float | None               # raw value (RSI=42, MACD=0.03)
signals_aligned: int (0-6)            # count in majority direction
convergence_label: "strong_bull" | "weak_bull" | "mixed" | "weak_bear" | "strong_bear"
divergence: DivergenceAlert
  - is_divergent: bool
  - forecast_direction: str | None
  - technical_majority: str | None
  - historical_hit_rate: float | None  # 0-1, how often forecast was right
  - sample_count: int | None
rationale: str | None
composite_score: float | None (0-10)
```

**`ConvergenceHistoryResponse`** (`backend/schemas/convergence.py:131-138`):
```
ticker: str
data: list[ConvergenceHistoryRow]
  - date: date
  - convergence_label: ConvergenceLabelEnum
  - signals_aligned: int (0-6)
  - composite_score: float | None
  - actual_return_90d: float | None
  - actual_return_180d: float | None
total: int
limit: int
offset: int
```

### TypeScript types (already defined)
`frontend/src/types/api.ts`:
- `ConvergenceResponse` — lines 1120-1129
- `ConvergenceHistoryRow` — lines 1149-1156
- `ConvergenceHistoryResponse` — lines 1158-1164
- `SignalDirectionDetail` — lines 1106-1110
- `DivergenceAlert` — lines 1112-1118
- `ConvergenceLabelType` — lines 1099-1104

### Component: `ConvergenceCard`

**New file:** `frontend/src/components/convergence-card.tsx`

**Props:**
```ts
interface ConvergenceCardProps {
  ticker: string;
  enabled?: boolean;  // gate on hasSignals like other secondary data
}
```

**Layout:**
1. **Label badge** — color-coded: `strong_bull`=green, `weak_bull`=light green, `mixed`=amber, `weak_bear`=light red, `strong_bear`=red
2. **Alignment count** — "4 of 6 signals bullish"
3. **Signal direction list** — compact inline: "RSI ↑ · MACD ↑ · SMA ↓ · Piotroski ↑ · Forecast ↑ · News —". Use ↑ for bullish, ↓ for bearish, — for neutral. Color each arrow.
4. **Divergence alert** (conditional) — amber bordered box, only renders when `divergence.is_divergent === true`. Text: "⚠ Divergence: {forecast_direction} forecast vs {technical_majority} technicals. Historically, forecast was right {hit_rate}% of the time (n={sample_count})."
5. **Rationale** (conditional) — muted text below, from `rationale` field if present
6. **Convergence history chart** — Recharts AreaChart, ~80px height, 30-day lookback. Y-axis maps convergence labels to numeric values (strong_bear=1, weak_bear=2, mixed=3, weak_bull=4, strong_bull=5). Fill color gradient green-to-red based on value. X-axis = dates, minimal labels.

**Error/empty states:**
- Loading: `SectionHeading` + 2 `Skeleton` rows (same pattern as other cards)
- Error: `ErrorState` with retry (same pattern as `IntelligenceCard`)
- No data: return `null` (don't render section)

**Design weight:** Medium. The badge is the hero element. History chart is subtle (low height, muted). Divergence alert only appears when relevant.

### Position
Section #4 in the new order — after Signal History, before Benchmark. Section ID: `sec-convergence`.

### Files to create
- `frontend/src/components/convergence-card.tsx`

### Files to modify
- `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx` — add import, hook call, section render
- `frontend/src/components/section-nav.tsx` — add "Convergence" to `SECTION_IDS`

---

## Section 2: Forecast Track Record

### What it answers
"Can I trust this forecast? Has the model been right before for this stock?"

### Data source — NEW backend endpoint required

**New endpoint:** `GET /forecasts/{ticker}/track-record?days=365`

**Router file:** `backend/routers/forecasts.py`

**IMPORTANT — route ordering:** This router has NO prefix (`APIRouter(tags=["forecasts"])`), so routes are bare paths like `/forecasts/{ticker}`. The new `/forecasts/{ticker}/track-record` route MUST be declared BEFORE the existing `GET /forecasts/{ticker}` (line 175), otherwise FastAPI will capture "track-record" as a ticker value. Place it between the portfolio forecast endpoint (line 34) and the ticker forecast endpoint (line 175), following the same pattern as `/forecasts/sector/{sector}` (line 273).

**Query logic:**
```sql
SELECT forecast_date, ticker, horizon_days, predicted_price, predicted_lower,
       predicted_upper, target_date, actual_price, error_pct
FROM forecast_results
WHERE ticker = :ticker
  AND error_pct IS NOT NULL          -- only evaluated (matured) forecasts
  AND forecast_date >= :since        -- lookback window
ORDER BY target_date ASC
```

The key filter is `error_pct IS NOT NULL` — this means the forecast's target date has passed and the nightly evaluation task has scored it against the actual price.

**Direction correctness** is computed at query time (not stored):
```python
direction_correct = (predicted_price > actual_at_forecast_date) == (actual_price > actual_at_forecast_date)
```

Simplification: since `ForecastResult` doesn't store the price at forecast time, we approximate by checking if `predicted_price` and `actual_price` are both above or both below the previous row's actual, OR more simply: `(predicted_price - actual_price)` sign matches the direction. The cleanest approach: compute `direction_correct = (predicted_price >= actual_price_at_forecast_date)` where `actual_price_at_forecast_date` can be looked up from the `stock_prices` table for `forecast_date`.

**Direction computation requires the price at forecast time.** Join `stock_prices` to get the closing price on `forecast_date`, then:
```python
# Did the model predict the right direction of movement?
forecast_date_price = <closing price from stock_prices on forecast_date>
direction_correct = bool(
    (row.predicted_price - forecast_date_price) * (row.actual_price - forecast_date_price) > 0
)
```
Batch-fetch all needed `forecast_date` prices in one query using `WHERE (ticker, date) IN (...)` to avoid N+1. If `forecast_date` falls on a weekend/holiday (no price row), use the most recent prior trading day (`ORDER BY date DESC LIMIT 1` per date).

### New response schema

**New file:** Add to `backend/schemas/forecasts.py`

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
    """Aggregate accuracy stats."""
    total_evaluated: int
    direction_hit_rate: float      # 0-1
    avg_error_pct: float           # mean absolute error_pct
    ci_containment_rate: float     # % of actuals within [lower, upper]

class ForecastTrackRecordResponse(BaseModel):
    """Full track record for a ticker."""
    ticker: str
    evaluations: list[ForecastEvaluation]
    summary: ForecastTrackRecordSummary
```

### New TypeScript types

**Add to:** `frontend/src/types/api.ts`

```ts
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
```

### New frontend hook

**Add to:** `frontend/src/hooks/use-forecasts.ts`

```ts
export function useForecastTrackRecord(ticker: string | null) {
  return useQuery({
    queryKey: ["forecast-track-record", ticker],
    queryFn: () => get<ForecastTrackRecordResponse>(`/forecasts/${ticker}/track-record`),
    enabled: !!ticker,
    staleTime: 30 * 60 * 1000,  // 30 min — data changes nightly
  });
}
```

### Component: `ForecastTrackRecord`

**New file:** `frontend/src/components/forecast-track-record.tsx`

**Props:**
```ts
interface ForecastTrackRecordProps {
  ticker: string;
  enabled?: boolean;
}
```

**Layout:**
1. **SectionHeading** — "Forecast Track Record"
2. **Dual-line Recharts chart** (~120px height):
   - Blue line: `predicted_price` over `target_date`
   - White/light gray line: `actual_price` over `target_date`
   - Light gray shaded band: `predicted_lower` to `predicted_upper` (confidence interval)
   - X-axis: target dates, chronological
   - Tooltip on hover showing predicted, actual, error % for each point
3. **4 summary KPI tiles** (grid-cols-4, same size as signal cards):
   - Total evaluated (count)
   - Direction hit rate (%, green ≥70%, amber 50-70%, red <50%)
   - Avg error (%, lower is better, green <5%, amber 5-10%, red >10%)
   - CI containment (%, green ≥80%, amber 60-80%, red <60%)

**Error/empty states:**
- Loading: SectionHeading + Skeleton chart + 4 Skeleton tiles
- Error: ErrorState with retry
- No data / `summary.total_evaluated === 0`: "No evaluated forecasts yet. Track record builds as predictions mature (typically 30-90 days after first forecast)."

**Design weight:** Medium-light. The chart is the hero. KPI tiles are compact. This section is supporting evidence for the Forecast section above — it should feel like a footnote that builds trust.

### Position
Section #9 in the new order — directly after Forecast, before Intelligence. Section ID: `sec-track-record`.

**SectionNav:** Do NOT add a separate nav link. Track Record is immediately below Forecast — the user sees it on scroll. Adding a nav link would clutter the nav for a section that's contextually part of the forecast story.

### Files to create
- `frontend/src/components/forecast-track-record.tsx`

### Files to modify
- `backend/schemas/forecasts.py` — add 3 new schemas
- `backend/routers/forecasts.py` — add `GET /forecasts/{ticker}/track-record` endpoint
- `frontend/src/types/api.ts` — add 3 new TypeScript types
- `frontend/src/hooks/use-forecasts.ts` — add `useForecastTrackRecord` hook
- `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx` — add import, hook, section

### Key backend files for context
- `backend/models/forecast.py:49-77` — `ForecastResult` model (source table)
- `backend/models/stock.py` — `StockPrice` model (for forecast_date price lookup)
- `backend/tasks/evaluation.py` — nightly task that fills `error_pct` and `actual_price`

---

## Section 3: Sentiment Trend + Articles

### What it answers
"What's the news mood for this stock? Is sentiment trending up or down?"

### Data source
- `useSentiment(ticker)` — hook at `frontend/src/hooks/use-sentiment.ts:7` (exists, orphaned)
- New hook: `useTickerArticles(ticker)` — endpoint exists at `GET /sentiment/{ticker}/articles`, no hook yet
- Backend: `GET /sentiment/{ticker}?days=30` → `SentimentTimeseriesResponse`
- Backend: `GET /sentiment/{ticker}/articles?days=30` → `ArticleListResponse`

### Response schemas (already defined)

**`SentimentTimeseriesResponse`** (`backend/schemas/sentiment.py`):
```
ticker: str
data: list[DailySentimentResponse]
  - date: date
  - ticker: str
  - stock_sentiment: float
  - sector_sentiment: float
  - macro_sentiment: float
  - article_count: int
  - confidence: float
  - dominant_event_type: str | None
  - rationale_summary: str | None
  - quality_flag: str
```

**`ArticleListResponse`** (`backend/schemas/sentiment.py`):
```
ticker: str
articles: list[ArticleSummaryResponse]
  - headline: str
  - source: str
  - source_url: str | None
  - ticker: str | None
  - published_at: str
  - event_type: str | None
  - scored_at: str | None
total: int
limit: int
offset: int
```

### TypeScript types
- `NewsSentiment` exists at `frontend/src/types/api.ts:1036-1045`
- Need to add `ArticleSummary` and `ArticleListResponse` types (not currently in `api.ts`)

**Add to** `frontend/src/types/api.ts`:
```ts
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
```

### Type fix needed
The `useSentiment` hook currently returns loosely typed data. The `NewsSentiment` interface exists at `api.ts:1036` but the hook at `use-sentiment.ts:7` doesn't use it properly. Fix the hook to use `SentimentTimeseriesResponse` (or a simplified typed version).

### New frontend hook

**Add to:** `frontend/src/hooks/use-sentiment.ts`

```ts
export function useTickerArticles(ticker: string | null, days = 30) {
  return useQuery({
    queryKey: ["sentiment-articles", ticker, days],
    queryFn: () => get<ArticleListResponse>(`/sentiment/${ticker}/articles?days=${days}`),
    enabled: !!ticker,
    staleTime: 30 * 60 * 1000,
  });
}
```

### Component: `SentimentCard`

**New file:** `frontend/src/components/sentiment-card.tsx`

**Props:**
```ts
interface SentimentCardProps {
  ticker: string;
  enabled?: boolean;
}
```

**Layout:**
1. **SectionHeading** — "Sentiment"
2. **Trend chart** — Recharts AreaChart, ~80px height, 30-day lookback:
   - 3 area series: stock_sentiment (green), sector_sentiment (blue), macro_sentiment (gray)
   - Y-axis: sentiment score range (typically -1 to +1), no explicit labels
   - X-axis: dates
   - Low opacity fills to keep it subtle
   - Tooltip showing date + all 3 values + article_count + dominant_event_type
3. **Current sentiment tiles** (grid-cols-3):
   - Stock sentiment score — color-coded (green positive, red negative)
   - Sector sentiment score
   - Macro sentiment score
   - Use latest data point from the timeseries
   - Show `dominant_event_type` as a small tag on the stock tile if present
4. **Collapsible article list** — reuse the `CollapsibleSection` pattern from `IntelligenceCard`:
   - Extract `CollapsibleSection` to a shared component or import from intelligence-card (see refactor note below)
   - Header: "Recent Articles ({total})"
   - Collapsed by default
   - Each row: headline (bold), source (muted), published_at (relative time), event_type tag (if present)
   - `source_url` wraps headline in `<a target="_blank" rel="noopener noreferrer">`
   - Show first 20 articles. If total > 20, show "Load more" or pagination.

**Refactor note:** `CollapsibleSection` is currently defined inside `intelligence-card.tsx` (lines 28-72). It should be extracted to `frontend/src/components/collapsible-section.tsx` as a shared component, then imported by both `IntelligenceCard` and `SentimentCard`. This is a small, safe refactor — same code, just moved.

**Error/empty states:**
- Loading: SectionHeading + Skeleton chart + 3 Skeleton tiles
- Error: ErrorState with retry
- No data: "No sentiment data available. Sentiment is computed nightly from news articles."

**Design weight:** Light. The chart is low-height with muted fills. Current values are small tiles. Articles are collapsed by default. This section provides mood context without demanding attention.

### Position
Section #11 in the new order — between Intelligence and News. Section ID: `sec-sentiment`.

**SectionNav:** Add "Sentiment" to `SECTION_IDS`.

### Files to create
- `frontend/src/components/sentiment-card.tsx`
- `frontend/src/components/collapsible-section.tsx` (extracted from intelligence-card)

### Files to modify
- `frontend/src/types/api.ts` — add `ArticleSummary`, `ArticleListResponse` types
- `frontend/src/hooks/use-sentiment.ts` — add `useTickerArticles` hook, fix typing on `useSentiment`
- `frontend/src/components/intelligence-card.tsx` — import `CollapsibleSection` from shared location (replace inline definition)
- `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx` — add import, hooks, section
- `frontend/src/components/section-nav.tsx` — add "Sentiment" to `SECTION_IDS`

---

## Section Reordering

### New order (13 sections)

| # | Section ID | Section | Status |
|---|-----------|---------|--------|
| 1 | `sec-price` | Price Chart (existing toggle) | Unchanged |
| 2 | `sec-signals` | Signal Breakdown | Unchanged |
| 3 | `sec-history` | Signal History (90 days) | Unchanged |
| 4 | `sec-convergence` | **Signal Convergence** | **NEW** |
| 5 | `sec-benchmark` | Benchmark vs SPY | Unchanged |
| 6 | `sec-risk` | Risk & Return / Analytics | Unchanged |
| 7 | `sec-fundamentals` | Fundamentals | Unchanged |
| 8 | `sec-forecast` | Forecast | Unchanged |
| 9 | `sec-track-record` | **Forecast Track Record** | **NEW** |
| 10 | `sec-intelligence` | Intelligence | Unchanged |
| 11 | `sec-sentiment` | **Sentiment** | **NEW** |
| 12 | `sec-news` | News | Unchanged |
| 13 | `sec-dividends` | Dividends | Unchanged |

### SectionNav updates

**Add to `SECTION_IDS`** (`frontend/src/components/section-nav.tsx:5-16`):
- `{ id: "sec-convergence", label: "Convergence" }` — after "History"
- `{ id: "sec-sentiment", label: "Sentiment" }` — after "Intelligence"

**Do NOT add:** "Track Record" — it's contextually part of Forecast, visible on scroll.

### File to modify
- `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx` — reorder `<section>` elements
- `frontend/src/components/section-nav.tsx` — update `SECTION_IDS` array

---

## PR Split

### PR1: Convergence + Section Reorder (~1.5 days)
- `ConvergenceCard` component (new)
- Wire `useStockConvergence` + `useConvergenceHistory` into stock detail
- Section reorder in `stock-detail-client.tsx`
- Update `SectionNav` with "Convergence"
- Tests: Jest component test for `ConvergenceCard` (render, loading, empty, divergence alert)

### PR2: Sentiment + Forecast Track Record (~2 days)
- Backend: `GET /forecasts/{ticker}/track-record` endpoint + schemas
- `ForecastTrackRecord` component (new)
- `SentimentCard` component (new)
- Extract `CollapsibleSection` to shared component
- `useTickerArticles` hook (new) + `useForecastTrackRecord` hook (new)
- Wire into stock detail, add "Sentiment" to SectionNav
- TypeScript types for track record + articles
- Tests: Backend endpoint tests (happy + empty + auth), Jest component tests for both new components

---

## Testing Strategy

### Backend (PR2 only)
- `tests/unit/routers/test_forecasts.py` — add tests for track-record endpoint:
  - Happy path: returns evaluated forecasts with correct summary stats
  - Empty: no evaluated forecasts returns `total_evaluated: 0`
  - Auth: requires authenticated user
  - Pagination: respects `days` parameter

### Frontend (both PRs)
- `frontend/src/__tests__/components/convergence-card.test.tsx`:
  - Renders convergence label and signal directions
  - Renders divergence alert when `is_divergent=true`
  - Hides divergence alert when `is_divergent=false`
  - Shows loading skeleton
  - Returns null when no data
- `frontend/src/__tests__/components/forecast-track-record.test.tsx`:
  - Renders chart and 4 KPI tiles with data
  - Shows empty state when `total_evaluated=0`
  - Color-codes KPIs (green/amber/red thresholds)
- `frontend/src/__tests__/components/sentiment-card.test.tsx`:
  - Renders 3 sentiment tiles with correct colors
  - Articles section collapsed by default
  - Article headlines render with source links

---

## Out of Scope

- `useBulkSentiment` / `useMacroSentiment` wiring (Batch 2 — dashboard/screener)
- `useSectorConvergence` wiring (Batch 2 — sectors page)
- Candlestick toggle (already shipped — `PriceChart` has Line/Candle toggle)
- Stock Intelligence display (already shipped — `IntelligenceCard` renders on stock detail)
- Any admin page changes (Spec C)
- Portfolio page changes (Spec B)

---

## Key Gotchas for Implementers

1. **`API_BASE = "/api/v1"` in `api.ts`** — hooks use `/forecasts/...` NOT `/api/v1/forecasts/...`
2. **Progressive loading** — new hooks should gate on `hasSignals` (line 60 in stock-detail-client.tsx) to avoid fetching secondary data before signals load
3. **Recharts chart sizing** — use `ResponsiveContainer` with explicit `minHeight`. Playwright/jsdom has no layout engine — disable animations in tests (`isAnimationActive={false}`)
4. **`CollapsibleSection` extraction** — when moving from intelligence-card.tsx, ensure the import path update doesn't break existing tests. The `framer-motion` dependency (`AnimatePresence`, `motion`) stays.
5. **Sentiment hook typing** — `useSentiment` currently returns loosely typed data. Fix to use `NewsSentiment` from `api.ts:1036`
6. **Forecast track record direction_correct** — requires joining `stock_prices` to get the price at `forecast_date`. Use `asyncio.gather` to fetch prices in batch, not per-row queries (N+1 rule).
7. **Empty forecast track record** — new tickers won't have evaluated forecasts for 30-90 days. The empty state must be informative, not alarming.
