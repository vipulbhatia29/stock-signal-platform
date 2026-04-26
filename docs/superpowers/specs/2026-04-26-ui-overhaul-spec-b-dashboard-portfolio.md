# Spec B: Dashboard, Screener & Sectors Enrichment

**Epic:** KAN-400 (UI Overhaul)
**Story:** KAN-512
**Date:** 2026-04-26
**Scope:** Wire 4 orphaned hooks + fix 2 type bugs + delete 1 dead hook
**Estimated effort:** ~1.5 days, 1 PR (all frontend-only, no backend changes)

---

## Context

Session 134 UI walkthrough and Session 137 code investigation identified 5 orphaned hooks — TanStack Query hooks with working backend endpoints that are **never imported** by any component. Session 135 brainstorming confirmed these belong in Spec B (dashboard/portfolio/screener/sectors scope).

Additionally, 2 hooks have type mismatches that would cause runtime shape bugs when wired:
- `usePortfolioHealthHistory` returns `PortfolioHealthResult[]` but backend sends `PortfolioHealthSnapshotResponse[]`
- `useBulkSentiment` returns `unknown[]` but backend sends `BulkSentimentResponse` (list of `DailySentimentResponse`)

**No backend changes required.** All endpoints are already implemented and tested.

---

## Design Principle

> These are "glue" changes — wiring existing data into existing layouts. Each integration should be **minimal and non-disruptive**: a small sparkline, a badge, a table column. No new sections, no new pages, no heavy components. If it takes more than ~30 lines of JSX per integration, the scope is wrong.

---

## Change 1: Portfolio Health Sparkline on Dashboard

### What it answers
"Is my portfolio health trending up or down this week?"

### Data source
- **Hook:** `usePortfolioHealthHistory(days)` — `frontend/src/hooks/use-stocks.ts:462-469`
- **Backend:** `GET /portfolio/health/history?days=7` → `list[PortfolioHealthSnapshotResponse]`
- **Endpoint file:** `backend/routers/portfolio.py:510-544`

### Response schema (backend — already defined)

**`PortfolioHealthSnapshotResponse`** (`backend/schemas/portfolio_health.py`):
```
snapshot_date: str (ISO date)
health_score: float
grade: str
diversification_score: float
signal_quality_score: float
risk_score: float
income_score: float
sector_balance_score: float
hhi: float
weighted_beta: float | null
weighted_sharpe: float | null
weighted_yield: float | null
position_count: int
```

### TypeScript type (already defined)
`PortfolioHealthSnapshotResponse` — `frontend/src/types/api.ts:789-803`

### Bug fix: type mismatch in hook
**File:** `frontend/src/hooks/use-stocks.ts:462-469`

The hook currently uses `PortfolioHealthResult[]` as its generic type. The backend returns `PortfolioHealthSnapshotResponse[]` which has a completely different shape (snapshot fields vs. components/concerns/strengths). Fix:
```ts
// BEFORE (wrong type)
export function usePortfolioHealthHistory(days: number = 7) {
  return useQuery<PortfolioHealthResult[]>({
    queryKey: ["portfolio-health-history", days],
    queryFn: () => get<PortfolioHealthResult[]>(`/portfolio/health/history?days=${days}`),

// AFTER (correct type)
export function usePortfolioHealthHistory(days: number = 7) {
  return useQuery<PortfolioHealthSnapshotResponse[]>({
    queryKey: ["portfolio-health-history", days],
    queryFn: () => get<PortfolioHealthSnapshotResponse[]>(`/portfolio/health/history?days=${days}`),
```

### Integration point
**File:** `frontend/src/app/(authenticated)/dashboard/_components/portfolio-zone.tsx`

**Placement:** Below the Health Grade badge (line 65), within the same grid cell. A tiny Recharts sparkline showing `health_score` over the last 7 days.

**Layout:**
```
┌──────────────────┐
│ Health Grade      │
│ [A] badge         │
│ ▁▂▃▄▅▆▇ sparkline │  ← NEW (Recharts LineChart, ~32px height, no axes)
└───────���──────────┘
```

