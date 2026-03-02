# Functional Specification Document (FSD)

## Stock Signal Platform

**Version:** 1.0
**Date:** March 2026
**Status:** Draft
**Prerequisite reading:** docs/PRD.md

---

## 1. Purpose

This document translates the PRD's product requirements into detailed
functional and non-functional specifications. It defines exactly WHAT the
system does, how it behaves under normal and edge conditions, and what
constitutes correct behavior. The TDD (docs/TDD.md) defines HOW to build it.

---

## 2. User Roles & Permissions

| Role | Description | Permissions |
|------|-------------|-------------|
| ADMIN | Platform owner (you) | Full access: CRUD all data, manage users, system config |
| USER | Regular investor | Own portfolio, own watchlist, own chat, read signals |

Phase 1 ships with ADMIN only. USER role added if sharing with others.

---

## 3. Functional Requirements

### FR-1: Authentication & User Management

**FR-1.1: Registration**
- Input: email, password
- Validation: email must be unique, password ≥ 8 chars with ≥1 uppercase,
  ≥1 digit
- Output: user record created, UserPreference created with defaults
- Side effect: none (no auto-login)

**FR-1.2: Login**
- Input: email, password
- Output: { access_token, refresh_token, token_type, expires_in }
- access_token: JWT, expires in ACCESS_TOKEN_EXPIRE_MINUTES (default 60)
- refresh_token: opaque token, expires in REFRESH_TOKEN_EXPIRE_DAYS (default 7)
- Error: 401 if credentials invalid

**FR-1.3: Token Refresh**
- Input: refresh_token
- Output: new { access_token, refresh_token } pair
- Old refresh_token is invalidated (rotation)
- Error: 401 if refresh_token expired or invalid

**FR-1.4: User Preferences**
- Users can update: timezone, notification settings, composite score weights,
  position/sector caps, stop-loss defaults
- Preferences used by recommendation engine, alert system, and background jobs

### FR-2: Stock Universe & Watchlist

**FR-2.1: Stock Universe**
- System maintains S&P 500 constituents (is_in_universe=True)
- Universe synced quarterly via script
- Screener operates on universe; watchlist is user's personal subset

**FR-2.2: Watchlist Management**
- Add ticker to watchlist: ticker must exist in Stock table
- Remove ticker from watchlist
- List watchlist with current price + latest signal summary
- Maximum 100 tickers per user watchlist

**FR-2.3: Stock Lookup**
- Search stocks by ticker or name (prefix match)
- If ticker not in database, attempt to add via yfinance lookup
- Return: ticker, name, exchange, sector, industry

### FR-3: Signal Engine

**FR-3.1: Technical Signal Computation**

For a given ticker, using the last 252 trading days of price data:

| Signal | Computation | Output Label |
|--------|------------|-------------|
| RSI(14) | Wilder's smoothed RSI | <30: OVERSOLD, 30-70: NEUTRAL, >70: OVERBOUGHT |
| MACD(12,26,9) | MACD line - Signal line | histogram > 0: BULLISH, ≤ 0: BEARISH |
| SMA Crossover | Compare SMA(50) vs SMA(200) vs current price | GOLDEN_CROSS (50 crosses above 200), DEATH_CROSS (50 crosses below 200), ABOVE_200 (price > SMA200), BELOW_200 (price < SMA200) |
| Bollinger(20,2) | Price position relative to bands | UPPER (> upper band), MIDDLE (between), LOWER (< lower band) |
| Annualized Return | (latest_close / close_252d_ago)^(252/trading_days) - 1 | Percentage |
| Volatility | std(daily_returns) × √252 | Percentage |
| Sharpe Ratio | (annualized_return - risk_free_rate) / volatility | Decimal (risk_free_rate from FRED or default 4.5%) |

**FR-3.2: Composite Score Calculation**

Phase 1 (technical only, composite_weights stored per snapshot):

```
score = 0
max_score = 10

# RSI contribution (0-2.5 points)
if RSI < 30: +2.5     # oversold = buying opportunity
elif RSI < 45: +1.5
elif RSI > 70: +0     # overbought = risky
else: +1.0            # neutral

# MACD contribution (0-2.5 points)
if MACD histogram > 0 and increasing: +2.5
elif MACD histogram > 0: +1.5
elif MACD histogram < 0 and decreasing: +0
else: +0.5

# SMA contribution (0-2.5 points)
if GOLDEN_CROSS: +2.5
elif ABOVE_200: +1.5
elif BELOW_200: +0.5
elif DEATH_CROSS: +0

# Sharpe contribution (0-2.5 points)
if sharpe > 1.5: +2.5
elif sharpe > 1.0: +2.0
elif sharpe > 0.5: +1.0
elif sharpe > 0: +0.5
else: +0

composite_score = score  # 0-10 range
```

