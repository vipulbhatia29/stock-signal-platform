# Test Suite Overhaul — Specification

**Epic:** Phase D — Test Infrastructure Overhaul
**Date:** 2026-04-01
**Status:** Reviewed — 4-expert panel (QA Architect, Security Engineer, DevOps/CI, Frontend/UX)
**Review:** 10 CRITICAL, 19 IMPORTANT, 8 MINOR findings — all CRITICAL/IMPORTANT incorporated below
**Author:** Claude (Opus 4.6) + PM (Vipul)

---

## 1. Problem Statement

The stock-signal-platform has 1625 tests (1296 backend + 329 frontend) built incrementally over 82 sessions. The test suite has served us well but now has structural issues:

1. **No test pyramid** — flat organization, no tiered execution strategy
2. **Playwright E2E exists but never runs in CI** — 7 specs sitting idle
3. **No coverage reporting in CI** — `pytest-cov` installed, `fail_under=80` configured, but CI never passes `--cov`
4. **No parallel execution** — 1296 backend tests run sequentially
5. **No performance testing** — Chrome DevTools MCP + Lighthouse available but unused
6. **No visual regression** — Recharts + navy theme are fragile to CSS drift
7. **Frontend test pyramid is inverted** — 43 component tests, 1 page test, 0 integration tests
8. **No domain/business invariant tests** — financial calculations not fuzz-tested
9. **No cache testing** — Redis TTL, invalidation, stampede patterns untested
10. **No quality gates beyond lint** — no SAST, no dependency audit, no complexity gates in CI
11. **Dead weight** — 5 test files test third-party behavior (Pydantic construction, string operations)
12. **CI runs all tests on every PR** — no path-based filtering

## 2. Goals

1. **Tiered test architecture** with clear run-when rules
2. **Path-based CI routing** — only run what's affected
3. **Eliminate zero-value tests**, upgrade shallow tests
4. **Add missing test categories**: domain invariants (Hypothesis), cache tests, regression snapshots, Playwright E2E expansion, Lighthouse performance, memory leak detection
5. **Quality gates** that block merges: SAST (Semgrep), dependency audit, type checking, coverage
6. **Sprint-end coverage reporting** — no hooks, no noise, part of closeout discipline
7. **Custom Semgrep rules** encoding our 10 Hard Rules as permanent guardrails
8. **Visual regression infrastructure** (git-lfs) — baseline capture deferred until UI is stable

## 3. Decisions Made

| Question | Decision | Rationale |
|----------|----------|-----------|
| Hypothesis depth | Deep (50+ properties) | Financial calculations are core product — fuzz everything |
| Visual regression storage | git-lfs | Prevents repo bloat as UI evolves |
| Visual regression baselines | Deferred (Phase 2) | UI is currently broken; fix first, snapshot after |
| Semgrep custom rules | Yes — encode Hard Rules | Ruff can't express semantic patterns like `str(e)` in HTTPException |
| Coverage hook | None — sprint-end reporting | Coverage checks mid-sprint are noise; report at PR time |
| Contract testing (Pact) | Skip | Single-consumer monorepo doesn't need it |
| Percy/Chromatic | Skip | Playwright `toHaveScreenshot()` is sufficient |
| TestSprite MCP | Skip | Too new; Claude + Serena already generates good tests |

## 4. Tier Architecture

### T0: Pre-commit (local, < 30s)

Runs on every commit via git pre-commit hook.

| Check | Tool |
|-------|------|
| Python lint + format | `ruff check --fix && ruff format` |
| TypeScript lint | `eslint` (frontend) |
| Fast unit tests | `pytest -m pre_commit -q` |
| No secrets | `gitleaks` (local) |

### T1: Unit Tests (CI per-PR, < 2 min)

Pure logic tests. No I/O, no real services. Mocked dependencies.
**IMPORTANT: xdist is ONLY for unit tests** — API/integration tests run sequentially to avoid shared-DB race conditions.

| Config | Value |
|--------|-------|
| Runner | `pytest tests/unit/ -n auto -m "not domain and not regression" --randomly-seed=last -q --timeout=30` |
| New packages | `pytest-xdist`, `pytest-randomly`, `pytest-timeout` |
| Path trigger | `backend/**`, `tests/unit/**`, `tests/conftest.py`, `pyproject.toml`, `uv.lock` |
| Excludes | `domain` and `regression` markers (owned by T5) |
| Note | `pytest-randomly` uses fixed seed in CI (`--randomly-seed=12345`), random seed in weekly cron for flake detection |

### T2: API + Integration (CI per-PR, < 3 min)

Real Postgres + Redis via CI service containers (NOT testcontainers — avoids Docker-in-Docker overhead on GHA).
Testcontainers reserved for local dev only.

| Config | Value |
|--------|-------|
| Runner | `pytest tests/api/ tests/integration/ --timeout=60` (NO xdist — sequential for DB isolation) |
| Path trigger | `backend/**`, `tests/api/**`, `tests/integration/**`, `tests/conftest.py` |
| Services | TimescaleDB (CI service container), Redis (CI service container) |
| Includes | Auth endpoint tests (KAN-354), cache behavior tests, rate limiting, IDOR authorization matrix, Celery task tests, NDJSON streaming tests |

