---
scope: project
category: domain
updated_by: session-91
phase: Phase 8.6+ COMPLETE — signal convergence (5 technical + sentiment), divergence detection, rationale generation, portfolio forecasting
---

# Convergence & Forecast Domain — Phase 8.6+

## Signal Convergence Architecture

### 5 Technical Classifiers + Sentiment (6th signal)

**Classifiers:**
1. **RSI** — Relative Strength Index (14-period, overbought >70, oversold <30)
2. **MACD** — Moving Average Convergence Divergence (12/26/9 EMA, signal line cross)
3. **SMA** — Simple Moving Averages (20/50/200, trend alignment)
4. **Piotroski** — Fundamental quality score (9-point scale, high cash quality)
5. **Forecast** — ML-based signal (LogisticRegression, calibrated on 2y walk-forward)
6. **News Sentiment** — GPT-4o-mini scoring, 4 providers (Finnhub, EDGAR, Fed RSS, Google News)

### Convergence Labels (0-6 aligned = label)

| Label | Alignment | Trading Signal |
|-------|-----------|-----------------|
| **strong_bull** | 5-6 aligned | BUY ≥8 composite score |
| **weak_bull** | 4 aligned | WATCH ≥5 |
| **mixed** | 3 aligned | HOLD (no action) |
| **weak_bear** | 2 aligned | WATCH <5 |
| **strong_bear** | 0-1 aligned | AVOID <5 |

### Divergence Detection

**Divergence:** When forecast direction opposes technical majority (≥3/5 classifiers)
- Example: forecast=SELL but RSI+MACD+SMA+Piotroski=SELL (4/5 aligned), forecast=BUY (DIVERGENCE)
- LLM-generated rationale for complex divergences (e.g., earnings surprise vs. technical momentum)
- Template-based rationale for 90%+ of cases (rules-based, no LLM call)

### Historical Hit Rate

**signal_convergence_daily table:**
- `ticker`, `date`, `rsi_direction`, `macd_direction`, `sma_direction`, `piotroski_direction`, `forecast_direction`, `sentiment_direction`
- `convergence_label` (computed from count of ALIGNED signals)
- `divergence_detected` (boolean)
- Populated by `backend/services/signal_convergence.py` (async Celery task, KAN-395 DONE)
- Hit rate metrics: % of strong_bull labels followed by 5d+ price gain (backtest data)

## RationaleGenerator Service

**Template-based (90%+ coverage):**
- Macro momentum (momentum >0.7 → bullish, <0.3 → bearish)
- Technical alignment (3+/5 → strong signal)
- Sentiment influence (news score >0.6 → supporting evidence)
- Divergence patterns (forecast vs. technical majority)
- Output: ~100-200 word prose, Markdown, no disclaimers (appended by API)

**LLM-based (complex divergences only):**
- Prompt: 5 signals + sentiment + recent news + earnings context
- Model: GPT-4o-mini (cost + speed)
- Input validation: no PII, max 2000 chars

**Key files:**
- `backend/services/rationale.py` — template dispatch + LLM fallback
- `backend/tools/convergence.py` — agent tool wrapper

## Portfolio Forecasting

### Black-Litterman (Idzorek form, Phase 8.6+)

**Setup:**
- Uses benchmark: 100% S&P 500 for single-ticker forecasts, user portfolio weights for multi-ticker
- Confidences (tau) calibrated per view (0.5-1.0 scale, higher = more confident)
- Views: analyst consensus targets (Phase 4D), forecast signals (Phase 5), convergence labels (Phase 8.6+)

**Constraints:**
- Long-only: weight_bounds = (0, 1) per asset
- Minimum 2 positions (fails otherwise, returns error)
- Sum constraint: weights sum to 1.0

**Output:**
- Optimal weights (portfolio allocation)
- Expected return (annualized)
- Volatility (annualized)

### Monte Carlo Simulation (10K draws, Cholesky decomposition)

**Setup:**
- Historical returns: 2-year rolling window, resampled daily
- Correlation matrix: 60-day rolling
- Drift + diffusion: μ (annualized) + σ (Cholesky factor)

**Algorithm:**
- Generate 10K path samples (252-day forward, daily steps)
- Drift: exp((μ - σ²/2) dt)
- Diffusion: σ × √dt × Z (where Z ~ N(0,1), NOT global state)
- **Gotcha:** Use `np.random.default_rng()` NOT `np.random.seed()` (stateless, no global pollution)

**Output:**
- Return distribution: mean, median, 5th, 25th, 75th, 95th percentiles
- CVaR (95th + 99th confidence levels)
- Drawdown percentiles

### Portfolio Forecast Service

**Key file:** `backend/services/portfolio_forecast.py`

**Endpoints:**
- POST /api/v1/portfolio/{portfolio_id}/forecast — returns BL + MC
- POST /api/v1/portfolio/{portfolio_id}/sensitivity — stress test (S&P ±5%, 10%, 20%)

