# Spec Z: Quick Wins (Batch 0)

**Status:** Draft
**Date:** 2026-04-06
**Authors:** Pipeline Overhaul team
**Part of:** Pipeline Architecture Overhaul Epic

---

## Problem Statement

Six small fixes with zero downstream blast radius. Each can be a separate small PR or grouped into one. Done before or in parallel with the bigger specs A-G.

---

## Goals

- Land quick correctness fixes immediately
- Unblock observability for admin "news_sentiment" pipeline group
- Fix the most blatant LIMIT 50 bug
- Mount dead code (WelcomeBanner) that's already built
- Improve frontend cache invalidation breadth

## Non-Goals

- Anything requiring design (defer to A-G specs)

---

## Design

### Z1. PipelineRegistry news task name typo

**File:** `backend/services/pipeline_registry_config.py:443`

**Current:**
```python
name="backend.tasks.news_sentiment.sentiment_scoring_task",
```

**Fix:**
```python
name="backend.tasks.news_sentiment.news_sentiment_scoring_task",
```

**Impact:** Admin "news_sentiment" pipeline group currently fails with Celery `Received unregistered task`. Beat schedule is unaffected (uses correct name). One-line fix.

**Test:** Add `tests/unit/services/test_pipeline_registry_config.py::test_every_registered_task_resolves_to_real_task` — iterate `build_registry().get_all_tasks()`, assert each `task.name` is in `celery_app.tasks` (Celery's registry). This catches future drift.

---

### Z2. Delete `calibrate_seasonality_task` stub

**Files:**
- `backend/tasks/forecasting.py:241-253` — delete the stub function entirely
- `backend/services/pipeline_registry_config.py:419` — delete the registration in the "model_training" group
- `backend/tasks/__init__.py:11-24` — remove from `include=[]` if present (currently in `forecasting` module so already imported transitively)

**Rationale:** The stub returns fake success without doing anything. It's been closed as "Done" since KAN-370 Sprint 4. Deleting removes the broken window. We can re-introduce a real implementation in a future spec when calibration is genuinely needed (with backtest baselines from Spec B2).

**Caveat:** User confirmed deletion is OK in their decision response. If priorities change, replace this with implementing the 4-config-per-ticker walk-forward calibration.

**Test:** Add `tests/unit/tasks/test_forecasting.py::test_calibrate_seasonality_task_deleted` — assert `calibrate_seasonality_task` is no longer importable from `backend.tasks.forecasting`. Future-proofs against accidental re-introduction without spec.

---

### Z3. News ingest LIMIT 50 bug

**File:** `backend/tasks/news_sentiment.py:48-53`

**Current:**
```python
async with async_session_factory() as session:
    result = await session.execute(
        select(Stock.ticker).where(Stock.is_active.is_(True)).limit(50)
    )
    tickers = [row[0] for row in result.all()]
```

**Fix:**
```python
async with async_session_factory() as session:
    from backend.services.ticker_universe import get_all_referenced_tickers
    all_tickers = await get_all_referenced_tickers(session)
    # Hard cap at 200 to control API quota; can be raised after rate limiter (Spec F2) lands
    tickers = all_tickers[:200]
```

**Impact:** All portfolio + watchlist + index tickers (up to 200) get news ingested per run, instead of an arbitrary 50.

**Tests:**
- `tests/unit/tasks/test_news_sentiment.py::test_news_ingest_uses_canonical_universe` — patch `get_all_referenced_tickers`, assert it's called instead of the old `select(Stock).limit(50)`
- `tests/unit/tasks/test_news_sentiment.py::test_news_ingest_caps_at_200` — return 250 tickers from canonical universe, assert only 200 are passed to `service.ingest_stock_news`
- `tests/unit/tasks/test_news_sentiment.py::test_news_ingest_caps_at_universe_size_when_smaller` — return 30 tickers, assert all 30 used

**Risk + Sequencing (CRITICAL — review finding):**

Z3 raises the news-ingest cap from the legacy 50 to 200 — a 4x increase
in Finnhub/Google News call volume during the nightly news ingest phase.
Without the Spec F2/F3 rate limiters in place, this will push a free-tier
Finnhub key over quota and trigger a temporary API ban that affects the
entire platform.

**Rule:** Z3 MUST merge AFTER Spec F2 + F3 rate limiters land. If schedule
pressure forces Z3 to ship first, keep `NEWS_INGEST_TICKER_CAP = 50` (no
behaviour change from today) until F2/F3 deploys — do NOT ship the 200
cap without an active rate limiter.

---

### Z4. Rename `refresh_all_watchlist_tickers_task` → `intraday_refresh_all_task`

**Files:**
- `backend/tasks/market_data.py:394-413` — rename function and update Celery `@celery_app.task(name=...)` decorator
- `backend/tasks/__init__.py:38-41` — update beat entry name

**Approach:** Keep old name as a deprecation alias for one release:

```python
@celery_app.task(name="backend.tasks.market_data.intraday_refresh_all_task")
def intraday_refresh_all_task() -> dict:
    """..."""
    # ... existing logic
    pass

# Deprecation alias — DELETE in next release
@celery_app.task(name="backend.tasks.market_data.refresh_all_watchlist_tickers_task")
def refresh_all_watchlist_tickers_task() -> dict:
    """DEPRECATED — use intraday_refresh_all_task. Will be removed in next release."""
    import warnings
    warnings.warn(
        "refresh_all_watchlist_tickers_task is deprecated; use intraday_refresh_all_task",
        DeprecationWarning,
        stacklevel=2,
    )
    return intraday_refresh_all_task()
```

**Beat schedule update** in `backend/tasks/__init__.py`:
```python
"intraday-refresh-all": {
    "task": "backend.tasks.market_data.intraday_refresh_all_task",
    "schedule": 30 * 60,
},
```

**PipelineRegistry update** in `backend/services/pipeline_registry_config.py:317`: update task name reference.

**Tests:**
- `tests/unit/tasks/test_celery_tasks.py::test_intraday_refresh_all_task_registered`
- `tests/unit/tasks/test_celery_tasks.py::test_legacy_alias_warns_and_delegates` — call old name, assert DeprecationWarning + delegation
- `tests/unit/tasks/test_seed_tasks.py` — verify beat schedule entry has new name

**Risk:** Any external Celery client code referencing the old name (none expected) breaks. Alias mitigates.

---

### Z5. Frontend `useIngestTicker` full cache invalidation

**File:** `frontend/src/hooks/use-stocks.ts:115-119`

**Current:**
```typescript
onSuccess: (_, ticker) => {
  queryClient.invalidateQueries({ queryKey: ["signals", ticker] });
  queryClient.invalidateQueries({ queryKey: ["prices", ticker] });
}
```

**Fix:**
```typescript
onSuccess: (_, ticker) => {
  // Invalidate every cache layer that depends on this ticker
  const tickerQueries = [
    ["signals", ticker],
    ["prices", ticker],
    ["fundamentals", ticker],
    ["stock-news", ticker],
    ["intelligence", ticker],
    ["forecast", ticker],
    ["benchmark", ticker],
    ["analytics", ticker],
    ["ingest-state", ticker],  // from Spec G1
  ];
  for (const key of tickerQueries) {
    queryClient.invalidateQueries({ queryKey: key });
  }
  // Global lists that may include this ticker
  queryClient.invalidateQueries({ queryKey: ["watchlist"] });
  queryClient.invalidateQueries({ queryKey: ["bulk-signals"] });
  queryClient.invalidateQueries({ queryKey: ["positions"] });
}
```

**Impact:** After successful ingest, every dependent UI surface refetches automatically. No more stale fundamentals/news/intelligence/etc. after click.

**Tests:**
- `frontend/src/__tests__/hooks/use-stocks.test.ts::useIngestTicker invalidates full query set` — mock queryClient, call mutation, assert all 12 query keys invalidated

---

### Z6. Mount `WelcomeBanner` for cold-start users

**File:** `frontend/src/app/(authenticated)/dashboard/page.tsx`

**Current:** No conditional rendering of `WelcomeBanner`. Component is built (`frontend/src/components/welcome-banner.tsx`) and tested but never displayed.

**Fix:** Add at top of dashboard page render, conditional on empty watchlist + no portfolio positions:

```tsx
import { WelcomeBanner } from "@/components/welcome-banner";
import { useWatchlist, usePositions } from "@/hooks/use-stocks";

export default function DashboardPage() {
  const { data: watchlist = [] } = useWatchlist();
  const { data: positions = [] } = usePositions();
  const isEmpty = watchlist.length === 0 && positions.length === 0;

  // Track in-flight adds for spinner state on banner buttons
  const [addingTickers, setAddingTickers] = useState<Set<string>>(new Set());

  const handleAddTicker = async (ticker: string) => {
    setAddingTickers(prev => new Set(prev).add(ticker));
    try {
      // After Spec C1, this is one call instead of two
      await addToWatchlist.mutateAsync(ticker);
    } finally {
      setAddingTickers(prev => {
        const next = new Set(prev);
        next.delete(ticker);
        return next;
      });
    }
  };

  return (
    <DashboardShell>
      {isEmpty && (
        <WelcomeBanner
          onAddTicker={handleAddTicker}
          addingTickers={addingTickers}
        />
      )}
      {/* existing zones */}
    </DashboardShell>
  );
}
```

**Impact:** New users see 5 suggested starter tickers (AAPL, MSFT, GOOGL, NVDA, TSLA) with one-click add. Eliminates the empty-dashboard cold-start.

**Tests:**
- `frontend/src/__tests__/app/dashboard.test.tsx::renders WelcomeBanner when watchlist and positions are empty` — mock empty data, assert banner present
- `frontend/src/__tests__/app/dashboard.test.tsx::hides WelcomeBanner when watchlist has items` — mock 1 watchlist item, assert banner absent

---

## Files Created

| Path | Purpose |
|---|---|
| `tests/unit/services/test_pipeline_registry_config.py` | Z1: registry → real-task validation |
| `tests/unit/tasks/test_forecasting_calibration_deletion.py` | Z2: future-proof against re-introduction |

(All other tests amend existing files.)

## Files Modified

| File | Change |
|---|---|
| `backend/services/pipeline_registry_config.py` | Z1: typo fix; Z2: remove calibrate_seasonality_task entry; Z4: rename in registry |
| `backend/tasks/forecasting.py` | Z2: delete `calibrate_seasonality_task` function |
| `backend/tasks/news_sentiment.py` | Z3: use canonical universe, cap at 200 |
| `backend/tasks/market_data.py` | Z4: rename + add deprecation alias |
| `backend/tasks/__init__.py` | Z4: update beat entry name |
| `frontend/src/hooks/use-stocks.ts` | Z5: full cache invalidation in useIngestTicker |
| `frontend/src/app/(authenticated)/dashboard/page.tsx` | Z6: mount WelcomeBanner conditionally |
| `tests/unit/services/test_pipeline_registry_config.py` | Z1: new test |
| `tests/unit/tasks/test_news_sentiment.py` | Z3: new test cases |
| `tests/unit/tasks/test_celery_tasks.py` | Z4: new test cases |
| `frontend/src/__tests__/hooks/use-stocks.test.ts` | Z5: new invalidation test |
| `frontend/src/__tests__/app/dashboard.test.tsx` | Z6: new mount tests |

---

## API Contract Changes

**None.** All Spec Z items are internal fixes.

## Frontend Impact

- 2 file changes (Z5, Z6)
- 0 new types
- 0 new components

---

## Test Impact

### Existing test files affected

- `tests/unit/tasks/test_news_sentiment.py` — Z3 modifies behavior
- `tests/unit/tasks/test_celery_tasks.py` — Z4 task rename
- `tests/unit/tasks/test_seed_tasks.py` — Z4 beat schedule reference
- `tests/unit/tasks/test_forecasting.py` — Z2 stub deletion
- `frontend/src/__tests__/hooks/use-stocks.test.ts` — Z5
- `frontend/src/__tests__/app/dashboard.test.tsx` — Z6 (may not exist; create)

### New test files

- `tests/unit/services/test_pipeline_registry_config.py` — Z1 enforcement test
- `tests/unit/tasks/test_forecasting_calibration_deletion.py` — Z2 future-proof

### Specific test cases (full enumeration)

**Z1 (1 case):**
1. test_every_registered_task_resolves_to_real_celery_task

**Z2 (2 cases):**
1. test_calibrate_seasonality_task_not_importable
2. test_calibrate_seasonality_not_in_registry

**Z3 (3 cases):**
1. test_news_ingest_uses_canonical_universe
2. test_news_ingest_caps_at_200
3. test_news_ingest_handles_universe_smaller_than_cap

**Z4 (3 cases):**
1. test_intraday_refresh_all_task_registered_with_new_name
2. test_legacy_refresh_all_watchlist_tickers_task_warns_and_delegates
3. test_beat_schedule_uses_new_task_name

**Z5 (1 case):**
1. test_use_ingest_ticker_invalidates_full_query_set

**Z6 (2 cases):**
1. test_dashboard_renders_welcome_banner_when_empty
2. test_dashboard_hides_welcome_banner_when_data_exists

**Total: 12 test cases across 6 fixes.**

---

## Migration Strategy

- All Z items are non-breaking, can land in any order
- Z3 (news LIMIT 50 fix) should land alongside or after Spec F2 rate limiter to avoid hammering news APIs
- Z4 alias prevents external client breakage
- Z5/Z6 are pure frontend, no backend coordination

## Risk + Rollback

| Item | Risk | Rollback |
|---|---|---|
| Z1 | None | Revert one line |
| Z2 | If a future spec wanted seasonality, would need to rebuild | Restore from git history |
| Z3 | Higher news API call volume | Restore LIMIT 50 |
| Z4 | None (alias preserved) | Drop alias |
| Z5 | More aggressive refetches → more backend load on ingest | Revert to 2-key invalidation |
| Z6 | None — only renders when both empty | Hide banner |

## Open Questions

1. **Z2 — delete or implement?** User confirmed delete in their last response. Spec assumes deletion.
2. **Z3 — cap value:** 200 default. Recommendation: tune after observing actual portfolio sizes.
3. **Z4 — release window for deprecation alias:** 1 release? 2? Recommendation: 1 release (until we cut the next minor version), then delete.

---

## Dependencies

- **Blocks:** None
- **Depends on:** None (Spec Z is the foundation; runs first or in parallel)
- **Supersedes JIRA:** None directly

---

## Doc Delta

- No doc updates needed for Z1, Z2, Z4, Z5, Z6
- Z3: minor mention in `docs/TDD.md` news ingestion section
