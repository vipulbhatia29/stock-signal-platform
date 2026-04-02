# Forecast Intelligence System — Specification

**Epic:** Phase 8.6+ — Forecast Intelligence
**Date:** 2026-04-02
**Status:** Reviewed — per-section expert review + 4-persona staff review + 5-persona comprehensive review (Full-Stack, Middleware, QA, Domain, Architect)
**Author:** Claude (Opus 4.6) + PM (Vipul)

---

## 1. Problem Statement

The stock-signal-platform has a working Prophet forecast pipeline (Phase 5) with 500+ tickers, 3 horizons (90d/180d/270d), nightly evaluation, and drift detection. However:

1. **No backtest validation** — we show forecasts but can't prove accuracy. Rolling MAPE exists but isn't calibrated per-ticker.
2. **Flat drift threshold** — 20% MAPE for all stocks. TSLA at 15% might be great; JNJ at 15% might be terrible.
3. **Seasonality may hurt** — Prophet's yearly/weekly seasonality could overfit on stocks where no real seasonal pattern exists.
4. **No news signal** — market-moving news (earnings, Fed decisions, macro events) isn't captured in any indicator.
5. **Disconnected forecast levels** — stock, sector, and portfolio forecasts are computed independently with no coherent methodology.
6. **No signal convergence** — users see individual indicators but no "do these all agree?" summary.
7. **No pipeline control** — admin can't trigger pipelines manually; seed data requires CLI; no operational dashboard.
8. **No rationale** — numbers on screen without explanation. The product's differentiator is transparency.

## 2. Goals

1. **Validate forecast accuracy** via walk-forward backtesting — determine which tickers/horizons to trust
2. **Calibrate drift detection** with per-ticker baselines instead of flat 20% threshold
3. **Determine optimal seasonality config** per ticker via A/B backtesting
4. **Ingest financial news** from multiple sources and score sentiment via LLM
5. **Feed sentiment as Prophet regressors** — transparent via component decomposition
6. **Build three-level forecast system** — Stock (Prophet) → Sector (aggregation) → Portfolio (Black-Litterman + Monte Carlo + CVaR)
7. **Signal convergence UX** — traffic lights + divergence alerts + rationale narrative
8. **Admin pipeline orchestrator** — manual triggers, seed hydration, task groups with dependency resolution
9. **Event-driven cache invalidation** — single CacheInvalidator service, trigger-agnostic

## 3. Decisions Made

| Question | Decision | Rationale |
|----------|----------|-----------|
| User persona | Medium-to-low risk part-time investors who trust signal convergence, not individual predictions | Shapes all UX: convergence > price prediction |
| UX model | Traffic lights (primary) + divergence alerts (contextual) + rationale (always present) | Quick scan → interesting insights → transparency |
| News sources | Finnhub (primary, free) + EDGAR 8-K + Fed RSS + FRED (authoritative, free) + Google News (fallback) | Best coverage-to-cost ratio. Polygon.io at $29/month when needed |
| News → forecast | LLM scores → 3 regressors (stock, sector, macro) → Prophet `add_regressor()` | Transparent via Prophet component decomposition |
| Sentiment LLM | GPT-4o-mini (structured JSON output, ~$5-22/month) with Groq fallback | Cheapest adequate model for high-volume batch scoring |
| Horizons | Generate all (90d/180d/270d), display only what backtesting validates | Data-driven — don't assume which horizons work |
| Seasonality | Per-ticker optimization via backtesting (4 configs, winner stored in ModelVersion) | Some stocks have real seasonality (retail, energy); most don't |
| Seasonality calibration | Weekly + on-demand. One-time calibration run, cached until next run | 4 configs x 500 tickers is expensive; don't run nightly |
| Portfolio forecast | Black-Litterman (Prophet views + market equilibrium + backtest confidence) | Industry standard. Already have PyPortfolioOpt with BL implementation |
| Portfolio risk | Monte Carlo bands (p5/p25/median/p75/p95) + CVaR at 95% and 99% | Monte Carlo computed on-demand, cached 1hr. Never stored |
| Sector forecast | Weighted aggregation of stock-level forecasts (equal-weight default) | Derives from stock level — no independent sector model |
| Drift detection | Per-ticker calibrated baseline (backtest MAPE x 1.5). Validate-before-promote. 3 consecutive failures → experimental status (self-healing) | Trust through accuracy, honest about uncertainty |
| Walk-forward method | Expanding window, non-overlapping test periods | Prevents look-ahead bias from overlapping test windows |
| Pipeline dashboard | Admin page with task groups, dependency resolution, generic task runner | Celery tasks triggered from UI. One pattern for all tasks |
| Cache invalidation | Event-driven CacheInvalidator service, trigger-agnostic | Same invalidation whether nightly, admin, or user-initiated |
| Storage strategy | Store inputs + summary outputs. Never store intermediate computations (Monte Carlo paths, BL internals) | ~55 MB/year compressed. TimescaleDB handles it |
| Signal history | `signal_convergence_daily` hypertable for historical pattern analysis | Powers "this divergence happened 23 times — forecast was right 61%" |
| Macro sentiment | Stored once as `ticker='__MACRO__'`, not duplicated per-ticker | Saves 499 duplicate writes per day |
| Rationale generation | Template-based for common patterns, LLM only for complex multi-signal divergences | Deterministic + cheap for 90%+ of cases |
| Spec decomposition | 4 specs: A (backtesting), B (news), C (convergence UX), D (admin pipeline) | A+B independent, D independent, C depends on A+B |
| Ship order | A → D → B → C | Admin value early, user value builds toward C |
| Scaling | TimescaleDB for now, DuckDB/Iceberg flagged for future if analytics bottleneck | Current volumes trivial (~55 MB/year) |

## 4. Architecture

### 4.1 Three-Level Forecast System

```
Stock Level (per-ticker)
├─ Prophet model with calibrated seasonality
├─ News sentiment regressors (stock, sector, macro)
├─ Component decomposition: trend + stock_news + sector_news + macro
├─ Backtest-validated accuracy badge
├─ Model versioning with validate-before-promote

Sector Level (derived from stock level)
├─ Equal-weight aggregation of stock-level forecasts
├─ Sector-level news sentiment overlay
├─ Not an independent model — derives from constituents

Portfolio Level (per-user, Black-Litterman)
├─ Market equilibrium returns (CAPM from historical prices)
├─ Prophet views as BL inputs (excess returns = predicted - risk_free)
├─ View confidence = inverse of backtest MAPE per ticker
├─ Monte Carlo simulation bands (p5/p25/median/p75/p95)
├─ CVaR at 95% and 99% ("worst 5%" and "worst 1%" scenarios)
├─ Covariance: Ledoit-Wolf shrinkage estimator
```

### 4.2 Signal Convergence

Six signals per stock, each classified as bullish/bearish/neutral:

| Signal | Bullish | Bearish | Neutral |
|--------|---------|---------|---------|
| RSI | < 40 (oversold recovery) | > 70 (overbought) | 40-70 |
| MACD | Histogram > 0 and rising | Histogram < 0 and falling | Near zero or flat |
| SMA | Price > SMA-200 | Price < SMA-200 | Within 2% |
| Piotroski | F-Score >= 6 | F-Score <= 3 | 4-5 |
| Forecast | Predicted return > +3% | Predicted return < -3% | -3% to +3% |
| News | Sentiment > +0.3 | Sentiment < -0.3 | -0.3 to +0.3 |

**Convergence labels (revised per domain review — neutral signals are common):**
- **Strong Bull:** 4+ bullish, 0 bearish
- **Weak Bull:** 3+ bullish, <=1 bearish
- **Mixed:** everything else (divergence alert triggers)
- **Weak Bear:** 3+ bearish, <=1 bullish
- **Strong Bear:** 4+ bearish, 0 bullish

**Divergence alert triggers** when forecast direction disagrees with technical majority (or vice versa). Historical hit rate queried from `signal_convergence_daily`.

### 4.3 News Sentiment Pipeline

