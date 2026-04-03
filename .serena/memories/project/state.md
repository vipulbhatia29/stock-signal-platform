## Project State (Session 90)

**Current phase:** Phase 8.6+ Forecast Intelligence COMPLETE (Epic KAN-369)
**All 4 specs shipped:** A (Backtesting), D (Admin Pipeline), B (News Sentiment), C (Convergence UX)
**Resume point:** Tech debt (KAN-395-399) or Phase F (Subscriptions + Monetization)
**Branch:** `develop` — all work merged

### Session 89-90 Summary
- Session 89: Specs D + B implemented (PRs #179-180). Spec C Sprint 10 started.
- Session 90: Spec C Sprints 10-13 completed. 5-persona extreme review. PR merged.
- Phase 8.6+ Epic KAN-369: ALL 13 sprints across 4 specs DONE.

### Key Facts
- Alembic head: `b2351fa2d293` (migration 024 — no new migrations sessions 89-90)
- Tests: 1848 backend + 423 frontend + 48 E2E + 27 nightly = ~2319 total
- Coverage: 68.95% (floor 60%)
- Internal tools: 25 + 4 MCP adapters
- 5 new models: BacktestRun, SignalConvergenceDaily, NewsArticle, NewsSentimentDaily, AdminAuditLog
- 12 new services: BacktestEngine, CacheInvalidator, SignalConvergenceService, PortfolioForecastService, RationaleGenerator, NewsIngestionService, SentimentScorer, PipelineRegistry, GroupRunManager, + 4 news providers
- 4 new routers: backtesting (5 endpoints), convergence (4), sentiment (4), admin_pipelines (8)
- 7 new frontend components: TrafficLightRow, DivergenceAlert, AccuracyBadge, RationaleSection, BLForecastCard, MonteCarloChart, CVaRCard, ConvergenceSummary
- Docker: Postgres 5433, Redis 6380, Langfuse 3001+5434

### Open Tech Debt (KAN-395-399)
- KAN-395 (HIGH): Wire convergence snapshot Celery task — signal_convergence_daily table is empty
- KAN-397 (HIGH): Integration tests for SQL queries (testcontainers)
- KAN-390 (HIGH): Extract portfolio forecast sub-router (portfolio.py at 760 lines)
- KAN-396 (MEDIUM): Add CacheService to convergence + forecast endpoints
- KAN-393/394 (MEDIUM): Remaining JIRA acceptance gaps + review medium findings
- KAN-398/399 (LOW): AccuracyBadge drill-down wiring, UTC-aware dates

### Open Bugs
- KAN-320 (HIGH): Intelligence endpoint intermittent 500
- KAN-321 (MEDIUM): Chat tool args char-by-char display
- KAN-322 (LOW): 63 stocks show "Unknown" sector
- KAN-388-394: 3 still open from Session 90 review
