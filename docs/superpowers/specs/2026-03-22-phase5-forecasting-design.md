# Phase 5: Forecasting, Evaluation & Background Automation — Design Spec

> **Status:** Draft
> **Author:** Session 45 brainstorm
> **Date:** 2026-03-22
> **JIRA Epic:** TBD (to be created after spec approval)

---

## 1. Overview

Phase 5 transforms the platform from reactive (user-triggered) to proactive (system-computed). Background jobs pre-compute signals, generate forecasts, evaluate past recommendations, and surface alerts — all without user intervention.

**User persona:** Active analyst with automation assist. The user still opens the app daily but no longer manually refreshes data. Forecasts and evaluations are a new analysis dimension the agent weaves into conversations.

**Not in scope:** Telegram notifications (Phase 5.1), red flag scanner (Phase 5.1), forecast blending into composite score (Phase 5.1).

---

## 2. Data Models

### 2.1 ModelVersion

Tracks every trained Prophet model. Supports versioning, rollback, and accuracy tracking.

```
Table: model_versions
- id: UUID PK
- ticker: FK → stocks.ticker
- model_type: String ("prophet")
- version: Integer (auto-increment per ticker)
- is_active: Boolean (one active per model_type + ticker)
- trained_at: DateTime
- training_data_start: Date
- training_data_end: Date
- data_points: Integer
- hyperparameters: JSONB
- metrics: JSONB (rolling_mape, mae, evaluated_count)
- status: String ("active", "degraded", "retired")
- artifact_path: String (data/models/{ticker}_prophet_v{N}.pkl)
- created_at: DateTime
- updated_at: DateTime
```

### 2.2 ForecastResult (TimescaleDB hypertable)

One row per ticker per horizon per forecast date.

```
Table: forecast_results (hypertable on forecast_date)
- forecast_date: Date PK (truncated to midnight — one forecast run per day)
- ticker: String PK, FK → stocks.ticker
- horizon_days: Integer PK (90, 180, 270)
- model_version_id: FK → model_versions.id
- predicted_price: Float
- predicted_lower: Float (80% CI lower)
- predicted_upper: Float (80% CI upper)
- target_date: Date
- actual_price: Float (nullable, filled by eval job)
- error_pct: Float (nullable, filled by eval job)
- created_at: DateTime
```

### 2.3 RecommendationOutcome

Evaluation of past BUY/SELL recommendations at 30/90/180d horizons.

Note: `RecommendationSnapshot` uses a composite PK of `(generated_at, ticker)` and is user-scoped via `user_id`. The FK here uses the composite key, and `user_id` is included for scoping.

```
Table: recommendation_outcomes
- id: UUID PK
- user_id: FK → users.id (scoped per user)
- rec_generated_at: DateTime (composite FK part 1 → recommendation_snapshots.generated_at)
- rec_ticker: String (composite FK part 2 → recommendation_snapshots.ticker)
- action: String (BUY or SELL only — directional claims)
- price_at_recommendation: Float
- horizon_days: Integer (30, 90, 180)
- evaluated_at: DateTime
- actual_price: Float
- return_pct: Float
- spy_return_pct: Float
- alpha_pct: Float (return_pct - spy_return_pct)
- action_was_correct: Boolean (BUY correct if return > 0, SELL correct if return < 0)
- created_at: DateTime
```

### 2.4 PipelineWatermark

Tracks pipeline progress for gap detection and recovery.

```
Table: pipeline_watermarks
- pipeline_name: String PK
- last_completed_date: Date
- last_completed_at: DateTime
- status: String ("ok", "backfilling", "failed")
```

### 2.5 PipelineRun

Observability log for every pipeline execution.

```
Table: pipeline_runs
- id: UUID PK
- pipeline_name: String
- started_at: DateTime
- completed_at: DateTime (nullable)
- status: String ("running", "success", "partial", "failed")
- tickers_total: Integer
- tickers_succeeded: Integer
- tickers_failed: Integer
- error_summary: JSONB (ticker → error reason)
- retry_count: Integer
- trigger: String ("scheduled", "backfill", "drift", "manual")
```

### 2.6 InAppAlert

User-facing notifications stored for the bell icon dropdown.

```
Table: in_app_alerts
- id: UUID PK
- user_id: FK → users.id
- message: String
- alert_type: String ("signal_change", "drift", "pipeline", "accuracy", "backfill")
- metadata: JSONB (nullable — e.g., {"ticker": "AAPL", "route": "/stocks/AAPL"} for deep-linking)
- is_read: Boolean (default false)
- created_at: DateTime
```