### T3: E2E + Visual (CI on develop merge OR frontend changed, < 8 min)

Playwright browser tests against **production build** (`next build && next start`), not dev server.

| Config | Value |
|--------|-------|
| Runner | `npx playwright test` |
| Build | `cd frontend && npm run build && npm start` (NOT `npm run dev`) |
| Path trigger | `frontend/**` changed OR merge to develop |
| Browsers | Chromium only |
| Includes | All page tests, chart sizing, breadcrumbs, no-leak-on-screen, responsive breakpoints |
| Phase 2 | `toHaveScreenshot()` baselines after UI stabilization |
| Caching | `actions/cache@v4` for `~/.cache/ms-playwright` (saves ~30-60s per run) |
| Note | PR runs: smoke subset (~15 tests, < 3 min). Full 150 tests on develop merge. |

#### Recharts Testing Constraints
- **Jest**: test data transformation, color mapping, prop passing. Never test visual layout (jsdom has no layout engine).
- **Playwright**: test sizing, CLS, tooltip content, animation completion, responsive behavior.
- All Playwright chart specs MUST disable Recharts animations (`isAnimationActive={false}`) or wait for animation completion via `page.waitForFunction()`.
- ResponsiveContainer renders 0x0 in jsdom — chart sizing is Playwright-only.

### T4: Performance + Memory (nightly, < 10 min)

Lighthouse audits and memory leak detection. All thresholds calibrated against `next build` (production mode).

| Config | Value |
|--------|-------|
| Lighthouse | `playwright-lighthouse` for authenticated pages + `@lhci/cli --collect.numberOfRuns=3` (median) |
| Memory | CDP heap tracking via Playwright (NOT MemLab — avoids duplicate Chrome install) |
| Schedule | `0 4 * * 1-5` (4am UTC, weekdays only — saves GHA quota) |
| Cost | ~10 min/run × 22 runs/month = ~220 min/month (11% of free GHA quota) |
| Thresholds | See Section 7 |

### T5: Domain + Regression (CI per-PR, < 1 min)

Financial invariants, signal golden datasets, API shape snapshots. Separated from T1 to avoid busting T1's 2-min budget.

| Config | Value |
|--------|-------|
| Runner | `pytest tests/unit/ -m "domain or regression" -q --timeout=30` |
| Hypothesis | `@settings(max_examples=20)` in CI, `@settings(max_examples=200)` in nightly profile |
| New packages | `hypothesis`, `syrupy` |
| Path trigger | `backend/**` (any backend change) |
| Includes | Property-based tests, golden signal datasets, snapshot regression, security header snapshots |

## 5. Path-Based CI Routing

Using `dorny/paths-filter@v3` in GitHub Actions:

```yaml
filters:
  backend:
    - 'backend/**'
    - 'tests/unit/**'
    - 'tests/api/**'
    - 'tests/integration/**'
    - 'tests/conftest.py'
    - 'pyproject.toml'
    - 'uv.lock'
  frontend:
    - 'frontend/**'
  auth:
    - 'backend/routers/auth.py'
    - 'backend/services/google_oauth.py'
    - 'backend/services/email.py'
    - 'backend/services/token_blocklist.py'
    - 'backend/dependencies.py'
    - 'backend/models/user.py'
    - 'backend/models/oauth_account.py'
    - 'backend/config.py'
    - 'backend/rate_limit.py'
    - 'frontend/src/app/auth/**'
    - 'frontend/src/app/(authenticated)/account/**'
  pipeline:
    - 'backend/pipeline/**'
    - 'backend/tasks/**'
  migrations:
    - 'backend/migrations/**'
    - 'alembic.ini'
  infra:
    - '.github/workflows/**'
    - 'docker-compose*.yml'
    - 'backend/config.py'
    - 'scripts/**'
```

**Routing rules:**
- `infra` changed → run EVERYTHING
- `backend` only → T1 + T2 + T5
- `frontend` only → Frontend Jest + T3 (E2E smoke)
- `backend` AND `frontend` → T1 + T2 + T3 + T5
- `migrations` → Migration consistency tests (pytest-alembic)
- Merge to `develop` → Full T1-T5
- `ci-gate` job with `if: always()` — **the ONLY required check in branch protection**
- `ci-gate` logic: `skipped` = pass, `failure` = fail, `cancelled` = fail
- Quality gates rolled out in phases: Sprint 2 adds as optional, Sprint 4 promotes to required via ci-gate

## 6. Existing Test Cleanup

### DELETE (5 files)

| File | Reason |
|------|--------|
| `frontend/src/__tests__/health-grade-badge.test.tsx` (root) | Duplicate of `components/` version |
| `tests/unit/test_ohlc_schema.py` | Tests Pydantic construction, not our code |
| `tests/unit/routers/test_pagination.py` | Tests `PaginatedResponse(total=0).total == 0` |
| `tests/unit/routers/test_cache_extension.py` | Tests `"app:recommendations".startswith("app:")` — string literals |
| `tests/unit/chat/test_chat_models.py` | Tests ORM attribute assignment, no custom logic |

### CONSOLIDATE (4 merges)

