# Plan B: Dashboard, Screener & Sectors Enrichment

**Spec:** `docs/superpowers/specs/2026-04-26-ui-overhaul-spec-b-dashboard-portfolio.md`
**Story:** KAN-512
**Branch:** `feat/KAN-512-dashboard-screener-enrichment`
**Target:** 1 PR → `develop`
**Estimated diff:** ~200 lines added, ~20 deleted

---

## Fact Sheet (grepped 2026-04-26)

| Item | File | Line(s) | Verified |
|------|------|---------|----------|
| `usePortfolioHealthHistory` type bug | `frontend/src/hooks/use-stocks.ts` | 462-469 | Uses `PortfolioHealthResult[]`, backend returns `PortfolioHealthSnapshotResponse[]` |
| `PortfolioHealthSnapshotResponse` TS type | `frontend/src/types/api.ts` | 789-803 | Exists, correct shape |
| `usePortfolioHealth` import in portfolio-zone | `frontend/src/app/(authenticated)/dashboard/_components/portfolio-zone.tsx` | 10 | Imported from `use-stocks` |
| Health Grade badge location | `portfolio-zone.tsx` | 63-66 | `<HealthGradeBadge>` at line 65 |
| `useMacroSentiment` hook | `frontend/src/hooks/use-sentiment.ts` | 34-43 | Typed as `SentimentTimeseriesResponse`, correct |
| Market Open badge location | `frontend/src/app/(authenticated)/dashboard/_components/market-pulse-zone.tsx` | 30-40 | In `SectionHeading action` prop |
| `useBulkSentiment` type bug + param bug | `frontend/src/hooks/use-sentiment.ts` | 24-31 | Uses `unknown[]` AND missing required `tickers` query param → always 422 |
| `/sentiment/bulk` requires `tickers` param | `backend/routers/sentiment.py` | 72-100 | `tickers: str` (comma-separated, required, max 100) |
| `NewsSentiment` TS type | `frontend/src/types/api.ts` | 1036-1045 | Missing `rationale_summary` + `quality_flag` |
| Screener column defs | `frontend/src/components/screener-table.tsx` | 37-155 | `COL` record, render signature: `(item: BulkSignalItem, heldTickers?)` |
| `TAB_COLUMNS` | `screener-table.tsx` | 161-165 | `signals: ["ticker", "rsi", "macd", "sma", "bb", "score", "meter"]` |
| `ScreenerTableProps` | `screener-table.tsx` | 175-184 | Has `heldTickers?: Set<string>` |
| Screener page hook call | `frontend/src/app/(authenticated)/screener/page.tsx` | 6 | `useBulkSignals` from `use-stocks` |
| `useSectorConvergence` hook | `frontend/src/hooks/use-convergence.ts` | 68-81 | Typed as `SectorConvergenceResponse`, correct |
| `SectorAccordionProps` | `frontend/src/components/sector-accordion.tsx` | 10-15 | `{sector, isOpen, onToggle, children}` — no badge prop |
| Sector accordion header layout | `sector-accordion.tsx` | 29-76 | Flex row: name, stock count, score bar, change, yours count, alloc %, chevron |
| `usePortfolioForecast` dead code | `frontend/src/hooks/use-forecasts.ts` | 24-31 | 0 consumers (confirmed grep) |
| All 4 backend endpoints tested | `tests/unit/routers/`, `tests/api/` | — | All have existing tests |

---

## Task Sequence

### Task 1: Type fixes (foundation — all subsequent tasks depend on this)
**Files:** `frontend/src/types/api.ts`, `frontend/src/hooks/use-stocks.ts`, `frontend/src/hooks/use-sentiment.ts`

1. **Fix `NewsSentiment` type** (`api.ts:1036`):
   - Add `rationale_summary: string | null;` after `dominant_event_type`
   - Add `quality_flag: string;` after `rationale_summary`

2. **Add `BulkSentimentResponse` type** (`api.ts`, after `NewsSentiment`):
   ```ts
   export interface BulkSentimentResponse {
     tickers: NewsSentiment[];
   }
   ```

