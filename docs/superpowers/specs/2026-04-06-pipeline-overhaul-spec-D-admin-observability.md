# Spec D: Admin + Observability

## Status, Date, Authors

- **Status:** Draft — pending review
- **Date:** 2026-04-06
- **Authors:** Platform team (Claude Opus 4.6 + PM)
- **Depends on:** Spec A (Ingestion Foundation — provides `@tracked_task`, `task_tracer`, `ticker_ingestion_state` table)
- **Supersedes (partial):** KAN-162 (Langfuse self-hosted integration)
- **Related:** Spec B (Pipeline Completeness), Spec C (Entry Point Unification)

---

## Problem Statement

Observability on the stock signal platform is fragmented. The `LangfuseService` and
`ObservabilityCollector` classes both exist and are exercised by the agent hot path,
but the 12+ Celery tasks that actually generate 99% of the data in the system are
effectively invisible. Admins can trigger full pipeline *groups* from the UI but
cannot re-run a single task for a single ticker; there is no per-ticker ingestion
health view; and there is no guarantee that every cache layer is evicted after a
write. This spec closes the observability gap uniformly across the Celery + FastAPI
worker fleet.

### Evidence of fragmentation

- **Langfuse only wired to the agent LLM client**
  `backend/observability/langfuse.py` defines a complete `LangfuseService`, but the
  only consumer is `backend/agents/llm_client.py:199` (`self._langfuse = langfuse_service`).
  No Celery task — forecasting, sentiment scorer, news ingest, convergence,
  recommendations — creates a trace, span, or generation record.
- **`ObservabilityCollector` only used by agent paths**
  `backend/observability/collector.py` is constructed at application start-up and
  wired into `agents/llm_client.py`, `agents/react_loop.py`, and `agents/executor.py`.
  Grep finds zero imports from `backend/tasks/**`.
- **`PipelineRunner` adoption is 3-of-20+**
  `backend/tasks/pipeline.py:24` provides `start_run`/`record_ticker_success`/
  `record_ticker_failure`/`complete_run`. Only three tasks call into it:
  - `backend/tasks/market_data.py::_nightly_price_refresh_async`
  - `backend/tasks/forecasting.py::_model_retrain_all_async`
  - `backend/tasks/forecasting.py::_forecast_refresh_async`

  The remaining tasks (`news_ingest_task`, `news_sentiment_scoring_task`,
  `generate_alerts_task`, `generate_recommendations_task`, `evaluate_forecasts_task`,
  `check_drift_task`, `evaluate_recommendations_task`, `snapshot_all_portfolios_task`,
  `snapshot_health_task`, `materialize_rebalancing_task`,
  `sync_analyst_consensus_task`, `sync_fred_indicators_task`,
  `sync_institutional_holders_task`, `compute_convergence_snapshot_task`,
  `run_backtest_task`, `calibrate_seasonality_task`, `dq_scan_task`, the audit
  purges, all 11 seed tasks) produce no `PipelineRun` row. When they fail at night,
  the admin UI shows nothing.
- **Admin pipelines page only triggers full groups**
  `backend/routers/admin_pipelines.py:237-307` exposes
  `POST /api/v1/admin/pipelines/groups/{group}/run`. There is no per-task endpoint,
  so an admin debugging a single ticker's missing forecast has to re-run the
  entire `nightly` group (~30 minutes) instead of
  `refresh_ticker_task(ticker="AAPL")`.
- **No per-ticker ingestion health dashboard**
  `frontend/src/components/admin/` has command-center panels for system / API / LLM
  / pipeline totals, but no "show me every ticker where sentiment hasn't refreshed
  in 48h" view. Operators cannot answer "is AAPL healthy across all ingestion stages?"
  without running ad hoc SQL.
- **Cache invalidator coverage is unverified**
  `backend/services/cache_invalidator.py` exposes `on_signals_updated`,
  `on_sentiment_scored`, `on_forecast_updated`, `on_prices_updated`,
  `on_backtest_completed`, etc. Nobody has audited every table write site to
  confirm the matching event fires after `db.commit()`. Bugs here cause the UI to
  show stale data *even after* a successful nightly run.
- **Nightly chain has no parent trace in Langfuse**
  `nightly_pipeline_chain_task` in `backend/tasks/market_data.py` is the single
  most important task on the platform. It has no Langfuse root trace, so phases
  cannot be compared across runs for latency regressions.

### Impact

- **Debugging time** — operators reach for psql + Redis instead of Langfuse + the
  admin dashboard.
- **Silent failures** — tasks that fail outside the 3 tracked tasks only surface
  via Celery logs, not the admin UI.
- **Data-freshness bugs** — cache invalidator gaps mean users see stale sentiment
  and forecasts for hours after a successful run.
- **No cost visibility** — sentiment scorer LLM calls are untracked; Langfuse has
  no record of spend.

---

## Goals

1. **G1** — Every Celery task wraps its body in `@tracked_task` (Spec A) so that
   every run creates a `PipelineRun` row with start/complete timestamps, ticker
   counts, duration, and error summary.
2. **G2** — Admins can trigger an individual task (optionally scoped to one
   ticker) from the pipelines page via a whitelisted endpoint.
3. **G3** — Admins can see a per-ticker ingestion health table with stage-level
   freshness and a one-click re-ingest button.
4. **G4** — Every write to `signal_snapshots`, `forecast_results`,
   `news_sentiment_daily`, `signal_convergence_daily`, `recommendation_snapshots`,
   and `in_app_alert` fires the matching cache invalidator event after commit.
   Coverage is enforced by a unit test.
5. **G5** — Non-agent paths create Langfuse traces and spans: nightly chain root
   trace with per-phase spans, Prophet training spans, sentiment scorer generation
   spans (with prompt/response sampled at 25%), news-provider fetch spans.
6. **G6** — Admins can view the last 50 audit log entries (group triggers, task
   triggers, cache clears) on the pipelines page.
7. **G7** — Task duration metrics are queryable. (MVP: push to Langfuse only;
   DB-backed `task_metric_history` deferred to follow-up.)

---

## Non-Goals

- **Not a Prometheus/Grafana rollout.** We continue to use Langfuse + the internal
  observability DB tables; no new metrics backend is introduced.
- **Not a full tracing SDK migration.** OpenTelemetry is explicitly deferred —
  Langfuse's Python SDK is sufficient for the cost/benefit trade-off at current scale.
- **Not per-user observability.** Everything here is admin-only; end-user analytics
  live in `backend/observability/routers/user_observability.py` and are out of scope.
- **Not a redesign of the existing command-center panels.** Ingestion health is
  added as a new sibling route, not a replacement.
