# Backend Code Health & Security — KAN-408 Final Spec

**Date:** 2026-04-06
**Tickets:** KAN-412 (router splits), KAN-413 (portfolio service split), KAN-417 (CSRF protection)
**Status:** Design approved

---

## 1. Auth Router Split (KAN-412)

### Problem

`backend/routers/auth.py` is 1,263 lines with 20 endpoints spanning 7 unrelated domains (login, OAuth, OIDC, email verification, password management, admin). This makes navigation, review, and testing harder than necessary.

### Solution

Split into a package with one module per domain:

```
backend/routers/auth/
├── __init__.py              # Re-exports combined `router`, defines __all__
├── core.py                  # register, login, refresh, logout, me (5 endpoints)
├── email_verification.py    # verify-email GET+POST, resend-verification (3 endpoints)
├── password.py              # forgot/reset/change/set-password (4 endpoints)
├── oauth.py                 # google/authorize, google/callback, google/unlink (3 endpoints)
├── oidc.py                  # .well-known, authorize, token, userinfo (4 endpoints)
├── admin.py                 # admin verify-email, admin recover (2 endpoints)
└── _helpers.py              # Shared: cookie set/clear, token TTL, background email/login helpers
```

### Blocklist/revocation imports — direct from `token_blocklist`

`is_blocklisted`, `add_to_blocklist`, and `set_user_revocation` are used across multiple sub-modules (`core.py` for refresh/logout, `password.py` for change-password/reset-password/delete-account). Each sub-module imports these directly from `backend.services.token_blocklist` — **not via `_helpers.py`**.

**Why not consolidate in `_helpers.py`?** Because `mock.patch` must target the lookup site (the module where the function is called). If `_helpers` re-exported and sub-modules did `from backend.routers.auth._helpers import is_blocklisted`, that import would bind `is_blocklisted` into the sub-module's namespace — patching `_helpers.is_blocklisted` would then be a no-op from the sub-module's perspective. The canonical fix is to patch at each sub-module's lookup site.

Mock targets after split:
- `backend.routers.auth.core.is_blocklisted`
- `backend.routers.auth.core.add_to_blocklist`
- `backend.routers.auth.password.set_user_revocation`

### Invariants

- `__init__.py` imports all sub-routers and includes them into a single `router` object. Defines `__all__`.
- `main.py` import unchanged: `from backend.routers.auth import router`.
- All URL paths, response schemas, and auth dependencies unchanged.
- `_helpers.py` exports shared utilities. Dependency flow is one-directional: `_helpers` → sub-routers.
- Tests hit URLs, not router objects — no test import changes needed (except mock paths — see Section 6).

---

## 2. Portfolio Router Reorganization (KAN-412)

### Problem

`backend/routers/portfolio.py` is 776 lines — borderline, but endpoints are tightly coupled around portfolio context. A file split would create artificial boundaries.

### Solution

Keep as single file. Reorder endpoints into logical sections with clear headers:

```
# ── Transactions ─────────────────────────────────────────
# POST /transactions, GET /transactions, DELETE /transactions/{id}

# ── Positions & Holdings ─────────────────────────────────
# GET /positions, GET /dividends/{ticker}

# ── Summary & History ────────────────────────────────────
# GET /summary, GET /history, GET /health/history

# ── Analytics & Health ───────────────────────────────────
# GET /health, GET /analytics, GET /rebalancing

# ── Forecasts ────────────────────────────────────────────
# GET /{portfolio_id}/forecast, GET /{portfolio_id}/forecast/components
```

### Invariants

- No file splits, no import changes, no URL changes.
- Endpoint ordering updated to match logical grouping.

---

## 3. Portfolio Service Split (KAN-413)

### Problem

`backend/services/portfolio_service.py` is 990 lines with 18 methods spanning CRUD, FIFO cost-basis computation, and heavy analytics (QuantStats, PyPortfolioOpt). These are distinct domains with different dependency profiles.

### Solution

Split into a package with one module per domain:

```
backend/services/portfolio/
├── __init__.py       # Re-exports all public functions + test-used privates, defines __all__
├── core.py           # get_or_create_portfolio, get_all_portfolio_ids, get_portfolio_summary,
│                     # get_portfolio_history, get_health_history, snapshot_portfolio_value
├── fifo.py           # _run_fifo, recompute_position, get_positions_with_pnl,
│                     # list_transactions, delete_transaction, _get_transactions_for_ticker
└── analytics.py      # compute_quantstats_portfolio, compute_rebalancing, materialize_rebalancing,
                      # _optimize, _equal_weight_fallback, _safe_round, _group_sectors,
                      # VALID_STRATEGIES
```