| From | Into |
|------|------|
| `test_fundamentals.py` + `test_fundamentals_tool.py` | `test_fundamentals.py` |
| 4 observability agent test files | `test_agent_observability.py` |
| `test_signals.py` + `test_signal_engine_hardening.py` | `test_signals.py` |
| Root `health-grade-badge.test.tsx` edge case | `components/health-grade-badge.test.tsx` |

### UPGRADE (8 files — deepen assertions)

| File | Current Problem | Target |
|------|----------------|--------|
| `frontend/.../price-chart.test.tsx` | Only checks button text exists | Test period switching, loading state, empty data |
| `frontend/.../portfolio-drawer.test.tsx` | Only checks height=0 when closed | Test open/close callbacks, data rendering |
| `frontend/.../message-bubble.test.tsx` | Asserts raw markdown string | Test rendered HTML output, alignment CSS |
| `tests/e2e/.../home.spec.ts` | Pure `toBeVisible()` smoke | Test zone content, refresh action, chart render |
| `tests/e2e/.../network-error.spec.ts` | `body.not.toBeEmpty()` | Test specific error message content |
| `tests/e2e/.../screener.spec.ts` | Page loads + table has row | Test sorting, filtering, navigation |
| `tests/unit/.../test_observability_writer.py` | 550 lines of repeated setup | Extract shared fixture, cut to ~200 lines |
| `tests/unit/.../test_observability_queries.py` | Over-mocked with call-order dispatch | Use consistent helper or move to integration |

## 7. Performance Thresholds

All thresholds calibrated against `next build && next start` (production mode), NOT `next dev`.

### Lighthouse (authenticated pages)

| Metric | Error Threshold | Warn Threshold |
|--------|----------------|----------------|
| LCP | > 3.5s | > 2.5s |
| FCP | > 2.5s | > 1.8s |
| CLS | > 0.15 | > 0.1 |
| INP | > 350ms | > 200ms |
| Performance score | < 50 | < 60 |
| Accessibility score | < 90 | < 95 |

### Lighthouse (public pages — login, register)

| Metric | Error Threshold | Warn Threshold |
|--------|----------------|----------------|
| LCP | > 2.5s | > 2.0s |
| FCP | > 1.8s | > 1.5s |
| Performance score | < 70 | < 80 |
| Accessibility score | < 90 | < 95 |

### Chart Sizing (UX rules — Tufte/Few)

**Desktop (viewport ≥ 1024px):**

| Element | Minimum Size |
|---------|-------------|
| Pie/donut chart | 250 x 250 px |
| Bar/line chart height | 280 px |
| Composed chart (price + volume) | 350 px height |
| Bar/line chart width | 300 px |
| Sparkline | 50 x 20 px |
| Chart-to-viewport ratio (single focus) | ≥ 60% width |
| Chart-to-viewport ratio (2-column) | ≥ 45% width each |

**Mobile (viewport < 768px):**

| Element | Minimum Size |
|---------|-------------|
| Pie/donut chart | 200 x 200 px (tooltip-only labels, no outer labels) |
| Bar/line chart height | 200 px |
| Composed chart (price + volume) | 280 px height |

### Bundle Size (frontend)

| Metric | Error Threshold | Warn Threshold |
|--------|----------------|----------------|
| Total JS (gzipped) | > 500 KB | > 400 KB |
| Measured via | `next build` output parsing | — |

### Memory (nightly)

| Metric | Error Threshold | Warn Threshold |
|--------|----------------|----------------|
| Heap growth after 5 navigation cycles | > 20 MB | > 10 MB |

## 8. New Packages

### Backend (Python)

| Package | Purpose | pytest marker |
|---------|---------|---------------|
| `pytest-xdist` | Parallel test execution via `-n auto` | — |
| `pytest-randomly` | Randomize test order | — |
| `pytest-timeout` | Kill hung tests (default 30s) | — |
| `hypothesis` | Property-based testing | `@pytest.mark.domain` |
| `syrupy` | API response snapshot regression | `@pytest.mark.regression` |
| `fakeredis[lua]` | In-memory Redis for unit tests | — |
| `pytest-alembic` | Migration up/down/consistency | `@pytest.mark.migration` |

### Frontend (Node.js)

| Package | Purpose |
|---------|---------|
| `playwright-lighthouse` | Lighthouse inside Playwright tests |
| `@lhci/cli` | Lighthouse CI for GitHub Actions |
| `msw` | Mock Service Worker for component integration tests |
| `jest-axe` | Component-level accessibility assertions |

### CI (GitHub Actions)

| Tool | Purpose |
|------|---------|
| `dorny/paths-filter@v3` | Path-based job routing |
| `returntocorp/semgrep-action@v1` | SAST scanning |
| `gitleaks/gitleaks-action@v2` | Secret detection |
| `pypa/gh-action-pip-audit@v1.1.0` | Python dependency CVE scanning |
| `google/osv-scanner-action` | Second-opinion vulnerability scanner (OSV database) |

## 9. Custom Semgrep Rules

File: `.semgrep/stock-signal-rules.yml`

**Hard Rule enforcement (8 rules):**