**Implementation notes:**
- Use Recharts `LineChart` + `Line` with no axes, no grid, no tooltip — pure sparkline
- Width: fill container. Height: 32px.
- Line color: inherit from health grade color (green A/B, amber C, red D/F)
- Gate on `historyData?.length >= 2` — don't render sparkline for single data point
- Loading: no skeleton (sparkline is supplementary, don't block the tile)

**Design weight:** Very light. The sparkline is a subtle trend indicator beneath the existing badge.

### Files to modify
- `frontend/src/hooks/use-stocks.ts` — fix type import and generic on `usePortfolioHealthHistory`
- `frontend/src/app/(authenticated)/dashboard/_components/portfolio-zone.tsx` — add hook call + sparkline render

---

## Change 2: Macro Sentiment Indicator on Dashboard

### What it answers
"What's the overall market mood today?"

### Data source
- **Hook:** `useMacroSentiment(days)` — `frontend/src/hooks/use-sentiment.ts:34-43`
- **Backend:** `GET /sentiment/macro?days=30` → `SentimentTimeseriesResponse`
- **Endpoint file:** `backend/routers/sentiment.py`

### Response schema
**`SentimentTimeseriesResponse`** (reuses same schema as per-ticker sentiment):
```
ticker: str (will be "MACRO" or similar)
data: list[DailySentimentResponse]
  - date: date
  - stock_sentiment: float    ← this is the macro score for macro endpoint
  - sector_sentiment: float
  - macro_sentiment: float
  - article_count: int
  - confidence: float
  - dominant_event_type: str | None
  - rationale_summary: str | None
  - quality_flag: str
```

### TypeScript types (already defined)
- `SentimentTimeseriesResponse` — `frontend/src/types/api.ts` (via `NewsSentiment` timeseries pattern)
- Hook already typed correctly (`SentimentTimeseriesResponse`)

### Integration point
**File:** `frontend/src/app/(authenticated)/dashboard/_components/market-pulse-zone.tsx`

**Placement:** In the header row, next to the Market Open/Closed badge (line 30-43). A small mood indicator showing today's macro sentiment.

**Layout:**
```
Market Pulse          [Market Open]  [Sentiment: Bullish ▲]  ← NEW badge
```

**Implementation notes:**
- Extract latest data point from `useMacroSentiment()` response (`data[data.length - 1]`)
- Use the `macro_sentiment` field from latest point
- Display as a colored badge: green "Bullish" (> 0.2), red "Bearish" (< -0.2), gray "Neutral" (between)
- Show ▲/▼/— arrow matching direction
- If no data or error: don't render (fail silently, market pulse already works without it)

**Design weight:** Minimal — a single badge in the header. No chart, no tile, no new section.

### Files to modify
- `frontend/src/app/(authenticated)/dashboard/_components/market-pulse-zone.tsx` — add hook import + badge render

---

## Change 3: Bulk Sentiment Column on Screener

### What it answers
"Which stocks in my screener have the best/worst news sentiment?"

### Data source
- **Hook:** `useBulkSentiment(enabled)` — `frontend/src/hooks/use-sentiment.ts:24-31`
- **Backend:** `GET /sentiment/bulk` → `BulkSentimentResponse`
- **Endpoint file:** `backend/routers/sentiment.py`

### Response schema (backend)
**`BulkSentimentResponse`** (`backend/schemas/sentiment.py:32-35`):
```
tickers: list[DailySentimentResponse]
```
Each `DailySentimentResponse` has `ticker`, `stock_sentiment`, `sector_sentiment`, `macro_sentiment`, `article_count`, `confidence`, etc.

### Bug fix: type mismatch AND missing query param in hook
**File:** `frontend/src/hooks/use-sentiment.ts:24-31`

The hook has TWO bugs: (1) typed as `unknown[]` instead of `BulkSentimentResponse`, and (2) does NOT pass the required `tickers` query param → always returns 422. The backend at `sentiment.py:72-100` requires `tickers: str` (comma-separated, max 100).

Fix:
```ts
// BEFORE (broken — wrong type AND missing required param)
export function useBulkSentiment(enabled = true) {
  return useQuery({
    queryKey: ["sentiment", "bulk"],
    queryFn: () => get<unknown[]>("/sentiment/bulk"),

// AFTER (fixed — accepts tickers, correct type)
export function useBulkSentiment(tickers: string[], enabled = true) {
  const tickerParam = tickers.join(",");
  return useQuery({
    queryKey: ["sentiment", "bulk", tickerParam],
    queryFn: () => get<BulkSentimentResponse>(`/sentiment/bulk?tickers=${tickerParam}`),
    staleTime: 30 * 60 * 1000,
    enabled: enabled && tickers.length > 0,
  });
}
```

### TypeScript type fixes needed
**File:** `frontend/src/types/api.ts`

1. **Fix `NewsSentiment`** (line 1036) — add 2 missing fields to match backend `DailySentimentResponse`:
```ts
export interface NewsSentiment {
  date: string;
  ticker: string;
  stock_sentiment: number;
  sector_sentiment: number;
  macro_sentiment: number;
  article_count: number;
  confidence: number;
  dominant_event_type: string | null;
  rationale_summary: string | null;  // ← ADD (missing from backend schema)
  quality_flag: string;              // ← ADD (missing from backend schema)
}
```

2. **Add `BulkSentimentResponse`**:
```ts
export interface BulkSentimentResponse {
  tickers: NewsSentiment[];
}
```

### Integration point
**File:** `frontend/src/app/(authenticated)/screener/page.tsx`

**Placement:** Add a "Sentiment" column to the screener table, after the existing signal columns.

**Layout per row:**
```
... | RSI | MACD | Sharpe | SMA | Sentiment |
                                    ▲ 0.42    ← color-coded score + arrow
```

**Implementation notes:**
- Extract ticker list from screener results, pass to `useBulkSentiment(tickers)` at the screener level
- Build a `Map<string, number>` from `ticker → stock_sentiment` for O(1) lookup per row
- Column renders: score value (2 decimal) + ▲/▼/— arrow
- Color: green > 0.2, red < -0.2, gray otherwise
- If bulk sentiment not loaded yet, show "—" in column (don't block table render)
- Column should be sortable (add to existing sort logic)

**Design weight:** Light — one new table column. No new sections or components.

### Files to modify
- `frontend/src/hooks/use-sentiment.ts` — fix `useBulkSentiment` return type
- `frontend/src/types/api.ts` — fix `NewsSentiment` (add 2 fields) + add `BulkSentimentResponse`
- `frontend/src/app/(authenticated)/screener/page.tsx` — add hook call
- `frontend/src/components/screener-table.tsx` — add Sentiment column to `TAB_COLUMNS` (columns defined at ~line 161)

---

## Change 4: Sector Convergence Badges

### What it answers
"Are the signals within this sector mostly agreeing or conflicting?"

### Data source
- **Hook:** `useSectorConvergence(sector, enabled)` — `frontend/src/hooks/use-convergence.ts:68-81`
- **Backend:** `GET /sectors/{sector}/convergence` → `SectorConvergenceResponse`
- **Endpoint file:** `backend/routers/convergence.py`

### Response schema
**`SectorConvergenceResponse`** (`backend/schemas/convergence.py:150-159`):
```
sector: str
date: date
tickers: list[SectorTickerConvergence]
  - ticker: str
  - convergence_label: ConvergenceLabelEnum
  - signals_aligned: int (0-6)
bullish_pct: float (0-1)
bearish_pct: float (0-1)
mixed_pct: float (0-1)
ticker_count: int
```

### TypeScript types (already defined)
`SectorConvergenceResponse` — `frontend/src/types/api.ts:1166-1177`

### Integration point
**File:** `frontend/src/app/(authenticated)/sectors/sectors-client.tsx`

**Placement:** In each `SectorAccordion` header, next to the sector name. Show a convergence badge for the **currently open** sector only (to avoid N API calls for all sectors).

**Layout:**
```
┌─ Technology ────────────── [72% Bullish] ──── ▼ ─┐
│  stocks table...                                  │
└────────────────────────────────────���──────────────┘
┌─ Healthcare ──────────────────────────────── ▶ ─┐  (closed — no badge)
```

**Implementation notes:**
- Call `useSectorConvergence(openSector, !!openSector)` in `SectorsClient` — only fetches when a sector is expanded
- Pass `convergenceBadge` data as a prop to `SectorAccordion`
- Badge shows `{Math.round(bullish_pct * 100)}% Bullish` or `{Math.round(bearish_pct * 100)}% Bearish` depending on which is dominant
- Color: green if bullish_pct > 0.5, red if bearish_pct > 0.5, amber if mixed_pct > 0.4
- Loading state: small skeleton badge while fetching
- The `SectorAccordion` component needs a new optional `badge` prop

**Design weight:** Very light — a single badge per open accordion header.

### Files to modify
- `frontend/src/app/(authenticated)/sectors/sectors-client.tsx` — add hook call + pass badge data
- `frontend/src/components/sector-accordion.tsx` — add optional `badge` prop to header

---

## Change 5: Delete Dead `usePortfolioForecast` Hook

### What
`usePortfolioForecast` at `frontend/src/hooks/use-forecasts.ts:24-31` is superseded by `usePortfolioForecastFull`. It has **0 imports** across the entire codebase.

### Action
Delete lines 24-31 from `use-forecasts.ts`. Remove the `PortfolioForecastResponse` import if it becomes unused.

### Verification
```bash
grep -rn "usePortfolioForecast\b" frontend/src/ --include="*.ts" --include="*.tsx" | grep -v "Full"
```
Expected: only the hook definition itself, no consumers.

### Files to modify
- `frontend/src/hooks/use-forecasts.ts` — delete `usePortfolioForecast` function

---

## PR Strategy

**Single PR** — all changes are frontend-only, independent, and small. Total estimated diff: ~150 lines added, ~15 lines deleted.

If reviewer prefers splitting, the natural split is:
- PR1: Changes 1-2 (dashboard enrichments) + Change 5 (dead code)
- PR2: Changes 3-4 (screener + sectors)

But the combined diff is well under 300 lines, so a single PR is recommended.

---

## Testing Strategy

### Existing tests to update
- `frontend/src/__tests__/components/dashboard-zones.test.tsx` — add mock for `usePortfolioHealthHistory`, verify sparkline renders
- Verify existing screener tests still pass with new column

### New test coverage
- **Sparkline:** renders when history has ≥2 points, doesn't render for <2 points
- **Macro badge:** renders "Bullish"/"Bearish"/"Neutral" based on threshold values
- **Sentiment column:** renders score for tickers present in bulk data, shows "—" for missing tickers
- **Sector convergence badge:** renders bullish_pct when sector is open, no badge when closed
- **Dead hook deletion:** verify no import errors after removing `usePortfolioForecast`

### No backend tests needed
All 4 backend endpoints are already tested in existing test suites.

---

## Out of Scope

- `/portfolio/{id}/forecast/components` endpoint wiring — **deferred to KAN-514** (requires backend Prophet implementation first)
- Screener sorting by sentiment — can be a follow-up if sorting infrastructure needs refactor
- Sentiment on stock detail page — already shipped in Spec A (`SentimentCard`)
- Convergence on stock detail page — already shipped in Spec A (`ConvergenceCard`)
- Admin page changes — Spec C (KAN-513)
- Any backend changes — all endpoints are already implemented

---

## Key Gotchas for Implementers

1. **`API_BASE = "/api/v1"` in `api.ts`** — hooks use `/sentiment/bulk` NOT `/api/v1/sentiment/bulk`
2. **`usePortfolioHealthHistory` type bug** — MUST fix from `PortfolioHealthResult[]` to `PortfolioHealthSnapshotResponse[]` before wiring, otherwise runtime data won't match type expectations
3. **`useBulkSentiment` type bug** — MUST fix from `unknown[]` to `BulkSentimentResponse` before wiring
4. **Recharts sparkline** — use `isAnimationActive={false}` in tests (jsdom has no layout engine)
5. **Sector convergence N+1** — only fetch for the open sector, NOT all sectors at once. The hook's `enabled` param gates this.
6. **Screener pagination** — bulk sentiment returns all tracked tickers, but screener shows 50 per page. The Map lookup handles this naturally.
7. **`NewsSentiment` type** — exists at `api.ts:1036` but is **missing `rationale_summary` and `quality_flag`** vs backend. Fix before wiring `BulkSentimentResponse`.
8. **Screener table columns** — defined in `screener-table.tsx` TAB_COLUMNS (~line 161), NOT in `page.tsx`. Add Sentiment column to the `signals` tab columns.
