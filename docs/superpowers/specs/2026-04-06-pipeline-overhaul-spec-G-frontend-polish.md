# Spec G: Frontend Polish — Progress UX, Stale Badges, Polling

**Status:** Draft
**Date:** 2026-04-06
**Authors:** Pipeline Overhaul team
**Part of:** Pipeline Architecture Overhaul Epic

---

## Problem Statement

The frontend has several UX gaps that become more visible once Specs B and C land:

1. **No ingest progress indicator.** When a user clicks "Add" on a new stock or logs a portfolio transaction, they see a spinner with no detail. After Spec C lands, latency increases from 200ms to 5-15s for new tickers — the user needs to know what's happening.
2. **No portfolio polling for freshly-added tickers.** TanStack Query staleTime is 60s+ on portfolio hooks; no `refetchInterval`. A user adds a ticker, sees "no data" briefly, refreshes manually.
3. **`is_stale` flag exists in API types but no component renders it.** Schema-only lie. Users see stale data without warning.
4. **`LogTransactionDialog` uses a free-text Input for ticker** — typos pass format validation, fail downstream with confusing errors. (`frontend/src/components/log-transaction-dialog.tsx:68-78`)
5. **`useIngestTicker.onSuccess` invalidates only signals + prices** — fundamentals, news, intelligence, forecast, etc. all stay stale until manual refresh. (`frontend/src/hooks/use-stocks.ts:115-119`)
6. **`WelcomeBanner` is dead code** — built but not mounted. Cold-start users see empty dashboard with no guidance. (`frontend/src/components/welcome-banner.tsx`)

---

## Goals

- User sees rich progress feedback during long-running ingest operations
- Recently-added tickers refresh automatically until "ready" state
- Stale data is visually marked everywhere it appears
- Cold-start users get guided onboarding via the existing `WelcomeBanner`
- Typo prevention in transaction logging via `TickerSearch`

## Non-Goals

- Full multi-step onboarding wizard (separate spec, post-MVP)
- WebSocket-based real-time updates (polling is enough for this use case)
- Internationalization of new strings

---

## Design

### G1. Ingest progress indicator (toast + optional modal)

**Backend dependency:** Spec D3 ingestion health endpoint provides per-ticker stage timestamps. Spec A ticker_ingestion_state table is the source. We can poll `GET /api/v1/admin/ingestion/health?ticker=X` (or a non-admin equivalent) to get progress.

**Decision:** instead of building a separate `/stocks/{ticker}/ingest/progress` endpoint, expose a non-admin **read-only** endpoint:

`GET /api/v1/stocks/{ticker}/ingest-state` — returns:
```json
{
  "ticker": "AAPL",
  "stages": {
    "prices": {"updated_at": "2026-04-06T20:30:00Z", "status": "fresh"},
    "signals": {"updated_at": "2026-04-06T20:30:05Z", "status": "fresh"},
    "fundamentals": {"updated_at": null, "status": "missing"},
    "forecast": {"updated_at": null, "status": "pending"},
    "news": {"updated_at": null, "status": "pending"},
    "sentiment": {"updated_at": null, "status": "pending"},
    "convergence": {"updated_at": null, "status": "pending"}
  },
  "overall_status": "ingesting",
  "completion_pct": 28
}
```

**Backend file:** `backend/routers/stocks/data.py` — new endpoint near other stock detail endpoints. Reads from `ticker_ingestion_state` (Spec A) + computes status based on `StalenessSLAs` (Spec A2). Returns `overall_status`: `"ready" | "ingesting" | "stale" | "missing"`.

**Frontend new component:** `frontend/src/components/ingest-progress-toast.tsx`

```tsx
// Shows in sonner toast positon. Polls /ingest-state every 2s while overall_status === "ingesting".
// Renders 7 stage rows with checkmarks/spinners.
// Auto-dismisses after 5s of "ready" state.
```

**Frontend new hook:** `frontend/src/hooks/use-ingest-progress.ts`