```
Every 4 hours (Celery Beat):
  Finnhub: sweep tracked tickers (rate-limited 55/min, ~9 min for 500)
  EDGAR: check 8-K filings since last run (item number pre-classification)
  Fed RSS: parse latest Federal Reserve press releases
  FRED: check for new economic data releases
  Google News: fallback for tickers with insufficient Finnhub coverage
      ↓
  Dedup via SHA256(headline + source + date)
  Store to news_articles (metadata only, no full article text)
      ↓
  Batch LLM scoring (GPT-4o-mini, 10-20 articles per prompt)
  temperature: 0, response_format: json
  Output per article: stock_sentiment, sector_sentiment, macro_sentiment,
                      event_type, confidence, rationale
  Cache scored articles by dedupe_hash (never re-score)
      ↓
  Aggregate to news_sentiment_daily:
    - Weighted average: event_significance x confidence x exp(-0.3 x days_old)
    - Significance tiers: HIGH (3.0): earnings, fda, m_and_a, fed_rate, management
                          MEDIUM (1.5): guidance, regulatory, cpi, employment
                          LOW (1.0): product, sector_trend, legal, other
    - Half-life: ~2.3 days (news older than 7 days = negligible weight)
    - Macro sentiment stored as ticker='__MACRO__' (one row, not per-ticker)
      ↓
  CacheInvalidator.on_sentiment_scored(affected_tickers)
```

### 4.4 Walk-Forward Backtesting

```
Expanding window (no look-ahead bias):
  Window 1: train [D0, D365],      predict D365+horizon
  Window 2: train [D0, D395],      predict D395+horizon (30d step)
  Window 3: train [D0, D425],      predict D425+horizon
  ...
  Minimum: 2 years test data spanning at least one market correction.

  Training set GROWS with each window.
  Test point is always one step ahead.
  No overlap between any test period and any training data.

Metrics per run:
  - MAPE (mean absolute percentage error)
  - MAE (mean absolute error)
  - RMSE (root mean squared error)
  - Direction accuracy (% correct up/down)
  - CI containment (% of actuals within predicted 80% interval)
  - CI bias (actuals systematically above/below/balanced)
  - Average interval width

Market regime tracked per backtest (bull/bear/sideways from SPY trend).

Seasonality calibration:
  4 configs x 3 horizons per ticker
  Winner stored in ModelVersion.hyperparameters
  Run weekly + on-demand
```

### 4.5 Drift Detection Upgrade

```
OLD: MAPE > 0.20 → retrain (flat threshold, all stocks)

NEW:
  1. Per-ticker threshold = backtest_baseline_mape x 1.5
     Fallback to 0.20 if no backtest exists

  2. Retrain-and-validate:
     - Train new model
     - Run walk-forward backtest on new model
     - Compare new MAPE vs old model's baseline
     - Promote only if new < old (is_active swap)
     - If worse: discard new, keep old, increment retrain_failures

  3. Experimental demotion:
     - retrain_failures >= 3 → status = "experimental"
     - UI shows grey traffic light + disclaimer
     - Forecast excluded from convergence alignment count

  4. Self-healing:
     - Successful retrain (new < baseline) → reset failures, promote to active
     - Experimental status is not permanent
```

### 4.6 Cache Strategy

| Data | Cache Key | TTL | Invalidation Event |
|------|-----------|-----|-------------------|
| Convergence traffic lights | `app:convergence:{ticker}` | 1hr | `on_signals_updated`, `on_forecast_updated` |
| Convergence rationale | `app:convergence:rationale:{ticker}` | 4hr | `on_signals_updated` (template rationale auto-expires) |
| Backtest results | `app:backtest:{ticker}` | 24hr | `on_backtest_completed` |
| News sentiment | `app:sentiment:{ticker}` | 4hr | `on_sentiment_scored` |
| BL portfolio forecast | `app:bl-forecast:{user_id}` | 1hr | `on_portfolio_changed`, `on_forecast_updated` |
| Monte Carlo bands | `app:monte-carlo:{user_id}` | 1hr | `on_portfolio_changed` |
| CVaR risk | `app:cvar:{user_id}` | 1hr | `on_portfolio_changed` |
| Sector forecast | `app:sector-forecast:{sector}` | 1hr | `on_forecast_updated` (any constituent) |

**CacheInvalidator** is a service class injected at every data-write site. One class, one pattern, every trigger path (nightly, admin, user, agent) uses it. Registered as FastAPI dependency for request lifecycle; imported directly in Celery tasks.

### 4.7 Event-Driven Cache Invalidation

```python
class CacheInvalidator:
    async def on_prices_updated(self, tickers: list[str]):
        # Clear convergence, forecast for affected tickers
        # Clear sector caches for affected sectors
        # Clear BL/MC/CVaR for users holding these tickers

    async def on_signals_updated(self, tickers: list[str]):
        # Clear convergence + rationale for affected tickers

    async def on_stock_ingested(self, ticker: str):
        # New stock: nothing to invalidate. Warm cache proactively.

    async def on_forecast_updated(self, tickers: list[str]):
        # Clear forecast, convergence, sector, BL caches

    async def on_backtest_completed(self, tickers: list[str]):
        # Clear backtest caches

    async def on_sentiment_scored(self, tickers: list[str]):
        # Clear sentiment + convergence caches

    async def on_portfolio_changed(self, user_id: str):
        # Clear BL, Monte Carlo, CVaR for this user
```

## 5. Data Model

### 5.1 New Tables

```sql
-- Migration 024

-- Backtest results (regular table, not hypertable)
CREATE TABLE backtest_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker VARCHAR(10) NOT NULL REFERENCES stocks(ticker),
    model_version_id UUID NOT NULL REFERENCES model_versions(id),
    config_label VARCHAR(30) NOT NULL,  -- "baseline", "no_yearly", etc.
    train_start DATE NOT NULL,
    train_end DATE NOT NULL,
    test_start DATE NOT NULL,
    test_end DATE NOT NULL,
    horizon_days INTEGER NOT NULL,
    num_windows INTEGER NOT NULL,
    mape FLOAT NOT NULL,
    mae FLOAT NOT NULL,
    rmse FLOAT NOT NULL,
    direction_accuracy FLOAT NOT NULL,
    ci_containment FLOAT NOT NULL,
    market_regime VARCHAR(20),  -- bull/bear/sideways
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB  -- per_window_results, ci_bias, avg_interval_width, residuals
);
CREATE INDEX ix_backtest_runs_ticker_horizon ON backtest_runs(ticker, horizon_days, created_at DESC);

-- Signal convergence daily (TimescaleDB hypertable)
CREATE TABLE signal_convergence_daily (
    date DATE NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    rsi_direction VARCHAR(10) NOT NULL,
    macd_direction VARCHAR(10) NOT NULL,
    sma_direction VARCHAR(10) NOT NULL,
    piotroski_direction VARCHAR(10) NOT NULL,
    forecast_direction VARCHAR(10) NOT NULL,
    news_sentiment FLOAT,  -- nullable until Spec B ships
    signals_aligned INTEGER NOT NULL,
    convergence_label VARCHAR(20) NOT NULL,
    composite_score FLOAT,
    actual_return_90d FLOAT,   -- filled 90 days later
    actual_return_180d FLOAT,  -- filled 180 days later
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (date, ticker)
);
SELECT create_hypertable('signal_convergence_daily', 'date');
CREATE INDEX ix_convergence_label ON signal_convergence_daily(convergence_label, forecast_direction);

-- News articles (TimescaleDB hypertable)
CREATE TABLE news_articles (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    published_at TIMESTAMPTZ NOT NULL,
    ticker VARCHAR(10),  -- null for macro/general news
    headline TEXT NOT NULL,
    summary TEXT,
    source VARCHAR(30) NOT NULL,
    source_url VARCHAR(500),
    event_type VARCHAR(30),
    dedupe_hash VARCHAR(64) NOT NULL UNIQUE,
    scored_at TIMESTAMPTZ,  -- null until LLM scores it
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (published_at, id)
);
SELECT create_hypertable('news_articles', 'published_at');
CREATE INDEX ix_news_ticker ON news_articles(ticker, published_at DESC);
-- TimescaleDB compression after 7 days, retention 1 year

-- News sentiment daily (TimescaleDB hypertable)
CREATE TABLE news_sentiment_daily (
    date DATE NOT NULL,
    ticker VARCHAR(10) NOT NULL,  -- '__MACRO__' for macro-level
    stock_sentiment FLOAT NOT NULL DEFAULT 0.0,
    sector_sentiment FLOAT NOT NULL DEFAULT 0.0,
    macro_sentiment FLOAT NOT NULL DEFAULT 0.0,
    article_count INTEGER NOT NULL DEFAULT 0,
    confidence FLOAT NOT NULL DEFAULT 0.0,
    dominant_event_type VARCHAR(30),
    rationale_summary TEXT,
    quality_flag VARCHAR(10) NOT NULL DEFAULT 'ok',  -- 'ok', 'suspect', 'invalidated'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (date, ticker)
);
SELECT create_hypertable('news_sentiment_daily', 'date');
-- TimescaleDB compression after 30 days, retention 2 years

-- Admin audit log (regular table)
CREATE TABLE admin_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    action VARCHAR(50) NOT NULL,
    target VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB
);
CREATE INDEX ix_audit_user ON admin_audit_log(user_id, created_at DESC);
```