**Cache:** Redis, 24h TTL, invalidated by CacheInvalidator (see below)

## News Pipeline

### Data Sources (4 providers)

1. **Finnhub** — real-time stock news, free tier (100/day), ~2h latency
2. **EDGAR** — SEC filings (10-K, 8-K, proxy), parsed by `backend/services/news/edgar_parser.py`
3. **Federal Reserve RSS** — https://www.federalreserve.gov/feeds/, FOMC statements, policy decisions
4. **Google News RSS** — semi-official, ticker + query parameterized

### SentimentScorer (Phase 8.6+)

**Model:** GPT-4o-mini (cost + latency)

**Input:** Article title + snippet + source

**Output:** 
- sentiment: -1.0 to +1.0 (negative to positive)
- confidence: 0.0 to 1.0
- key_themes: list of 1-3 tags (e.g., ["earnings_beat", "macro_headwind"])

**Regressors (3 models):**
1. LinearRegression(sentiment_score, returns_5d)
2. Ridge(sentiment_score, returns_5d, alpha=1.0)
3. GradientBoostingRegressor(sentiment_score, returns_5d)

**Ensemble:** Median of 3 predictions (robust to outliers)

**Cache:** Redis, 7d TTL (same article = same sentiment)

### Key file:
- `backend/services/news/` — providers, parser, scorer
- `backend/models/news_article.py` — `NewsArticle` SQLAlchemy model

## Backtesting Framework

### Expanding Window Walk-Forward

**Data split:**
- Train window: start → t
- Test window: t → t + 252 days (1 year)
- Slide: expand train by 252 days each iteration
- Repeat: 5-10 iterations (data permitting)

**Retraining:** Model refitted at start of each test window (not rolling)

### 5 Metrics

1. **Annual Return** — `(end_value / start_value) ** (1 / years) - 1`
2. **Sharpe Ratio** — `(mean_return - rf) / std_return` (rf = 2% annual)
3. **Max Drawdown** — `min(cumsum(returns))`
4. **Calmar Ratio** — `annual_return / abs(max_drawdown)` (guard against inf when dd=0)
5. **MAPE** — Mean Absolute Percentage Error (forecast vs. actual)

### Per-Ticker Calibrated Drift

**Drift calibration (KAN-395, Session 89):**
- MAPE from forecast model × 1.5 (conservative buffer)
- Applied to drift μ in Monte Carlo (reduce expected returns, add safety margin)
- Example: MAPE=0.08 → calibrated_drift = 0.08 × 1.5 = 0.12 (12% lower expected return)

### Key file:
- `backend/services/backtesting.py` — walk-forward engine, metric computation
- `docs/superpowers/specs/2026-04-01-test-suite-overhaul.md` — full spec

## Cache Invalidation Strategy

### CacheInvalidator Service (Phase 8.6+)

**7 event methods:** (fire-and-forget, batched Redis deletes)

1. `on_new_signal()` — clear signal_convergence, portfolio_forecast caches
2. `on_news_published()` — clear sentiment, market_briefing caches
3. `on_price_update()` — clear forecast, portfolio_forecast caches
4. `on_fundamentals_update()` — clear analyst_targets, fundamentals caches
5. `on_earnings_published()` — clear forecast, convergence caches
6. `on_portfolio_rebalance()` — clear portfolio_forecast, portfolio_health caches
7. `on_settings_change()` — clear all portfolio-scoped caches

**Pattern:** Celery task, try-except wrapped (no logging of cache errors to user)

**Batching:** Redis pipeline, max 100 deletes per batch

### Key file:
- `backend/services/cache_invalidator.py`

## Key Gotchas

1. **signal_convergence_daily population:** Requires Celery task wired (KAN-395 DONE Session 89). If missing, table empty → agent sees no convergence data.

2. **Black-Litterman feasibility:** Needs ≥2 positions. With 1 position, return None + error (handled in API response).

3. **Monte Carlo randomness:** ALWAYS use `np.random.default_rng()` NOT `np.random.seed()`. Global state pollutes parallel tests.

4. **QuantStats guards:** Returns NaN/Inf on edge cases. Always guard with `math.isfinite()`. Calmar ratio = inf when max_drawdown = 0 (no loss periods).

5. **Sentiment cache race:** Same article published by 2 sources → score once, cache, reuse. Manual cache invalidation if article retracted.

6. **Convergence table indices:** TimescaleDB hypertable, no secondary indices (breaks hypertable compression). Queries: time-ordered (start_date DESC), per-ticker filtered in app code.

7. **RationaleGenerator template drift:** Templates lock in assumptions (e.g., "strong bull = buy signal"). If convergence label definition changes, audit templates for compatibility.

8. **MAPE calibration scope:** Per-ticker, NOT global. E.g., low-vol stocks (MAPE=2%) vs. high-vol (MAPE=12%) get different drift adjustments in Monte Carlo.