### Internal import pattern

Sub-modules import from sibling modules directly (not via `__init__.py`):
- `core.py` imports from `fifo.py` (needs `get_positions_with_pnl` for `get_portfolio_summary`)
- `analytics.py` imports from `fifo.py` (needs `get_positions_with_pnl` for rebalancing)
- `fifo.py` has no sibling imports

Dependency direction: `core → fifo ← analytics` (fan-in on fifo). No circular imports.

### Re-export and private helper policy

`__init__.py` re-exports:
- All public functions (for backward-compatible external imports)
- `_run_fifo`, `_optimize`, `_equal_weight_fallback` — these are algorithmically private but directly imported by 5 test files. Re-exporting avoids mass test import changes. Documented in `__all__` with comment.

`VALID_STRATEGIES` lives in `analytics.py` (single user — no separate `constants.py`).

### Invariants

- `__init__.py` re-exports all public functions + test-used privates — external call sites unchanged.
- `__all__` defined explicitly to make the public API clear.
- Dependency flow is one-directional: `core → fifo ← analytics`. No circular imports.
- Sub-modules import siblings directly, not via `__init__.py`.

---

## 4. CSRF Protection (KAN-417)

### Problem

Cookie-based JWT auth (httpOnly, SameSite=lax) lacks CSRF token protection. SameSite=lax blocks cross-origin POST from third-party sites in modern browsers, but does not protect against subdomain attacks or older browser vulnerabilities.

### Solution

Double-submit cookie pattern, enforced only on cookie-authenticated mutating requests.

### Flow

1. **Token generation:** On login/refresh (any response that sets auth cookies), server also sets a `csrf_token` cookie:
   - Value: 32 bytes, `secrets.token_urlsafe(32)`
   - `httpOnly=False` (frontend must read it via `document.cookie`)
   - `secure=settings.COOKIE_SECURE`, `samesite="lax"`, `path="/"`
   - `max_age` matches access token expiry
2. **Frontend sends token:** `api.ts` reads `csrf_token` from `document.cookie` and attaches `X-CSRF-Token` header on POST/PUT/PATCH/DELETE requests.
3. **Middleware validates:** `CSRFMiddleware` intercepts mutating requests:
   - Authorization header present (case-insensitive `Bearer`) → **skip** (Bearer auth is CSRF-safe)
   - Cookie auth (either `access_token` OR `refresh_token` cookie present) → compare `X-CSRF-Token` header with `csrf_token` cookie value
   - Mismatch or missing → **403 Forbidden** with generic error message
   - **Security note:** The refresh_token cookie alone counts as cookie-auth. Otherwise an attacker with only a refresh cookie could bypass CSRF.
4. **Logout:** `csrf_token` cookie cleared alongside auth cookies.
5. **Refresh:** Exempt from CSRF *checking* (CSRF cookie may have expired with access token), but refresh response *issues* a new CSRF token alongside the new auth cookies.

### Files Changed

| File | Change |
|---|---|
| `backend/middleware/csrf.py` | New — `CSRFMiddleware` class |
| `backend/middleware/__init__.py` | Export `CSRFMiddleware` |
| `backend/routers/auth/_helpers.py` | `_generate_csrf_token()`, updated `_set_auth_cookies()` and `_clear_auth_cookies()` |
| `backend/dependencies.py` | Add `COOKIE_CSRF_TOKEN = "csrf_token"` constant |
| `backend/main.py` | Register CSRF middleware + add `X-CSRF-Token` to CORS `allow_headers` |
| `frontend/src/lib/api.ts` | Read `csrf_token` cookie, attach `X-CSRF-Token` header |

### CORS Integration

`main.py` CORS config must add `X-CSRF-Token` to `allow_headers`:
```python
allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"]
```
Without this, browser CORS preflight will reject all mutating cookie-auth requests.

### Middleware Ordering

Starlette executes middleware in reverse registration order: **last registered = outermost**.

Desired stack (outermost → innermost):
1. `ErrorHandlerMiddleware` — catches all errors
2. `CORSMiddleware` — handles preflight OPTIONS, blocks rejected origins before they reach CSRF
3. `CSRFMiddleware` — enforces CSRF on mutating cookie-auth requests
4. `HttpMetricsMiddleware` — measures processing time

