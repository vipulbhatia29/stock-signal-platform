## Project State (Session 98)

**Current phase:** Pipeline Architecture Overhaul (KAN-419 epic refined this session)
**Resume point:** Execute Batch Z (quick wins) + Batch A (foundation) in parallel — both are independent and unblock everything else
**Branch:** `develop` — Session 98 was specs/plans/reviews/JIRA only, no code changes

### Session 98 Summary — Pipeline Architecture Overhaul

Comprehensive deep audit found multiple critical gaps in the backend pipeline:

**Stub tasks closed without code (KAN-395 was the canary):**
- `compute_convergence_snapshot_task` at `backend/tasks/convergence.py:143-153` — returns `{"computed": 0}`. `signal_convergence_daily` table is empty in prod. Convergence history chart, divergence hit rate, sector convergence panel all dead.
- `run_backtest_task` at `backend/tasks/forecasting.py:225-238` — returns fake success. `backtest_runs` empty. Drift detection's calibrated threshold uses fallback because `backtest_mapes` dict is empty.
- `calibrate_seasonality_task` at `backend/tasks/forecasting.py:241-253` — same pattern.

**Prophet sentiment regressor half-broken:**
- Training side correctly adds `add_regressor("stock_sentiment")` etc.
- Predict side fills future DataFrame with `0.0` for ALL dates including historical → systematic bias documented in code as "KNOWN LIMITATION"
- Fix in Spec B3: make `predict_forecast` async, fetch real historical sentiment for past dates, use 7-day trailing mean for forecast dates

**Entry point inconsistency:**
- Watchlist add returns 404 if stock not in DB (no auto-ingest)
- Portfolio transaction creates Stock row only (no price fetch, no forecast dispatch)
- Chat `analyze_stock` computes signals inline but never persists them
- Only `POST /stocks/{ticker}/ingest` calls the canonical `ingest_ticker` pipeline
- News ingest hard-codes `LIMIT 50` with no ordering — most tickers never get news

**Observability gaps:**
- `LangfuseService` only wired to agent path; sentiment scorer + Prophet training have ~100 LLM calls/day untraced
- `ObservabilityCollector` only used by agent paths
- Only 3 of 12+ Celery tasks use `PipelineRunner` (price_refresh, forecast_refresh, model_retrain_all)
- No per-ticker ingestion health view for admin

### Deliverables

**8 specs + 8 plans + 4 review docs = ~15,429 lines of design content**

| Spec | Plan | KAN ticket | Title |
|---|---|---|---|
| A | A | KAN-421 | Ingestion Foundation (state table, SLAs, PipelineRunner contract, task_tracer) |
| B | B | KAN-422 | Pipeline Completeness (convergence, backtest, Prophet sentiment fix, news concurrency) |
| C | C | KAN-423 | Entry Point Unification (watchlist, portfolio, chat, stale, bulk CSV) |
| D | D | KAN-420 | Admin + Observability (universal PipelineRunner, per-task trigger, ingestion health, Langfuse spans) |
| E | E | KAN-424 | Forecast Quality & Scale (cap raise, weekly retrain, intraday fast/slow) |
| F | F | KAN-425 | DQ + Retention + Rate Limiting (DQ scanner, token bucket, retention, TimescaleDB compression) |
| G | G | KAN-426 | Frontend Polish (ingest progress, polling, stale badges, TickerSearch) |
| Z | Z | KAN-427 | Quick Wins (registry typo, news LIMIT 50, task rename, cache invalidation, WelcomeBanner) |

**Files:**
- Specs: `docs/superpowers/specs/2026-04-06-pipeline-overhaul-spec-{A..G,Z}-*.md`
- Plans: `docs/superpowers/plans/2026-04-06-pipeline-overhaul-plan-{A..G,Z}-*.md`
- Reviews: `docs/superpowers/plans/2026-04-06-pipeline-overhaul-review-{staff-engineer,test-engineer,efgz,resolutions}.md`

### Review Findings

3 expert reviews (Staff Engineer + Test Engineer + EFGZ combined) found ~80 findings:
- **28 CRITICAL** (cross-spec drift, broken tests, security holes, schema mismatches)
- ~42 HIGH
- ~34 MEDIUM
- ~19 LOW

**All 28 CRITICALs were applied inline to specs/plans before JIRA registration.** Resolution log: `docs/superpowers/plans/2026-04-06-pipeline-overhaul-review-resolutions.md`.