| Rule ID | Pattern | Hard Rule |
|---------|---------|-----------|
| `no-str-exception-in-response` | `HTTPException(detail=str(...))` or `ToolResult(error=str(...))` | #10 |
| `no-str-exception-in-httpexception` | `raise HTTPException(detail=str($E))` | #10 |
| `async-endpoints-only` | `@app.get/post/put/delete` + `def` (not `async def`) | #5 |
| `no-pip-install` | `subprocess.run(["pip", ...])` or `pip install` in comments/strings | #1 |
| `no-mutable-module-state` | Module-level `list()`, `dict()`, `set()` assignments (not `Final`/`const`) | #7 |
| `no-secrets-in-code` | Hardcoded JWT secrets, API keys, passwords | #4 |
| `no-stack-trace-in-response` | `traceback.format_exc()` passed to response | #10 |
| `no-file-path-in-error` | `__file__` or `os.path` in HTTPException detail | #10 |

**Auth/JWT/OAuth security rules (6 rules):**

| Rule ID | Pattern | Risk |
|---------|---------|------|
| `jwt-no-algorithm-pinning` | `jwt.decode(token, key)` without `algorithms=` kwarg | Algorithm confusion (CVE-2022-29217) |
| `jwt-verify-disabled` | `jwt.decode(..., options={"verify_signature": False})` | Signature bypass |
| `no-timing-unsafe-secret-compare` | `==` or `!=` on tokens/secrets (must use `hmac.compare_digest`) | Timing attack |
| `no-open-redirect` | `RedirectResponse(url=<user-input>)` without validation | Open redirect |
| `cookie-missing-secure-flag` | `set_cookie(...)` without `secure=True` in production | Cookie theft |
| `no-unbounded-redis-key` | `redis.set(f"...{user_input}...")` with unsanitized input | Redis key injection |

**Testing the rules:** `tests/semgrep/` directory with intentionally-bad code snippets + `semgrep --test` in CI.

## 10. Quality Gates (CI merge blockers)

| Gate | Tool | Blocks Merge? |
|------|------|---------------|
| Python lint + format | ruff | Yes |
| TypeScript lint | eslint | Yes |
| Python type check | pyright (basic → standard over time) | Yes (after baseline clean) |
| Unit tests (T1) | pytest + xdist | Yes |
| API tests (T2) | pytest | Yes |
| Coverage ≥ 80% | pytest-cov | Yes |
| Semgrep SAST | semgrep (OWASP + custom) | Yes |
| Secret detection | gitleaks | Yes |
| Dependency audit | pip-audit + osv-scanner + npm audit --audit-level=high | Yes |
| Cyclomatic complexity | ruff C901 (max=10) | Yes (already configured) |
| Migration consistency | pytest-alembic | Yes (when migrations change) |
| E2E smoke | Playwright | Yes (on develop merge) |
| Lighthouse scores | @lhci/cli | Warn only (nightly) |
| Memory leaks | CDP heap tracking (Playwright) | Warn only (nightly) |
| Bundle size | `next build` output (JS < 500KB gzipped) | Yes |

## 11. Playwright E2E Expansion Plan

### Current: 7 specs (~20 tests)

```
auth/login.spec.ts, auth/logout.spec.ts
chat/chat.spec.ts
dashboard/home.spec.ts, dashboard/navigation.spec.ts
stocks/screener.spec.ts
errors/network-error.spec.ts
```

### Target: ~40 specs

**Auth flows (8 specs):**
- login.spec.ts (upgrade existing)
- logout.spec.ts (keep)
- register.spec.ts (new)
- google-oauth.spec.ts (new — mock OAuth redirect)
- forgot-password.spec.ts (new)
- reset-password.spec.ts (new)
- email-verification.spec.ts (new)
- account-settings.spec.ts (new — password change, Google link/unlink, delete)

**Dashboard (6 specs):**
- home.spec.ts (upgrade — test all 5 zones, chart sizing)
- navigation.spec.ts (upgrade — test breadcrumbs on every page)
- dashboard-refresh.spec.ts (new — refresh button triggers reload)
- dashboard-responsive.spec.ts (new — 4 viewport breakpoints)
- dashboard-charts.spec.ts (new — chart sizing, CLS, no overflow)
- dashboard-no-leaks.spec.ts (new — no backend output/stack traces in DOM)

**Portfolio (6 specs):**
- portfolio-list.spec.ts (new)
- portfolio-detail.spec.ts (new)
- portfolio-positions.spec.ts (new)
- portfolio-allocation-chart.spec.ts (new — pie chart ≥ 200x200)
- portfolio-transactions.spec.ts (new)
- portfolio-analytics.spec.ts (new)

**Stocks (5 specs):**
- screener.spec.ts (upgrade — sorting, filtering, pagination)
- stock-detail.spec.ts (new — tabs, signal display)
- stock-analytics.spec.ts (new — analytics card)
- stock-fundamentals.spec.ts (new)
- watchlist.spec.ts (new)

**Chat (3 specs):**
- chat.spec.ts (keep)
- chat-streaming.spec.ts (new — NDJSON streaming visual)
- chat-agent-tools.spec.ts (new — tool execution display)

**Admin (2 specs):**
- command-center.spec.ts (new — 4 zone panels render)
- admin-actions.spec.ts (new — verify user, recover account)

**Cross-cutting (4 specs):**
- accessibility.spec.ts (new — axe-core on all pages)
- no-backend-leaks.spec.ts (new — scan DOM for stack traces, file paths, SQL)
- performance-lighthouse.spec.ts (new — Lighthouse thresholds)
- memory-leaks.spec.ts (new — CDP heap tracking after navigation cycles)