```ts
export function useIngestProgress(ticker: string | null, enabled: boolean) {
  return useQuery({
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

**Integration sites:**

- `frontend/src/app/(authenticated)/layout.tsx:31-38` — replace `toast.loading(...)` in `handleAddTicker` with `<IngestProgressToast ticker={ticker} />` component triggered via `toast.custom(...)`
- `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx:96-110` — same replacement for the "Run Analysis" flow
- `frontend/src/components/log-transaction-dialog.tsx` — show inline progress bar during sync ingest of new ticker (Spec C2)

**TypeScript types** in `frontend/src/types/api.ts`:

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

---

### G2. Portfolio + dashboard polling for ingesting tickers

**Files modified:**

- `frontend/src/hooks/use-stocks.ts:190-196` — `useSignals`:
  ```ts
  refetchInterval: (q) => {
    const data = q.state.data;
    if (!data) return false;
    if (data.is_refreshing) return 5000;  // from Spec C4
    return false;
  },
  ```
- `frontend/src/hooks/use-stocks.ts` (or `use-portfolio.ts`) — `usePositions`:
  ```ts
  refetchInterval: (q) => {
    const positions = q.state.data;
    if (!positions) return false;
    // Poll if any position has ingestion_status === "ingesting"
    const anyIngesting = positions.some(p => p.ingestion_status === "ingesting");
    return anyIngesting ? 5000 : false;
  },
  ```
- Backend dependency: `Position` API response needs `ingestion_status` field. Add via join with `ticker_ingestion_state` in `backend/services/portfolio/fifo.py:get_positions_with_pnl` (or wherever positions are fetched). Add to `PositionWithAlerts` schema in `backend/schemas/portfolio.py`.

**Frontend type update** `Position` in `frontend/src/types/api.ts`: add `ingestion_status?: "ready" | "ingesting" | "stale" | "missing"`.

---

### G3. `LogTransactionDialog` ticker search integration

**File modified:** `frontend/src/components/log-transaction-dialog.tsx:68-78`

**Change:** Replace the free-text `<Input>` for ticker with the existing `<TickerSearch>` component:

```tsx
import { TickerSearch } from "@/components/ticker-search";

// Inside form:
<div className="space-y-2">
  <Label htmlFor="ticker">Ticker</Label>
  <TickerSearch
    onSelect={(ticker) => setForm({ ...form, ticker })}
    initialValue={form.ticker}
    placeholder="Search ticker or company name..."
  />
</div>
```

**TickerSearch behavior:** searches `/api/v1/stocks/search` (in-DB + Yahoo), returns `in_db: bool`. After Spec C2, the user can pick any external ticker and it will be auto-ingested on transaction submit.

---

### G4. Stale badges across stock detail page

**Files modified:**

- `frontend/src/components/signal-cards.tsx` — render small "Stale" badge next to each signal card if `signals.is_stale === true`. If `is_refreshing === true`, swap for "Refreshing..." with spinner.
- `frontend/src/components/stock-header.tsx` — add small stale indicator next to score badge.
- `frontend/src/components/score-bar.tsx` — opacity to 0.6 when `is_stale`, with tooltip "Last updated 26h ago — refreshing in background".
- `frontend/src/components/forecast-card.tsx` — add "Forecast 5 days old" subtitle if forecast `created_at > 5 days ago`. Forecast staleness check: 7-day SLA from Spec A2.
- `frontend/src/components/news-card.tsx` — add "News last updated 12h ago" footer if news `published_at` max > 6h.

**New shared component:** `frontend/src/components/staleness-badge.tsx`:

```tsx
interface StalenessBadgeProps {
  lastUpdated: string | null;
  slaHours: number;
  refreshing?: boolean;
}