Notable cross-cutting fixes:
- `task_tracer` location locked to `backend/services/observability/task_tracer.py` (was 3 different paths)
- `mark_stage_updated(ticker, stage)` signature locked (no `db` argument; opens own session)
- `Stage` Literal extended with `"recommendation"`
- `tracked_task(pipeline_name, *, trigger="scheduled")` signature locked
- Prophet test rewritten as deterministic synthetic-correlation test (was no-op mock)
- All DB-hitting tests in plans moved from `tests/unit/` to `tests/api/`
- `LangfuseService` real method names used (`create_trace`, `create_span` — NOT `start_span`)
- Spec E `Semaphore(10)` → `Semaphore(5)` (DB pool is 5+10=15 effective, not 20)
- Spec F TimescaleDB downgrade now decompresses chunks before clearing flag
- Spec G frontend tests use Jest not Vitest
- Spec C adds Redis SETNX `ingest:in_flight:{ticker}` dedup for parallel users
- Migration revision IDs use hash format (matches `b2351fa2d293_024_*.py` convention)

### Superseded JIRA tickets (7)

| Ticket | Folded into | Why |
|---|---|---|
| KAN-395 | KAN-422 (Spec B1) | Was wrongly closed; convergence task is still a stub |
| KAN-405 | KAN-422 (Spec B4) | Sentiment concurrent batch dispatch — exact match |
| KAN-398 | KAN-422 + KAN-426 | AccuracyBadge needs backtest data which Spec B2 enables |
| KAN-406 | KAN-424 (Spec E3) | SPY 2y history misalignment touched by intraday refresh |
| KAN-212 | KAN-423 (Spec C3) | Tool orchestration tests covered by `analyze_stock` test additions |
| KAN-213 | KAN-419 epic | Testcontainer-based integration tests = the overhaul test strategy |
| KAN-214 | KAN-419 epic | Error path + edge case tests covered across all 8 plans |
| KAN-162 | KAN-420 (Spec D5) — partial | Langfuse spans for non-agent paths |

All 7 commented in JIRA with link to the new ticket.

### Migration sequence
Current head `b2351fa2d293` → 025 `ticker_ingestion_state` (Spec A) → 026 `dq_check_history` (Spec F) → 027 `timescale_compression` (Spec F)

### Execution Order (isolation batches)

```
Batch Z (KAN-427) ─────────┐ Independent — anytime
Batch A (KAN-421) ─────────┤ Foundation — anytime
                            │
Batch A → Batch B (KAN-422) ┤ B uses A's primitives
Batch A → Batch D (KAN-420) ┤ D uses A's primitives
Batch B → Batch C (KAN-423) ┤ C uses B's extended ingest_ticker
Batch A + F → Batch E ──────┤ E uses F3 yfinance rate limiter
Batch C → Batch G (KAN-426) ┘ G uses C's API contract
```

### Key Facts (carry forward)

- **Alembic head:** `b2351fa2d293` (migration 024)
- **Tests:** 1907 backend unit + 13 moved to tests/api/ (security_headers + api_snapshots) + 38 API + 48 E2E
- **Coverage:** ~69% (floor 60%)
- **Pyright errors:** 170 (down from 200 after Session 98 PR #203)
- **Recent merged PRs (Session 97-98):** #198-204
- **Internal tools:** 25 + 4 MCP adapters
- **Docker:** Postgres 5433, Redis 6380, Langfuse 3001+5434

### Critical Process Insights from this session

1. **JIRA auto-close on PR merge** can wrongly close tickets if the PR body mentions ticket keys. Use `feedback_jira_no_ticket_refs_in_docs_prs.md` rule.
2. **`continue-on-error: true` workflows** show as failed jobs in GitHub UI but do not block merges. The `ci-merge` workflow is advisory; only `ci-pr` is the gate.
3. **xdist + shared DB teardown** is a classic race. PR #202 fixed by removing the session DROP teardown; PR #204 added a guardrail preventing `client`/`authenticated_client` fixtures in `tests/unit/`.
4. **Stub tasks closed as Done** is a process failure pattern (KAN-395). Need stricter "Done = code merged + test passing + verified" rule.
5. **Cross-spec import drift** was the #1 source of CRITICAL review findings — 8 specs with overlapping primitives need a single canonical declaration.

### Open Bugs (post-Session 98)

None new. Existing:
- KAN-401, KAN-402 (news pipeline tz/varchar — hotfixed in Session 95, proper migrations pending. May get folded into KAN-425.)
- KAN-417 (CSRF) — part of KAN-408, still pending implementation

### Resume

Run `/execute-plan docs/superpowers/plans/2026-04-06-pipeline-overhaul-plan-Z-quick-wins.md` to start with the smallest batch. Or `/execute-plan docs/superpowers/plans/2026-04-06-pipeline-overhaul-plan-A-foundation.md` for the foundation batch. Both are independent.