**Visual regression (6 specs — Phase 2, after UI stable):**
- visual-login.spec.ts
- visual-dashboard.spec.ts
- visual-portfolio.spec.ts
- visual-screener.spec.ts
- visual-stock-detail.spec.ts
- visual-chat.spec.ts

## 12. Hypothesis Property Tests (Deep)

### Signal Engine (~15 properties)

| Property | Invariant |
|----------|-----------|
| RSI bounded | `0 ≤ RSI ≤ 100` for any price series |
| RSI constant prices | RSI = 50 (or NaN) when all prices identical |
| Bollinger ordering | `upper ≥ middle ≥ lower` always |
| Bollinger middle = SMA | Middle band equals SMA(period) |
| MACD signal smoothing | Signal line is EMA of MACD line |
| SMA window size | SMA(1) = close prices |
| Composite score bounded | `0 ≤ score ≤ 10` |
| Composite pairwise dominance | If A dominates B on all input dimensions, score(A) ≥ score(B) |
| Signal NaN guard | No NaN/Inf in output for any finite input |
| Warmup period | First `period` values are NaN/None, rest are populated |

### Portfolio Math (~15 properties)

| Property | Invariant |
|----------|-----------|
| Weights sum to 1 | For any rebalancing output |
| Unrealized P&L correctness | `unrealized_pnl = current_value - cost_basis` for each position |
| Portfolio value ≥ 0 | Long-only portfolio |
| FIFO cost basis | Average cost tracks running weighted average |
| Volatility annualization | `annual_vol = daily_vol × √252` |
| Return annualization | `annual_return = (1 + daily_return)^252 - 1` |
| Sharpe is finite | For any non-degenerate return series |
| Sharpe scaling invariant | `sharpe(k * returns, rf=0) = sharpe(returns, rf=0)` for k > 0 |
| Partial sell cost basis | After partial sell, remaining lots' cost basis is preserved |
| Sortino uses downside only | Sortino ≥ Sharpe when positive skew |
| Max drawdown ≤ 0 | By definition |
| Calmar Inf guard | Calmar when drawdown = 0 → capped, not Inf |
| Weight bounds feasible | `max_weight ≥ 1/n_assets` |
| Rebalancing preserves value | Total portfolio value unchanged by rebalancing |
| Dividend reinvestment | Share count increases, cost basis adjusts |

### QuantStats (~10 properties)

| Property | Invariant |
|----------|-----------|
| All metrics finite | No NaN/Inf for any bounded return series |
| Volatility ≥ 0 | By definition |
| Win rate ∈ [0, 1] | Percentage |
| Profit factor > 0 | When gains and losses both exist |
| Monthly returns sum | ~= total return (approximate) |
| Benchmark comparison | Alpha = portfolio_return - benchmark_return (approximate) |
| Empty series handling | Graceful None/NaN, never exception |
| Single-day series | Returns 0 or None for all metrics |
| Timezone normalization | UTC conversion doesn't change values |
| Negative-only returns | All metrics still computable |

### Recommendation Engine (~10 properties)

| Property | Invariant |
|----------|-----------|
| Score → action mapping | BUY ≥ 8, WATCH ≥ 5, AVOID < 5 |
| Divestment rules fire | Holdings violating rules always flagged |
| Portfolio-aware dedup | Never recommend stocks already held |
| Recommendation count bounded | ≤ configured limit |
| Reason string non-empty | Every recommendation has explanation |
| Priority ordering | Higher composite score → earlier in list |
| Sector diversity | Max sector concentration enforced |
| Risk tolerance respected | Conservative → lower volatility picks |
| Fresh data requirement | Stale signals (> 7 days) excluded |
| Idempotent recomputation | Same inputs → same recommendations |

## 13. Cache Tests

### Unit tests (fakeredis)

| Test | What it verifies |
|------|------------------|
| TTL set correctly | Every cached key has expected TTL |
| Cache-aside pattern | Miss → DB fetch → cache populated → next call hits cache |
| Write-through invalidation | DB write updates cache atomically |
| Pattern invalidation | `user:{id}:*` clears all user cache keys |
| Graceful Redis down | `get_current_user` returns DB fallback when Redis unreachable |
| CachedUser serialization | JSON roundtrip preserves all fields including `email_verified`, `has_password` |
| Token blocklist | Revoked token detected, non-revoked passes |

### Integration tests (real Redis)

| Test | What it verifies |
|------|------------------|
| TTL actually expires | Key gone after TTL elapses |
| Concurrent cache miss | Only 1 DB call under stampede (mutex) |
| Cache hit ratio | > 75% for hot-path access patterns |
| Redis reconnect | After brief outage, client reconnects automatically |

## 14. Security Test Matrix

### IDOR / Cross-User Authorization (~15 tests, T2)

Every detail/write endpoint must have a test where User A's token attempts to access User B's resource.

