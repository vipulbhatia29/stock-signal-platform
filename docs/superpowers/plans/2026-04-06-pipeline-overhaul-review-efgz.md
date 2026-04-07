# Pipeline Overhaul — Combined Review: Specs E, F, G, Z

**Reviewer:** Staff Engineer + Test Engineer (combined pass)
**Date:** 2026-04-06
**Scope:** 4 specs + 4 plans (E forecast quality, F DQ/retention/rate-limit, G frontend polish, Z quick wins)
**Severity tags:** CRITICAL / HIGH / MEDIUM / LOW

---

## Cross-cutting findings (apply to all 4)

### CRITICAL — Migration revision-ID convention mismatch
The plans (esp. F) use friendly slugs like `025_ingestion_foundation`, `026_dq_check_history`, `027_timescale_compression` as both filenames AND `revision` / `down_revision` strings. **The actual repo convention is hash-based revision IDs** with the migration *number* embedded in the filename only:

- Current head per `b2351fa2d293_024_forecast_intelligence_tables.py`:
  - `revision: str = "b2351fa2d293"`
  - `down_revision: ... = "5c9a05c38ee1"`

If Spec A's plan creates a migration with `revision = "025_ingestion_foundation"`, Alembic will work, but it diverges from the established naming convention and will be jarring. More importantly, **Plan F hard-codes `down_revision = "025_ingestion_foundation"`** which only works if Spec A actually used that string. Both spec-A and the F plan must agree.

**Fix:** Either (a) standardise on hash-based IDs and refer to migrations by friendly name in comments only, or (b) explicitly note that Spec A introduces the slug-style convention and document that all subsequent migrations follow it. Currently the plans assume (b) without saying so.

### CRITICAL — Postgres connection-pool size mismatch (affects Spec E)
Spec E.3 claims:
> "Postgres connection pool max is 20 (configured in `database.py`)"
> "Each call needs 1 DB connection from `async_session_factory()`"
> "Going higher than 10 risks starving other tasks"

**Reality (`backend/config.py:76-77`):**
```
DB_POOL_SIZE: int = 5
DB_MAX_OVERFLOW: int = 10
```
Effective max ~15 connections, **not 20**. With `Semaphore(10)` + a webserver and Celery workers also drawing from the pool, this is likely to exhaust the pool under load. The fast path (`asyncio.gather` with sem=10) plus Phase 2 forecasting plus a request hitting `get_async_session` could push over the limit and trigger `TimeoutError: QueuePool limit ... overflow ... reached`.

**Fix options:**
1. Lower `INTRADAY_REFRESH_CONCURRENCY` default to **5** (keep `DB_POOL_SIZE=5`, leverage overflow), and document the math.
2. Bump `DB_POOL_SIZE` to 15 / `DB_MAX_OVERFLOW` to 25 in the same PR, document the new total in spec.
3. Require the spec to update the math sentences before merging.

This affects rollout safety; should not ship with the current claim.

---

## Spec E — Forecast Quality & Scale

### Architectural

- **CRITICAL — Pool math wrong** (see cross-cutting). Spec text says "max 20" but config is 5+10. The Open Question "semaphore=10 vs 20" is moot until pool is verified.
- **HIGH — Phase 1.5 placement makes nightly chain longer.** The slow path (`_refresh_all_slow_async`) runs sequentially over ~600 tickers. Even with the F3 yfinance limiter at 30 RPM that is ~20 minutes of pure rate-limited time, plus actual yfinance latency. The spec doesn't budget this against the existing nightly chain time. Add an estimate; consider parallelising slow path with a *separate* small semaphore (e.g. 3) so it isn't dominated by serial yfinance latency.
- **MEDIUM — Slow path mandatory in nightly chain coupling.** Spec puts slow path inside `nightly_pipeline_chain_task` Phase 1.5. If yfinance is down, the entire chain is slowed/delayed. Consider moving slow path to its own Celery beat entry (e.g. `slow-path-nightly` 22:30 ET, before Phase 2) so a yfinance outage doesn't stall forecasts/recs/alerts. Spec already lists this trade-off only in Open Question #2 — escalate to a design decision.
- **MEDIUM — `_attach_quantstats` call is invented in plan but not in spec.** Plan E Task 3 Step 2 references `_attach_quantstats(signal_result, full_df, spy_closes)` but spec body shows inline `# QuantStats inline (it's fast — already computed in memory) ...`. This helper does not exist today. Either add a step to extract it, or inline. Currently the plan won't compile as written.
- **MEDIUM — `mark_stage_updated` only called in fast path.** Plan adds it for `signals` in fast path, but slow path also updates fundamentals — and the plan does call `mark_stage_updated(ticker, "fundamentals", db)` there. Good. Verify that Spec A defines this exact stage name. The Spec G `STAGE_SLA_HOURS` dict uses keys `prices, signals, fundamentals, forecast, news, sentiment, convergence` — confirm Spec A's table columns line up with all 7.
- **LOW — `priority` parameter is added to `retrain_single_ticker_task` but the cap is on the *sweep loop*, not on the task.** The signature change is mostly cosmetic — a future engineer might assume `priority=False` means "respect cap" inside the task. Spec is actually correct (the cap lives in `_forecast_refresh_async`), but the docstring should make this explicit so callers aren't misled.