### 5.2 Modified Tables

**model_versions.hyperparameters (JSONB) — extended fields:**
```json
{
  "changepoint_prior_scale": 0.05,
  "seasonality_prior_scale": 10,
  "yearly_seasonality": false,
  "weekly_seasonality": false,
  "daily_seasonality": false,
  "interval_width": 0.80,
  "mcmc_samples": 0,
  "regressors": ["stock_sentiment", "sector_sentiment", "macro_sentiment"],
  "config_version": "v2",
  "calibration_run_id": "uuid",
  "parent_model_id": "uuid"
}
```

**model_versions.metrics (JSONB) — extended fields:**
```json
{
  "rolling_mape": 0.08,
  "backtest_mape_90d": 0.07,
  "backtest_mape_180d": 0.12,
  "backtest_mape_270d": 0.18,
  "direction_accuracy_90d": 0.64,
  "ci_containment": 0.78,
  "calibration_date": "2026-04-10",
  "retrain_failures": 0
}
```

No schema migration needed — JSONB is schema-free. These are convention extensions.

### 5.3 Storage Sizing (1 year)

| Table | Raw Rows/Year | Compressed Size |
|-------|--------------|-----------------|
| backtest_runs | ~5K (10 per ticker, updated in-place) | < 1 MB |
| signal_convergence_daily | ~182K (500 tickers x 365 days) | ~3 MB |
| news_articles | ~912K (500 tickers x 5 articles/day) | ~50 MB |
| news_sentiment_daily | ~183K (500 tickers + 1 macro x 365) | ~2 MB |
| admin_audit_log | ~1K (admin actions) | < 1 MB |
| **Total new storage** | | **~55 MB/year** |

## 6. API Endpoints

### 6.1 Backtesting (Spec A)

```
GET  /api/v1/backtests/{ticker}              → latest backtest summary per horizon
GET  /api/v1/backtests/summary               → all tickers sorted by accuracy
POST /api/v1/backtests/run                   → trigger backtest (admin only)
POST /api/v1/backtests/calibrate             → trigger seasonality calibration (admin only)
GET  /api/v1/backtests/{ticker}/history      → last 10 runs
```

### 6.2 Sentiment (Spec B)

```
GET  /api/v1/sentiment/{ticker}              → latest daily sentiment + 7d/30d trend
GET  /api/v1/sentiment/bulk?tickers=...      → batch sentiment for multiple tickers
GET  /api/v1/sentiment/macro                 → latest macro sentiment
GET  /api/v1/sentiment/{ticker}/articles     → recent articles with scores (paginated)
```

### 6.3 Convergence (Spec C)

```
GET  /api/v1/convergence/{ticker}            → traffic lights + rationale
GET  /api/v1/convergence/portfolio/{id}      → portfolio convergence summary
GET  /api/v1/convergence/{ticker}/history    → convergence over time
GET  /api/v1/portfolio/{id}/forecast         → BL returns + Monte Carlo + CVaR
GET  /api/v1/portfolio/{id}/forecast/components → per-position contribution
GET  /api/v1/sectors/{sector}/convergence    → sector convergence summary
```

### 6.4 Admin Pipeline (Spec D)

```
GET  /api/v1/admin/pipelines                 → all groups with task definitions
GET  /api/v1/admin/pipelines/{group}         → single group detail
POST /api/v1/admin/pipelines/{group}/run     → trigger entire group
POST /api/v1/admin/pipelines/tasks/{name}/run → trigger single task
GET  /api/v1/admin/pipelines/runs/{run_id}   → poll group run status + progress
GET  /api/v1/admin/pipelines/history         → last 50 runs across all groups
POST /api/v1/admin/cache/clear               → clear all caches (with audit log)
POST /api/v1/admin/cache/clear/{pattern}     → targeted clear (whitelisted patterns only)
```

**Cache clear whitelist:** `convergence:*`, `forecast:*`, `sentiment:*`, `bl-forecast:*`, `monte-carlo:*`, `cvar:*`, `sector-forecast:*`. All others rejected. Uses `SCAN` not `KEYS`.

## 7. Celery Tasks

### 7.1 New Tasks

| Task | Group | Schedule | Dependencies |
|------|-------|----------|-------------|
| `news_ingest_task` | news_sentiment | Every 4h (6,10,14,18 ET) | None |
| `news_sentiment_scoring_task` | news_sentiment | After ingest (7,11,15,19 ET) | news_ingest |
| `compute_convergence_snapshot_task` | nightly | After evaluate_forecasts | evaluate_forecasts. Also backfills `actual_return_90d/180d` for rows from 90/180 days ago |
| `run_backtest_task` | model_training | Weekly + on-demand | None |
| `calibrate_seasonality_task` | model_training | Weekly + on-demand | model_retrain |
| `seed_admin_user_task` | seed | On-demand | None |

### 7.2 Modified Nightly Chain

```
Phase 0: Cache Invalidation (unchanged)
Phase 1: Price Refresh (unchanged)
Phase 2: Forecast Refresh + Recommendations + Evaluate Forecasts +
         Evaluate Recommendations + Portfolio Snapshots (unchanged — 5 parallel)
Phase 3: Drift Detection + Convergence Snapshot (NEW — 2 parallel)
Phase 4: Alerts + Health + Rebalancing (unchanged — 3 parallel)
```

### 7.3 Existing Seed Scripts → Celery Tasks

All seed scripts expose `async def seed_X_async(**kwargs) -> dict`. Celery task wraps with `asyncio.run()`. CLI entry point calls the same async function. One implementation, two entry points.

Long-running seeds use `self.update_state(state='PROGRESS', meta={'current': i, 'total': N, 'ticker': t})` for progress reporting.

## 8. Pipeline Registry & Task Groups

### 8.1 Task Groups

| Group | Tasks (in order) | Parallel within group |
|-------|------------------|-----------------------|
| **seed** | admin_user → sp500 → [indexes, etfs] → [prices, dividends, fundamentals] → [forecasts, reason_tier] | Yes, same-order tasks run parallel |
| **nightly** | cache_clear → price_refresh → [forecast, recommendations, evaluate_x3] → [drift, convergence] → [alerts, health, rebalancing] | Yes, per phase |
| **intraday** | refresh_all_watchlist | Single task |
| **warm_data** | [analyst, fred, institutional] | All parallel |
| **maintenance** | purge_logins → purge_accounts | Sequential |
| **model_training** | retrain_all → [backtest, calibrate] | Backtest + calibrate parallel |
| **news_sentiment** | ingest → scoring | Sequential |

### 8.2 Failure Modes

- **stop_on_failure** (default for seed): any task failure stops the chain
- **continue** (for nightly): log failure, continue with available data
- **threshold:N** (for price refresh): continue if >N% succeeded, stop if <N%

### 8.3 Concurrent Run Protection

Before dispatching, check for active run in group (status = STARTED/PROGRESS). If exists, return 409 Conflict with run_id. Frontend disables "Run" button during active run.

