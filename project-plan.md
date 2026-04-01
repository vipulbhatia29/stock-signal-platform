# Stock Signal Platform — Project Plan

## Completed Phases (Sessions 1-81)

### Phase 1: Signal Engine + Database + API ✅ (Sessions 1-3)
FastAPI + SQLAlchemy async + Alembic + TimescaleDB + JWT auth. Signal engine (RSI, MACD, SMA, Bollinger, composite 0-10). Recommendation engine (BUY/WATCH/AVOID). 7 endpoints. Seed scripts.

### Phase 2: Dashboard + Screener UI ✅ (Sessions 4-7)
httpOnly cookie auth, StockIndex model, on-demand ingest, bulk signals, signal history. Next.js frontend (login, dashboard, screener, stock detail).

### Phase 2.5: Design System + UI Polish ✅ (Sessions 8-13, PR #1)
Financial CSS vars, `useChartColors()`, 10 new components, entry animations, Bloomberg dark mode.

### Phase 3: Security + Portfolio + Fundamentals ✅ (Sessions 14-25, PRs #2-5)
JWT validation, rate limiting, CORS. Portfolio FIFO engine, P&L, sector allocation. Piotroski F-Score (50/50 blending). Snapshots, dividends, divestment rules, portfolio-aware recs, rebalancing.

### Phase 4: AI Agent + UI Redesign ✅ (Sessions 26-44, PRs #5-50)
- **4A:** Navy command-center UI (25 tasks, KAN-87-98)
- **4B:** LangGraph Plan→Execute→Synthesize (KAN-12/13/15, Epic KAN-1)
- **4C:** NDJSON streaming chat UI (23 files, Epic KAN-30)
- **4D:** ReAct loop + enriched data layer (Epic KAN-61, KAN-62-68)
- **4E:** Security hardening (11 findings, KAN-70-72)
- **4F:** Full UI migration (9 stories KAN-89-96, KAN-94 sectors, KAN-97 animations)
- **4G:** Backend hardening (154 tests, Epic KAN-73, KAN-74-84)

### Phase 5: Forecasting + Alerts ✅ (Sessions 45-52, PRs #54-93, Epic KAN-106)
Prophet forecasting, 9-step nightly pipeline, recommendation evaluation, drift detection, in-app alerts, 6 agent tools (KAN-107-117). MCP stdio tool server (KAN-119, KAN-132-136). Redis refresh token blocklist. Dashboard bug sprints.

### Phase 6: LLM Factory + Observability ✅ (Sessions 53-55, PRs #95-101)
V1 deprecation (KAN-140), TokenBudget (KAN-141), llm_model_config (KAN-142), GroqProvider cascade (KAN-143), admin API (KAN-144), truncation (KAN-145), ObservabilityCollector DB writer, Playwright E2E. Redis cache (KAN-148).

### Phase 7: Backend Hardening + Tech Debt ✅ (Sessions 56-60, PRs #102-121)
Guardrails (KAN-158), data enrichment (KAN-159), agent intelligence (KAN-160), pagination (KAN-168), cache (KAN-170), passlib→bcrypt (KAN-174). SaaS readiness audit (KAN-176-186). Service layer extraction (KAN-172/173).

### Phase 8: Observability + ReAct Agent ✅ (Sessions 61-64, PRs #123-131)
- **8A:** Provider observability, cost_usd, cache_hit, agent_id (KAN-190-198)
- **8B:** ReAct loop (KAN-189, KAN-203-210)
- **8C:** Intent classifier + tool filtering (KAN-199-202)
- Input validation (KAN-154), OHLC (KAN-150)

### SaaS Launch Roadmap Phase A ✅ (Session 67, PR #138, KAN-186)
TokenBudget → Redis sorted sets. ObservabilityCollector reads → DB.

### SaaS Launch Roadmap Phase B ✅ (Sessions 68-70, PRs #140-143, Epic KAN-218)
Langfuse infra (KAN-220), trace instrumentation (KAN-221), assessment data layer (KAN-222), OIDC SSO + eval framework (KAN-223).

### SaaS Launch Roadmap Phase B.5 ✅ (Sessions 72-79, PRs #144-157, Epic KAN-226)
- **BU-1:** Schema sync + alerts redesign (KAN-227)
- **BU-2:** Stock detail enrichment (KAN-228)
- **BU-3/4:** Dashboard 5-zone redesign + chat (KAN-229/230)
- **BU-5:** Observability backend gaps (KAN-231)
- **BU-6:** Observability frontend (KAN-232)
- **BU-7:** Command Center (KAN-233, KAN-300-316)

### Phase 8.5: Portfolio Analytics ✅ (Session 81, PR #158, Epic KAN-246)
pandas-ta-openbb (KAN-249), QuantStats (KAN-247), PyPortfolioOpt (KAN-248). Migration 022. 4-expert review (21 findings fixed). Bug fixes: KAN-318, KAN-319. 25 internal tools. Alembic head: `c870473fe107`.

---

## Active / Future Phases

### Phase C: Google OAuth + User Acquisition (~3 days, KAN-152)

> Unblocks subscriptions and real user signups. PKCE flow, account linking.

| # | Task | Brainstorm? | Effort |
|---|------|-------------|--------|
| C1 | Account linking policy (merge on email? separate accounts?) | **Business** | ~0.5 day |
| C2 | PKCE flow, CachedJWKSClient, dual auth (JWT + Google) | **Technical** | ~0.5 day |
| C3 | Backend: Google OAuth provider, user linking, token exchange | No | ~1.5 days |
| C4 | Frontend: "Sign in with Google" button, auth flow | No | ~0.5 day |