Registration order in `main.py` (first added = innermost):
```python
app.add_middleware(HttpMetricsMiddleware)        # innermost
app.add_middleware(CSRFMiddleware, ...)
app.add_middleware(CORSMiddleware, ...)
app.add_middleware(ErrorHandlerMiddleware)       # outermost
```

### Exempt Paths

The middleware accepts a `csrf_exempt_paths: set[str]` parameter. Default exempt set (pre-auth or non-cookie-auth):

- `/api/v1/auth/login` — pre-auth
- `/api/v1/auth/register` — pre-auth
- `/api/v1/auth/refresh` — CSRF cookie may be expired (but refresh *issues* a new CSRF token)
- `/api/v1/auth/forgot-password` — token-based
- `/api/v1/auth/reset-password` — token-based
- `/api/v1/auth/google/callback` — OAuth state parameter provides CSRF
- `/api/v1/health`, `/api/v1/health/detail` — public (GET-only but exempt for clarity)
- `/docs`, `/openapi.json` — dev tooling

GET/HEAD/OPTIONS requests are always exempt (safe methods).

### Testing

**Unit tests (`tests/unit/middleware/test_csrf.py`):**
- Cookie-only enforcement: request with cookie auth + valid CSRF → pass
- Header-auth bypass: request with Authorization Bearer → skip CSRF
- Missing `X-CSRF-Token` header with cookie auth → 403
- Mismatched token (header ≠ cookie) → 403
- Empty `X-CSRF-Token` header → 403
- Valid token pass-through → 200
- Exempt paths → skip CSRF check
- OPTIONS/HEAD requests → always skip
- CSRF token with URL-safe special characters (`_`, `-`) → pass

**API tests (`tests/api/test_csrf.py`):**
- Login → verify `csrf_token` cookie is SET (non-httpOnly)
- Login → mutating request with correct CSRF token → succeeds
- Login → mutating request without CSRF token → 403
- Refresh → verify new `csrf_token` cookie issued (rotated)
- Logout → verify `csrf_token` cookie cleared
- Delete account with invalid CSRF token → 403 (not deleted)

**Existing test updates:**
- `test_login_cookies_are_httponly` — update to assert httpOnly on `access_token` and `refresh_token` only, explicitly assert `csrf_token` is NOT httpOnly
- `test_login_sets_cookies` — add assertion for `csrf_token` cookie
- `test_refresh_sets_cookies` — add assertion for `csrf_token` cookie
- `test_logout_clears_cookies` — add assertion that `csrf_token` is cleared

### Invariants

- Bearer token API clients work without modification.
- Only browser cookie-auth flow gets CSRF enforcement.
- No server-side state (stateless double-submit pattern).
- CSRF token rotates on each login/refresh (tied to auth cookie lifecycle).

---

## 5. Dependency Map — All Affected Files

### Auth Router Split (KAN-412)

| File | Dependency | Change Required |
|---|---|---|
| `backend/main.py` | `from backend.routers.auth import router` | None — `__init__.py` re-exports `router` |
| `backend/dependencies.py` | Defines `COOKIE_*` constants imported by auth helpers | None — import direction unchanged |
| `tests/api/test_auth.py` | Mocks `backend.routers.auth.is_blocklisted` and `backend.routers.auth.add_to_blocklist` | **Yes** — see Section 6 |
| `tests/api/test_oauth_csrf.py` | Tests OAuth CSRF via URL hits | None — URL-based tests |
| `tests/semgrep/test_rules_ok.py` | References `COOKIE_SECURE` pattern | None |

### Portfolio Service Split (KAN-413)

All external imports use `from backend.services.portfolio import ...`. The `__init__.py` re-exports all public functions, so **no import changes** in consumers. However, **mock patch paths must target the actual module** where the function is defined, not the `__init__.py` re-export.