## 9. Frontend Integration

### 9.1 Where Convergence Appears

| Page | Addition | Visibility |
|------|----------|-----------|
| **Stock detail** | Traffic light row (6 signals), divergence alert banner (conditional), rationale (expandable), accuracy badge, Prophet component breakdown | Traffic lights always visible. Rest: progressive disclosure |
| **Sector page** | Sector convergence summary (% bullish/bearish/mixed), sector sentiment | Summary card |
| **Portfolio page** | Portfolio convergence card, BL forecast, Monte Carlo bands chart, CVaR (95% + 99%), per-position mini traffic lights | Cards in portfolio layout |
| **Dashboard** | Portfolio zone: convergence indicator + BL return number | Compact indicator, click-through to portfolio |
| **Admin: Pipeline Control** | New page `/admin/pipelines` | Admin only |

### 9.2 Pipeline Control Page (`/admin/pipelines`)

Accordion-style group cards. Each group shows:
- Task list with status dots (not run / success / failed / running)
- "Run All" button (runs group respecting dependencies)
- Per-task "Run" button for individual triggers
- Progress indicator for running tasks ("Step 3/9 — Seeding prices 412/500")
- Parallel tasks shown on same row, sequential on different rows with connecting lines

Run history table at bottom: group, started, duration, status, tasks completed/total.
Cache controls: "Clear All" (confirmation modal) + "Clear by pattern" (dropdown of whitelisted patterns).

### 9.3 Design System Compliance

All new components MUST use existing design tokens. No hardcoded colors.

**Traffic Light Colors (map to existing tokens):**

| State | Color Token | Hex | Existing Usage |
|-------|------------|-----|----------------|
| Bullish | `--gain` | `#22d3a0` | Same as positive price changes |
| Bearish | `--loss` | `#f87171` | Same as negative price changes |
| Neutral | `--warning` | `#fbbf24` | Same as medium confidence |
| Experimental / Unknown | `--subtle` | `#5a7099` | Grey, same as tertiary text |

**Card Pattern (match MetricCard):**
- Background: `bg-card2` (`#0f1d32`)
- Border: `border border-border` (`rgba(255,255,255,0.07)`)
- Padding: `px-4 py-3`
- Labels: `text-[9px] uppercase tracking-wider text-subtle`
- Values: `font-mono text-[16px] font-semibold text-foreground`

**Chart (Monte Carlo bands):**
- Use `useChartColors()` hook for all Recharts colors
- Bands: chart1 (`#38bdf8`) for median, chart2 (`#22d3a0`) for p25/p75, chart3 (`#a78bfa`) for p5/p95
- Band fill: 10-20% opacity of stroke color
- Grid: `strokeDasharray="3 3"`, axis font-size 11px

**Convergence Summary Card:**
- Follow ForecastCard pattern: `rounded-lg border border-border bg-card p-4`
- Accent line at top: `h-px` gradient from `--gain` (if bullish) or `--loss` (if bearish)
- Section heading: `SECTION_HEADING` from typography tokens (`text-sm font-medium uppercase tracking-wider text-muted-foreground`)

**Status Indicators:**
- Reuse `StatusDot` component from command-center (emerald/yellow/red/zinc with pulse)
- Traffic light circles: 32px diameter on desktop, badge collapse on mobile (< 640px)

**Animations:**
- New components use `FadeIn` / `StaggerGroup` / `StaggerItem` from `motion-primitives.tsx`
- Divergence alert banner: `animate-fade-slide-up`
- Traffic lights on load: stagger 0.06s per circle

**Typography:**
- Convergence label: `METRIC_PRIMARY` (`text-2xl font-semibold tabular-nums`)
- Signal names: `LABEL` (`text-xs text-muted-foreground`)
- Rationale text: `text-sm text-foreground` with `leading-relaxed`
- All numbers: `font-mono tabular-nums`

**Responsive:**
- Traffic lights: 6 circles in row on desktop (lg:), collapse to badge on mobile
- Monte Carlo chart: full-width on all breakpoints
- BL forecast + CVaR: side-by-side on lg:, stacked on mobile
- Pipeline groups: single column always (accordion pattern)

### 9.4 No New User-Facing Pages

All forecast intelligence integrates into existing pages. No separate `/forecasts` or `/convergence` route. Users see convergence in context.

Only new page: `/admin/pipelines` (admin only).

## 10. News Provider Architecture

```
backend/services/news/
├─ __init__.py              # exports NewsIngestionService
├─ base.py                  # NewsProvider ABC, RawArticle dataclass
├─ finnhub_provider.py      # Primary, 60 calls/min free
├─ edgar_provider.py        # SEC 8-K, free, item number pre-classification
├─ fed_provider.py          # Fed RSS + FRED API
├─ google_provider.py       # Fallback, RSS feed
├─ ingestion.py             # Orchestrates all providers, dedup, store
└─ sentiment_scorer.py      # GPT-4o-mini batch scoring
```

All providers implement `NewsProvider(ABC)`:
```python
class NewsProvider(ABC):
    @abstractmethod
    async def fetch_stock_news(self, ticker: str, since: date) -> list[RawArticle]: ...
    @abstractmethod
    async def fetch_macro_news(self, since: date) -> list[RawArticle]: ...
    @property
    @abstractmethod
    def source_name(self) -> str: ...
```

### 10.1 LLM Scoring Details

- **Model:** GPT-4o-mini, `temperature: 0`, `response_format: {"type": "json_object"}`
- **Batching:** 10-20 articles per prompt, ~500 LLM calls/day
- **Cost:** ~$5-22/month at current volumes
- **Caching:** Articles cached by `dedupe_hash` — never re-scored
- **Fallback:** If OpenAI down, queue unscored articles. Next run picks up backlog. Prophet fills missing sentiment with 0.0 (neutral).
- **Headline truncation:** 500 chars max (prompt injection mitigation)
- **Output:** Structured JSON per article with stock_sentiment, sector_sentiment, macro_sentiment, event_type, confidence, rationale

### 10.2 Sentiment Aggregation

Weighted average per ticker per day:
```
weight = event_significance × confidence × exp(-0.3 × days_since_publication)

Significance tiers:
  HIGH (3.0): earnings, fda, m_and_a, fed_rate, management
  MEDIUM (1.5): guidance, regulatory, cpi, employment
  LOW (1.0): product, sector_trend, legal, other

Half-life: ~2.3 days. News > 7 days old = negligible weight.
```

## 11. Portfolio Forecast Details

### 11.1 Black-Litterman

- **Market equilibrium:** CAPM returns from historical prices (252 trading days)
- **Covariance:** Ledoit-Wolf shrinkage estimator (via PyPortfolioOpt)
- **Views:** Prophet predicted returns per held ticker, converted to excess returns (subtract risk-free rate from FRED DFF)
- **View confidence:** `min(0.95, max(0.1, 1.0 - backtest_mape))` per ticker
- **Output:** Blended expected returns per position, portfolio expected return

### 11.2 Monte Carlo

- **Drift:** BL expected returns (annualized → daily: ÷ 252)
- **Volatility:** From covariance matrix (annualized → daily: ÷ sqrt(252))
- **Simulations:** 10,000 paths
- **Correlation:** Cholesky decomposition for correlated random walks
- **Output:** Terminal value distribution → percentile bands (p5, p25, median, p75, p95)
- **Seeded randomness in tests:** `np.random.seed(42)`, assert within tolerance

### 11.3 CVaR

- Show both 95% and 99% levels:
  - "In a bad month (1-in-20): -X%"
  - "In a very bad month (1-in-100): -Y%"
- Computed from Monte Carlo terminal value distribution

## 12. Rationale Generation

### 12.1 Template vs LLM Boundary

| Scenario | Method | Example |
|----------|--------|---------|
| All signals agree (any direction) | Template | "5 of 6 signals align bullish. RSI shows oversold recovery (42), MACD crossed positive, fundamentals strong (F-Score 7/9), 90-day forecast predicts +12%, news sentiment neutral." |
| One signal disagrees | Template + hit rate query | "5 signals bullish, but 90-day forecast predicts -4.2%. When forecast disagreed with technicals like this, the forecast was right 61% of the time (23 cases)." |
| 2+ signals disagree in different directions | LLM | Complex multi-signal narrative needed |
| Model is "experimental" status | LLM | Nuanced disclaimer about forecast reliability |

