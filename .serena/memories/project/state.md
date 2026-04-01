## Project State (Session 81)

**Current phase:** Phase 8.5 Portfolio Analytics COMPLETE — shipped PR #158
**Branch:** develop (docs/session-81-closeout for doc updates)
**Resume point:** Phase C (Google OAuth, KAN-152) or Phase 8.6 (Prophet Backtesting, KAN-323) or Phase 2 Command Center.

### Session 81 Summary
- Phase 8.5 all 4 stories implemented in one session: pandas-ta, QuantStats, PyPortfolioOpt, frontend
- 4-expert review panel (PM, Staff FS, Staff Backend, Test Lead): 21 findings fixed (6C/9I/6M)
- Pre-existing bugs found and fixed: SignalSnapshot.snapshot_date→computed_at, grade B+ dedup
- PR #158 merged to develop, all 6 CI checks passing
- JIRA: KAN-246 (Epic), KAN-247, KAN-248, KAN-249, KAN-318, KAN-319 → Done

### Key Facts
- Alembic head: `c870473fe107` (migration 022 — QuantStats columns + rebalancing_suggestions)
- Backend tests: 1296 unit + API
- Frontend tests: 329
- Internal tools: 25 + 4 MCP adapters (PortfolioAnalyticsTool added)
- Docker: Postgres 5433, Redis 6380, Langfuse 3001+5434
- User: vipul@example.com / TestPass123! (97 positions, $41K portfolio value)
- Dependencies added: pandas-ta-openbb, quantstats, pyportfolioopt (+ scipy, statsmodels, cvxpy, scikit-learn)

### Critical Learnings (Session 81)
- Column case matters: DataFrame has "Adj Close" not "adj_close" — passed all unit tests but silently null in production
- `importlib.metadata` must be imported before `import pandas_ta` — pandas-ta-openbb bug, needs `noqa: F401`
- QuantStats returns NaN/Inf for edge cases — always use `math.isfinite()` guard
- `qs.stats.calmar()` returns inf when drawdown is 0 — must isolate in own try/except
- PyPortfolioOpt `weight_bounds=(0, max_w)` infeasible when `max_w * n < 1` — use `max(max_w, 1/n)`
- Raw SQL INSERT in migrations must include `id` column with `gen_random_uuid()` when no server_default
- SPY benchmark data needs explicit refresh in pipeline — seeding stocks row alone is not enough
- Pre-existing bugs surface when new code depends on them: `snapshot_date` was never caught because try/except swallowed the AttributeError