3. **Fix `usePortfolioHealthHistory` type** (`use-stocks.ts:462-469`):
   - Change `PortfolioHealthResult[]` → `PortfolioHealthSnapshotResponse[]` (both query generic and queryFn generic)
   - Add `PortfolioHealthSnapshotResponse` to the import from `@/types/api`

4. **Fix `useBulkSentiment` type AND signature** (`use-sentiment.ts:24-31`):
   - The hook is **broken as-is** — the backend requires a `tickers` query param but the hook passes none (→ always 422)
   - Change signature to accept tickers:
     ```ts
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
   - Add `BulkSentimentResponse` to the import from `@/types/api`

**Tests:** Run `npx tsc --noEmit` to verify no type errors introduced. Run `npx jest --passWithNoTests` to verify no test breakage.

---

### Task 2: Portfolio health sparkline on dashboard
**Files:** `frontend/src/app/(authenticated)/dashboard/_components/portfolio-zone.tsx`

1. **Add import** for `usePortfolioHealthHistory` from `@/hooks/use-stocks`
2. **Add import** for Recharts `LineChart`, `Line`, `ResponsiveContainer` from `recharts`
3. **Add hook call** inside `PortfolioZone()`:
   ```ts
   const { data: healthHistory } = usePortfolioHealthHistory(7);
   ```
4. **Add sparkline render** inside the Health Grade grid cell (after `<HealthGradeBadge>` at line 65):
   ```tsx
   {healthHistory && healthHistory.length >= 2 && (
     <div className={cn(
       "h-8 w-full mt-1",
       health?.grade && ["A", "B"].includes(health.grade) ? "text-gain" :
       health?.grade === "C" ? "text-amber-400" : "text-loss"
     )}>
       <ResponsiveContainer width="100%" height="100%">
         <LineChart data={healthHistory}>
           <Line
             type="monotone"
             dataKey="health_score"
             stroke="currentColor"
             strokeWidth={1.5}
             dot={false}
             isAnimationActive={false}
           />
         </LineChart>
       </ResponsiveContainer>
     </div>
   )}
   ```

**Tests:** Update `dashboard-zones.test.tsx`:
- Add `usePortfolioHealthHistory` mock to the `use-stocks` mock block (line ~18)
- Add `jest.mock("@/hooks/use-convergence", ...)` and `jest.mock("@/hooks/use-forecasts", ...)` — currently missing, needed since `portfolio-zone.tsx` imports both
- Add Recharts mock for jsdom compatibility (ResponsiveContainer renders nothing in jsdom):
  ```ts
  jest.mock("recharts", () => ({
    ...jest.requireActual("recharts"),
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div style={{ width: 100, height: 32 }}>{children}</div>
    ),
  }));
  ```
- Add test: "renders health sparkline when history has ≥2 data points"
- Add test: "does not render sparkline when history has <2 data points"

---

### Task 3: Macro sentiment badge on market pulse
**Files:** `frontend/src/app/(authenticated)/dashboard/_components/market-pulse-zone.tsx`

1. **Add import** for `useMacroSentiment` from `@/hooks/use-sentiment`
2. **Add hook call** inside `MarketPulseZone()`:
   ```ts
   const { data: macroData } = useMacroSentiment(7);
   const latestMacro = macroData?.data?.[macroData.data.length - 1];
   ```
3. **Add badge render** in the `SectionHeading action` prop (after the Market Open/Closed badge, line ~40):
   **IMPORTANT:** The `action` prop takes a single `ReactNode`. Wrap both the existing market status badge and the new macro badge in a flex container:
   ```tsx
   action={
     <div className="flex items-center gap-2">
       {/* existing market status badge */}
       <span className={cn(...)}>
         {open ? <Activity ... /> : <Clock ... />}
         {open ? "Market Open" : "Market Closed"}
       </span>
       {/* NEW macro sentiment badge */}
       {latestMacro && (
         <span className={cn(
           "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-semibold",
           latestMacro.macro_sentiment > 0.2 ? "bg-gain/10 text-gain" :
           latestMacro.macro_sentiment < -0.2 ? "bg-loss/10 text-loss" :
           "bg-muted text-muted-foreground"
         )}>
           {latestMacro.macro_sentiment > 0.2 ? "▲ Bullish" :
            latestMacro.macro_sentiment < -0.2 ? "▼ Bearish" : "— Neutral"}
         </span>
       )}
     </div>
   }
   ```

**Tests:** Update `dashboard-zones.test.tsx`:
- Add `useMacroSentiment` mock to a `jest.mock("@/hooks/use-sentiment", ...)` block
- Add test: "renders bullish badge when macro_sentiment > 0.2"
- Add test: "renders bearish badge when macro_sentiment < -0.2"
- Add test: "renders neutral badge when macro_sentiment between -0.2 and 0.2"
- Add test: "does not render macro badge when sentiment data is empty array"

---

### Task 4: Bulk sentiment column on screener
**Files:** `frontend/src/components/screener-table.tsx`, `frontend/src/app/(authenticated)/screener/page.tsx`

**Approach:** The screener table's `COL` record uses `(item: BulkSignalItem, heldTickers?)` render signature. Rather than changing the render signature (which touches every column), pass the sentiment map as a new prop to `ScreenerTable` and define the sentiment column inside the component where it can close over the prop.

1. **In `screener/page.tsx`** (inside `ScreenerContent`):
   - Add import for `useBulkSentiment` from `@/hooks/use-sentiment`
   - Extract tickers from screener results and pass to hook:
     ```ts
     const screenerTickers = useMemo(() => items.map(i => i.ticker), [items]);
     const { data: sentimentData } = useBulkSentiment(screenerTickers);
     ```
   - Build map: `const sentimentMap = useMemo(() => new Map(sentimentData?.tickers?.map(t => [t.ticker, t.stock_sentiment]) ?? []), [sentimentData]);`
   - Pass `sentimentMap` prop to `<ScreenerTable>`

2. **In `screener-table.tsx`**:
   - Add `sentimentMap?: Map<string, number>` to `ScreenerTableProps`
   - Inside the component function, define a dynamic sentiment column:
     ```ts
     const sentimentCol: Column = {
       key: "sentiment",
       label: "Sentiment",
       sortable: false,
       render: (item) => {
         const score = sentimentMap?.get(item.ticker);
         if (score == null) return <span className="text-subtle">—</span>;
         const color = score > 0.2 ? "text-gain" : score < -0.2 ? "text-loss" : "text-subtle";
         const arrow = score > 0.2 ? "▲" : score < -0.2 ? "▼" : "—";
         return <span className={cn("tabular-nums text-sm", color)}>{arrow} {score.toFixed(2)}</span>;
       },
     };
     ```
   - Modify the column resolution to inject sentiment:
     ```ts
     const columns = TAB_COLUMNS[activeTab].map((k) =>
       k === "sentiment" ? sentimentCol : COL[k]
     );
     ```
   - Add `"sentiment"` to `TAB_COLUMNS.signals` array: `["ticker", "rsi", "macd", "sma", "bb", "score", "sentiment"]`
     (replace `"meter"` with `"sentiment"` — meter and score are redundant on the same tab)

**Tests:**
- Update existing screener table tests to pass `sentimentMap` prop
- Add test: "renders sentiment score for tickers in sentiment data"
- Add test: "renders — for tickers not in sentiment data"

---

### Task 5: Sector convergence badge
**Files:** `frontend/src/app/(authenticated)/sectors/sectors-client.tsx`, `frontend/src/components/sector-accordion.tsx`

1. **In `sector-accordion.tsx`**:
   - Add optional `badge` prop to `SectorAccordionProps`:
     ```ts
     interface SectorAccordionProps {
       sector: SectorSummary;
       isOpen: boolean;
       onToggle: () => void;
       children: React.ReactNode;
       badge?: React.ReactNode;  // NEW
     }
     ```
   - Render `badge` in the header flex row, after the stock count span (line 36):
     ```tsx
     {badge}
     ```

2. **In `sectors-client.tsx`**:
   - Add import for `useSectorConvergence` from `@/hooks/use-convergence`
   - Add hook call:
     ```ts
     const { data: sectorConvergence, isLoading: convergenceLoading } =
       useSectorConvergence(openSector, !!openSector);
     ```
   - Build badge JSX:
     ```tsx
     const convergenceBadge = openSector && sectorConvergence ? (
       <span className={cn(
         "rounded-full px-2 py-0.5 text-[10px] font-semibold",
         sectorConvergence.bullish_pct > 0.5 ? "bg-gain/10 text-gain" :
         sectorConvergence.bearish_pct > 0.5 ? "bg-loss/10 text-loss" :
         "bg-amber-500/10 text-amber-400"
       )}>
         {sectorConvergence.bullish_pct > 0.5
           ? `${Math.round(sectorConvergence.bullish_pct * 100)}% Bullish`
           : sectorConvergence.bearish_pct > 0.5
           ? `${Math.round(sectorConvergence.bearish_pct * 100)}% Bearish`
           : `${Math.round(sectorConvergence.mixed_pct * 100)}% Mixed`}
       </span>
     ) : convergenceLoading && openSector ? (
       <Skeleton className="h-5 w-20 rounded-full" />
     ) : null;
     ```
   - Pass badge to `<SectorAccordion>`:
     ```tsx
     <SectorAccordion
       sector={sector}
       isOpen={openSector === sector.sector}
       onToggle={() => handleToggle(sector.sector)}
       badge={openSector === sector.sector ? convergenceBadge : undefined}
     >
     ```

**Tests:**
- Add test: "renders convergence badge when sector is open and data loaded"
- Add test: "does not render badge when sector is closed"
- Add test: "renders skeleton badge while loading"

---

### Task 6: Delete dead `usePortfolioForecast` hook
**Files:** `frontend/src/hooks/use-forecasts.ts`

1. Delete lines 23-31 (the `usePortfolioForecast` function and its comment)
2. Check if `PortfolioForecastResponse` import is still used by other code. If not, remove from imports.

**Verification:**
```bash
grep -rn "usePortfolioForecast\b" frontend/src/ --include="*.ts" --include="*.tsx" | grep -v "Full"
# Expected: 0 results after deletion
grep -rn "PortfolioForecastResponse" frontend/src/ --include="*.ts" --include="*.tsx"
# Check if still referenced elsewhere
```

**Tests:** Run full frontend test suite to confirm no import errors.

---

### Task 7: Tests + lint + final verification
**Files:** `frontend/src/__tests__/components/dashboard-zones.test.tsx`, new test files as needed

1. Run `npx tsc --noEmit` — zero type errors
2. Run `npx jest` — zero failures
3. Run `cd frontend && npm run lint` — zero lint errors
4. Run `uv run ruff check --fix backend/ tests/` + `uv run ruff format backend/ tests/` — zero issues (no backend changes, but verify)
5. Run `uv run pytest tests/unit/ -q --tb=short` — confirm baseline still 2633 passed

---

## Dependency Graph

```
Task 1 (type fixes) ← Task 2, Task 3, Task 4, Task 5
Task 6 (dead code) ← independent
Task 7 (verification) ← all above
```

Tasks 2-5 are independent of each other and can be implemented in parallel (or by separate subagents). Task 1 must complete first. Task 6 is independent. Task 7 is final.

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Screener column width overflow with new Sentiment column | Replace `meter` column (redundant with `score`) rather than adding a 8th column |
| `BulkSentimentResponse` may return no data for tickers without sentiment | Render "—" for missing tickers, don't block table |
| Sector convergence fetch on every accordion toggle | Hook `enabled` param prevents fetch until sector is open; staleTime=30min prevents re-fetch |
| Health sparkline Recharts in jsdom tests | `isAnimationActive={false}` already set in spec; mock ResponsiveContainer width if needed |

---

## Subagent Dispatch Strategy

Given ~200 lines total diff across 7 independent-ish tasks, and all frontend-only:

- **Single Sonnet subagent** is sufficient (additive work, no refactors)
- Tasks 1→2→3→4→5→6→7 in sequence (type fixes first, then each integration, then verify)
- No need for parallel subagents — the total diff is small enough for one pass