- **Not a ticker ingestion state migration plan.** Spec A defines the table and the
  `@tracked_task` contract; Spec D is the consumer.

---

## Design

### D1. Universal `PipelineRunner` adoption

Every Celery task in `backend/tasks/**` gets wrapped in the `@tracked_task`
decorator introduced by Spec A. The decorator's responsibilities are defined by
Spec A; Spec D only specifies adoption strategy.

**`@tracked_task` contract (recap from Spec A — authoritative signature):**

```python
@tracked_task("nightly_price_refresh", trigger="scheduled")  # positional pipeline_name, optional trigger
@celery_app.task(name="backend.tasks.market_data.nightly_price_refresh_task")
def nightly_price_refresh_task():
    ...
```

Signature: `tracked_task(pipeline_name: str, *, trigger: str = "scheduled")`.
Spec D does NOT pass `scope=` or `tracer=` kwargs — those were earlier drafts.
Langfuse root tracing and per-ticker vs global semantics are handled inside
the decorator based on task return shape (dict with `ticker_successes` /
`ticker_failures` → per-ticker; anything else → global).

Behaviour:

- If the task returns a dict containing `ticker_successes` / `ticker_failures`,
  the decorator records each into the `PipelineRun` row via
  `record_ticker_success` / `record_ticker_failure` (per-ticker mode).
- Otherwise the decorator records a single success/failure row and uses the
  duration as the run total (global mode).