Phase 3 adds fundamental signals (see FR-5) and rebalances to 50/50 weight.

**FR-3.3: Signal Staleness**
- Signals older than 24 hours are flagged as STALE
- Stale signals cannot generate recommendations
- Dashboard shows "last updated" timestamp prominently

### FR-4: Recommendation Engine

**FR-4.1: Decision Rules**

Run daily after signal computation. For each stock in watchlist + universe:

```
INPUT: composite_score, portfolio_state (optional), macro_regime (Phase 5)

IF composite_score >= 8:
    IF stock is held AND allocation >= max_position_pct:
        action = HOLD, confidence = HIGH
        reason = "Strong signals but already at target allocation"
    ELIF macro_regime == RISK_OFF (Phase 5):
        action = BUY, confidence = LOW
        reason = "Strong signals but macro environment is cautious"
    ELSE:
        action = BUY, confidence = HIGH
        suggested_amount = calculate_position_size()

ELIF composite_score >= 5:
    IF stock is held:
        action = HOLD, confidence = MEDIUM
    ELSE:
        action = WATCH, confidence = MEDIUM

ELIF composite_score < 5:
    IF stock is held:
        IF trailing_stop_breached:
            action = SELL, confidence = HIGH
            reason = "Stop-loss triggered at X%"
        ELIF piotroski < 4 (Phase 3):
            action = SELL, confidence = HIGH
            reason = "Fundamental deterioration"
        ELSE:
            action = SELL, confidence = MEDIUM
    ELSE:
        action = AVOID, confidence = MEDIUM
```

**FR-4.2: Position Sizing**

```
calculate_position_size(ticker, portfolio):
    total_value = portfolio.total_value
    target_pct = min(max_position_pct, equal_weight_pct)
        # equal_weight_pct = 100% / number_of_target_positions
        # max_position_pct from UserPreference (default 5%)
    current_pct = portfolio.allocation[ticker] or 0
    gap_pct = target_pct - current_pct

    # Enforce cash reserve
    available_cash = portfolio.cash - (total_value * min_cash_reserve_pct)
    if available_cash <= 0:
        return 0

    # Enforce sector cap
    sector = stock.sector
    sector_allocation = sum(portfolio.allocation for stocks in sector)
    if sector_allocation >= max_sector_pct:
        return 0

    suggested_amount = min(gap_pct * total_value, available_cash)
    if suggested_amount < 100:  # minimum trade size
        return 0

    return round(suggested_amount, 2)
```

**FR-4.3: Recommendation Surfacing**
- `GET /api/v1/recommendations` returns today's actionable items
- Sorted by: confidence DESC, then composite_score DESC
- Filterable by: action (BUY/SELL/HOLD), confidence level
- "Action Required" panel on dashboard shows only BUY and SELL with HIGH confidence
- User can acknowledge a recommendation (marks acknowledged=True)

### FR-5: Fundamental Analysis (Phase 3)

**FR-5.1: Fundamental Signals**

| Metric | Source | Scoring |
|--------|--------|---------|
| P/E vs 5Y avg | yfinance | Below avg: +1, Above: 0 |
| PEG < 1 | yfinance | Yes: +1, No: 0 |
| FCF Yield > 5% | yfinance | Yes: +1, No: 0 |
| Debt/Equity < 1 | yfinance | Yes: +1, No: 0 |
| Interest Coverage > 3x | yfinance | Yes: +1, No: 0 |
| Piotroski F-Score | Computed from financials | 7-9: +3, 5-6: +1, <5: 0 |

Fundamental sub-score: 0 to 8 points, normalized to 0-10.

**FR-5.2: Combined Composite Score (Phase 3+)**
```
composite = (technical_score * 0.5) + (fundamental_score * 0.5)
```
Users can override weights via UserPreference.composite_weights.

### FR-6: Portfolio Management (Phase 3)

**FR-6.1: Transaction Logging**
- Input: ticker, action (BUY/SELL), quantity, price_per_share, fees, date, notes
- Validation: SELL quantity cannot exceed current holdings
- Side effect: Position table updated (recalculate avg_cost, quantity)