### 12.2 Prophet Component Breakdown

When Prophet has regressors, `model.predict()` returns contribution columns:
```
"Base trend: +8%. Stock news: +3%. Macro headwinds: -4%. Net: +7%"
```
This IS the rationale for the forecast signal. No LLM needed — it's structural.

## 13. Config Additions

```python
# backend/config.py — new fields

# News sources
FINNHUB_API_KEY: str = ""
FRED_API_KEY: str = ""
OPENAI_API_KEY: str = ""
EDGAR_USER_AGENT: str = "StockSignalPlatform admin@example.com"

# Sentiment scoring
NEWS_SCORING_MODEL: str = "gpt-4o-mini"
NEWS_SCORING_FALLBACK: str = "groq"
NEWS_INGEST_LOOKBACK_HOURS: int = 6
NEWS_MIN_ARTICLES_FOR_SCORE: int = 1

# Backtesting
BACKTEST_MIN_TRAIN_DAYS: int = 365
BACKTEST_STEP_DAYS: int = 30
BACKTEST_MIN_WINDOWS: int = 12

# Black-Litterman
BL_RISK_AVERSION: float = 3.07  # S&P 500 historical excess return / variance (retail-appropriate)
BL_MAX_VIEW_CONFIDENCE: float = 0.95

# Monte Carlo
MONTE_CARLO_SIMULATIONS: int = 10000

# Pipeline
PIPELINE_FAILURE_MODE: str = "continue"  # stop_on_failure, continue, threshold:90
```

## 14. Security Considerations