- On unhandled exception, the decorator calls `complete_run` with status
  `"failed"` and sets `error_summary["_unhandled"]` (redacted — see Spec A
  Hard Rule #10) before re-raising.
- The decorator creates a root Langfuse trace named `task.{pipeline_name}` with
  metadata `{celery_task_id, pipeline_name, trigger}` whenever Langfuse is
  enabled. There is no `tracer=` knob.

**Per-task adoption table**

| Celery task | File | Scope | Tracer | Notes |
|---|---|---|---|---|
| `nightly_price_refresh_task` | `tasks/market_data.py` | per_ticker | langfuse | Already manual — migrate to decorator |
| `refresh_ticker_task` | `tasks/market_data.py` | per_ticker | langfuse | Single-ticker convenience task |
| `refresh_all_watchlist_tickers_task` | `tasks/market_data.py` | per_ticker | langfuse | Intraday refresh |
| `nightly_pipeline_chain_task` | `tasks/market_data.py` | global | langfuse | Root trace wraps entire chain |
| `forecast_refresh_task` | `tasks/forecasting.py` | per_ticker | langfuse | Already manual — migrate |
| `model_retrain_all_task` | `tasks/forecasting.py` | per_ticker | langfuse | Already manual — migrate |
| `run_backtest_task` | `tasks/forecasting.py` | per_ticker | langfuse | New tracking |
| `calibrate_seasonality_task` | `tasks/forecasting.py` | per_ticker | langfuse | New tracking |
| `news_ingest_task` | `tasks/news_sentiment.py` | per_ticker | langfuse | Per-provider spans (D5) |
| `news_sentiment_scoring_task` | `tasks/news_sentiment.py` | per_ticker | langfuse | Sampled prompt/response |
| `compute_convergence_snapshot_task` | `tasks/convergence.py` | per_ticker | langfuse | |
| `generate_recommendations_task` | `tasks/recommendations.py` | per_ticker | langfuse | |
| `generate_alerts_task` | `tasks/alerts.py` | per_ticker | langfuse | |
| `evaluate_forecasts_task` | `tasks/evaluation.py` | per_ticker | langfuse | |
| `check_drift_task` | `tasks/evaluation.py` | per_ticker | langfuse | |
| `evaluate_recommendations_task` | `tasks/evaluation.py` | per_ticker | langfuse | |
| `snapshot_all_portfolios_task` | `tasks/portfolio.py` | per_ticker | none | Per-portfolio, not per-ticker — use portfolio_id as "ticker" |
| `snapshot_health_task` | `tasks/portfolio.py` | global | none | Cheap, low value in Langfuse |
| `materialize_rebalancing_task` | `tasks/portfolio.py` | per_ticker | none | Per-portfolio |
| `sync_analyst_consensus_task` | `tasks/warm_data.py` | per_ticker | langfuse | |
| `sync_fred_indicators_task` | `tasks/warm_data.py` | global | langfuse | Macro indicators have no ticker dimension |
| `sync_institutional_holders_task` | `tasks/warm_data.py` | per_ticker | langfuse | |
| `dq_scan_task` (Spec E) | `tasks/dq.py` | per_ticker | none | |
| `purge_login_attempts_task` | `tasks/audit.py` | global | none | Maintenance — low value in Langfuse |
| `purge_deleted_accounts_task` | `tasks/audit.py` | global | none | Maintenance — low value in Langfuse |
| `seed_*` (11 tasks) | `tasks/seed_tasks.py` | global | none | One-off bootstrap tasks; track runs but skip Langfuse |

**Migration pattern (example)**

Before (`tasks/alerts.py:442`):

```python
@celery_app.task(name="backend.tasks.alerts.generate_alerts_task")
def generate_alerts_task():
    return asyncio.run(_generate_alerts_async())
```

After:

```python
from backend.services.observability.task_tracer import tracked_task  # Spec A

@tracked_task("generate_alerts", trigger="scheduled")
@celery_app.task(name="backend.tasks.alerts.generate_alerts_task")
def generate_alerts_task():
    return asyncio.run(_generate_alerts_async())
```

No changes to the async helper itself — the decorator reads the return value (a
`TaskResult` TypedDict defined in Spec A) and dispatches to `PipelineRunner`.

**Enforcement test.** `tests/unit/tasks/test_pipeline_runner_all_tasks.py`
discovers every `@celery_app.task` decorator in `backend/tasks/**` and asserts
that each is also wrapped by `@tracked_task`. The test fails loudly if a new
task is added without tracking — this is the teeth behind G1.

---

### D2. Per-task admin trigger

**New endpoint.**

```
POST /api/v1/admin/pipelines/tasks/{task_name}/run
```

Request body (`PipelineTaskTriggerRequest`):

```python
class PipelineTaskTriggerRequest(BaseModel):
    """Admin trigger payload — intentionally minimal.

    `ticker` is the ONLY user-supplied kwarg that flows into the Celery
    task. We explicitly do NOT accept an `extra_kwargs` dict — that would
    let an authenticated admin pass arbitrary Pydantic fields into any
    whitelisted task. All other per-task knobs must ship as first-class
    fields on this model and pass through a per-task validator.
    """

    model_config = {"extra": "forbid"}

    ticker: str | None = Field(default=None, max_length=10)
    failure_mode: Literal["stop_on_failure", "continue"] = "continue"
```

Response (202):

```python
class PipelineTaskTriggerResponse(BaseModel):
    task_name: str
    run_id: str               # PipelineRun UUID (not Celery task id)
    celery_task_id: str
    ticker: str | None
    status: Literal["accepted"]
    message: str
```

**Whitelist mechanism.**

`task_name` must resolve via `registry.get_task(task_name)` — only tasks
registered in `pipeline_registry_config.py` are eligible. Any other value
returns `404 Not Found` with message `"Task not registered"`. This prevents
arbitrary Celery task execution by authenticated admins.

Additional validation:

- `task_name` path param is length-bounded (`max_length=100`) and regex-restricted
  (`^[a-zA-Z0-9_.]+$`).
- When `ticker` is supplied, the task must be in a hard-coded single-ticker
  accepts-ticker set: `{refresh_ticker_task, news_ingest_task,
  compute_convergence_snapshot_task, run_backtest_task, forecast_refresh_task}`.
  If the task is not in this set, return 400 `"Task does not accept a ticker argument"`.
- Require `user.is_admin` via `require_admin(user)` (unchanged from group trigger).

**Audit log.** Writes `AdminAuditLog` row with `action="trigger_task"`,
`target=task_name`, `metadata_={"ticker": ticker, "failure_mode": failure_mode,
"run_id": run_id, "celery_task_id": celery_task_id}`.

**Implementation sketch.**

```python
@router.post("/tasks/{task_name}/run", response_model=PipelineTaskTriggerResponse, status_code=202)
async def trigger_task_run(
    task_name: Annotated[str, Path(pattern=r"^[a-zA-Z0-9_.]+$", max_length=100)],
    body: PipelineTaskTriggerRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> PipelineTaskTriggerResponse:
    require_admin(user)

    registry = build_registry()
    task_def = registry.get_task(task_name)
    if task_def is None:
        raise HTTPException(404, "Task not registered")

    if body.ticker and task_name not in TASKS_ACCEPTING_TICKER:
        raise HTTPException(400, "Task does not accept a ticker argument")

    from backend.tasks import celery_app
    signature = celery_app.signature(task_name)
    # Only `ticker` (explicit, whitelisted) flows through. No arbitrary kwargs.
    kwargs: dict[str, Any] = {}
    if body.ticker:
        kwargs["ticker"] = body.ticker
    async_result = signature.apply_async(kwargs=kwargs)

    run_id = str(uuid.uuid4())  # correlation id — actual PipelineRun created by @tracked_task
    audit = AdminAuditLog(
        user_id=user.id,
        action="trigger_task",
        target=task_name,
        metadata_={
            "ticker": body.ticker,
            "failure_mode": body.failure_mode,
            "run_id": run_id,
            "celery_task_id": async_result.id,
        },
    )
    db.add(audit)
    await db.commit()

    return PipelineTaskTriggerResponse(
        task_name=task_name,
        run_id=run_id,
        celery_task_id=async_result.id,
        ticker=body.ticker,
        status="accepted",
        message=f"Task '{task_name}' dispatched"
        + (f" for ticker {body.ticker}" if body.ticker else ""),
    )
```

**Frontend wiring.**

- `frontend/src/hooks/use-admin-pipelines.ts` — add:
  ```typescript
  export function useTriggerTask() {
    const qc = useQueryClient();
    return useMutation<
      PipelineTaskTriggerResponse,
      Error,
      { taskName: string; ticker?: string; failureMode?: string }
    >({
      mutationFn: ({ taskName, ticker, failureMode = "continue" }) =>
        post<PipelineTaskTriggerResponse>(
          `/admin/pipelines/tasks/${taskName}/run`,
          { ticker, failure_mode: failureMode },
        ),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["admin-pipelines"] });
        qc.invalidateQueries({ queryKey: ["admin-audit"] });
      },
    });
  }
  ```
- `frontend/src/components/admin/pipeline-task-row.tsx` — add a **Play** icon
  button (lucide `Play`) that opens a small popover with an optional "Ticker"
  text input and a "Run" button. Calls `useTriggerTask`. On success, flash a
  green check; on error, flash a red X and expose error via toast.
- `frontend/src/components/admin/pipeline-group-card.tsx:95-112` — pass
  `onTriggerTask={(taskName, ticker) => trigger.mutate(...)}` to each row.

---

### D3. Ingestion health dashboard

**Data source.** The `ticker_ingestion_state` table introduced in Spec A. Shape
from Spec A (recap):

```sql
CREATE TABLE ticker_ingestion_state (
    ticker VARCHAR(10) PRIMARY KEY REFERENCES stocks(ticker),
    prices_updated_at TIMESTAMPTZ,
    signals_updated_at TIMESTAMPTZ,
    forecast_updated_at TIMESTAMPTZ,
    news_updated_at TIMESTAMPTZ,
    sentiment_updated_at TIMESTAMPTZ,
    convergence_updated_at TIMESTAMPTZ,
    last_error JSONB,  -- {stage: error_msg}
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Staleness rules** (configurable in `backend/config.py`):

- `prices`: stale if `prices_updated_at < now() - 24h`
- `signals`: stale if `signals_updated_at < now() - 24h`
- `forecast`: stale if `forecast_updated_at < now() - 48h`
- `news`: stale if `news_updated_at < now() - 12h`
- `sentiment`: stale if `sentiment_updated_at < now() - 24h`
- `convergence`: stale if `convergence_updated_at < now() - 24h`

**`overall_health`** is derived server-side:
- `green` — zero stages stale
- `yellow` — 1-2 stages stale
- `red` — 3+ stages stale OR any stage has a `last_error` entry

**Endpoint 1: list**

```
GET /api/v1/admin/ingestion/health
  ?stale_only=true|false       (default false)
  &ticker=AAPL                 (exact match filter)
  &stage=signals|forecast|...  (return tickers stale in this stage)
  &limit=100                   (default 100, max 500)
  &offset=0                    (default 0)
```

Response (`IngestionHealthResponse`):

```json
{
  "tickers": [
    {
      "ticker": "AAPL",
      "name": "Apple Inc.",
      "sector": "Technology",
      "prices_updated_at": "2026-04-06T21:35:02Z",
      "signals_updated_at": "2026-04-06T21:38:14Z",
      "forecast_updated_at": "2026-04-05T22:02:55Z",
      "news_updated_at": "2026-04-06T18:00:10Z",
      "sentiment_updated_at": "2026-04-06T19:12:44Z",
      "convergence_updated_at": "2026-04-06T21:45:00Z",
      "is_stale_per_stage": {
        "prices": false, "signals": false, "forecast": false,
        "news": false, "sentiment": false, "convergence": false
      },
      "last_error": null,
      "overall_health": "green"
    }
  ],
  "summary": {
    "total": 505,
    "fresh": 488,
    "stale": 12,
    "missing": 5
  },
  "limit": 100,
  "offset": 0
}
```

Sort: `ORDER BY overall_health DESC, ticker ASC` (red/yellow float to the top).

**Endpoint 2: single-ticker re-ingest convenience**

```
POST /api/v1/admin/ingestion/health/{ticker}/reingest
```

Dispatches `refresh_ticker_task.delay(ticker=ticker.upper())` and returns 202
with `{ticker, celery_task_id, status: "accepted"}`. Writes an `AdminAuditLog`
with `action="reingest_ticker"`, `target=ticker`.

**Frontend.**

- New route: `frontend/src/app/(authenticated)/admin/ingestion-health/page.tsx`
  — server component that renders `<IngestionHealthTable />`.
- New hook: `frontend/src/hooks/use-ingestion-health.ts` —
  ```typescript
  export function useIngestionHealth(filters: {
    staleOnly?: boolean;
    ticker?: string;
    stage?: string;
    limit?: number;
    offset?: number;
  }) {
    return useQuery<IngestionHealthResponse>({
      queryKey: ["admin-ingestion-health", filters],
      queryFn: () => get<IngestionHealthResponse>(
        `/admin/ingestion/health?${buildQuery(filters)}`
      ),
      refetchInterval: 60_000,
    });
  }
  export function useReingestTicker() { /* POST .../{ticker}/reingest */ }
  ```
- New component: `frontend/src/components/admin/ingestion-health-table.tsx` —
  sortable TanStack Table with columns: ticker, name, sector, last_signal,
  last_news, last_forecast, last_convergence, overall_health (shadcn Badge:
  green/yellow/red), action (shadcn Button with Play icon → `useReingestTicker`).
  Summary bar at top with totals. Filter chips above the table:
  "All / Stale only / Red only" and a stage selector.
- Modify `frontend/src/components/sidebar-nav.tsx` — under the admin section,
  add `{ label: "Ingestion Health", href: "/admin/ingestion-health", icon: Activity }`.
- Types (`frontend/src/types/api.ts`):
  ```typescript
  export interface IngestionHealthRow {
    ticker: string;
    name: string;
    sector: string | null;
    prices_updated_at: string | null;
    signals_updated_at: string | null;
    forecast_updated_at: string | null;
    news_updated_at: string | null;
    sentiment_updated_at: string | null;
    convergence_updated_at: string | null;
    is_stale_per_stage: Record<string, boolean>;
    last_error: Record<string, string> | null;
    overall_health: "green" | "yellow" | "red";
  }
  export interface IngestionHealthSummary {
    total: number;
    fresh: number;
    stale: number;
    missing: number;
  }
  export interface IngestionHealthResponse {
    tickers: IngestionHealthRow[];
    summary: IngestionHealthSummary;
    limit: number;
    offset: number;
  }
  ```

---

### D4. Cache invalidator coverage audit

**Current events** (`backend/services/cache_invalidator.py`):

- `on_prices_updated(tickers)` — clears convergence + forecast + sector-forecast
- `on_signals_updated(tickers)` — clears convergence
- `on_sentiment_scored(tickers)` — clears sentiment + convergence
- `on_forecast_updated(tickers)` — clears forecast + convergence + sector + BL
- `on_backtest_completed(tickers)` — clears backtest
- `on_portfolio_changed(user_id)` — clears BL / MC / CVaR
- `on_stock_ingested(ticker)` — currently a no-op

**New events to add**

- `on_convergence_updated(tickers)` — clears `app:convergence:{t}` and
  `app:convergence:rationale:{t}`. (Writes to `signal_convergence_daily`
  currently don't fire any invalidator — gap.)
- `on_recommendations_updated(tickers)` — clears `app:recs:{t}`. (New cache
  namespace added by Spec B.)
- `on_drift_detected(tickers)` — clears `app:drift:{t}`. (Alerts page cache.)
- `on_ticker_state_updated(ticker)` — clears `app:ingestion-health:*`
  (ingestion-health endpoint cache, TTL 60s).

**Audit checklist** — every write site must fire the matching event after
`db.commit()`:

| Table | Writer | Current? | Required event |
|---|---|---|---|
| `signal_snapshots` | `tasks/market_data.py::_compute_and_upsert_signals` | Yes (`on_signals_updated`) | Keep |
| `signal_snapshots` | `tools/signals.py::compute_signals` (synchronous read-compute-write path) | **No — GAP** | Add `on_signals_updated` |
| `forecast_results` | `tasks/forecasting.py::_forecast_refresh_async` | Yes (`on_forecast_updated`) | Keep |
| `forecast_results` | `tools/forecasting.py::train_prophet_model` (manual/on-demand) | **No — GAP** | Add `on_forecast_updated` |
| `news_sentiment_daily` | `tasks/news_sentiment.py::_score_sentiment_async` | Yes (`on_sentiment_scored`) | Keep |
| `signal_convergence_daily` | `tasks/convergence.py::_compute_convergence_async` | **No — GAP** | Add `on_convergence_updated` |
| `recommendation_snapshots` | `tasks/recommendations.py::_generate_recommendations_async` | **No — GAP** | Add `on_recommendations_updated` |
| `in_app_alert` | `tasks/alerts.py::_generate_alerts_async` | **No — GAP** | Add `on_drift_detected` (alerts are the consumer) |
| `stock_prices` | `tasks/market_data.py::_nightly_price_refresh_async` | Yes (`on_prices_updated`) | Keep |
| `ticker_ingestion_state` | `tasks/tracking.py::@tracked_task` | **No — new** | Add `on_ticker_state_updated` |

**Pattern.** All invalidator calls happen *after* successful `db.commit()`, not
before — Redis eviction before commit + commit failure would leave Redis stale
relative to the DB.

```python
async with async_session_factory() as session:
    session.add(snapshot)
    await session.commit()

redis = await get_redis()
invalidator = CacheInvalidator(redis)
await invalidator.on_convergence_updated([ticker])
```

**Enforcement test.**
`tests/unit/services/test_cache_invalidator_coverage.py` uses an AST walk
(NOT a substring/line-distance heuristic) to locate every
`db.add(SignalSnapshot(...))` / `db.add(Recommendation(...))` / etc. `Call`
node across `backend/` and asserts that within the same enclosing function
(not "50 lines") there is a subsequent `await cache_invalidator.on_*(...)`
`Call` node matching the written table.

The old "substring `"add("` within 50 lines of `table` name" heuristic
produced false positives (comments, unrelated variables named `add`) and
false negatives (refactored helpers). The AST walk is strict: it visits
`ast.Call` nodes whose `.func` is `ast.Attribute(attr="add")` with
arg-0 of type `ast.Call` whose `.func` is `ast.Name` matching a guarded
model class, then scans siblings inside the same `FunctionDef` for an
`await cache_invalidator.on_{table}_updated(...)` call. Missing matches
yield a clear `CacheInvalidatorGap(file, line, model, function)` failure.

Additionally, integration tests per write site use a real Redis container
to verify eviction end-to-end.

---

### D5. Langfuse spans for non-agent paths

All non-agent Langfuse work goes through the `trace_task` async context
manager defined by Spec A in `backend/services/observability/task_tracer.py`.
Spec D is a consumer — it does NOT define a new `tracing.py` module or a new
`task_tracer` signature. The authoritative contract (recap from Spec A):

```python
# backend/services/observability/task_tracer.py  (defined in Spec A)

@asynccontextmanager
async def trace_task(
    name: str,
    *,
    langfuse: LangfuseService,
    collector: ObservabilityCollector,
    metadata: dict[str, Any] | None = None,
) -> AsyncIterator[TaskTraceHandle]:
    """Trace a non-agent task block. Async context manager.

    Fire-and-forget: if Langfuse is disabled or the call fails, the context
    manager silently becomes a no-op. Never raises.
    """
```

`TaskTraceHandle` exposes `add_metadata(**kwargs)` and
`record_llm(model, provider, tier, latency_ms, prompt_tokens,
completion_tokens, cost_usd)`. It does NOT expose `kind="generation"` /
`input_data` / `output_data` — LLM accounting goes through
`handle.record_llm(...)` which routes into the DB collector.

**Every `with task_tracer(...)` sketch below is shorthand for
`async with trace_task(..., langfuse=langfuse_service, collector=observability_collector)`
using the module-level singletons published by `main.py` lifespan (Spec A).**

**D5.1 Nightly chain root trace**

`nightly_pipeline_chain_task` in `tasks/market_data.py` is the orchestrator
called by Beat at 21:30 ET. Wrap its body:

```python
with task_tracer(
    "nightly_pipeline_chain_run",
    metadata={"trigger": "scheduled", "beat_iso": datetime.now(tz=UTC).isoformat()},
) as root:
    with task_tracer("phase0_cache_invalidation", parent=root): ...
    with task_tracer("phase1_price_refresh", parent=root): ...
    with task_tracer("phase2_forecast_recs_eval_snapshots", parent=root): ...
    with task_tracer("phase3_drift_convergence", parent=root): ...
    with task_tracer("phase4_alerts_health_rebalancing", parent=root): ...
```

Each phase span's metadata includes `{tickers_total, tickers_succeeded,
tickers_failed, duration_ms}` — set via `root.update_metadata()` before exit.

**D5.2 Prophet training spans**

Wrap `tools/forecasting.py::train_prophet_model` (body starts at line 43) and
the Celery wrapper `_forecast_refresh_async`'s per-ticker loop:

```python
with task_tracer(
    "prophet_train",
    metadata={
        "ticker": ticker,
        "data_points": len(price_df),
        "sentiment_regressors_present": has_sentiment,
        "horizon_days": horizon,
    },
) as span:
    model = Prophet(...)
    model.fit(df)
    forecast = model.predict(future)
    span.update_metadata({
        "mape": round(mape, 4),
        "rmse": round(rmse, 4),
    })
```

**D5.3 Sentiment scorer generation spans**

`services/news/sentiment_scorer.py::_score_single_batch` makes ~100 LLM calls
per day (5 articles per batch × ~20 batches). Each batch becomes a
Langfuse **generation** span — not a plain span — so cost is tracked:

```python
import random

SAMPLING_RATE = 0.25  # log prompt/response for 25% of batches
should_log_io = random.random() < SAMPLING_RATE

with task_tracer(
    "sentiment_score_batch",
    kind="generation",
    model=self.model_name,
    input_data=prompt if should_log_io else None,  # gated
    metadata={
        "article_count": len(batch),
        "batch_idx": batch_idx,
        "sampling_io_logged": should_log_io,
    },
) as gen:
    response = await self._llm.complete(prompt)
    gen.update(
        output=response.text if should_log_io else None,
        usage={
            "input": response.prompt_tokens,
            "output": response.completion_tokens,
            "total": response.total_tokens,
        },
    )
```

Metadata is always logged (100%); prompt/response text is sampled at 25% to
bound Langfuse storage cost. Truncation: 4KB input, 4KB output hard cap.

**D5.4 News provider fetch spans**

`tasks/news_sentiment.py::_ingest_news_async` iterates over providers
(Finnhub, EDGAR, Fed, Google News). Wrap each provider call:

```python
for provider_name, provider in self._providers.items():
    with task_tracer(
        f"news_fetch_{provider_name}",
        metadata={"ticker": ticker, "provider": provider_name},
    ) as span:
        articles = await provider.fetch(ticker)
        span.update_metadata({"articles_returned": len(articles)})
```

**D5.5 Cost mitigation**

Rough estimate: sentiment scorer ~20 batches × 365 days = ~7,300 generations/year.
With 4KB prompt + 4KB output and 25% sampling, storage ≈ `7,300 × 0.25 × 8KB ≈ 14.6 MB/year`.
Metadata-only (100%) adds ~0.5 MB/year. Well within Langfuse self-hosted budget.

Guardrails:
- Feature flag `LANGFUSE_TRACK_TASKS=true|false` in `backend/config.py` —
  default true in prod, false in tests to keep tests hermetic.
- Sampling rate configurable via `LANGFUSE_SENTIMENT_IO_SAMPLING_RATE` (default `0.25`).
- `task_tracer` is a no-op if `LangfuseService.enabled` is false, so tests
  without a Langfuse server continue to pass.

---

### D6. Admin audit log viewer

**New endpoint.**

```
GET /api/v1/admin/audit/recent?limit=50&offset=0&action=trigger_task
```

Query params:
- `limit`: int, default 50, max 200
- `offset`: int, default 0
- `action`: optional filter (`trigger_group`, `trigger_task`, `cache_clear`,
  `cache_clear_all`, `reingest_ticker`)

Response (`AdminAuditLogResponse`):

```json
{
  "entries": [
    {
      "id": "uuid",
      "created_at": "2026-04-06T21:42:11Z",
      "user_id": "uuid",
      "user_email": "admin@example.com",
      "action": "trigger_task",
      "target": "backend.tasks.forecasting.forecast_refresh_task",
      "metadata": {"ticker": "AAPL", "run_id": "...", "celery_task_id": "..."}
    }
  ],
  "total": 342,
  "limit": 50,
  "offset": 0
}
```

The endpoint joins `admin_audit_log` with `users` to resolve `user_email`
(no N+1 — single `SELECT ... JOIN users ... ORDER BY created_at DESC LIMIT/OFFSET`).

**Frontend.**

- New hook `frontend/src/hooks/use-admin-audit.ts` (TanStack Query, 30s stale).
- New component `frontend/src/components/admin/recent-audit-panel.tsx`:
  shadcn `Card` wrapping a compact table — columns: Timestamp (relative),
  User, Action (badge with color by action type), Target (truncated with
  tooltip), Metadata (JSON collapsed, expandable).
- Mount panel on existing admin pipelines page
  (`frontend/src/app/(authenticated)/admin/pipelines/page.tsx`) below the
  group cards.
- Types in `frontend/src/types/api.ts`:
  ```typescript
  export interface AdminAuditLogRow {
    id: string;
    created_at: string;
    user_id: string;
    user_email: string;
    action: string;
    target: string;
    metadata: Record<string, unknown>;
  }
  export interface AdminAuditLogResponse {
    entries: AdminAuditLogRow[];
    total: number;
    limit: number;
    offset: number;
  }
  ```

---

### D7. Task latency metrics

**MVP: Langfuse-only.** `@tracked_task` already creates a root Langfuse trace
per task invocation (D1 + D5). The trace naturally records
`start_time`, `end_time`, and derived `duration_ms`. For the 7-day rolling
latency trend panel, the backend queries the existing
`pipeline_runs` table (which is already populated by `PipelineRunner`):

```sql
SELECT pipeline_name,
       DATE_TRUNC('hour', started_at) AS bucket,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_duration_seconds) AS p50_s,
       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_duration_seconds) AS p95_s,
       COUNT(*) AS runs