**FR-6.2: Position Calculation (FIFO)**
- When selling, cost basis uses First-In-First-Out
- Realized P&L = (sell_price - cost_basis) × quantity - fees
- Unrealized P&L = (current_price - avg_cost) × current_quantity

**FR-6.3: Stock Split Handling**
- On split detection (via yfinance): create CorporateAction record
- Adjust all open position quantities: multiply by ratio_to/ratio_from
- Adjust avg_cost: divide by ratio_to/ratio_from
- Historical prices use adj_close (already split-adjusted by yfinance)

**FR-6.4: Dividend Tracking**
- Auto-detect dividends from yfinance dividend history
- Record DividendPayment: amount_per_share × shares_held_at_ex_date
- Include in total return calculations
- Dashboard shows: total dividend income, trailing 12-month yield

**FR-6.5: Portfolio Snapshots**
- Nightly task computes and stores PortfolioSnapshot
- total_value = sum(position_qty × current_price) + cash
- day_pnl = today_value - yesterday_value
- total_pnl = total_value - total_invested
- positions_json stores snapshot of all positions for historical reconstruction

### FR-7: Screener (Phase 2)

**FR-7.1: Stock Universe**
- Operates on all stocks where is_in_universe=True (S&P 500)
- Uses pre-computed signals (not live computation)

**FR-7.2: Filtering**
- RSI state: OVERSOLD / NEUTRAL / OVERBOUGHT
- MACD state: BULLISH / BEARISH
- Sector: multi-select from GICS sectors
- Composite score: range slider (0-10)
- Sharpe ratio: minimum threshold

**FR-7.3: Sorting**
- Default: composite_score DESC
- Sortable by any visible column
- Client-side sorting (data pre-loaded)

**FR-7.4: Display**
- Color coding: ≥8 green, 5-7 amber, <5 red
- Click row → navigate to stock detail page

### FR-8: AI Chatbot (Phase 4)

**FR-8.1: Agent Selection**
- General Agent: web search + Q&A (no tool access to portfolio)
- Stock Agent: full tool access (signals, fundamentals, portfolio, screener, forecast)
- User selects agent type per conversation

**FR-8.2: Tool Orchestration**
- Agent uses LLM tool-calling to invoke platform tools
- Maximum 15 tool calls per conversation turn
- All data in responses must come from tool results (no hallucination)
- If a tool fails, agent explains the failure and continues with available data

**FR-8.3: Streaming**
- Response streams via NDJSON over SSE
- Frontend renders incrementally as tokens arrive
- Tool execution status shown as progress indicators

**FR-8.4: Conversation History**
- Stored per ChatSession (user + agent_type)
- ChatMessage records: role, content, tool_calls, tokens_used, model_used
- History sent as context for multi-turn conversations
- Sessions auto-expire after 24 hours of inactivity

### FR-9: Alerts & Notifications (Phase 5)

**FR-9.1: Alert Rules**
- Trailing stop-loss: price drops X% from recent high (X from UserPreference)
- Position concentration: allocation exceeds max_position_pct
- Sector concentration: sector allocation exceeds max_sector_pct
- Cash reserve: cash drops below min_cash_reserve_pct
- Fundamental deterioration: Piotroski drops below 4
- Signal flip: stock's composite action changes (e.g., HOLD → SELL)

**FR-9.2: Alert Deduplication**
- Same alert rule + same ticker cannot fire more than once per 24 hours
- Acknowledged alerts don't re-fire until condition clears and re-triggers

**FR-9.3: Notification Channels**
- Telegram: real-time alerts + daily morning briefing
- Morning briefing contents: overnight signal changes, portfolio P&L,
  today's recommendations, any triggered alerts
- Quiet hours: no notifications between quiet_hours_start and quiet_hours_end
  (from UserPreference)

### FR-10: Recommendation Evaluation (Phase 5)

This is the feedback loop that answers: "Is this platform giving good advice?"
Without it, the recommendation engine runs on assumptions that are never
validated against reality.

**FR-10.1: Outcome Capture**

Nightly task `evaluate_recommendations.py`:

```
For each RecommendationSnapshot WHERE:
    generated_at + horizon <= today
    AND no matching RecommendationOutcome exists for this (recommendation, horizon):

    For horizon in [30d, 90d, 180d]:
        price_at_rec = recommendation.price_at_recommendation
        price_now = StockPrice.close WHERE ticker AND date = generated_at + horizon
        spy_at_rec = StockPrice.close WHERE ticker='SPY' AND date = generated_at
        spy_now = StockPrice.close WHERE ticker='SPY' AND date = generated_at + horizon

        return_pct = (price_now - price_at_rec) / price_at_rec
        benchmark_return_pct = (spy_now - spy_at_rec) / spy_at_rec
        alpha = return_pct - benchmark_return_pct

        IF action == BUY:
            action_was_correct = (return_pct > benchmark_return_pct)
        ELIF action == SELL:
            action_was_correct = (return_pct < benchmark_return_pct)
        ELIF action == HOLD:
            action_was_correct = (abs(return_pct - benchmark_return_pct) < 0.05)
        ELSE:
            action_was_correct = NULL  # WATCH/AVOID not evaluated

        Store RecommendationOutcome row
```

**FR-10.2: Key Metrics (derived from outcome data)**

After 3+ months of data accumulation, the following metrics become available:

| Metric | Query | What It Tells You |
|--------|-------|-------------------|
| BUY hit rate | % of BUY outcomes where action_was_correct | Are buy calls beating the market? |
| SELL hit rate | % of SELL outcomes where action_was_correct | Are sell calls avoiding losses? |
| Hit rate by confidence | Group by confidence, compare hit rates | Are HIGH confidence calls better? |
| Mean alpha by score bucket | Group by composite_score ranges, avg alpha | Does the 0-10 score actually predict returns? |
| Signal contribution | Join reasoning JSONB, correlate signal presence with alpha | Which signals matter most? |
| Score threshold validation | Hit rate above vs below threshold (8.0) | Is ≥8 the right BUY threshold? |

**FR-10.3: Weight Calibration (manual, not automated)**
- After 6 months of data, user reviews outcome metrics
- If a signal (e.g., RSI) shows no correlation with alpha → reduce its weight
- If a signal (e.g., Sharpe) strongly correlates → increase its weight
- Weight changes are applied via UserPreference.composite_weights
- Previous snapshots retain their original weights (composite_weights JSONB)
  so historical analysis remains valid

**FR-10.4: Data Requirements**
- SPY must ALWAYS be in the stock universe with daily price data
  (required for benchmark calculations)
- price_at_recommendation must be captured at recommendation time
  (not reconstructed later — avoids look-ahead bias)
- Outcome evaluation uses closing prices only (no intraday)

---

## 4. Non-Functional Requirements

### NFR-1: Performance

| Operation | Target | Measurement |
|-----------|--------|-------------|
| Dashboard page load | < 2s | Lighthouse, pre-computed data |
| Signal computation per ticker | < 5s | Backend timing |
| Screener load (500 stocks) | < 3s | Full table render |
| Chat first token | < 2s | SSE first byte |
| Chat full response (multi-tool) | < 15s | Last token |
| API response (cached) | < 200ms | P95 latency |
| Nightly batch (500 tickers) | < 30 min | Celery task completion |

### NFR-2: Scalability

| Dimension | Target |
|-----------|--------|
| Tracked stocks (universe) | 500 |
| Watchlist per user | 100 |
| Portfolio positions | 100 |
| Concurrent users | 10 |
| Signal history retention | Indefinite |
| Price history | 20 years |

### NFR-3: Availability & Reliability

- Target uptime: 99% (personal tool, ~7 hours downtime/month acceptable)
- yfinance failures: retry 3x with exponential backoff, skip ticker on final failure
- LLM API failures: fall through Groq → Claude → LM Studio → error message
- Background job failures: retry 3x, log to TaskLog, alert on 3 consecutive failures
- Database: daily pg_dump backup (local), Azure automated backup (production)

### NFR-4: Security

- All API endpoints require JWT (except /auth/login, /auth/register, /health)
- Password hashing: bcrypt with cost factor 12
- JWT tokens: RS256 or HS256, short-lived access (60 min), rotating refresh (7 days)
- Rate limiting: 60 requests/minute per user (configurable)
- CORS: whitelist frontend origin only
- Secrets: environment variables only, never in code or git
- HTTPS: enforced in production via reverse proxy
- SQL injection: prevented by SQLAlchemy parameterized queries
- XSS: prevented by React's default escaping + CSP headers

### NFR-5: Data Integrity

- Portfolio transactions are immutable — no edits, only new entries
- All time-series data is append-only
- Every recommendation and forecast traces to its input data
- Stock splits adjust positions atomically (single transaction)
- FIFO cost basis is deterministic and reproducible