| File | Import | Mock Path Update? |
|---|---|---|
| `backend/routers/portfolio.py` | Imports `_get_transactions_for_ticker`, `_run_fifo`, `get_or_create_portfolio`, `get_portfolio_history`, `get_portfolio_summary`, `get_positions_with_pnl`, `recompute_position` + aliased imports of `delete_transaction`, `get_health_history`, `list_transactions` | None — re-exports cover it |
| `backend/tools/portfolio.py` | Re-exports 10 symbols including `_get_transactions_for_ticker`, `_group_sectors`, `_run_fifo`, `get_or_create_portfolio`, `get_positions_with_pnl`, `get_portfolio_summary`, `get_portfolio_history`, `recompute_position`, `snapshot_portfolio_value`, `get_all_portfolio_ids` | None — `__init__.py` must re-export `_get_transactions_for_ticker` and `_group_sectors` (and all public names) |
| `backend/tasks/portfolio.py` | `compute_quantstats_portfolio`, `get_all_portfolio_ids`, `materialize_rebalancing`, `snapshot_portfolio_value` | None (no mocks) |
| `backend/tasks/alerts.py` | Lazy import `get_positions_with_pnl` | None (no mocks) |
| `backend/services/pipelines.py` | Lazy import `get_or_create_portfolio`, `get_positions_with_pnl` | None (no mocks) |
| `backend/agents/user_context.py` | Lazy import `get_or_create_portfolio`, `get_positions_with_pnl` | None (no mocks) |
| `tests/unit/services/test_portfolio_service.py` | Direct import of `_run_fifo`, `delete_transaction`, `get_or_create_portfolio`, `get_positions_with_pnl` | None — re-exports cover it. Audit mocks (spec assumes none) |
| `tests/unit/services/test_quantstats_portfolio.py` | `compute_quantstats_portfolio` | None — direct call, no mocks |
| `tests/unit/services/test_rebalancing_optimizer.py` | Direct import of `VALID_STRATEGIES`, `_equal_weight_fallback`, `_optimize`, `compute_rebalancing` | **Yes** — mock paths at lines 105, 118 (see Section 6) |
| `tests/unit/infra/test_user_context.py` | Mocks `get_or_create_portfolio`, `get_positions_with_pnl` (5 patches) | **Yes** — see Section 6 |
| `tests/unit/portfolio/test_portfolio.py` | `from backend.tools.portfolio import _run_fifo, _group_sectors` | None — goes through `tools/portfolio.py` which re-exports via `services/__init__.py` |
| `tests/unit/portfolio/test_portfolio_fifo_correctness.py` | `from backend.services.portfolio import _run_fifo` | None — direct call, no mocks. Re-export in `__init__.py` |
| `tests/unit/portfolio/test_portfolio_properties.py` | `from backend.services.portfolio import _run_fifo` | None — direct call, no mocks. Re-export in `__init__.py` |

**Required `__init__.py` re-exports** (all names consumers import must exist at package level):
- Public: `get_or_create_portfolio`, `get_all_portfolio_ids`, `get_portfolio_summary`, `get_portfolio_history`, `get_health_history`, `snapshot_portfolio_value`, `recompute_position`, `get_positions_with_pnl`, `list_transactions`, `delete_transaction`, `compute_quantstats_portfolio`, `compute_rebalancing`, `materialize_rebalancing`, `VALID_STRATEGIES`
- Private (consumed by tools/routers/tests): `_run_fifo`, `_get_transactions_for_ticker`, `_group_sectors`, `_optimize`, `_equal_weight_fallback`

### CSRF Protection (KAN-417)

| File | Change |
|---|---|
| `backend/middleware/csrf.py` | **New** — `CSRFMiddleware` class |
| `backend/middleware/__init__.py` | Export `CSRFMiddleware` |
| `backend/main.py` | Register CSRF middleware + add `X-CSRF-Token` to CORS `allow_headers` |
| `backend/routers/auth/_helpers.py` | `_generate_csrf_token()`, update `_set_auth_cookies()` to set csrf cookie, update `_clear_auth_cookies()` to clear it |
| `backend/dependencies.py` | Add `COOKIE_CSRF_TOKEN = "csrf_token"` constant |
| `frontend/src/lib/api.ts` | Read `csrf_token` cookie, attach `X-CSRF-Token` header on mutating requests |
| `tests/unit/middleware/test_csrf.py` | **New** — middleware unit tests |
| `tests/api/test_csrf.py` | **New** — end-to-end CSRF API tests |
| `tests/api/test_auth.py` | Update `test_login_cookies_are_httponly`, `test_login_sets_cookies`, `test_refresh_sets_cookies`, `test_logout_clears_cookies` |

---

## 6. Test Migration Checklist

### Mock Patch Path Strategy

**Rule:** Patch at the lookup site (where the function is imported), not where it's defined. For lazy imports inside functions, patch at the package re-export (`backend.services.portfolio.<func>`) since the lazy import binds from the package namespace at call time.