### 2.7 Stock Table Extension

Add `is_etf: Boolean` column (default false). Seed 11 SPDR Select Sector ETFs as Stock rows with `is_etf=True`:

| Sector | ETF Ticker |
|--------|-----------|
| Technology | XLK |
| Healthcare | XLV |
| Financials | XLF |
| Consumer Discretionary | XLY |
| Consumer Staples | XLP |
| Energy | XLE |
| Industrials | XLI |
| Materials | XLB |
| Utilities | XLU |
| Real Estate | XLRE |
| Communication Services | XLC |

Also seed SPY (`is_etf=True`) for benchmark comparison in recommendation evaluation.

VIX (`^VIX`) is fetched ad-hoc via yfinance during drift detection — it is NOT stored as a Stock row (it's an index, not a tradeable instrument). The drift check fetches the latest VIX value at runtime and caches it for the pipeline run duration.

---

## 3. Nightly Pipeline Orchestration

### 3.1 Pipeline Chain

Runs nightly at 9:30 PM ET (after market close + data settlement). Celery beat uses UTC — configure crontab as `01:30 UTC` (EST) / `01:30 UTC` (EDT shifts to 9:30 PM EDT = 01:30 UTC). Note: to handle DST correctly, switch `celery_app.conf.timezone` to `"US/Eastern"` and use `crontab(hour=21, minute=30)`.

```
price_refresh
  → signal_computation
    → recommendation_generation
      → forecast_refresh (predict-only, no retrain)
        → forecast_evaluation
          → recommendation_evaluation
            → portfolio_snapshot
              → alert_generation
```

Uses Celery `chain()` — each step runs only after the previous completes.

### 3.2 Step Behaviors

| Step | Input | Output | Failure handling |
|------|-------|--------|-----------------|
| price_refresh | All watchlist + portfolio + ETF + SPY tickers | StockPrice rows | Per-ticker: 3 retries w/ exponential backoff (1s→2s→4s). Skip after 3 failures. Partial success OK |
| signal_computation | Tickers with fresh prices | SignalSnapshot rows | Skip tickers without fresh prices |
| recommendation_generation | Tickers with fresh signals | RecommendationSnapshot rows | Uses existing engine. Skip tickers without signals |
| forecast_refresh | Tickers with trained models | ForecastResult rows (predict-only) | Skip if model artifact missing. Log warning |
| forecast_evaluation | ForecastResults where target_date ≤ today AND actual_price IS NULL | Fill actual_price, error_pct. Update ModelVersion.metrics | Pure DB op, unlikely to fail |
| recommendation_evaluation | Recommendations at horizon age without outcomes | RecommendationOutcome rows | Skip if SPY price missing |
| portfolio_snapshot | Current positions + prices | PortfolioSnapshot row | Already exists |
| alert_generation | All outputs from above | InAppAlert rows | Best-effort, never blocks pipeline |

### 3.3 Biweekly Retrain (separate schedule)

Runs every other Sunday at 2:00 AM ET:

```
model_retrain_all → forecast_refresh
```

- Train Prophet for all tickers + ETFs
- Save artifacts to `data/models/{ticker}_prophet_v{N}.pkl`
- Create new ModelVersion rows (is_active=True)
- Retire previous versions
- Run forecast_refresh with new models
- **Scale note:** At ~5s per ticker, 60 tickers = ~5 min (sequential). If watchlist grows >100, use Celery `group()` to parallelize training across workers. Current design is sequential (simpler, sufficient for <100 tickers).

### 3.4 Drift-Triggered Retrain

Checked during nightly forecast_evaluation:

- **Model drift:** Rolling MAPE (last 10 evaluated forecasts) > 20% → queue retrain for that ticker
- **Volatility spike:** Ticker's 5-day realized volatility > 2× its 90-day average → queue retrain
- **VIX regime:** If VIX (^VIX via yfinance) > 30 → mark all forecasts as "high uncertainty regime" (no retrain, just a confidence flag)

Drift retrain runs immediately as a separate Celery task, doesn't wait for biweekly cycle.

### 3.5 Gap Recovery

On pipeline startup, before running the normal chain:

1. Read `PipelineWatermark` for `price_refresh`
2. Compare `last_completed_date` against last trading day
3. If gap detected:
   a. Set status = "backfilling"
   b. For each missing trading day (chronological order):
      - Fetch prices for that date
      - Compute signals for that date
      - Update watermark atomically
   c. Set status = "ok"
4. Run normal pipeline

Key: prices and signals backfill in chronological order because RSI/SMA need a continuous window. Forecasts and recommendations only run after full catch-up.

### 3.6 Self-Healing Rules

| Failure | Detection | Recovery |
|---------|-----------|----------|
| yfinance rate limit (429) | HTTP status or empty response | Exponential backoff, max 3 retries per ticker. Skip on failure |
| yfinance empty DataFrame | Empty/None check | Log warning, skip ticker, retry next cycle |
| DB connection lost | SQLAlchemy error | Celery auto-retry (30s delay, max 2). Per-ticker commits preserve progress |
| Prophet training failure | Exception in model.fit() | Catch, skip that ticker. Other tickers unaffected |
| Pipeline crash mid-run | PipelineRun.status "running" for >1 hour | Next run detects stale status, marks "failed", resumes from watermark |

**Principle:** Per-ticker atomicity. Each ticker is its own unit of work. Pipeline marked `partial` if most tickers succeed.

### 3.7 Pipeline Observability

Every pipeline execution creates a `PipelineRun` row. In-app alert generated for notable events:

| Condition | Alert |
|-----------|-------|
| New BUY recommendation | "AAPL triggered BUY signal (score 8.2)" |
| Signal flipped | "MSFT signal changed: BUY → SELL" |
| Model drift detected | "GOOG forecast model degraded (MAPE 22%) — retraining" |
| Gap backfilled | "Data gap recovered: Mar 18-22 (4 trading days)" |
| Partial pipeline failure | "Nightly refresh: 58/61 tickers updated. 3 failed — retrying tonight" |
| Accuracy milestone | "Your recommendation hit rate: 78% over last 30 days" |

---

## 4. Prophet Forecasting Engine

### 4.1 Training

For each ticker in (watchlist ∪ portfolio ∪ 11 ETFs ∪ SPY):

1. Fetch 2 years of daily adj_close from StockPrice
2. Format as Prophet DataFrame: `ds` (date), `y` (price)
3. Configure and fit Prophet model
4. Serialize to `data/models/{ticker}_prophet_v{N}.pkl`
5. Create ModelVersion row
6. Predict at 3 horizons: today+90d, today+180d, today+270d
7. Store ForecastResult rows

### 4.2 Prophet Configuration

| Parameter | Value | Reasoning |
|-----------|-------|-----------|
| changepoint_prior_scale | 0.05 | Conservative, avoids overfitting |
| seasonality_prior_scale | 10 | Default, let seasonality express |
| yearly_seasonality | True | Calendar effects in equities |
| weekly_seasonality | True | Mon/Fri patterns |
| daily_seasonality | False | Daily data only |
| interval_width | 0.80 | 80% confidence band |
| mcmc_samples | 0 | MAP estimation (fast) |

### 4.3 Forecast Horizons

| Horizon | Use case |
|---------|----------|
| 90 days | Short-term, actionable for swing decisions |
| 180 days | Medium-term, position sizing |
| 270 days | Long-term, allocation strategy |

### 4.4 Sharpe Direction Enrichment

Each forecast is enriched with a Sharpe ratio direction flag:

- Compare current `sharpe_ratio` from latest SignalSnapshot against the value from 30 days ago
- Three states: **improving** (↑), **flat** (→), **declining** (↓)
- If no snapshot exists 30 days ago (e.g., newly ingested ticker), default to **flat**

Combined interpretation:

| Sharpe Trend | Price Direction | Signal |
|-------------|----------------|--------|
| Improving ↑ | Up ↑ | Strong conviction |
| Flat → | Up ↑ | Moderate conviction |
| Declining ↓ | Up ↑ | Caution — volatility increasing |
| Declining ↓ | Down ↓ | Strong avoid |

### 4.5 Portfolio Forecast Derivation

Not a separate model — derived from stock-level forecasts:

**Expected return:**
```
portfolio_return = Σ (weight_i × stock_return_i)
where weight_i = market_value_i / total_portfolio_value
```

**Confidence band (correlation-aware):**
```
portfolio_variance = Σ Σ (w_i × w_j × σ_i × σ_j × ρ_ij)
where σ_i = model MAPE / 100 (forecast uncertainty proxy)
      ρ_ij = cross-sector correlation (see note below)
```

**Output:**
- Expected return % at each horizon
- Lower/upper confidence band (80% CI using ±1.28σ)
- Diversification ratio (portfolio σ vs weighted average σ)
- Confidence level (High / Moderate / Low from avg MAPE)

**Cross-sector correlation note:** The existing `/sectors/{sector}/correlation` endpoint only computes within-sector correlations. Portfolio forecast needs cross-sector correlations (e.g., AAPL in Tech vs. JPM in Financials). A new utility function `compute_portfolio_correlation_matrix(tickers, period_days)` will compute the full n×n correlation matrix across all portfolio tickers regardless of sector, using the same daily-returns approach as the sectors endpoint.

### 4.6 Sector Forecast

Sector forecasts use the SPDR ETF models. The agent maps user holdings to sectors:

"XLK (tech sector) forecast is +6% over 90d. Your tech exposure (AAPL, GOOG) represents 45% of your portfolio."

### 4.7 Confidence Levels

| Avg MAPE | Level | UI |
|----------|-------|-----|
| < 10% | High | Green badge |
| 10-20% | Moderate | Yellow badge + "predictions may vary" |
| > 20% | Low | Red badge + "use with caution" |
| VIX > 30 | Reduced (any MAPE) | Amber overlay: "Elevated market volatility" |

### 4.8 Model Artifact Storage

```
data/models/
  AAPL_prophet_v1.pkl
  AAPL_prophet_v2.pkl    ← active
  XLK_prophet_v1.pkl     ← active
```

Old artifacts kept 90 days, then pruned by a cleanup task.

---

## 5. Recommendation Evaluation

### 5.1 What Gets Evaluated

Only **BUY** and **SELL** recommendations — these are directional claims. WATCH/HOLD are non-committal.

### 5.2 Evaluation Process

Nightly job checks: for each RecommendationSnapshot where `generated_at + horizon ≤ today` AND no RecommendationOutcome exists at that horizon:

1. Look up actual stock price at `generated_at + horizon_days`
2. Look up SPY price at same dates
3. Compute return_pct, spy_return_pct, alpha_pct
4. Determine action_was_correct (BUY: return > 0, SELL: return < 0)
5. Store RecommendationOutcome row

### 5.3 Scorecard Metrics

| Metric | Computation |
|--------|------------|
| Hit rate | % of correct calls per action type |
| Average alpha | Mean alpha_pct across all evaluated calls |
| Worst miss | Largest negative return on a BUY call |
| SELL accuracy | % of SELL calls where stock declined |
| By horizon | All metrics broken down by 30d/90d/180d |

---

## 6. Agent Integration

### 6.1 New Tools (6)

| Tool | Purpose |
|------|---------|
| GetForecastTool | Latest forecast for a ticker at all horizons + confidence + Sharpe direction |
| GetSectorForecastTool | Sector ETF forecast + user's sector exposure |
| GetPortfolioForecastTool | Derived portfolio forecast with correlation-based confidence bands |
| CompareStocksTool | Side-by-side signals, forecasts, Sharpe, fundamentals for 2+ tickers |
| GetRecommendationScorecard | Hit rate, alpha, history from RecommendationOutcome |
| DividendSustainabilityTool | Payout ratio, FCF coverage, dividend growth history. Data source: yfinance `info` dict fields (`payoutRatio`, `freeCashflow`, `dividendRate`, `dividendYield`). Fetched on-demand at query time (not stored), same pattern as existing `fetch_fundamentals()`. |

### 6.2 Enhanced Tools (1)

RiskNarrativeTool — enriched with forecast data and sector ETF context.

### 6.3 Session Entity Registry

In-memory dict on LangGraph state (not persisted to DB):

```python
class EntityRegistry:
    discussed_tickers: dict[str, EntityInfo]
    # Auto-populated when tools return ticker data
    # Enables pronoun resolution: "them" → last 2+ tickers, "it" → last 1
```

### 6.4 Context-Aware Planner

Planner prompt extended with `recently_discussed_tickers` from entity registry. Enables the planner to reference previous tickers without the user repeating them.

### 6.5 Few-Shot Prompts

Each new tool gets 2-3 few-shot examples in the planner, following the existing pattern (13 few-shots currently). Examples cover:
- Simple query: "forecast for AAPL"
- Comparative: "compare AAPL and MSFT forecasts"
- Portfolio-level: "how does my portfolio look over 90 days?"
- Scorecard: "how accurate have your recommendations been?"

---

## 7. API Endpoints

### 7.1 New Endpoints (6)

| Method | Path | Response | Notes |
|--------|------|----------|-------|
| GET | /api/v1/forecasts/{ticker} | ForecastResponse (3 horizons + confidence + Sharpe direction) | |
| GET | /api/v1/forecasts/portfolio | PortfolioForecastResponse (expected return, confidence band, diversification) | Derived computation |
| GET | /api/v1/forecasts/sector/{sector} | SectorForecastResponse (ETF forecast + user exposure) | Maps sector to ETF |
| GET | /api/v1/recommendations/scorecard | ScorecardResponse (hit rate, alpha, history) | Aggregates RecommendationOutcome |
| GET | /api/v1/alerts | AlertListResponse (paginated, unread first) | |
| PATCH | /api/v1/alerts/read | BatchReadResponse | Body: { alert_ids: [...] } |

### 7.2 Response Schemas

Detailed Pydantic schemas to be defined during planning phase, following existing patterns in `backend/schemas/`.

---

## 8. Frontend

### 8.1 Stock Detail — Forecast Card

Below existing signal cards on stock detail page:
- 3 horizon pills (90d/180d/270d) with predicted price + % change
- Confidence badge (High/Moderate/Low)
- Sharpe direction indicator
- Prophet trend line overlaid on price chart (dashed, with shaded confidence band)

### 8.2 Dashboard — New Tiles

Two additions to KPI StatTile row:
- **Portfolio Outlook:** "90d: +4.2% ($2,100)" with confidence range. Click → portfolio forecast modal.
- **Recommendation Accuracy:** "78% hit rate, +3.2% alpha". Click → scorecard modal.

### 8.3 Recommendation Scorecard Modal

shadcn Dialog with backdrop blur, triggered from accuracy tile:
- Summary row: overall hit rate, avg alpha, total evaluated
- Per-action breakdown (BUY vs SELL)
- Horizon comparison (30d/90d/180d)
- Recent calls table with outcomes
- Worst misses (transparency)

### 8.4 Alert Bell Dropdown

Topbar bell icon (currently stub) becomes functional:
- Badge count for unread alerts
- Popover/Sheet dropdown on click
- Alert rows: icon + text + timestamp + read/unread
- "Mark all read" button
- Sourced from InAppAlert table

### 8.5 Sectors Page — ETF Forecast

In sector accordion expanded view, below correlation:
- Sector ETF forecast: "XLK 90d: +6.2% (confidence: high)"

---

## 9. Testing Strategy

| Layer | Scope | Estimated |
|-------|-------|-----------|
| Unit | Prophet helpers, portfolio derivation, drift detection, gap detection, Sharpe direction, entity registry, alert rules | ~40 |
| API | 6 endpoints × (auth + happy + edge cases) | ~25 |
| Integration | Full pipeline chain with testcontainers | ~5 |
| Frontend | Forecast card, scorecard modal, alert dropdown, outlook tile | ~10 |
| **Total** | | **~80 tests** |

---

## 10. Scope & Phasing

### Phase 5 (this spec)

- DB models: ModelVersion, ForecastResult, RecommendationOutcome, PipelineWatermark, PipelineRun, InAppAlert, Stock.is_etf
- Celery tasks: full nightly pipeline chain, biweekly retrain, drift-triggered retrain, gap recovery
- Agent: 6 new tools + 1 enhanced + entity registry + planner update + few-shots
- API: 6 new endpoints
- Frontend: forecast card, dashboard tiles, scorecard modal, alert bell, sector ETF forecast
- Seed data: 11 SPDR ETFs + SPY

### Deferred to Phase 5.1

- Red flag scanner (needs new data sources)
- Telegram notifications (external integration)
- Forecast blending into composite score (validate accuracy first)
- Live LLM eval tests (needs CI secrets)

---

## 11. Dependencies & Prerequisites

- `prophet` package (via `uv add prophet`)
- SPY + 11 SPDR ETFs seeded with historical price data (2+ years)
- VIX data available via yfinance (`^VIX`)
- `data/models/` directory for serialized Prophet artifacts
- Existing Celery + Redis infrastructure (already operational)