| Endpoint | Test |
|----------|------|
| `GET /api/v1/portfolio/{id}` | User A cannot read User B's portfolio |
| `PUT /api/v1/portfolio/{id}` | User A cannot modify User B's portfolio |
| `DELETE /api/v1/watchlist/{id}` | User A cannot delete User B's watchlist item |
| `GET /api/v1/chat/sessions/{id}` | User A cannot read User B's chat history |
| `PUT /api/v1/preferences` | User A cannot modify User B's preferences |
| `GET /api/v1/alerts` | User A cannot see User B's alerts |
| `DELETE /api/v1/alerts/{id}` | User A cannot delete User B's alerts |
| Admin verify-email | Non-admin gets 403 |
| Admin recover-account | Non-admin gets 403 |

### Token Security (~8 tests, T2)

| Test | What it verifies |
|------|------------------|
| Revoked token + Redis up | Request rejected with 401 |
| Revoked token + Redis DOWN on /refresh | Request REJECTED (fail-closed, NOT fail-open) |
| Logout + Redis DOWN | Logout returns success but token not actually blocklisted (known limitation, logged) |
| JWT with tampered payload | Rejected (signature verification) |
| JWT with weak algorithm (none/HS256 when RS256 expected) | Rejected |
| Expired access token | 401 |
| Refresh token rotation | Old refresh token invalidated after use |

### OAuth State CSRF (~4 tests, T2 + T3)

| Test | What it verifies |
|------|------------------|
| Missing state parameter | Returns error |
| Reused state parameter | Returns error (replay prevention) |
| State from different session | Returns error |
| Valid state + nonce | Succeeds |

### Rate Limiting (~6 tests, T2)

| Endpoint | Threshold | Test |
|----------|-----------|------|
| Login | 5/minute | 6th attempt returns 429 with Retry-After header |
| Register | 3/minute | 4th attempt returns 429 |
| Forgot password | 3/hour per email | 4th attempt for same email returns 429 |
| Rate limit isolation | — | User A's rate limit does not affect User B |

### Email Verification Bypass (~3 tests, T2)

| Test | What it verifies |
|------|------------------|
| Unverified user cannot create portfolio | 403 |
| Unverified user cannot create watchlist | 403 |
| Same verification token cannot be reused | Error on second attempt |

### Soft-Delete Data Isolation (~4 tests, T2)

| Test | What it verifies |
|------|------------------|
| Deleted user's portfolios inaccessible via API | 404 or empty |
| Anonymized email not in any list response | No `deleted_*@removed.local` |
| Deleted user's OAuth accounts removed | No provider_email leak |
| Login attempt history isolated | Other users can't see |

### No-Backend-Leaks (expanded, T3)

Beyond DOM scanning, also test:
- Intercept network responses: scan JSON bodies for `Traceback`, `File "`, `sqlalchemy`, `pydantic`
- Check `X-Powered-By` and `Server` headers absent or generic
- Check `console.error` messages contain no file paths or stack traces
- Verify source maps not served (request `.map` files → assert 404)

### Security Header Regression (T5, syrupy)

Snapshot all security response headers: `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security`, `X-XSS-Protection`. Any change triggers review.

### OWASP Top 10 Coverage Map

| OWASP | Coverage | Where |
|-------|----------|-------|
| A01: Broken Access Control | IDOR matrix + email verification bypass | S14, Sprint 4 |
| A02: Cryptographic Failures | JWT algorithm tests, bcrypt rounds check | S14, Sprint 4 |
| A03: Injection | Semgrep SQL injection rules + NDJSON streaming test | S9, Sprint 2 |
| A04: Insecure Design | Rate limiting + account lockout tests | S14, Sprint 4 |
| A05: Security Misconfiguration | CORS test, debug mode check, security header snapshot | Sprint 3-4 |
| A06: Vulnerable Components | pip-audit + osv-scanner + npm audit | S10, Sprint 2 |
| A07: Auth Failures | Token security + OAuth state + rate limiting | S14, Sprint 4 |
| A08: Data Integrity Failures | JWT tampering test + Semgrep algorithm rule | S14, Sprint 4 |
| A09: Logging Failures | Verify login failures and permission denials are logged | Sprint 4 |
| A10: SSRF | Semgrep rule for redirect URL validation | S9, Sprint 2 |

## 14b. Celery Task Tests

| Test Category | Tests |
|---------------|-------|
| Task invocation (eager mode) | Each task callable with valid inputs, returns expected shape |
| Error handling | Task with invalid input raises, does not silently swallow |
| Fire-and-forget paths | Import paths verified (no masked import bugs) |
| Integration (real worker) | Key tasks produce correct DB state after execution |
| Hypothesis | Any task invoked with valid inputs never raises unhandled exception |

Covers: `audit.py`, `portfolio.py`, `market_data.py`, `recommendations.py`, `alerts.py`, `forecasting.py`, `evaluation.py`, `warm_data.py`

## 14c. Frontend Component Integration Tests (msw)

Add ~15 tests using Mock Service Worker (msw) instead of mocking hooks directly.
These render real component trees with network-level mocking, catching shape mismatches.

| Test | What it catches |
|------|----------------|
| Dashboard zones with real hook → real API shape | Field rename bugs (e.g., `name` → `company_name`) |
| Portfolio summary with real data flow | Missing null guards on optional fields |
| Stock detail tabs with real API response | Tab content rendering with actual data shapes |
| Auth pages with real error responses | Error message rendering from API errors |

New package: `msw` (Mock Service Worker)