### Tests
- **HIGH — `test_intraday_refresh_completes_under_2min` is flaky on slow CI.** Spec test #13 acknowledges `@pytest.mark.slow` but the plan's test file (`test_market_data_fast_slow_split.py`) doesn't actually mark it. Add `@pytest.mark.slow` AND exclude from PR runs (`-m "not slow"` in CI config). Otherwise this gates PR merges on machine speed.
- **HIGH — `test_db_connection_pool_not_exhausted_during_intraday`** in spec but **missing from plan**. This is the test most directly tied to the CRITICAL pool finding above. Add it to Plan E Task 3.
- **MEDIUM — Plan Task 1 Step 1 test for `priority` is a placeholder (`pass`) with a comment.** Test #2 in spec (`test_retrain_single_ticker_task_priority_default_false`) inspects `__wrapped__.__signature__` — this attribute may not exist on Celery `@task` objects (Celery wraps differently than functools). Verify with a real REPL or use `inspect.signature(retrain_single_ticker_task.run)` instead.
- **MEDIUM — `test_biweekly_self_filter_removed`** does a source-level grep (`"isocalendar" not in source or "% 2" not in source`). The `or` is logically wrong — it passes whenever EITHER substring is missing, which is a tautology if the function never had both tokens. Use `and`: `assert "isocalendar" not in source and "% 2" not in source`.
- **LOW — Plan does not patch tests that previously asserted `_refresh_ticker_async`.** Plan Step 6 says "Fix any mock imports that now point at removed symbols". Better: enumerate them up-front via grep and list explicitly so the implementing agent knows the surface area.

### Plan completeness vs spec
- ✅ E1 cap raise + priority bypass — covered (Task 1).
- ✅ E2 weekly retrain — covered (Task 2).
- ✅ E3 fast/slow split + parallelisation + Phase 1.5 — covered (Task 3).
- ❌ Spec test #15 (`test_db_connection_pool_not_exhausted_during_intraday`) — **missing in plan**.
- ❌ Spec test #1 explicitly asserts `compute_quantstats_stock` not called — plan version asserts only `mock_yf.assert_not_called()`. Add explicit QS assertion since the spec promises QS-inline behaviour.
- ❌ `INTRADAY_REFRESH_CONCURRENCY` env var added to `config.py` (Plan Task 3 Step 5) but no test asserts the default value is 10 (mirroring `test_max_new_models_per_night_is_100`).

### Cross-spec dependency check
- ✅ Plan E header lists "Depends on: Spec A (`mark_stage_updated`), Spec F3 (yfinance rate limiter for slow path)".
- ⚠️ Plan E references `mark_stage_updated` from Spec A but doesn't import it — assumes Spec A already merged. Add a check step.

---

## Spec F — DQ, Retention, Rate Limiting

### Architectural

- **CRITICAL — TimescaleDB compression downgrade is not actually reversible.** Spec text says "Both fully reversible". Plan + spec both have downgrade:
  ```sql
  ALTER TABLE stock_prices SET (timescaledb.compress = false);
  ```
  This **only blocks new compression; it does not decompress already-compressed chunks**. Once 30 days pass and policy compresses chunks, downgrading fails (Timescale errors out: `cannot change ... while compression is enabled and chunks are compressed`). The proper downgrade must:
  1. `SELECT remove_compression_policy(...)` (already in plan) ✅
  2. `SELECT decompress_chunk(c) FROM show_chunks('stock_prices') c WHERE c IS compressed` — **missing**
  3. Then `SET (timescaledb.compress = false)`
  Document this asymmetry explicitly in spec ("downgrade is best-effort and only works before chunks are compressed; otherwise requires manual decompress"). Add an integration test covering downgrade after a chunk is forced-compressed.