### NFR-6: Observability

- Structured logging: structlog with JSON output
- Request tracing: correlation ID on every API request
- Background job monitoring: TaskLog table + dashboard widget
- LLM usage tracking: tokens_used and model_used on every ChatMessage
- Error alerting: log ERROR level → future integration with monitoring

---

## 5. Business Rules Summary

| Rule | Value | Source |
|------|-------|--------|
| Max position allocation | 5% of portfolio | UserPreference.max_position_pct |
| Max sector allocation | 30% of portfolio | UserPreference.max_sector_pct |
| Min cash reserve | 10% of portfolio | UserPreference.min_cash_reserve_pct |
| Default trailing stop-loss | 20% from high | UserPreference.default_stop_loss_pct |
| Minimum trade size | $100 | Hardcoded |
| Signal staleness threshold | 24 hours | Hardcoded |
| Composite score BUY threshold | ≥ 8 | Recommendation engine |
| Composite score SELL threshold | < 5 | Recommendation engine |
| Piotroski deterioration threshold | < 4 | Recommendation engine |
| Recommendation eval horizons | 30d, 90d, 180d | RecommendationOutcome |
| Benchmark ticker | SPY (S&P 500 ETF) | RecommendationOutcome |
| BUY correct definition | stock return > benchmark return | RecommendationOutcome |
| SELL correct definition | stock return < benchmark return | RecommendationOutcome |
| Alert dedup window | 24 hours | AlertLog |
| Max chat tool calls per turn | 15 | Agent loop |
| LLM fallback order | Groq → Claude → LM Studio | Agent config |

---

## 6. Error Handling

### API Errors (returned to client)

| HTTP Code | When | Response Body |
|-----------|------|--------------|
| 400 | Bad request (invalid ticker format, etc.) | { detail: "description" } |
| 401 | Missing/invalid/expired JWT | { detail: "Not authenticated" } |
| 403 | Insufficient role (USER accessing ADMIN endpoint) | { detail: "Forbidden" } |
| 404 | Resource not found (ticker, portfolio, etc.) | { detail: "Not found" } |
| 409 | Conflict (duplicate email, etc.) | { detail: "Already exists" } |
| 422 | Validation error (Pydantic) | { detail: [field errors] } |
| 429 | Rate limit exceeded | { detail: "Too many requests" } |
| 500 | Unexpected server error | { detail: "Internal error" } (no stack trace) |

### Background Job Errors (logged to TaskLog)

| Error | Handling |
|-------|----------|
| yfinance timeout | Retry 3x, skip ticker, continue batch |
| yfinance rate limit | Exponential backoff (2s, 4s, 8s) |
| LLM API error | Fall through to next provider |
| Database connection lost | Retry with fresh connection |
| Invalid data from yfinance | Log warning, skip ticker, don't corrupt DB |

---

## 7. Feature × Phase Matrix

| Feature | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 | Phase 6 |
|---------|---------|---------|---------|---------|---------|---------|
| Auth + JWT refresh | ✓ | | | | | |
| User preferences | ✓ | | Enhanced | | Enhanced | |
| Stock universe + watchlist | ✓ | | | | | |
| Technical signals | ✓ | | | | | |
| Composite score (tech only) | ✓ | | Upgraded 50/50 | | | |
| Basic recommendations | ✓ | | Portfolio-aware | | Macro-aware | |
| Signal API | ✓ | | | | | |
| Dashboard UI | | ✓ | Enhanced | | Enhanced | |
| Screener UI | | ✓ | | | | |
| Stock detail page | | ✓ | Enhanced | | | |
| Fundamental signals | | | ✓ | | | |
| Portfolio tracker | | | ✓ | | | |
| Dividends + splits | | | ✓ | | | |
| Portfolio snapshots | | | ✓ | | | |
| Alert rules engine | | | ✓ | | | |
| Position sizing | | | ✓ | | | |
| AI chatbot | | | | ✓ | | |
| Chat UI | | | | ✓ | | |
| Background jobs (Celery) | | | | | ✓ | |
| Forecasting (Prophet) | | | | | ✓ | |
| Model versioning | | | | | ✓ | |
| Macro overlay | | | | | ✓ | |
| Telegram notifications | | | | | ✓ | |
| Recommendation evaluation | | | | | ✓ | |
| MCP servers | | | | | | ✓ |
| Cloud deployment | | | | | | ✓ |
| CI/CD | | | | | | ✓ |