Shared test utility: `renderWithProviders()` wrapping QueryClientProvider + mocked next/navigation + auth context.

## 14d. Coverage Configuration

```toml
# pyproject.toml additions
[tool.coverage.run]
source = ["backend"]
omit = [
    "backend/migrations/*",
    "backend/__init__.py",
    "backend/*/__init__.py",
]
```

## 15. Sprint Plan

### Sprint 1: Foundation + Cleanup
- Delete 5 dead test files
- Consolidate 4 file groups
- Add `pytest-xdist`, `pytest-randomly`, `pytest-timeout`
- Add `fakeredis[lua]`, `hypothesis`, `syrupy`
- Add `msw` + `jest-axe` to frontend dev deps
- Configure new pytest markers: `domain`, `regression`, `migration`, `cache`
- Configure coverage omit list in `pyproject.toml`
- Set up git-lfs for `*.png` in `tests/e2e/playwright/`
- Refactor `test_observability_writer.py` (extract fixture)
- Create shared `renderWithProviders()` test utility (frontend)
- Create shared `next-navigation.ts` mock (frontend)

### Sprint 2: CI Overhaul
- Rewrite `.github/workflows/ci-pr.yml` with `dorny/paths-filter`
- Add `ci-gate` job (single required check, `skipped` = pass)
- Add `pytest --cov --cov-report=json` to CI (coverage enforcement)
- Add `pyright` type checking job (basic mode — optional at first)
- Add `pip-audit` + `osv-scanner` + `npm audit` jobs
- Add `gitleaks` + Semgrep jobs
- Write `.semgrep/stock-signal-rules.yml` (14 custom rules: 8 Hard Rules + 6 auth/JWT)
- Create `tests/semgrep/` with bad-code snippets for rule testing
- Add `pytest-alembic` migration consistency job (up/down/data-preservation)
- Add Playwright browser caching (`actions/cache@v4` for `~/.cache/ms-playwright`)
- Add coverage + Lighthouse artifact uploads
- Bundle size gate (`next build` output parsing)
- Change Playwright webServer to `next build && next start`
- Quality gates added as OPTIONAL (not required) — promoted in Sprint 4

### Sprint 3: Domain + Cache + Regression Tests (parallelizable with Sprint 4)
- Hypothesis property tests: signal engine (~15)
- Hypothesis property tests: portfolio math (~16, including partial-sell cost basis)
- Hypothesis property tests: QuantStats (~10)
- Hypothesis property tests: recommendation engine (~10)
- Golden dataset tests: RSI, MACD, Bollinger (reference data from TA-Lib)
- Cache unit tests (fakeredis) — including token blocklist fail-closed on /refresh
- Cache integration tests (real Redis)
- API response snapshot tests (syrupy) for major endpoints
- Security header regression snapshots (syrupy)
- Celery task tests (eager mode + integration)
- Concurrent portfolio transaction race condition tests

### Sprint 4: Auth + Security Test Suite (KAN-354 + KAN-355)
- API tests for 14 auth endpoints (~42 tests)
- IDOR / cross-user authorization matrix (~15 tests)
- Token security tests (~8 tests, including Redis-down fail-closed)
- OAuth state CSRF tests (~4 tests)
- Rate limiting tests with threshold assertions (~6 tests)
- Email verification bypass tests (~3 tests)
- Soft-delete data isolation tests (~4 tests)
- Security audit logging verification
- Frontend Jest tests for auth pages (~12 tests)
- Upgrade 3 shallow frontend component tests
- Add `jest-axe` to all component tests (`toHaveNoViolations()`)
- Promote quality gates from optional → required via ci-gate

### Sprint 5: Playwright E2E Expansion + Component Integration
- **E2E specs:**
  - Auth flow specs (8 new)
  - Dashboard specs (6 new/upgraded)
  - Portfolio specs (6 new)
  - Stock specs (5 new/upgraded)
  - Chat specs (2 new)
  - Admin specs (2 new)
  - Cross-cutting: no-backend-leaks (expanded: DOM + network + headers + console + sourcemaps), accessibility
- **Component integration tests (msw, ~15 tests):**
  - Dashboard zones, portfolio summary, stock detail, auth pages
- **Next.js App Router patterns:**
  - loading.tsx / error.tsx boundary tests
  - Server component identification (Playwright-only)

### Sprint 6: Performance + Memory
- Install `playwright-lighthouse`, `@lhci/cli`
- Lighthouse specs for authenticated + public pages (3x median via `numberOfRuns=3`)
- Chart sizing assertion specs (desktop + mobile thresholds)
- CDP heap tracking spec (< 20MB growth threshold)
- Nightly CI workflow for T4 tier (`0 4 * * 1-5`, weekdays only)
- Responsive breakpoint specs (1920, 1440, 1024, 768)
- All specs run against `next build` (production mode)

### Sprint 7: Visual Regression (Phase 2 — after UI stable)
- Capture baselines with `--update-snapshots`
- 6 visual regression specs
- Update CI to run visual comparison on PRs

## 15. Expected Outcomes