- **HIGH — `news_articles` lacks `compress_segmentby`.** Plan migration only sets `compress_orderby = 'published_at DESC'`, no segmentby. With ~30K rows/year and queries usually filtered by ticker, this defeats the main benefit of TimescaleDB compression. Recommend `compress_segmentby = 'ticker'` (matching the other tables). Caveat: `news_articles.ticker` is nullable — check whether segmentby on a nullable column is allowed (it is, but null rows go in their own group).

- **HIGH — slowapi limiter is per-IP, not per-user.** Spec F4 says "20/hour per user prevents abuse". `backend/rate_limit.py` uses `key_func=get_remote_address` (IP-based). Behind a reverse proxy, multiple users on one corporate NAT share an IP and could all be blocked from the 21st request. Either:
  1. Update `key_func` to derive `current_user.id` (requires the limiter to access request state — slowapi supports `key_func=lambda r: r.state.user_id`).
  2. Document explicitly that the limit is per-IP (acceptable for early deployment).
  Either way, don't claim "per-user" in spec while wiring per-IP.

- **HIGH — Token bucket Lua script `EXPIRE` ttl can be misleading under bursty traffic.** `EXPIRE key, ceil(capacity / refill_rate) + 60`. For yfinance (cap=30, refill=0.5 → 60 + 60 = 120s) means after 2 minutes of inactivity the bucket resets to full. Acceptable, but document this behavior — a user testing in dev might hit "300 requests in a row" if they wait between batches.

- **HIGH — `time.time()` vs `time.monotonic()` mix.** `acquire()` uses `time.monotonic()` for the deadline loop (correct) but `time.time()` for the Redis script timestamp (correct for cross-process clock). However, NTP skew between worker hosts could give negative `elapsed` in Lua. Lua already guards: `local elapsed = math.max(0, now - last)`. Good. Note in docstring.

- **HIGH — `_check_orphan_positions` SQL uses `position` (singular) table name.** Verify this matches the model's `__tablename__`. Most projects use `positions`. Wrong name will silently 0-find. Same for `composite_score` — verify column exists in `signal_snapshots` (the codebase notes mention this is on a 0-10 scale; column may be `composite_score` or similar).

- **MEDIUM — Single-node Redis assumed for Lua atomicity.** Spec correctly uses Redis Lua for atomic CAS, but in cluster mode `EVALSHA` requires all keys to map to the same hash slot. Currently single-node so OK; document the constraint.

- **MEDIUM — `news_articles.published_at` is naive (no `timezone=True`).** Plan retention task correctly converts cutoff to naive — good. But the DQ scanner queries `now() - interval '48 hours'` against `signals_updated_at` which (per Spec A) should be tz-aware. Confirm consistency, otherwise checks may silently mis-classify.

- **MEDIUM — `dq_scan_task` uses `tracked_task(name="dq_scan", scope="global", tracer="none")` but Spec A's signature is unspecified to this review.** Plan's invocation may not match. Verify after Spec A merges; add an integration smoke test that imports + calls `dq_scan_task.run()` with a fully empty DB.

- **MEDIUM — `_check_forecast_extreme_ratios` SQL JOIN does a per-ticker latest-close subquery on every run.** Will scale linearly with ticker count and price-row count. With Spec F6 compression on stock_prices, this query may decompress chunks. Recommend using a materialised CTE or limiting to forecasts created in last 24h.

- **MEDIUM — Plan F's "dedup_key" assumption.** `_create_alert(..., dedup_key=...)` is referenced from `backend.tasks.alerts`. Verify that helper exists and accepts `dedup_key`.

- **LOW — Bulk endpoint rate limit `3/hour` is wrong tool placement.** `POST /portfolio/transactions/bulk` is in Spec C5. F lists it but plan doesn't actually modify portfolio router. If C5 doesn't ship first, F's mention is dead text. Move the bulk-rate-limit step to Plan C5 instead, or add it explicitly to Plan F.

### Tests

- **HIGH — DQ scanner SQL queries are unit-tested with mocked `db.execute` only.** This hides actual SQL bugs (wrong column name, wrong table name). Spec lists `tests/api/test_dq_scan_integration.py` but plan Task 6 only creates `tests/unit/tasks/test_dq_scan.py` with mocks. **Plan is missing the API/integration test file.** Add it; run all 10 checks against a real testcontainer DB with seeded fixtures.