### Phase D: Subscriptions + Monetization (~5 days)

> Stripe integration, tier enforcement, pricing. **Depends on Phase C.**

| # | Task | Brainstorm? | Effort |
|---|------|-------------|--------|
| D1 | Tier definitions (Free/Pro/Premium), quotas, pricing | **Business** | ~0.5 day |
| D2 | Stripe integration, webhooks, lifecycle | **Technical** | ~0.5 day |
| D3 | User model: subscription_tier, stripe_customer_id, migration | No | ~0.5 day |
| D4 | Stripe checkout + webhook endpoints | No | ~1.5 days |
| D5 | SubscriptionGuard middleware: tier + quota enforcement | No | ~1 day |
| D6 | LLM tier routing: free users → cheap models | No | ~0.5 day |
| D7 | Frontend: pricing cards, usage meter, billing page | No | ~1 day |

### Phase E: Cloud Deployment (~4 days)

| # | Task | Brainstorm? | Effort |
|---|------|-------------|--------|
| E1 | Cloud provider selection (Azure/AWS/GCP), managed services | **Technical** | ~0.5 day |
| E2 | Docker Compose: all services containerized (inc. MCP Tool Server) | No | ~1 day |
| E3 | MCP transport swap: stdio → Streamable HTTP (config change only) | No | ~0.5 day |
| E4 | Terraform / IaC for cloud infra | No | ~1.5 days |
| E5 | deploy.yml: wire actual CI/CD deployment | No | ~0.5 day |

### Phase F: Comparison Fan-Out (optional, ~2 days)

Parallel multi-ticker analysis with concurrency control. Data-driven activation — only if eval scores warrant it per multi-agent decision gate.

### Phase 8.6: Prophet Backtesting (KAN-323)

> Walk-forward validation of Prophet forecasts. **Depends on Phase 8.5 ✅.**

| # | Task | Description |
|---|------|-------------|
| 1 | Walk-forward validation framework | Split train/test windows, measure MAPE/MAE per ticker |
| 2 | Accuracy tracking table | Migration: `forecast_backtests` (ticker, train_end, horizon, mape, mae, direction_accuracy) |
| 3 | Confidence calibration | Compare predicted vs actual confidence intervals |
| 4 | Backtest dashboard | API endpoint + frontend: per-ticker accuracy, worst performers |

### Phase 8.7: News-Sentiment Regressor (KAN-324)

> Augment Prophet with LLM-scored news sentiment. **Depends on Phase 8.6.**

| # | Task | Description |
|---|------|-------------|
| 1 | News scoring pipeline | LLM: ingest news → score sentiment (-1 to +1) → store daily aggregate |
| 2 | Sentiment table | Migration: `news_sentiment_daily` (ticker, date, score, article_count) |
| 3 | Prophet integration | `add_regressor()` with daily sentiment |
| 4 | A/B backtest | Compare Prophet-only vs Prophet+sentiment using Phase 8.6 framework |

---

## Open Bugs

| Ticket | Severity | Bug | Status |
|--------|----------|-----|--------|
| KAN-318 | CRITICAL | Dashboard crash (undefined grade) | ✅ Fixed S81 |
| KAN-319 | HIGH | Duplicate React key in movers | ✅ Fixed S81 |
| KAN-320 | HIGH | Intelligence endpoint intermittent 500 | Open |
| KAN-321 | MEDIUM | Chat tool args char-by-char display | Open |
| KAN-322 | LOW | 63 stocks show "Unknown" sector | Open |

## Backlog (JIRA tickets, not yet scheduled)

| Ticket | Summary | Notes |
|--------|---------|-------|
| KAN-152 | Google OAuth (PKCE flow) | → Phase C |
| KAN-157 | Live LLM eval tests in CI | Needs CI_GROQ_API_KEY + CI_ANTHROPIC_API_KEY secrets |
| KAN-162 | Langfuse Self-Hosted Integration | Reopened S67, visual trace waterfall |
| KAN-211 | Test Suite Hardening Epic (KAN-212-216) | 5 stories: tool orchestration, pipeline mocks, error paths, ReAct integration, frontend components |
| KAN-217 | Playwright E2E Refresh | Rewrite stale POM selectors after Phase 4F UI rewrite |
| KAN-225 | Deferred items from KAN-223 review | 7 items: LLM-as-judge wiring, resilience detector, Groq in assessment, golden dataset sync, few-shot examples, dividend query dedup, Langfuse CI vars |

## Frontend Backlog (no JIRA tickets yet)

| Item | Notes |
|------|-------|
| Stock detail: revenue/margins/growth card | Data exists via StockIntelligenceTool, needs UI |
| Stock detail: analyst price targets viz | Bar/gauge, data from AnalystTargetsTool |
| Stock detail: earnings history chart | EPS estimate vs actual, from EarningsHistoryTool |
| Stock detail: company profile section | Summary, employees, website, market cap |
| Stock detail: analyst consensus chart | Buy/hold/sell bar chart |
| Stock detail: candlestick toggle | Backend done (KAN-150), needs Line/Candle pill |
| Stock detail: benchmark chart | Backend done (KAN-151), needs 3-line comparison |
| Chat: artifact bar enhancements | Tool buttons, scroll pill, agent badge, auto-retry |
| Portfolio: strategy picker UI | PATCH /preferences exists, no frontend selector |

## Parking Lot

- Schwab CSV import — parse "Positions" export, create BUY transactions
- ForecastCard currentPrice display — signal schema doesn't expose it
- Forecasts blended into composite score — deferred pending accuracy validation
- Telegram alerts — deferred, in-app only for now