FROM pipeline_runs
WHERE started_at > now() - interval '7 days'
  AND status IN ('success', 'partial')
GROUP BY pipeline_name, bucket
ORDER BY pipeline_name, bucket;
```

Exposed as:

```
GET /api/v1/admin/pipelines/latency-trends?days=7
```

Response:

```json
{
  "series": [
    {
      "pipeline_name": "nightly_price_refresh",
      "points": [
        {"bucket": "2026-04-06T21:00:00Z", "p50_s": 312.4, "p95_s": 498.1, "runs": 1}
      ]
    }
  ]
}
```

**Frontend.** New component `frontend/src/components/admin/task-latency-panel.tsx`
— a Recharts `LineChart` with p50 + p95 per pipeline, filterable by pipeline
via a shadcn `Select`. Animations disabled
(`isAnimationActive={false}`) per project Recharts conventions. Added to the
admin command center as a fifth panel.

**Deferred:** `task_metric_history` dedicated table. The `pipeline_runs` table
is sufficient for the 7-day rolling window. If queries become slow at sprint
end, we revisit with a continuous aggregate or materialised view.

---

## Files Created

**Backend:**

- `backend/routers/admin_ingestion.py` — ingestion health endpoints (D3)
- `backend/routers/admin_audit.py` — audit log viewer endpoint (D6)
- `backend/schemas/admin_ingestion.py` — `IngestionHealthRow`,
  `IngestionHealthSummary`, `IngestionHealthResponse`
- `backend/schemas/admin_audit.py` — `AdminAuditLogRow`, `AdminAuditLogResponse`
- `backend/tasks/tracing.py` — `task_tracer` context manager (implements Spec A contract)
- `tests/unit/tasks/test_pipeline_runner_all_tasks.py` — enforcement test
- `tests/unit/tasks/test_task_tracer.py`
- `tests/unit/services/test_cache_invalidator_coverage.py`
- `tests/unit/services/test_langfuse_spans.py`
- `tests/api/test_admin_pipeline_task_trigger.py`
- `tests/api/test_admin_ingestion_health.py`
- `tests/api/test_admin_audit_recent.py`

**Frontend:**

- `frontend/src/app/(authenticated)/admin/ingestion-health/page.tsx`
- `frontend/src/hooks/use-ingestion-health.ts`
- `frontend/src/hooks/use-admin-audit.ts`
- `frontend/src/components/admin/ingestion-health-table.tsx`
- `frontend/src/components/admin/recent-audit-panel.tsx`
- `frontend/src/components/admin/task-latency-panel.tsx`
- `frontend/src/__tests__/components/admin/ingestion-health-table.test.tsx`
- `frontend/src/__tests__/components/admin/recent-audit-panel.test.tsx`
- `frontend/src/__tests__/hooks/use-trigger-task.test.tsx`

## Files Modified

**Backend:**

- `backend/tasks/market_data.py` — wrap 4 tasks in `@tracked_task`; root-trace
  nightly chain
- `backend/tasks/forecasting.py` — wrap 5 tasks; Prophet training spans
- `backend/tasks/news_sentiment.py` — wrap 2 tasks; provider + batch spans
- `backend/tasks/convergence.py` — wrap 1 task; fire `on_convergence_updated`
- `backend/tasks/recommendations.py` — wrap 1 task; fire `on_recommendations_updated`
- `backend/tasks/alerts.py` — wrap 1 task; fire `on_drift_detected`
- `backend/tasks/evaluation.py` — wrap 3 tasks
- `backend/tasks/portfolio.py` — wrap 3 tasks
- `backend/tasks/warm_data.py` — wrap 3 tasks
- `backend/tasks/audit.py` — wrap 2 tasks
- `backend/tasks/seed_tasks.py` — wrap 11 seed tasks (scope=global, tracer=none)
- `backend/routers/admin_pipelines.py` — add `POST /tasks/{task_name}/run` +
  `GET /latency-trends`
- `backend/schemas/admin_pipeline.py` — add `PipelineTaskTriggerRequest`,
  `PipelineTaskTriggerResponse`, `TaskLatencyPoint`, `TaskLatencySeries`,
  `TaskLatencyResponse`
- `backend/services/cache_invalidator.py` — add `on_convergence_updated`,
  `on_recommendations_updated`, `on_drift_detected`, `on_ticker_state_updated`
- `backend/tools/signals.py` — fire `on_signals_updated` after commit (gap fix)
- `backend/tools/forecasting.py` — fire `on_forecast_updated` after commit (gap fix)
- `backend/config.py` — add `LANGFUSE_TRACK_TASKS`,
  `LANGFUSE_SENTIMENT_IO_SAMPLING_RATE`, ingestion staleness thresholds
- `backend/main.py` — mount new routers (`admin_ingestion`, `admin_audit`)
- `backend/observability/langfuse.py` — add `update_metadata()` passthrough

**Frontend:**

- `frontend/src/hooks/use-admin-pipelines.ts` — add `useTriggerTask`,
  `useTaskLatencyTrends`
- `frontend/src/components/admin/pipeline-task-row.tsx` — add Play button
- `frontend/src/components/admin/pipeline-group-card.tsx` — wire `onTriggerTask`
- `frontend/src/app/(authenticated)/admin/pipelines/page.tsx` — mount
  `<RecentAuditPanel />` + `<TaskLatencyPanel />`
- `frontend/src/components/sidebar-nav.tsx` — add "Ingestion Health" link
- `frontend/src/types/api.ts` — 8 new types (D2, D3, D6)

---

## API Contract Changes

**New endpoints:**

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| POST | `/api/v1/admin/pipelines/tasks/{task_name}/run` | admin | `PipelineTaskTriggerRequest` | 202 `PipelineTaskTriggerResponse` |
| GET | `/api/v1/admin/pipelines/latency-trends` | admin | — | `TaskLatencyResponse` |
| GET | `/api/v1/admin/ingestion/health` | admin | — | `IngestionHealthResponse` |
| POST | `/api/v1/admin/ingestion/health/{ticker}/reingest` | admin | — | 202 `ReingestResponse` |
| GET | `/api/v1/admin/audit/recent` | admin | — | `AdminAuditLogResponse` |

All endpoints:
- Return 401 if unauthenticated
- Return 403 if authenticated but not admin
- Return 422 on malformed body / query params
- Never return `str(exc)` in error detail (Hard Rule #10)

**New Pydantic schemas** (module per concern):

- `backend/schemas/admin_pipeline.py` (existing file):
  - `PipelineTaskTriggerRequest`, `PipelineTaskTriggerResponse`
  - `TaskLatencyPoint`, `TaskLatencySeries`, `TaskLatencyResponse`
- `backend/schemas/admin_ingestion.py` (new):
  - `IngestionHealthRow`, `IngestionHealthSummary`, `IngestionHealthResponse`,
    `ReingestResponse`
- `backend/schemas/admin_audit.py` (new):
  - `AdminAuditLogRow`, `AdminAuditLogResponse`

---

## Frontend Impact

### TypeScript types (`frontend/src/types/api.ts`)

- `PipelineTaskTriggerRequest`, `PipelineTaskTriggerResponse`
- `TaskLatencyPoint`, `TaskLatencySeries`, `TaskLatencyResponse`
- `IngestionHealthRow`, `IngestionHealthSummary`, `IngestionHealthResponse`,
  `ReingestResponse`
- `AdminAuditLogRow`, `AdminAuditLogResponse`

### Files summary

| File | Change |
|---|---|
| `hooks/use-admin-pipelines.ts` | +`useTriggerTask`, +`useTaskLatencyTrends` |
| `hooks/use-ingestion-health.ts` | new |
| `hooks/use-admin-audit.ts` | new |
| `components/admin/pipeline-task-row.tsx` | +Play button, +popover for ticker input |
| `components/admin/pipeline-group-card.tsx` | wire `onTriggerTask` |
| `components/admin/ingestion-health-table.tsx` | new |
| `components/admin/recent-audit-panel.tsx` | new |
| `components/admin/task-latency-panel.tsx` | new |
| `app/(authenticated)/admin/pipelines/page.tsx` | mount new panels |
| `app/(authenticated)/admin/ingestion-health/page.tsx` | new route |
| `components/sidebar-nav.tsx` | +Ingestion Health link |
| `types/api.ts` | +10 interfaces |

All components follow project conventions: functional, shadcn/ui primitives,
Recharts with `isAnimationActive={false}`, TanStack Query for all fetches,
routes via `/api/v1/...` through `lib/api.ts`.

---

## Test Impact

### Existing tests affected

Grep targets:
- `tests/` matching `pipeline_runner` — tests for `backend/tasks/pipeline.py`
  (start_run, complete_run). Behaviour unchanged; tests should continue to pass.
  New tests for `@tracked_task` are additive.
- `tests/unit/agents/test_llm_client.py` — `LangfuseService` mock. Unchanged
  API, so no edits needed.
- `tests/api/test_admin_pipelines.py` — existing group-trigger tests. Unchanged.
- `tests/unit/services/test_cache_invalidator.py` — existing event tests.
  Will expand with new events.

### New test files

- `tests/unit/tasks/test_pipeline_runner_all_tasks.py` — AST discovers every
  `@celery_app.task` in `backend/tasks/**`, asserts each is wrapped by
  `@tracked_task`. One test per task (parametrised).
- `tests/unit/tasks/test_task_tracer.py` — `task_tracer` happy path, error
  path (exception inside `with` block), Langfuse-disabled no-op path,
  nested spans, sampling gate.
- `tests/api/test_admin_pipeline_task_trigger.py`
- `tests/api/test_admin_ingestion_health.py`
- `tests/api/test_admin_audit_recent.py`
- `tests/unit/services/test_cache_invalidator_coverage.py` — AST walk of every
  write to the 6 guarded tables; asserts matching invalidator call within 50
  lines of the commit.
- `tests/unit/services/test_langfuse_spans.py` — `MagicMock` Langfuse;
  verifies spans are created for Prophet training, sentiment batch, news
  provider fetch, nightly phases.
- Frontend: `ingestion-health-table.test.tsx`, `recent-audit-panel.test.tsx`,
  `use-trigger-task.test.tsx` (MSW v2 handlers).

### Specific test cases (~30)

**D1 enforcement:**
1. `test_every_celery_task_is_tracked` — discovery test
2. `test_tracked_task_per_ticker_records_success`
3. `test_tracked_task_per_ticker_records_failure`
4. `test_tracked_task_global_records_one_row`
5. `test_tracked_task_unhandled_exception_marks_failed`
6. `test_tracked_task_langfuse_disabled_no_op`

**D2 per-task trigger:**
7. `test_trigger_task_unauth_returns_401`
8. `test_trigger_task_non_admin_returns_403`
9. `test_trigger_task_unregistered_returns_404`
10. `test_trigger_task_accepts_ticker_for_whitelisted_tasks`
11. `test_trigger_task_rejects_ticker_for_non_ticker_tasks`
12. `test_trigger_task_writes_audit_log`
13. `test_trigger_task_returns_202_with_celery_task_id`
14. `test_trigger_task_regex_rejects_shell_metacharacters`

**D3 ingestion health:**
15. `test_ingestion_health_returns_all_tickers`
16. `test_ingestion_health_stale_only_filter`
17. `test_ingestion_health_by_stage`
18. `test_ingestion_health_overall_health_classification`
19. `test_ingestion_health_pagination`
20. `test_reingest_ticker_dispatches_celery_task`
21. `test_reingest_ticker_writes_audit`

**D4 cache invalidator:**
22. `test_every_signal_write_fires_invalidator` — AST audit
23. `test_on_convergence_updated_clears_convergence_keys`
24. `test_on_recommendations_updated_clears_rec_keys`
25. `test_integration_signal_write_evicts_redis_end_to_end`

**D5 Langfuse spans:**
26. `test_nightly_chain_creates_root_trace_with_5_phases`
27. `test_prophet_training_span_includes_mape_rmse`
28. `test_sentiment_batch_samples_io_at_25pct` (hypothesis + seeded RNG)
29. `test_news_provider_span_per_provider`

**D6 audit viewer:**
30. `test_audit_recent_joins_user_email`
31. `test_audit_recent_filter_by_action`

**D7 latency:**
32. `test_latency_trends_groups_by_pipeline_and_hour`
33. `test_latency_trends_excludes_running_and_failed`

**Frontend:**
34. `IngestionHealthTable renders red rows first`
35. `RecentAuditPanel collapses long metadata`
36. `useTriggerTask invalidates admin-audit on success`

---

## Migration Strategy

All changes are **additive** — new endpoints, new components, new tracking
calls, new events. Schema changes live in Spec A (`ticker_ingestion_state`),
and this spec only consumes that table.

**Ordering within the Spec D PR:**

1. Land `backend/tasks/tracing.py::task_tracer` (no-op when Langfuse disabled).
2. Land `@tracked_task` consumers — one commit per task file for reviewability.
3. Land new cache invalidator events + fix write-site gaps.
4. Land new admin endpoints (D2, D3, D6, D7).
5. Land frontend: hooks first, then components, then page wiring.
6. Land enforcement tests last so they gate future additions.

**Can this ship incrementally?** Technically yes — each task's migration is
independent — but we require a single PR for D1 so the enforcement test
(`test_every_celery_task_is_tracked`) is green at merge. Splitting would
require a temporary allowlist, which we explicitly reject.

---

## Risk + Rollback

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `@tracked_task` adds Redis/DB writes to every task | Medium | Low | Single-digit ms per task; PipelineRunner already does this for 3 tasks with no measurable overhead |
| Langfuse traces explode storage | Medium | Medium | Sampling (25%) for sentiment I/O, 4KB caps, feature flag |
| Per-task endpoint used to run arbitrary tasks | Low | High | Registry-based whitelist; regex path param; admin-only; audit logged |
| Cache invalidator test is too strict (AST distance heuristic) | Medium | Low | Allow `# noqa: cache-audit` escape hatch for intentional exceptions; backed by integration tests |
| Ingestion health endpoint N+1 joins | Low | Medium | Single JOIN query; server-side pagination; 60s TanStack staleTime |
| Nightly chain root trace breaks on Langfuse outage | Low | Low | `task_tracer` is fire-and-forget no-op on error |

**Rollback.** Each sub-feature is isolated:
- Disable D1 tracking: flip `LANGFUSE_TRACK_TASKS=false` and `@tracked_task`
  becomes a thin PipelineRunner wrapper with no Langfuse writes.
- Disable D2 endpoint: feature-flag behind `ADMIN_PER_TASK_TRIGGER_ENABLED`;
  if false, return 404.
- Revert D3-D7 UI: hide the sidebar link via feature flag
  `NEXT_PUBLIC_INGESTION_HEALTH_ENABLED`.
- Cache invalidator gap fixes cannot be rolled back independently — they are
  correctness fixes.

---

## Open Questions

1. **Sampling rate for sentiment scorer I/O?**
   Recommendation: 25% of batches log full prompt/response; 100% log metadata +
   usage counts. Configurable via `LANGFUSE_SENTIMENT_IO_SAMPLING_RATE`.
   Revisit once we have 30 days of data.
2. **`task_metric_history` DB table or Langfuse-only?**
   Recommendation: **Langfuse-only + pipeline_runs** for MVP; defer dedicated
   table to a follow-up spec if latency-trend queries become too expensive.
3. **Should the nightly chain root trace become the parent for all Celery task
   traces started inside it?** Langfuse's Python SDK supports cross-process
   trace parenting via `traceparent` headers, but Celery's broker strips custom
   headers by default. Recommendation: defer to a follow-up — phase spans inside
   the chain task are sufficient for now.
4. **Who owns per-ticker staleness thresholds?** Start with constants in
   `backend/config.py`; promote to a DB-backed admin-editable settings table if
   ops requests flexibility.
5. **Should the audit log viewer live in the existing observability section
   (`/admin/observability/audit`) rather than the pipelines page?** Recommendation:
   both — keep the pipelines-page panel as a quick peek and add a full route in
   a follow-up.

---

## Dependencies

- **Depends on Spec A:** provides `@tracked_task` decorator, `task_tracer`
  context manager contract, `ticker_ingestion_state` table + migration, and the
  `TaskResult` TypedDict.
- **Blocks:** Spec E (Quality gates) uses the audit log viewer for test-run
  inspection; Spec G (Frontend observability) extends the ingestion-health
  panel with chart thumbnails.
- **Supersedes (partial):** KAN-162 — Langfuse self-hosted integration. This
  spec completes the non-agent coverage gap.

---

## Doc Delta (for `session/doc-delta`)

- [endpoint] `POST /api/v1/admin/pipelines/tasks/{task_name}/run` — TDD
- [endpoint] `GET /api/v1/admin/pipelines/latency-trends` — TDD
- [endpoint] `GET /api/v1/admin/ingestion/health` — TDD
- [endpoint] `POST /api/v1/admin/ingestion/health/{ticker}/reingest` — TDD
- [endpoint] `GET /api/v1/admin/audit/recent` — TDD
- [service] `CacheInvalidator` new events — TDD
- [FR] New FR — "Admins can view per-ticker ingestion health and trigger
  single-task re-runs" — FSD
- [FR] New FR — "All scheduled tasks are observable in Langfuse with duration
  and error metadata" — FSD
- [ADR] Consider an ADR for "Langfuse-only task metrics (vs dedicated metric
  table)" decision — author during implementation.