1. **API keys in `.env` only** — FINNHUB_API_KEY, OPENAI_API_KEY, FRED_API_KEY never logged, never in error messages
2. **News URLs display-only** — stored as strings, rendered as frontend links with `rel="noopener noreferrer"`. Backend never re-fetches stored URLs
3. **Cache clear whitelist** — admin can only clear predefined patterns, not arbitrary Redis keys. Uses `SCAN` not `KEYS`
4. **LLM prompt injection** — headlines truncated to 500 chars, structured JSON output prevents injection escape, user content prefixed with `"Article headline: "`
5. **Admin endpoints** — all pipeline/cache endpoints require `UserRole.ADMIN`
6. **Admin audit log** — all admin actions logged (who, what, when)
7. **No `str(e)` in responses** — all error messages use safe generic text (Hard Rule #10)

## 15. Testing Strategy

Following the tiered architecture from the test suite overhaul spec (`docs/superpowers/specs/2026-04-01-test-suite-overhaul.md`):

### T1: Unit Tests

| Component | Test Focus | Tools |
|-----------|-----------|-------|
| BacktestEngine | Walk-forward window logic, metric computation, expanding window correctness | factory-boy (ModelVersion, ForecastResult, StockPrice), freezegun |
| SentimentScorer | Prompt construction, JSON parsing, batch aggregation, weighted average with decay | Mock OpenAI client, known article fixtures |
| CacheInvalidator | Correct keys cleared per event, no over-invalidation | Mock Redis |
| SignalConvergenceService | Direction classification, convergence labels, divergence detection | factory-boy (SignalSnapshot) |
| PortfolioForecastService | BL with known inputs → known outputs (academic examples), excess return calculation | Mock DB, np.random.seed(42) for Monte Carlo |
| PipelineRegistry | Dependency resolution, parallel grouping, failure mode handling | Pure logic, no mocks |
| RationaleGenerator | Template selection boundary, template output correctness | Known convergence inputs |
| NewsProvider implementations | HTTP response parsing, dedup hash computation, rate limiting | httpx mock, JSON fixtures from real API responses |

**Prophet mocking:** Unit tests mock Prophet entirely. Walk-forward window logic, metric computation, and DB storage tested separately from model training.

### T2: API + Integration Tests

| Area | Test Focus |
|------|-----------|
| Backtest endpoints | Auth (admin-only for POST), happy path (GET results), pagination |
| Sentiment endpoints | GET per-ticker, bulk, macro. Auth for all. Empty state handling |
| Convergence endpoints | GET per-ticker, portfolio, sector. Auth. Divergence alert content |
| Portfolio forecast | BL endpoint returns, Monte Carlo bands shape, CVaR values |
| Admin pipeline | Trigger group (admin-only), poll status, concurrent run 409, cache clear whitelist rejection |
| News ingest → score → store | Integration: mock HTTP → real DB → verify sentiment_daily populated |
| CacheInvalidator integration | Write data → verify correct Redis keys cleared |

### T3: E2E (Playwright)

| Page | Test |
|------|------|
| Stock detail | Traffic lights render, divergence alert appears for known divergent stock, rationale expands |
| Portfolio | BL forecast card renders, Monte Carlo chart loads, CVaR values displayed |
| Admin pipelines | Page loads, group cards render, "Run" button triggers (mock Celery), progress updates |

### T4: Nightly Performance

| Test | Threshold |
|------|-----------|
| Convergence endpoint latency | < 200ms (cached), < 500ms (cold) |
| BL forecast computation | < 3s for 50-position portfolio |
| Monte Carlo simulation | < 5s for 10K paths |

**One slow integration test** (marked `@pytest.mark.slow`): trains real Prophet model with 200 data points, runs walk-forward, verifies end-to-end.

## 16. Spec Decomposition

### Spec A: Backtesting Engine + Drift + Seasonality
**Dependencies:** None
**Delivers:** Walk-forward engine, `backtest_runs` table, `signal_convergence_daily` table (basic — no news column), drift detection upgrade, CacheInvalidator service, backtest API + admin trigger, convergence snapshot task (basic — RSI/MACD/SMA/Piotroski/Forecast, no news)

### Spec B: News Sentiment Pipeline
**Dependencies:** None (independent of A)
**Delivers:** `news_articles` + `news_sentiment_daily` tables, NewsProvider implementations (Finnhub, EDGAR, Fed, Google), LLM sentiment scorer, Prophet regressor integration, Celery tasks + beat schedule, sentiment API endpoints

### Spec C: Portfolio Intelligence + Convergence UX
**Dependencies:** Spec A + Spec B
**Delivers:** Black-Litterman + Monte Carlo + CVaR services, convergence service (full — including news signal), rationale generator, convergence API endpoints, all frontend components (traffic lights, divergence alerts, rationale, BL card, Monte Carlo chart, CVaR), stock detail / portfolio / sector / dashboard modifications

### Spec D: Admin Pipeline Orchestrator
**Dependencies:** None (independent)
**Delivers:** PipelineRegistry, all seed scripts as Celery tasks, admin user seed, `admin_audit_log` table, pipeline control page (`/admin/pipelines`), generic task runner API, progress reporting, failure modes, concurrent run protection, cache clear endpoints (whitelisted patterns)

### Ship Order: A → D → B → C

## 17. Migration Plan

Single migration (024) creates all new tables. Specs ship independently but share one migration to avoid ordering conflicts. Migration is safe to apply before any spec's code ships — empty tables don't cause issues.

Alembic head moves from `5c9a05c38ee1` (migration 023) to migration 024.

**Immutability rule:** Migration 024 is immutable once applied to any environment. Post-deployment schema changes require new migrations (025+), not amendments to 024.

## 18. Review Findings Applied

### Per-Section Expert Reviews

| Finding | Section | Fix Applied |
|---------|---------|-------------|
| Look-ahead bias in sliding windows | Sec 1 | Expanding window with non-overlapping test periods |
| CI containment needs bias direction | Sec 1 | `ci_bias` + `avg_interval_width` in metadata JSONB |
| Seasonality calibration needs market correction coverage | Sec 1 | Minimum 2 years test data requirement |
| Experimental status needs recovery path | Sec 1 | Self-healing on successful retrain |
| Missing index on backtest_runs | Sec 1 | `(ticker, horizon_days, created_at DESC)` index |
| LLM scoring non-deterministic and expensive | Sec 2 | Batch 10-20 per prompt, cache by dedupe_hash, temperature: 0 |
| Naive sentiment aggregation | Sec 2 | Weighted by event_significance x confidence x temporal decay |
| Sentiment decay missing | Sec 2 | Exponential decay, half-life ~2.3 days |
| EDGAR 8-K needs structured parsing | Sec 2 | Item number pre-classification in EdgarProvider |
| No fallback if LLM fails | Sec 2 | Queue unscored, backlog processing, Prophet fills with 0.0 |
| Macro sentiment duplicated per-ticker | Sec 2 | `ticker='__MACRO__'` single row |
| BL assumes excess returns | Sec 3 | Subtract risk-free rate (FRED DFF) before BL |
| Monte Carlo drift/vol annualization | Sec 3 | Daily = annual / 252 (drift), annual / sqrt(252) (vol) |
| CVaR too aggressive for risk-averse users | Sec 3 | Show both 95% and 99% levels |
| Convergence hit rate query slow | Sec 3 | Composite index on (convergence_label, forecast_direction) |
| Rationale template vs LLM ambiguity | Sec 3 | Explicit boundary defined (see Section 12.1) |
| Sector convergence mega-cap bias | Sec 3 | Equal-weight for sector, market-cap for portfolio |
| Seed scripts execution context change | Sec 4 | Async function exposed, Celery wraps with asyncio.run() |
| Long-running seeds need progress | Sec 4 | Celery update_state with PROGRESS metadata |
| Group failure handling | Sec 4 | Three failure modes: stop, continue, threshold |
| Concurrent run protection | Sec 4 | 409 Conflict if group already running |
| Cache clear needs audit | Sec 4 | admin_audit_log table |
| Seed idempotency feedback | Sec 4 | Return skipped/partial/complete + record counts |

### Staff-Level Cross-Cutting Reviews

| Reviewer | Finding | Resolution |
|----------|---------|------------|
| Staff Architect | Spec A creates convergence table but service is in Spec C | Spec A includes basic convergence snapshot task (no news column) |
| Staff Architect | Single migration for all tables | Migration 024 creates everything; empty tables are harmless |
| Staff Architect | CacheInvalidator needs singleton/DI | FastAPI dependency for requests, direct import for Celery tasks |
| Staff Security | source_url SSRF risk | Display-only, never re-fetched server-side |
| Staff Security | Cache clear pattern injection | Whitelist of allowed patterns, `SCAN` not `KEYS` |
| Staff Security | LLM prompt injection via headlines | Structured JSON output, headline truncation, content prefix |
| Staff QA | Prophet training too slow for unit tests | Mock Prophet; one `@pytest.mark.slow` integration test |
| Staff QA | Monte Carlo non-deterministic | `np.random.seed(42)`, tolerance assertions |
| Staff QA | News provider fixtures | Record real responses, store as JSON fixtures |
| Staff PM | Nothing user-visible until Spec C | Acceptable — A gives product decisions, D gives operational control |
| Staff PM | Stock detail page getting dense | Progressive disclosure — only traffic lights always visible |
| Staff PM | Ship order recommendation | A → D → B → C (admin value early) |

## 19. Future Considerations

- **DuckDB/Iceberg:** If analytics queries (cross-ticker backtest comparison, portfolio-wide pattern analysis) become slow on TimescaleDB, consider DuckDB for OLAP workloads
- **Polygon.io ($29/month):** Add when Finnhub coverage gaps identified
- **Fama-French factor model:** Useful for explaining portfolio behavior but deferred — adds complexity without immediate user value
- **Per-sector seasonality (Phase 2):** If global A/B shows mixed results, investigate sector-driven patterns
- **Automated post-retrain validation in CI:** Currently admin-triggered; could become part of nightly pipeline
- **News event backtesting:** "When an FDA rejection happened to pharma stocks, what was the average 30d return?" — queryable from signal_convergence_daily + news_sentiment_daily

## 20. Complete File Inventory

### Backend — Modify

| File | What Changes | Spec |
|------|-------------|------|
| `backend/config.py` | Add FINNHUB_API_KEY, FRED_API_KEY, OPENAI_API_KEY, EDGAR_USER_AGENT, NEWS_*, BACKTEST_*, BL_*, MONTE_CARLO_*, PIPELINE_* settings | A,B,C,D |
| `backend/models/__init__.py` | Import new models (BacktestRun, NewsArticle, NewsSentimentDaily, SignalConvergenceDaily, AdminAuditLog) for Alembic discovery | A,B,D |
| `backend/models/forecast.py` | Add `BacktestRun` model | A |
| `backend/tools/forecasting.py` | Accept calibrated config, add sentiment regressors via `add_regressor()`, fetch sentiment data | A,B |
| `backend/tasks/evaluation.py` | Replace flat MAPE threshold with per-ticker calibrated baseline, retrain-and-validate, experimental demotion/self-healing | A |
| `backend/tasks/market_data.py` | Add `compute_convergence_snapshot_task` to nightly Phase 3. Call CacheInvalidator after price updates | A,D |
| `backend/tasks/forecasting.py` | Add `run_backtest_task`, `calibrate_seasonality_task`. Call CacheInvalidator after forecast updates | A |
| `backend/tasks/__init__.py` | Register new beat schedule entries (news ingest, convergence snapshot) | A,B |
| `backend/routers/forecasts.py` | Add backtest endpoints (GET results, POST trigger) | A |
| `backend/routers/portfolio.py` | Add BL forecast, Monte Carlo, CVaR endpoints | C |
| `backend/observability/routers/command_center.py` | Add backtest health, sentiment coverage metrics to aggregate endpoint | A,B |
| `backend/main.py` | Mount new routers (sentiment, backtesting, convergence, admin pipelines) | A,B,C,D |
| `frontend/src/components/forecast-card.tsx` | Add accuracy badge (MAPE%), link to backtest drill-down | C |
| `frontend/src/app/(authenticated)/portfolio/portfolio-client.tsx` | Add BL forecast card, Monte Carlo chart, CVaR, per-position mini traffic lights | C |
| `frontend/src/app/(authenticated)/admin/command-center/page.tsx` | Add navigation link to Pipeline Control page | D |
| `frontend/src/hooks/use-forecasts.ts` | Add `useBacktestResults(ticker)` hook | A,C |
| `frontend/src/lib/api.ts` | Add API client functions for backtest, sentiment, convergence, pipeline endpoints | A,B,C,D |
| `frontend/src/types/api.ts` | Add BacktestResult, NewsSentiment, SignalConvergence, BLForecast, MonteCarloResult, CVaRResult, PipelineTask types | A,B,C,D |
| `frontend/src/mocks/handlers.ts` | Add MSW handlers for convergence, sentiment, BL forecast endpoints | C |
| `scripts/seed_prices.py` | Expose `async def seed_prices_async()` for Celery task wrapping | D |
| `scripts/seed_dividends.py` | Expose `async def seed_dividends_async()` | D |
| `scripts/seed_fundamentals.py` | Expose `async def seed_fundamentals_async()` | D |
| `scripts/seed_forecasts.py` | Expose `async def seed_forecasts_async()` | D |
| `scripts/seed_etfs.py` | Expose `async def seed_etfs_async()` | D |
| `scripts/seed_reason_tier.py` | Expose `async def seed_reason_tier_async()` | D |
| `scripts/seed_portfolio.py` | Expose `async def seed_portfolio_async()` | D |
| `scripts/sync_sp500.py` | Expose `async def sync_sp500_async()` | D |
| `scripts/sync_indexes.py` | Expose `async def sync_indexes_async()` | D |

### Backend — Create

| File | Purpose | Spec |
|------|---------|------|
| `backend/migrations/versions/024_forecast_intelligence.py` | Create backtest_runs, signal_convergence_daily, news_articles, news_sentiment_daily, admin_audit_log tables | A (shared migration) |
| `backend/models/backtest.py` | `BacktestRun` SQLAlchemy model | A |
| `backend/models/news.py` | `NewsArticle`, `NewsSentimentDaily` models | B |
| `backend/models/convergence.py` | `SignalConvergenceDaily` model | A |
| `backend/models/audit.py` | `AdminAuditLog` model | D |
| `backend/services/backtesting.py` | `BacktestEngine` — walk-forward validation, seasonality calibration | A |
| `backend/services/signal_convergence.py` | `SignalConvergenceService` — direction classification, convergence labels, divergence detection, bulk queries | A,C |
| `backend/services/portfolio_forecast.py` | `PortfolioForecastService` — Black-Litterman, Monte Carlo, CVaR | C |
| `backend/services/rationale.py` | `RationaleGenerator` — template-based + LLM for complex cases | C |
| `backend/services/cache_invalidator.py` | `CacheInvalidator` — event-driven, trigger-agnostic | A |
| `backend/services/pipeline_registry.py` | `PipelineRegistry`, `TaskDefinition` — task groups, dependency resolution, failure modes | D |
| `backend/services/pipeline_registry_config.py` | Registration of all tasks into registry | D |
| `backend/services/news/__init__.py` | Export `NewsIngestionService` | B |
| `backend/services/news/base.py` | `NewsProvider` ABC, `RawArticle` dataclass | B |
| `backend/services/news/finnhub_provider.py` | Finnhub API integration | B |
| `backend/services/news/edgar_provider.py` | SEC EDGAR 8-K parser with item number classification | B |
| `backend/services/news/fed_provider.py` | Federal Reserve RSS + FRED API | B |
| `backend/services/news/google_provider.py` | Google News RSS fallback | B |
| `backend/services/news/ingestion.py` | Orchestrates all providers, dedup, store | B |
| `backend/services/news/sentiment_scorer.py` | GPT-4o-mini batch scoring with structured output | B |
| `backend/services/llm/openai_provider.py` | OpenAI provider for LLM Factory | B |
| `backend/schemas/backtesting.py` | Pydantic schemas for backtest API | A |
| `backend/schemas/sentiment.py` | Pydantic schemas for sentiment API | B |
| `backend/schemas/convergence.py` | Pydantic schemas for convergence API (traffic lights, rationale) | C |
| `backend/schemas/portfolio_forecast.py` | Pydantic schemas for BL, Monte Carlo, CVaR responses | C |
| `backend/schemas/admin_pipeline.py` | Pydantic schemas for pipeline registry, task status, run progress | D |
| `backend/routers/backtesting.py` | Backtest endpoints | A |
| `backend/routers/sentiment.py` | Sentiment endpoints | B |
| `backend/routers/convergence.py` | Convergence endpoints (stock, portfolio, sector) | C |
| `backend/routers/admin_pipelines.py` | Pipeline orchestrator + cache clear endpoints | D |
| `backend/tasks/news_sentiment.py` | `news_ingest_task`, `news_sentiment_scoring_task` | B |
| `backend/tasks/convergence.py` | `compute_convergence_snapshot_task` (+ actual_return backfill) | A |
| `backend/tasks/seed_tasks.py` | All seed scripts wrapped as Celery tasks with progress reporting | D |

### Frontend — Create

| File | Purpose | Spec |
|------|---------|------|
| `frontend/src/components/convergence/traffic-light-row.tsx` | 6-signal traffic light display (responsive: circles on desktop, badge on mobile) | C |
| `frontend/src/components/convergence/divergence-alert.tsx` | Contextual alert banner with historical hit rate | C |
| `frontend/src/components/convergence/rationale-section.tsx` | Expandable rationale with Prophet component breakdown | C |
| `frontend/src/components/convergence/accuracy-badge.tsx` | MAPE% badge with backtest drill-down trigger | C |
| `frontend/src/components/portfolio/bl-forecast-card.tsx` | Black-Litterman expected return + per-position contribution | C |
| `frontend/src/components/portfolio/monte-carlo-chart.tsx` | Recharts area chart with p5/p25/median/p75/p95 bands | C |
| `frontend/src/components/portfolio/cvar-card.tsx` | CVaR display (95% and 99% levels) | C |
| `frontend/src/components/portfolio/convergence-summary.tsx` | Portfolio-level convergence card | C |
| `frontend/src/app/(authenticated)/admin/pipelines/page.tsx` | Pipeline Control admin page | D |
| `frontend/src/components/admin/pipeline-group-card.tsx` | Accordion card per task group | D |
| `frontend/src/components/admin/pipeline-task-row.tsx` | Individual task with status dot and run button | D |
| `frontend/src/components/admin/pipeline-run-history.tsx` | Run history table | D |
| `frontend/src/components/admin/cache-controls.tsx` | Cache clear controls (dropdown of whitelisted patterns) | D |
| `frontend/src/hooks/use-convergence.ts` | `useStockConvergence(ticker)`, `usePortfolioConvergence(portfolioId)` | C |
| `frontend/src/hooks/use-sentiment.ts` | `useSentiment(ticker)`, `useMacroSentiment()` | C |
| `frontend/src/hooks/use-bl-forecast.ts` | `useBLForecast(portfolioId, horizon)`, `useMonteCarlo(...)`, `useCVaR(...)` | C |
| `frontend/src/hooks/use-admin-pipelines.ts` | `usePipelineGroups()`, `useTriggerGroup()`, `useRunStatus(runId)` | D |

### Tests — Create

| File | Tier | Purpose | Spec |
|------|------|---------|------|
| `tests/unit/services/test_backtest_engine.py` | T1 | Walk-forward windows, metric computation, expanding window, seasonality calibration | A |
| `tests/unit/services/test_signal_convergence.py` | T1 | Direction classification, convergence labels, divergence detection, divergence hit rate query | A,C |
| `tests/unit/services/test_cache_invalidator.py` | T1 | Correct keys cleared per event, no over-invalidation (negative test) | A |
| `tests/unit/services/test_sentiment_scorer.py` | T1 | Prompt construction, JSON parsing, weighted aggregation with decay, edge cases | B |
| `tests/unit/services/test_news_providers.py` | T1 | HTTP response parsing per provider, dedup hash, rate limiting | B |
| `tests/unit/services/test_portfolio_forecast.py` | T1 | BL with known academic inputs, excess return subtraction, Monte Carlo (seeded), CVaR | C |
| `tests/unit/services/test_rationale_generator.py` | T1 | Template selection boundary, template output, Prophet component formatting | C |
| `tests/unit/services/test_pipeline_registry.py` | T1 | Dependency resolution, parallel grouping, failure modes, concurrent run protection | D |
| `tests/unit/tasks/test_news_sentiment_tasks.py` | T1 | Ingest task with mocked HTTP, scoring task with mocked OpenAI | B |
| `tests/unit/tasks/test_convergence_task.py` | T1 | Snapshot computation, actual_return backfill logic | A |
| `tests/unit/tasks/test_seed_tasks.py` | T1 | Seed task wrapping, progress reporting, idempotency | D |
| `tests/api/test_backtest_endpoints.py` | T2 | Auth (admin-only POST), GET results, pagination, empty state | A |
| `tests/api/test_sentiment_endpoints.py` | T2 | GET per-ticker, bulk, macro. Auth. Empty state | B |
| `tests/api/test_convergence_endpoints.py` | T2 | GET per-ticker, portfolio, sector. Auth. Divergence content | C |
| `tests/api/test_portfolio_forecast_endpoints.py` | T2 | BL returns, Monte Carlo shape, CVaR values | C |
| `tests/api/test_admin_pipeline_endpoints.py` | T2 | Trigger group (admin-only), poll status, concurrent 409, cache clear whitelist rejection | D |
| `tests/integration/test_news_pipeline.py` | T2 | Mock HTTP → real DB → verify sentiment_daily populated | B |
| `tests/integration/test_cache_invalidation.py` | T2 | Write data → verify correct Redis keys cleared | A |
| `tests/integration/test_backtest_slow.py` | T2 (slow) | Real Prophet, AAPL fixture, 252 points, 3 windows, sanity assertions | A |
| `tests/e2e/playwright/tests/convergence.spec.ts` | T3 | Traffic lights render, divergence alert, rationale expands | C |
| `tests/e2e/playwright/tests/portfolio-forecast.spec.ts` | T3 | BL card, Monte Carlo chart, CVaR values | C |
| `tests/e2e/playwright/tests/admin-pipelines.spec.ts` | T3 | Page loads, group cards, run button (mock Celery) | D |
| `tests/fixtures/news/finnhub_aapl.json` | Fixture | Recorded Finnhub API response for AAPL | B |
| `tests/fixtures/news/edgar_8k_sample.json` | Fixture | Sample 8-K filing response | B |
| `tests/fixtures/news/fed_rss_sample.xml` | Fixture | Sample Federal Reserve RSS | B |

### Total File Count

| Category | Modify | Create | Total |
|----------|--------|--------|-------|
| Backend (models, services, tasks, routers, config) | 16 | 32 | 48 |
| Frontend (components, pages, hooks, types) | 7 | 17 | 24 |
| Tests | 0 | 25 | 25 |
| Scripts | 9 | 0 | 9 |
| Migration | 0 | 1 | 1 |
| **Total** | **32** | **75** | **107** |

## 21. Comprehensive 5-Persona Review Findings

### Full-Stack Engineer Findings

| # | Severity | Finding | Fix |
|---|----------|---------|-----|
| 1 | CRITICAL | Portfolio convergence N+1 queries (3 queries × 97 positions) | Add `get_bulk_convergence(tickers)` — single query per data type, join in Python |
| 2 | CRITICAL | Monte Carlo response schema undefined | Time-series: `[{day, p5, p25, median, p75, p95}, ...]` for each day in horizon, not just terminal values |
| 3 | IMPORTANT | TanStack Query key collisions with existing hooks | Use query-key factory: `['convergence', ticker]`, `['backtest', ticker]`, `['bl-forecast', portfolioId]` |
| 4 | IMPORTANT | Backtest drill-down UX unspecified | DrillDownSheet on stock detail (same pattern as Command Center), triggered by accuracy badge click |
| 5 | IMPORTANT | Mobile responsive for 6 traffic lights | Collapse to convergence badge with count on mobile (< 640px). Tap expands to full list |

### Middleware / Integration Engineer Findings

| # | Severity | Finding | Fix |
|---|----------|---------|-----|
| 6 | CRITICAL | CacheInvalidator `on_prices_updated` queries all users' positions to clear BL cache — effectively full clear nightly | Remove user-lookup from `on_prices_updated`. BL/MC/CVaR caches have 1hr TTL — natural expiry is sufficient. Only explicit invalidation on `on_portfolio_changed` and `on_forecast_updated` |
| 7 | IMPORTANT | Celery task return values must be JSON-serializable (no UUID, datetime) | All task returns: dicts with strings/ints/floats only. Already existing pattern, now explicit requirement |
| 8 | CRITICAL | News scoring at fixed schedule (7,11,15,19) may start before ingest (6,10,14,18) completes | Chain scoring after ingest: `news_ingest_task.apply_async(link=news_sentiment_scoring_task.s())`. Remove separate scoring schedule |
| 9 | IMPORTANT | OpenAI client outside LLM Factory pattern | Add `OpenAIProvider` to `backend/services/llm/openai_provider.py`. SentimentScorer calls via factory. Keeps all LLM calls instrumented |
| 10 | IMPORTANT | Seed tasks need `@celery_app.task(bind=True)` for progress reporting | Explicit requirement for all seed tasks |

### QA / Test Engineer Findings

| # | Severity | Finding | Fix |
|---|----------|---------|-----|
| 11 | CRITICAL | No test for divergence hit rate computation | T1: seed convergence_daily with known patterns, assert hit rate query returns expected %. T2: verify via API |
| 12 | CRITICAL | No test for sentiment weighted aggregation formula | T1: 3 articles with known inputs, assert matches hand-calculated expected. Test edge cases: same day, 7+ days old, single article |
| 13 | CRITICAL | No test for BL excess return calculation | T1: known Prophet return (12%) - known risk-free (5%) = 7% excess. Assert BL receives 0.07 |
| 14 | IMPORTANT | Slow integration test scope too vague | Define: AAPL fixture data, 252 points, 3-window walk-forward at 30d, assert MAPE < 0.50, direction_accuracy > 0.0, ci_containment in [0.0, 1.0]. Validates pipeline, not accuracy |
| 15 | IMPORTANT | Frontend tests need MSW handlers for new endpoints | Spec C includes MSW handler additions for `/convergence/*`, `/sentiment/*`, `/portfolio/*/forecast` |
| 16 | IMPORTANT | No test for cache invalidation NOT over-invalidating | T1: set cache for AAPL and MSFT. Invalidate AAPL. Assert MSFT untouched |

### Stock Domain Expert Findings

| # | Severity | Finding | Fix |
|---|----------|---------|-----|
| 17 | CRITICAL | RSI < 40 as bullish is non-standard (traditional: < 30 = oversold) | Two-tier: < 30 = strong bullish (green), 30-40 = weak bullish (yellow-green), 40-70 = neutral. **PM decision: keep < 40 as single threshold for simplicity, but document deviation from tradition** |
| 18 | CRITICAL | "Strong Bull: 5-6 bullish, 0 bearish" almost never triggers (neutral signals common) | Revise: Strong Bull = 4+ bullish, 0 bearish. Weak Bull = 3+ bullish, <=1 bearish. Mixed = everything else. Weak Bear = 3+ bearish, <=1 bullish. Strong Bear = 4+ bearish, 0 bullish |
| 19 | CRITICAL | BL risk_aversion 2.5 is institutional; retail medium-risk users need higher (3.0+) | Change default to 3.07 (S&P 500 historical excess return / variance). Configurable via settings |
| 20 | IMPORTANT | CI containment target not specified (should match interval_width 80%) | Add: target ~80%. <70% = overconfident. >90% = underconfident (intervals too wide) |
| 21 | IMPORTANT | Macro sentiment uses single score for all stocks, ignoring sector-specific sensitivity | LLM prompt: "Score sector_sentiment relative to THIS stock's sector." Fed hike → tech sentiment -0.5, financials +0.3 |

### Staff Architect Findings

| # | Severity | Finding | Fix |
|---|----------|---------|-----|
| 22 | CRITICAL | Migration 024 immutability not stated — risk of amending after partial deployment | Add: "Migration 024 is immutable once applied. Post-deployment changes require migrations 025+" |
| 23 | CRITICAL | `actual_return_90d` backfill not in nightly chain | Add to convergence snapshot task: after today's snapshot, backfill 90-day-old rows with actual returns (same pattern as evaluate_forecasts) |
| 24 | CRITICAL | Pipeline group run tracking has no storage — can't report "60% done" | Add `pipeline_runs` tracking in Redis: `{run_id, group, status, started_at, child_task_ids, completed, failed, total}`. Status endpoint reads this |
| 25 | IMPORTANT | No rollback for bad LLM sentiment scores | Add `quality_flag` column to `news_sentiment_daily` (default 'ok'). Admin endpoint to invalidate date ranges. Invalidated rows excluded from Prophet. Neutral fallback |

### Applied Fixes Summary

**Data model changes from review:**
- `news_sentiment_daily` gets `quality_flag VARCHAR(10) DEFAULT 'ok'` column
- Convergence labels revised (4+ bullish for Strong Bull, not 5+)
- `BL_RISK_AVERSION` default changed from 2.5 to 3.07
- `pipeline_runs` tracking via Redis (not a new table)

**Architecture changes from review:**
- Portfolio convergence uses batch queries, not per-position
- CacheInvalidator `on_prices_updated` does NOT clear user-scoped caches (BL/MC/CVaR)
- News scoring chained after ingest, not on separate schedule
- OpenAI provider integrated into LLM Factory
- Migration 024 is immutable once applied
- Convergence snapshot task backfills actual_return columns

**Testing additions from review:**
- T1: divergence hit rate query test
- T1: sentiment weighted aggregation formula test
- T1: BL excess return subtraction test
- T1: cache invalidation negative test (no over-invalidation)
- T2: slow integration test with defined scope (AAPL fixture, 252 points, 3 windows)
- MSW handler additions noted for Spec C