export function StalenessBadge({ lastUpdated, slaHours, refreshing }: StalenessBadgeProps) {
  if (refreshing) return <Badge variant="info"><Spinner /> Refreshing</Badge>;
  if (!lastUpdated) return <Badge variant="warning">No data</Badge>;
  const ageHours = (Date.now() - new Date(lastUpdated).getTime()) / 3600000;
  if (ageHours > slaHours * 2) return <Badge variant="destructive">Very stale ({Math.round(ageHours)}h old)</Badge>;
  if (ageHours > slaHours) return <Badge variant="warning">Stale ({Math.round(ageHours)}h old)</Badge>;
  return null;
}
```

Use across all 5 components above.

---

### G5. Frontend cache invalidation in `useIngestTicker` (already in Batch 0 / Spec Z)

**File modified:** `frontend/src/hooks/use-stocks.ts:115-119`

**Change:** Already covered in Spec Z.B0.5. After successful ingest, invalidate the full query set:
```ts
onSuccess: (_, ticker) => {
  queryClient.invalidateQueries({ queryKey: ["signals", ticker] });
  queryClient.invalidateQueries({ queryKey: ["prices", ticker] });
  queryClient.invalidateQueries({ queryKey: ["fundamentals", ticker] });
  queryClient.invalidateQueries({ queryKey: ["watchlist"] });
  queryClient.invalidateQueries({ queryKey: ["bulk-signals"] });
  queryClient.invalidateQueries({ queryKey: ["stock-news", ticker] });
  queryClient.invalidateQueries({ queryKey: ["intelligence", ticker] });
  queryClient.invalidateQueries({ queryKey: ["forecast", ticker] });
  queryClient.invalidateQueries({ queryKey: ["benchmark", ticker] });
  queryClient.invalidateQueries({ queryKey: ["analytics", ticker] });
  queryClient.invalidateQueries({ queryKey: ["ingest-state", ticker] });
},
```

(This is the Batch 0 quick win — restated here for completeness, will not be re-implemented in Spec G.)

---

### G6. Mount `WelcomeBanner` for cold-start users (already in Batch 0)

**File modified:** `frontend/src/app/(authenticated)/dashboard/page.tsx`

**Change:** Conditionally render `<WelcomeBanner onAddTicker={handleAddTicker} addingTickers={addingSet} />` when both watchlist and portfolio are empty.

(Restated from Spec Z.B0.6.)

---

## Files Created

| Path | Purpose |
|---|---|
| `frontend/src/components/ingest-progress-toast.tsx` | Rich progress UI with stage breakdown |
| `frontend/src/components/staleness-badge.tsx` | Shared "stale/refreshing" badge component |
| `frontend/src/hooks/use-ingest-progress.ts` | Polling hook for ingest state |
| `backend/routers/stocks/data.py` (new endpoint) | `GET /stocks/{ticker}/ingest-state` for non-admin polling |
| `frontend/src/__tests__/components/ingest-progress-toast.test.tsx` | Component test |
| `frontend/src/__tests__/components/staleness-badge.test.tsx` | Component test |
| `frontend/src/__tests__/hooks/use-ingest-progress.test.ts` | Hook test |
| `tests/api/test_stock_ingest_state.py` | API test for new endpoint |

## Files Modified

| File | Change |
|---|---|
| `frontend/src/hooks/use-stocks.ts` | G1: integrate progress; G2: refetchInterval on signals + positions; G5: full invalidation in useIngestTicker (already in Z) |
| `frontend/src/app/(authenticated)/layout.tsx` | G1: replace plain toast with IngestProgressToast |
| `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx` | G1: same; G4: render stale badges |
| `frontend/src/components/log-transaction-dialog.tsx` | G3: replace ticker Input with TickerSearch; G1: inline progress for new tickers |
| `frontend/src/components/signal-cards.tsx` | G4: render stale badges |
| `frontend/src/components/stock-header.tsx` | G4: render stale badges |
| `frontend/src/components/score-bar.tsx` | G4: opacity + tooltip when stale |
| `frontend/src/components/forecast-card.tsx` | G4: forecast age subtitle |
| `frontend/src/components/news-card.tsx` | G4: news age footer |
| `frontend/src/types/api.ts` | New types: IngestState, StageStatus, StageInfo; Position add ingestion_status |
| `frontend/src/app/(authenticated)/dashboard/page.tsx` | G6: mount WelcomeBanner conditionally |
| `backend/routers/stocks/data.py` | New `/ingest-state` endpoint |
| `backend/schemas/stock.py` | New IngestStateResponse, StageInfo, StageStatus enum schemas |
| `backend/schemas/portfolio.py` | Add `ingestion_status` field to PositionWithAlerts |
| `backend/services/portfolio/fifo.py` (after Spec from KAN-413 split) or `backend/services/portfolio.py` | Join with `ticker_ingestion_state` in `get_positions_with_pnl` |

---

## API Contract Changes

| Endpoint | Change |
|---|---|
| `GET /api/v1/stocks/{ticker}/ingest-state` | **NEW** — returns IngestStateResponse |
| `GET /api/v1/portfolio/positions` | Position response now includes `ingestion_status` field |
| `GET /api/v1/stocks/{ticker}/signals` | Already extended in Spec C4 with `is_refreshing`, `last_refresh_attempt` |

## Frontend Impact Summary

- ~12 component changes across signal/forecast/news cards + dialogs
- 1 new shared component (`StalenessBadge`)
- 1 new toast component (`IngestProgressToast`)
- 1 new hook (`useIngestProgress`)
- ~5 new TypeScript types

---

## Test Impact

### Existing test files affected

Grep evidence:

- `frontend/src/__tests__/components/log-transaction-dialog.test.tsx` — replace mock for ticker Input with TickerSearch mock
- `frontend/src/__tests__/components/signal-cards.test.tsx` — add stale badge rendering test
- `frontend/src/__tests__/components/stock-header.test.tsx` — same
- `frontend/src/__tests__/integration/portfolio.test.tsx` — verify ingestion_status flows through
- `frontend/src/__tests__/components/welcome-banner.test.tsx` — verify mount condition
- `frontend/src/__tests__/hooks/use-stocks.test.ts` — verify useSignals refetchInterval triggers when is_refreshing
- Backend: `tests/api/test_stocks.py` — add test for new /ingest-state endpoint
- Backend: `tests/api/test_portfolio.py` — verify positions response includes `ingestion_status`

### New test cases enumerated

**IngestProgressToast (8 cases):**
1. test_renders_7_stage_rows
2. test_polls_every_2_seconds_when_ingesting
3. test_stops_polling_when_ready
4. test_auto_dismisses_5_seconds_after_ready
5. test_shows_checkmark_for_fresh_stages
6. test_shows_spinner_for_pending_stages
7. test_shows_red_for_failed_stages
8. test_handles_404_gracefully (ticker disappears from state)

**StalenessBadge (6 cases):**
1. test_returns_null_when_within_sla
2. test_renders_warning_when_stale
3. test_renders_destructive_when_very_stale_2x_sla
4. test_renders_no_data_when_last_updated_null
5. test_renders_refreshing_when_refreshing_true
6. test_calculates_age_hours_correctly

**Hooks (4 cases):**
1. test_use_ingest_progress_polls_when_ingesting
2. test_use_ingest_progress_stops_when_ready
3. test_use_signals_refetch_when_is_refreshing
4. test_use_positions_refetch_when_any_ingesting

**Backend endpoint (5 cases):**
1. test_ingest_state_returns_all_7_stages
2. test_ingest_state_overall_status_ready_when_all_fresh
3. test_ingest_state_overall_status_ingesting_when_some_pending
4. test_ingest_state_completion_pct_calculated
5. test_ingest_state_404_for_unknown_ticker

**Visual regression (3 cases — for KAN-363 unblock later):**
1. signal-cards-stale snapshot
2. forecast-card-old snapshot
3. ingest-progress-toast snapshot

---

## Migration Strategy

- All additive — new types, new components, new endpoint
- Existing components get `is_stale` rendering added without breaking current behavior
- WelcomeBanner mounted conditionally — no impact on users with existing data
- TickerSearch in LogTransactionDialog is a UX upgrade; old free-text input deleted in same PR

## Risk + Rollback

| Risk | Mitigation | Rollback |
|---|---|---|
| Polling overload from too many open tabs | Bound polling to 2s minimum, only when status=ingesting | Disable polling, fall back to manual refresh |
| StalenessBadge clutters UI | Only renders when stale; null otherwise | Remove from individual components |
| TickerSearch in dialog confuses existing users | Add tooltip "Search by ticker or company name"; existing typed-text usage falls back to search results | Revert dialog component |

## Open Questions

1. **IngestProgress polling cadence:** 2s vs 5s? Recommendation: 2s for first 30s, 5s after. (Implement as exponential backoff.)
2. **Stale badge visual style:** colored badge vs subtle text? Recommendation: badge for clarity.
3. **WelcomeBanner placement:** above dashboard zones vs below? Recommendation: above — first thing user sees.

---

## Dependencies

- **Blocks:** None (frontend-only after backend deps land)
- **Depends on:**
  - Spec A (`ticker_ingestion_state` table for ingest-state endpoint)
  - Spec C2/C4 (sync portfolio ingest + stale auto-refresh)
  - Spec D3 (admin ingestion health uses same backend logic)
- **Supersedes JIRA:** Partial KAN-216 (frontend component tests for high-impact components — IngestProgressToast, StalenessBadge fall under this)

---

## Doc Delta

- `docs/FSD.md`: add FR for "Ingest progress feedback", "Staleness indicators on stock detail"
- `docs/PRD.md`: small mention in "User feedback" section
- README: no change
- ADR: not needed