| Metric | Before | After |
|--------|--------|-------|
| Total tests | ~1625 | ~2200+ |
| Backend unit | ~1100 | ~1350 (+ domain/cache/regression/celery, - dead weight) |
| Backend API | ~200 | ~330 (+ auth + security matrix + IDOR + rate limiting) |
| Frontend Jest | 329 | ~360 (+ auth pages, msw integration, jest-axe) |
| Playwright E2E | ~20 | ~150 |
| Performance/Memory | 0 | ~15 |
| Security tests | ~50 (scattered) | ~150 (dedicated matrix + OWASP coverage) |
| CI time (PR, backend-only change) | ~5 min | ~2 min (parallel + path filtering) |
| CI time (PR, frontend-only change) | ~5 min | ~3 min (Jest + E2E smoke) |
| CI time (develop merge) | ~5 min | ~9 min (full T1-T5, parallel jobs) |
| Quality gates | 2 (lint, tests) | 12 (via ci-gate: lint, types, tests, coverage, SAST, secrets, deps, complexity, migration, E2E, Semgrep, bundle size) |
| Coverage enforcement | Configured but not run | 80% enforced in CI (with omit list) |
| Semgrep custom rules | 0 | 14 (8 Hard Rules + 6 auth/JWT) |
| Dead test files | 5 | 0 |

## 16. Non-Goals

- Pact contract testing (single-consumer monorepo)
- Percy/Chromatic SaaS (Playwright screenshots sufficient)
- TestSprite MCP (too new, Claude generates tests fine)
- Storybook (not in our stack)
- Cross-browser testing (Chromium-only sufficient for internal SaaS)
- Load/stress testing (not needed at current scale)
- MemLab (duplicate Chrome install; use Playwright CDP instead)
- Vitest migration (evaluate after overhaul stabilizes — primary benefit: ESM mock elimination + 2-5x speed)

## 17. Dependencies

- Docker (for testcontainers in local dev)
- GitHub LFS enabled on repo
- Semgrep 1.156.0+ (already installed)
- Playwright browsers installed (`npx playwright install chromium`)
- Backend + frontend running locally for E2E tier

## 18. Risks

| Risk | Mitigation |
|------|------------|
| Hypothesis finds real bugs in financial calcs | Good — fix them. Budget time in Sprint 3. |
| Lighthouse scores are noisy in CI | Run 3x median (`numberOfRuns=3`). Warn-only, don't block. |
| pytest-xdist with shared DB causes flaky tests | xdist for T1 (unit) ONLY. T2 (API/integration) runs sequentially. |
| Path-filter misses a dependency | `infra` trigger runs everything. `ci-gate` catches skipped jobs. Develop merge runs full suite. |
| git-lfs requires dev setup | One-time `git lfs install`. Document in onboarding. |
| syrupy snapshots become stale | Update during refactors. Mark as `@pytest.mark.regression`. |
| Pyright basic mode produces many errors day one | Start as optional gate. Fix errors over 2 sprints. Promote to required in Sprint 4. |
| 11 new quality gates block all merges | ci-gate is the ONLY required check. Phased rollout: optional in Sprint 2, required in Sprint 4. |
| T3 exceeds 5-min budget with 150 tests | PR runs smoke subset (~15 tests). Full 150 on develop merge. Target < 8 min. |
| CDP heap tracking false positives | Error > 20MB, Warn > 10MB. Review before acting. |
| Semgrep custom rules silently stop matching | `tests/semgrep/` with bad-code snippets + `semgrep --test` in CI. |
| Recharts animations cause flaky Playwright tests | All chart specs disable animations or wait for completion. |

## 19. Expert Review Log

**Date:** 2026-04-01
**Reviewers:** 4-persona panel (QA Architect, Security Engineer, DevOps/CI, Frontend/UX)

### Critical Findings Addressed
1. xdist + shared DB isolation → xdist unit-only (S4 T1, S18)
2. No IDOR tests → added S14 authorization matrix
3. Token blocklist fails open → added fail-closed test (S14)
4. T5/T1 overlap → T1 excludes domain/regression markers (S4)
5. Sharpe scaling invariant wrong → fixed to rf=0 (S12)
6. Composite monotonicity untestable → pairwise dominance (S12)
7. P&L antisymmetry invalid → unrealized P&L correctness (S12)
8. ci-gate skipped state → explicit handling documented (S5)
9. E2E against next dev → changed to next build (S4 T3)
10. Recharts animation gotchas → constraints subsection (S4 T3)

### Important Findings Addressed
- Celery task tests added (S14b)
- Semgrep expanded 8 → 14 rules (S9)
- osv-scanner added (S8, S10)
- Coverage omit list added (S14d)
- Pyright basic → standard graduated rollout (S10)
- Bundle size gate added (S7, S10)
- Playwright browser caching (S4 T3)
- msw component integration layer (S14c)
- jest-axe for component a11y (Sprint 4)
- Chart sizing split desktop/mobile (S7)
- LCP tightened 4.5→3.5s, accessibility 85→90 (S7)
- Memory threshold tightened 50→20MB (S7)
- T3 time revised 5→8 min (S4 T3)
- Quality gates phased rollout (S5, S15 Sprint Plan)
- App Router testing patterns (Sprint 5)
- Return vs volatility annualization split (S12)
- Path filters: config.py, conftest.py, scripts/ added (S5)
- Security header snapshots (S14, Sprint 3)
- Nightly workflow design (S4 T4)