### Auth Router — Mock Path Changes

Each sub-module imports blocklist functions directly from `backend.services.token_blocklist`. The `from ... import` syntax binds names into the sub-module's namespace, so `mock.patch` must target the sub-module call site.

| File | Current Path | New Path | Sub-module where it's called |
|---|---|---|---|
| `tests/api/test_auth.py` (autouse fixture) | `backend.routers.auth.is_blocklisted` | `backend.routers.auth.core.is_blocklisted` | `refresh_token` in core |
| `tests/api/test_auth.py` (autouse fixture) | `backend.routers.auth.add_to_blocklist` | `backend.routers.auth.core.add_to_blocklist` | `refresh_token`, `logout` in core |
| `tests/api/test_auth.py` (autouse fixture, NEW) | — | `backend.routers.auth.password.set_user_revocation` | `reset_password`, `change_password`, `delete_account` in password |

The autouse `_mock_blocklist` fixture patches these for every test in the file. If wrong, mocks become no-ops and tests will attempt real Redis calls (hang or connection refused).

### Portfolio Service — Mock Path Changes

Mocks should target the sub-module where the function is **defined** (definition site), not the `__init__.py` re-export.

| File | Current Path | New Path |
|---|---|---|
| `tests/unit/services/test_rebalancing_optimizer.py:105` | `backend.services.portfolio.get_positions_with_pnl` | `backend.services.portfolio.fifo.get_positions_with_pnl` |
| `tests/unit/services/test_rebalancing_optimizer.py:118` | `backend.services.portfolio.get_positions_with_pnl` | `backend.services.portfolio.fifo.get_positions_with_pnl` |
| `tests/unit/infra/test_user_context.py:80` | `backend.services.portfolio.get_or_create_portfolio` | `backend.services.portfolio.core.get_or_create_portfolio` |
| `tests/unit/infra/test_user_context.py:85` | `backend.services.portfolio.get_positions_with_pnl` | `backend.services.portfolio.fifo.get_positions_with_pnl` |
| `tests/unit/infra/test_user_context.py:121` | `backend.services.portfolio.get_or_create_portfolio` | `backend.services.portfolio.core.get_or_create_portfolio` |
| `tests/unit/infra/test_user_context.py:126` | `backend.services.portfolio.get_positions_with_pnl` | `backend.services.portfolio.fifo.get_positions_with_pnl` |
| `tests/unit/infra/test_user_context.py:159` | `backend.services.portfolio.get_or_create_portfolio` | `backend.services.portfolio.core.get_or_create_portfolio` |

**Sub-module mapping** for any additional mock paths discovered during implementation audit:
- `get_or_create_portfolio`, `get_all_portfolio_ids`, `get_portfolio_summary`, `get_portfolio_history`, `get_health_history`, `snapshot_portfolio_value` → `backend.services.portfolio.core.*`
- `_run_fifo`, `recompute_position`, `get_positions_with_pnl`, `list_transactions`, `delete_transaction` → `backend.services.portfolio.fifo.*`
- `compute_quantstats_portfolio`, `compute_rebalancing`, `materialize_rebalancing`, `_optimize`, `_equal_weight_fallback` → `backend.services.portfolio.analytics.*`

### Existing Test Assertion Updates (CSRF)

| File | Test | Change |
|---|---|---|
| `tests/api/test_auth.py` | `test_login_cookies_are_httponly` | Assert httpOnly on `access_token` and `refresh_token` only. Assert `csrf_token` is NOT httpOnly. **If naively "fixed" by removing assertion, httpOnly guarantee on auth cookies is lost.** |
| `tests/api/test_auth.py` | `test_login_sets_cookies` | Add assertion: `csrf_token` cookie present |
| `tests/api/test_auth.py` | `test_refresh_sets_cookies` | Add assertion: `csrf_token` cookie present, value differs from pre-refresh |
| `tests/api/test_auth.py` | `test_logout_clears_cookies` | Add assertion: `csrf_token` cookie cleared |

---

## Out of Scope

- Splitting other oversized routers (`sectors.py` 549L, `chat.py` 527L) — future work
- Splitting other oversized services (`signals.py` 901L, `stock_data.py` 844L) — future work
- CSRF for non-cookie auth flows (Bearer token) — not needed
- `fastapi-csrf-protect` dependency — custom middleware is simpler for our double-submit pattern