- **HIGH — Test placement guardrail violation risk.** `tests/api/test_ingest_rate_limit.py` (Task 4) lives correctly under `tests/api/`. ✅ `tests/api/test_dq_scan_integration.py` is enumerated in spec but **NOT in plan** — add it. ✅ `tests/integration/test_compression_migration.py` — note that the repo standard is `tests/api/` for DB-hitting tests; `tests/integration/` may not have the right fixtures. Verify whether `tests/integration/` is an accepted tier or whether it should be `tests/api/`.

- **HIGH — `test_token_bucket_lua_atomicity`** is enumerated in spec (case #5) but not present in plan tests. Without a real Redis (fakeredis or testcontainer), atomicity claims are unverified.

- **MEDIUM — `test_ingest_endpoint_429_after_20_per_hour`** uses an `authenticated_client` fixture in `tests/api/`. ✅ But the test pattern hits real backend logic; `slowapi` storage is Redis. In CI, ensure Redis is available or the limiter falls back. Otherwise the test will hit a different path than production.

- **MEDIUM — `test_purge_old_news_articles_uses_naive_datetime` mocks the session entirely.** It only verifies `deleted == 3` from a mocked rowcount. Doesn't actually verify the cutoff datetime is naive vs aware. Add an assertion on the actual `delete()` call's WHERE clause datetime kind, or add an integration test.

- **LOW — Lua script is loaded once per limiter instance via `script_load`.** Test should cover Redis flushing scripts (NOSCRIPT error → reload). Spec doesn't enumerate this case.

### Plan completeness vs spec

- ✅ F1 DQ scanner — covered (Tasks 5, 6).
- ✅ F2 News provider rate limiter — covered (Tasks 1, 3).
- ✅ F3 yfinance limiter — covered (Task 2).
- ✅ F4 ingest endpoint rate limit — covered (Task 4).
- ✅ F5 retention tasks — covered (Task 7).
- ✅ F6 compression migration — covered (Task 8).
- ❌ `tests/api/test_dq_scan_integration.py` is in spec's "Files Created" but **missing from plan**.
- ❌ Spec mentions `backend/services/pipeline_registry_config.py` register dq_scan_task in "data_quality" group + retention in "maintenance" group; plan mentions these in step text but doesn't add a unit test asserting the registry contains the new groups.
- ❌ Frontend 429 toast handling is in spec ("Frontend Impact") but **plan F has no frontend tasks**. Either move to Plan G or add explicit Plan F frontend task.
- ❌ Spec lists bulk endpoint rate limit `3/hour` as part of F4 but plan does not modify `backend/routers/portfolio.py`.

### Cross-spec dependency check
- ✅ Plan F header: "Depends on: Spec A (`tracked_task`...)". ✅
- ⚠️ Migration sequence text: `b2351fa2d293 → 025_ingestion_foundation → 026_dq_check_history → 027_timescale_compression`. This presumes Spec A's revision string is exactly `025_ingestion_foundation`. See CRITICAL above.
- ✅ Plan F does not depend on Spec G/Spec C.

### Migration ordering
- 026 down_revision = `"025_ingestion_foundation"` → depends on Spec A using that exact revision string. **Verify.**
- 027 down_revision = `"026_dq_check_history"` → consistent with Plan F naming.

---

## Spec G — Frontend Polish

### Architectural

- **HIGH — `GET /stocks/{ticker}/ingest-state` access control.** Plan correctly requires `current_user` (not admin). ✅ But the endpoint exposes per-ticker stage timestamps including `fundamentals_updated_at` etc. — these are not PII and are not user-scoped data, so no leak. Recommend caching headers (`Cache-Control: no-store, max-age=0`) since clients poll every 2s and we don't want intermediate caches absorbing requests.
- **HIGH — `_classify_stage` thresholds are duplicated.** Plan G defines `STAGE_SLA_HOURS` inside `backend/routers/stocks/data.py`. Spec A2 ("staleness SLAs") is supposed to own these constants. Move to a shared `backend/services/staleness.py` (plan G even mentions this in Task 3 Step 1). The router copy will drift. Pull constants from Spec A.
- **HIGH — `IngestProgressToast` polls every 2s indefinitely if backend never reaches "ready".** No max-attempt cap. A stuck/missing ticker → infinite polling. Add a hard timeout (e.g. stop after 10 min) or backoff after N attempts.
- **HIGH — `usePositions` `refetchInterval` change breaks SSE-style polling expectations.** Polling every 5s while ANY position is ingesting will refetch the *full* positions list — for users with 100+ positions this is heavy. Recommend either (a) only polling the ingest-state endpoint for the specific ingesting ticker(s), or (b) a maximum poll duration (e.g. 5 minutes) before falling back.
- **MEDIUM — `overall_status` derivation logic is fragile.** Plan classifier:
  ```python
  if fresh_count == 7: "ready"
  elif any pending/missing: "ingesting"
  else: "stale"
  ```
  But `_classify_stage` returns `STALE` between SLA and 2x SLA, then `PENDING` after 2x SLA. **A 96h-old `prices` (sla=24) gets classified `pending`, which is misleading semantically** — the stage is *late*, not *in-progress*. Reorder: sla<age<2*sla → STALE; age>2*sla → STALE (more severe), and reserve PENDING/MISSING for null. Otherwise the toast will say "ingesting" forever for a degraded ticker.
- **MEDIUM — Backend `IngestStateResponse` uses both `Literal[...]` AND `StageStatus(str, Enum)` — pick one.** Mixing leads to FastAPI generating two OpenAPI schemas. Prefer the enum.
- **MEDIUM — `seed_ticker_state` fixture is referenced in test but not defined anywhere in plan.** Add fixture creation step.
- **LOW — `Position` ingestion_status added via JOIN in `get_positions_with_pnl`** — adds a query on every position fetch. With Spec A's `ticker_ingestion_state` having one row per ticker, the JOIN is cheap, but ensure it's a LEFT JOIN (some positions may pre-date the table). Plan says LEFT JOIN ✅.
- **LOW — `score-bar.tsx` opacity change** is described as `<div className={cn(isStale && "opacity-60")}>` — `isStale` source isn't defined. Add the prop wiring step.

### Tests

- **HIGH — Polling tests with `vi.useFakeTimers()` + TanStack Query are notoriously flaky.** TanStack Query v5 schedules refetches via `setTimeout`, but the internal QueryObserver also uses microtasks. Test #2 (`onComplete after 5s`) does `await vi.advanceTimersByTimeAsync(6000)` which can race. **Recommendation:** use `@testing-library/react` `waitFor` with real timers and a short polling interval injected via prop or query option override. Avoid fake timers for refetchInterval tests.
- **HIGH — Tests for `useSignals` polling on `is_refreshing` rely on Spec C4** which adds the field. Plan G assumes the field exists; if Plan C4 hasn't merged, frontend tests fail with type errors. Add a precondition check / depends-on assertion.
- **MEDIUM — `test_ingest_state_overall_ingesting_when_missing_stages`** test fixture passes `stages={"prices": "fresh", "signals": None}` — this maps to fixture-implementation details that aren't defined. Define `seed_ticker_state` first.
- **MEDIUM — Visual regression cases listed in spec (3 cases)** but plan has no Playwright/snapshot setup steps. Either drop them from spec or add a Plan G Task for visual tests.
- **MEDIUM — Frontend tests use `vitest` but the rest of the repo uses Jest** (per memory: "Jest: testEnvironment: jsdom, tests at frontend/src/__tests__/"). Plan G test code imports from `vitest` — **wrong test runner**. Should be `@jest/globals` or just bare describe/it/expect from Jest. This will not compile.

### Plan completeness vs spec

- ✅ G1 ingest progress (backend endpoint + frontend toast + hook) — covered (Tasks 1, 2, 6).
- ✅ G2 polling — covered (Task 3).
- ✅ G3 TickerSearch in dialog — covered (Task 4).
- ✅ G4 stale badges — covered (Task 5).
- ✅ G5 + G6 — restated as Plan Z items, plan has verification step (Task 7) ✅.
- ❌ Spec test "shows red for failed stages" (#7) — plan toast renders only `fresh / pending / missing → spinner / yellow alert`. No red/failed state. Either remove from spec or add a stage failure status.
- ❌ Spec test #4 `test_auto_dismisses_5_seconds_after_ready` — plan implements this via `useEffect` with `setTimeout(5000)` but also calls `onComplete?.()` (which is the dismiss path). Plan test (`calls onComplete 5s after reaching ready state`) has fake-timer flakiness risk above.
- ❌ Spec lists `tests/api/test_portfolio.py` update for `ingestion_status` field — plan only references it in Task 8 sweep, no explicit test case added.

### Cross-spec dependency check
- ✅ Header: "Depends on: Spec A, Spec C2/C4, Spec D3". ✅
- ⚠️ Plan G also depends on **Spec Z** for G5/G6 — listed but only in body. Make explicit at top.

### Test placement
- ✅ `tests/api/test_stock_ingest_state.py` lives in `tests/api/` (correct for DB-hitting test).
- ⚠️ Frontend tests use `vitest` syntax but project uses Jest — **broken**.

---

## Spec Z — Quick Wins

### Architectural

- **HIGH — Z3 LIMIT 50 → 200 cap before Spec F2 lands risks Finnhub rate limit.** Spec F2 (rate limiter) is the safety net. If Spec Z lands before Spec F2:
  - Finnhub free tier = 60 RPM. Z3 will iterate 200 tickers and fire ~1 call/ticker → bursts of 200 calls within seconds → rate-limit ban.
  - **Sequencing rule:** Z3 must NOT merge before F2/F3 (rate limiters) OR temporarily ship Z3 with cap=50 (no functional change), then bump to 200 in the same PR as F2.
  - Spec acknowledges this in "Risk" section but the plan doesn't enforce ordering. Add a check step + JIRA blocker link from Z3 → F2.
- **MEDIUM — Z4 deprecation alias names a new Celery task with the same body via delegation.** When the alias is called via Celery beat, it creates a *second* task entry in the registry with a different name. Both will appear in `celery_app.tasks`. Confirm this isn't an issue for Z1's enforcement test (it iterates registry → asserts in `celery_app.tasks`, so duplicate entries are fine — both register, both are real).
- **MEDIUM — Z2 deletion includes a future-proofing test** but doesn't migrate any callers. Confirm there are no live references to `calibrate_seasonality_task` outside the registry. Run `grep -rn calibrate_seasonality backend/ tests/` before deletion.
- **LOW — Z1 enforcement test catches more than the typo.** It will fail for any future spec that lands a registry entry before merging the task module — including Spec Z4's own alias if order is wrong. Document run order in plan: Z1 must be first task; Z4 alias must be added before tests run.
- **LOW — Z5 invalidation is broad.** Adds `["positions"]` to invalidation. After every ingest the entire portfolio refetches. Acceptable but worth noting in PR description.

### Tests

- **HIGH — Z1 `test_every_registered_task_resolves_to_real_celery_task` import-order risk.** Test imports `build_registry()` first, then `celery_app`. If `build_registry()` triggers a side-effect that loads Celery tasks, OK. If not, the registry may reference a task that hasn't been imported yet. **Mitigation:** ensure `from backend.tasks import celery_app` is also imported at module top of the test, BEFORE `build_registry()` is called. Better: explicitly call `celery_app.loader.import_default_modules()` before the assertion. Otherwise test may produce false negatives.
- **MEDIUM — Z3 `test_news_ingest_uses_canonical_universe`** patches `mod.get_all_referenced_tickers` but plan also says "Move the import to the top of the module if not already imported". The patch target must match the *binding inside `backend.tasks.news_sentiment`*. If the import is `from backend.services.ticker_universe import get_all_referenced_tickers`, then patching `mod.get_all_referenced_tickers` is correct. If it stays inside the function, patch the original location. Plan's instruction is correct but worth a callout.
- **MEDIUM — Z4 `test_legacy_refresh_all_watchlist_tickers_task_warns_and_delegates`** patches `market_data.intraday_refresh_all_task` with `autospec=True`, then calls `market_data.refresh_all_watchlist_tickers_task.run()`. The Celery `.run()` invokes the underlying function which calls `intraday_refresh_all_task()` (not `intraday_refresh_all_task.run()`). With autospec patching the Celery task object, the call inside the alias will hit the patched object's `__call__` — verify that Celery tasks are callable as functions in the test environment. Otherwise test will fail.
- **LOW — Z6 dashboard test mocks `useWatchlist`/`usePositions` from `@/hooks/use-stocks` but plan code at Step 2 also imports `useAddToWatchlist` — mock must include it. Plan has it (`useAddToWatchlist: vi.fn(...)`) ✅. But again, **vitest vs jest mismatch** — same issue as Plan G.

### Plan completeness vs spec
- ✅ Z1-Z6 all covered (Tasks 1-6).
- ✅ All 12 spec test cases enumerated in plan.
- ⚠️ Spec mentions Z3 risk + Spec F2 sequencing but plan does not include a "sequencing check" or JIRA blocker.
- ⚠️ Plan does not include the `tests/unit/tasks/test_forecasting_calibration_deletion.py` file enumerated in spec; instead appends to `tests/unit/tasks/test_forecasting.py`. Reconcile spec ↔ plan filenames.

### Cross-spec dependency check
- ✅ Plan Z header: no dependencies. ✅ Independent.
- ⚠️ Z3 has soft sequencing dependency on F2 (see HIGH above).

### Test placement
- ✅ All Z tests live in `tests/unit/...` and don't use DB-hitting fixtures. Guardrail-compliant.
- ⚠️ Frontend tests use `vitest` syntax — same Jest mismatch as Plan G.

---

## Cross-spec sequencing summary

Recommended merge order to avoid the rough edges above:

1. **Spec A** (foundation: `mark_stage_updated`, `tracked_task`, `ticker_ingestion_state`, migration 025) — must land first.
2. **Z1, Z2, Z4, Z5, Z6** — independent quick wins (frontend + non-Z3 backend).
3. **Spec F (F2 + F3 first)** — rate limiter must precede Z3 expansion.
4. **Z3** — bump news cap once rate limiter is in place.
5. **Spec F (F1, F4, F5, F6)** — DQ + retention + compression.
6. **Spec E** — fast/slow split. Requires Spec A. Verify pool config first.
7. **Spec G** — frontend polish. Requires Spec A + Spec C2/C4 + Spec D3.

---

## Top action items (must-fix before merging plans)

| # | Severity | Spec | Action |
|---|---|---|---|
| 1 | CRITICAL | Cross | Reconcile migration revision-ID convention; document Spec A's choice and update all `down_revision` strings. |
| 2 | CRITICAL | E | Fix pool-size math in spec (5+10, not 20) and lower default `INTRADAY_REFRESH_CONCURRENCY` to 5 OR raise pool. |
| 3 | CRITICAL | F | TimescaleDB compression downgrade is not actually reversible — add `decompress_chunk` step or document as one-way. |
| 4 | HIGH | F | News articles compression needs `compress_segmentby='ticker'`. |
| 5 | HIGH | F | slowapi limiter is per-IP not per-user — fix `key_func` or correct spec language. |
| 6 | HIGH | F | DQ scanner integration test (`tests/api/test_dq_scan_integration.py`) is in spec but missing from plan — add it. |
| 7 | HIGH | G | Frontend tests use `vitest` syntax but project uses Jest — rewrite for Jest. (Same fix needed in Plan Z Task 5/6.) |
| 8 | HIGH | G | `IngestProgressToast` polls forever if backend never reaches ready — add max-duration cap. |
| 9 | HIGH | Z | Z3 must merge after F2/F3 OR ship with cap=50 first — add sequencing gate. |
| 10 | MEDIUM | E | `test_biweekly_self_filter_removed` boolean logic bug (`or` → `and`). |
| 11 | MEDIUM | E | Plan references `_attach_quantstats` helper that doesn't exist — extract or inline. |
| 12 | MEDIUM | F | DQ scanner SQL: verify table name `position` vs `positions` and column names against real schema. |
| 13 | MEDIUM | G | `overall_status` classifier conflates "stale" and "pending" — reorder logic. |
| 14 | MEDIUM | G | Move `STAGE_SLA_HOURS` to shared `backend/services/staleness.py` (Spec A territory). |
| 15 | LOW | F | Plan F includes bulk-endpoint rate limit text but no edit — move to Plan C5 or add explicit step. |

---

## Sign-off

The plans are well-structured and the test coverage is comprehensive in count, but several integration points need fixes before any of these can be safely run by an implementation agent:

- Spec E will fail in production (or under load testing) until the pool-size math is corrected.
- Spec F's compression downgrade will become irreversible the moment the first 30-day chunk is compressed; this is a one-way door we should know about.
- Plan G's frontend tests won't even run as written (vitest vs Jest).
- Spec Z3 timing relative to Spec F2 is unenforced and will trip a Finnhub ban if merged out of order.

After fixing the items in the table above, these plans are ready to hand to subagent implementation runs (sonnet, per Hard Rule #11).
