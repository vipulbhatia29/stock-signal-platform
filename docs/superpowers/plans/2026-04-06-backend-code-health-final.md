# Backend Code Health & Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the KAN-408 epic — split oversized auth router and portfolio service into focused modules, add CSRF protection for cookie-based auth.

**Architecture:** File-to-package refactors with `__init__.py` re-exports for backward compatibility. Custom CSRF middleware using double-submit cookie pattern, enforced only on cookie-authenticated mutating requests.

**Tech Stack:** FastAPI, Starlette middleware, Python `secrets` module, TypeScript `document.cookie`

**Spec:** `docs/superpowers/specs/2026-04-06-backend-code-health-final.md`

---

## File Structure

### Auth Router Split (KAN-412)
```
backend/routers/auth.py                → DELETE (replaced by package)
backend/routers/auth/
├── __init__.py              # NEW — combines sub-routers into single `router`
├── _helpers.py              # NEW — shared cookie/token/background helpers
├── core.py                  # NEW — register, login, refresh, logout, me
├── email_verification.py    # NEW — verify-email, resend-verification
├── password.py              # NEW — forgot/reset/change/set-password
├── oauth.py                 # NEW — Google OAuth
├── oidc.py                  # NEW — OIDC provider (Langfuse SSO)
└── admin.py                 # NEW — admin verify-email, admin recover
```

### Portfolio Service Split (KAN-413)
```
backend/services/portfolio.py          → DELETE (replaced by package)
backend/services/portfolio/
├── __init__.py              # NEW — re-exports all public functions
├── core.py                  # NEW — CRUD, snapshots, history, summary
├── fifo.py                  # NEW — FIFO engine, positions, transactions
└── analytics.py             # NEW — QuantStats, rebalancing, optimization
```

### CSRF Protection (KAN-417)
```
backend/middleware/csrf.py             # NEW — CSRFMiddleware
backend/middleware/__init__.py         # MODIFY — export CSRFMiddleware
backend/main.py                        # MODIFY — register middleware + CORS header
backend/dependencies.py                # MODIFY — add COOKIE_CSRF_TOKEN constant
backend/routers/auth/_helpers.py       # MODIFY — CSRF token in cookie helpers
frontend/src/lib/api.ts                # MODIFY — attach X-CSRF-Token header
```

### Test Files
```
tests/api/test_auth.py                 # MODIFY — mock paths + cookie assertions
tests/unit/infra/test_user_context.py  # MODIFY — mock paths
tests/unit/middleware/test_csrf.py     # NEW — CSRF middleware unit tests
tests/api/test_csrf.py                 # NEW — CSRF API integration tests
```

---

## Task 1: Auth Router — Create `_helpers.py`

**Files:**
- Create: `backend/routers/auth/_helpers.py`

- [ ] **Step 1: Create the `_helpers.py` module**

Extract all shared helper functions from `backend/routers/auth.py` (lines 66-218) into `backend/routers/auth/_helpers.py`. This module has no endpoints — only utilities used by multiple sub-routers.

```python
"""Shared auth helpers — cookie management, token TTL, background tasks."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

import jwt
from fastapi import Response

from backend.config import settings
from backend.dependencies import (
    COOKIE_ACCESS_TOKEN,
    COOKIE_PATH,
    COOKIE_REFRESH_TOKEN,
    COOKIE_SAMESITE,
)
from backend.services.email import (
    send_deletion_confirmation,
    send_password_reset_email,
    send_password_reset_google_only,
    send_verification_email,
)

logger = logging.getLogger(__name__)


def _get_token_remaining_ttl(token: str) -> int:
    """Get remaining TTL in seconds for a JWT token.

    Decodes without verification (already validated by decode_token).
    Returns 0 if the token is already expired.
    """
    import time

    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={"verify_exp": False},
    )
    exp = payload.get("exp", 0)
    remaining = int(exp - time.time())
    return max(remaining, 0)


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Set httpOnly auth cookies on the response.

    Args:
        response: FastAPI Response object.
        access_token: JWT access token.
        refresh_token: JWT refresh token.
    """
    response.set_cookie(
        key=COOKIE_ACCESS_TOKEN,
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key=COOKIE_REFRESH_TOKEN,
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )


def _clear_auth_cookies(response: Response) -> None:
    """Clear httpOnly auth cookies from the response."""
    response.delete_cookie(key=COOKIE_ACCESS_TOKEN, path=COOKIE_PATH)
    response.delete_cookie(key=COOKIE_REFRESH_TOKEN, path=COOKIE_PATH)


def _record_login_attempt_bg(
    email: str,
    success: bool,
    user_id: uuid.UUID | None,
    ip_address: str,
    user_agent: str,
    failure_reason: str | None = None,
    method: str = "password",
) -> None:
    """Schedule fire-and-forget login attempt recording.

    Uses its own DB session to avoid blocking the auth flow
    or double-committing on the caller's session.
    """
    asyncio.create_task(
        _write_login_attempt(
            email=email,
            success=success,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            failure_reason=failure_reason,
            method=method,
        )
    )


async def _write_login_attempt(
    email: str,
    success: bool,
    user_id: uuid.UUID | None,
    ip_address: str,
    user_agent: str,
    failure_reason: str | None = None,
    method: str = "password",
) -> None:
    """Write login attempt to DB with its own session."""
    try:
        from backend.database import async_session_factory
        from backend.models.login_attempt import LoginAttempt

        async with async_session_factory() as db:
            attempt = LoginAttempt(
                timestamp=datetime.now(timezone.utc),
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                success=success,
                failure_reason=failure_reason,
                method=method,
            )
            db.add(attempt)
            await db.commit()
    except Exception:
        logger.debug("Failed to record login attempt", exc_info=True)


async def _send_verification_bg(email: str, token: str) -> None:
    """Fire-and-forget verification email."""
    try:
        await send_verification_email(email, token)
    except Exception:
        logger.exception("Failed to send verification email to %s", email)


async def _send_reset_email_bg(email: str, token: str, google_only: bool = False) -> None:
    """Fire-and-forget password reset email."""
    try:
        if google_only:
            await send_password_reset_google_only(email)
        else:
            await send_password_reset_email(email, token)
    except Exception:
        logger.exception("Failed to send reset notification email to %s", email)


async def _send_deletion_email_bg(email: str) -> None:
    """Fire-and-forget deletion confirmation email."""
    try:
        await send_deletion_confirmation(email)
    except Exception:
        logger.exception("Failed to send deletion email to %s", email)
```

- [ ] **Step 2: Verify no syntax errors**

Run: `uv run python -c "import backend.routers.auth._helpers"`

This will fail because `backend/routers/auth/` doesn't exist as a package yet (no `__init__.py`). That's expected — we'll create it in Task 2. For now, just verify the file has no syntax errors:

Run: `uv run python -c "import ast; ast.parse(open('backend/routers/auth/_helpers.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/routers/auth/_helpers.py
git commit -m "refactor(auth): extract shared helpers into _helpers.py (KAN-412)"
```

---

## Task 2: Auth Router — Create Sub-Router Modules

**Files:**
- Create: `backend/routers/auth/core.py`
- Create: `backend/routers/auth/email_verification.py`
- Create: `backend/routers/auth/password.py`
- Create: `backend/routers/auth/oauth.py`
- Create: `backend/routers/auth/oidc.py`
- Create: `backend/routers/auth/admin.py`

Each sub-module creates its own `APIRouter()` and imports shared helpers from `_helpers.py`. Copy the endpoints verbatim from `backend/routers/auth.py` — no logic changes, only import reorganization.

- [ ] **Step 1: Create `core.py`** (register, login, refresh, logout, me — lines 221-475 of auth.py)

```python
"""Core auth endpoints: register, login, refresh, logout, me."""

import asyncio
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_async_session
from backend.dependencies import (
    COOKIE_REFRESH_TOKEN,
    CachedUser,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from backend.models.user import User, UserPreference
from backend.rate_limit import limiter
from backend.routers.auth._helpers import (
    _clear_auth_cookies,
    _get_token_remaining_ttl,
    _record_login_attempt_bg,
    _send_verification_bg,
    _set_auth_cookies,
)
from backend.schemas.auth import (
    TokenRefreshRequest,
    TokenResponse,
    UserLoginRequest,
    UserProfileResponse,
    UserRegisterRequest,
    UserRegisterResponse,
)
from backend.services.email import generate_token
from backend.services.redis_pool import get_redis
from backend.services.token_blocklist import add_to_blocklist, is_blocklisted

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Z])(?=.*\d).{8,}$")

# Paste register, login, refresh_token, logout, get_me endpoints verbatim from auth.py lines 221-475.
# Replace _set_auth_cookies / _clear_auth_cookies / _record_login_attempt_bg / _send_verification_bg
# with imports from _helpers (already done in the import block above).
# is_blocklisted / add_to_blocklist are imported directly from backend.services.token_blocklist.
```

**Mock target:** `core.py` imports `is_blocklisted` and `add_to_blocklist` directly from `token_blocklist`. Since `from ... import` binds the name into `core`'s namespace, the correct mock path is `backend.routers.auth.core.is_blocklisted` (lookup site).

- [ ] **Step 2: Create `email_verification.py`** (lines 478-573 of auth.py)

```python
"""Email verification endpoints."""

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.rate_limit import limiter
from backend.routers.auth._helpers import _send_verification_bg
from backend.schemas.auth import MessageResponse, VerifyEmailRequest
from backend.services.email import generate_token
from backend.services.redis_pool import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# Paste verify_email_page, verify_email, resend_verification endpoints verbatim.
```

- [ ] **Step 3: Create `password.py`** (lines 576-719 of auth.py)

```python
"""Password management endpoints: forgot, reset, change, set."""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_async_session
from backend.dependencies import (
    CachedUser,
    get_current_user,
    hash_password,
    verify_password,
)
from backend.models.user import User
from backend.rate_limit import limiter
from backend.routers.auth._helpers import _send_reset_email_bg, _send_deletion_email_bg
from backend.schemas.auth import (
    AccountInfoResponse,
    ChangePasswordRequest,
    DeleteAccountRequest,
    ForgotPasswordRequest,
    MessageResponse,
    ResetPasswordRequest,
    SetPasswordRequest,
)
from backend.services.email import generate_token
from backend.services.redis_pool import get_redis
from backend.services.token_blocklist import set_user_revocation

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Z])(?=.*\d).{8,}$")
_PW_STRENGTH_MSG = "Password must contain at least 1 uppercase letter and 1 digit"
_NO_PW_MSG = "No password set. Use set-password instead."
_PW_ALREADY_SET_MSG = "Password already set. Use change-password instead."
_RESET_SENT_MSG = "If an account with that email exists, a reset link has been sent"

# Paste forgot_password, reset_password, change_password, set_password endpoints verbatim.
# Also paste get_account_info and delete_account (lines 722-798) — these are account management.
```

**Note:** `get_account_info` (GET /account) and `delete_account` (POST /delete-account) belong in `password.py` as they are account management endpoints that share password-related dependencies. The module name is slightly misleading but avoids creating a 5th tiny module. An alternative would be naming this `account.py` — implementer's choice as long as `__init__.py` wiring is correct.

- [ ] **Step 4: Create `oauth.py`** (lines 801-1013 of auth.py)

```python
"""Google OAuth endpoints."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_async_session
from backend.dependencies import (
    CachedUser,
    create_access_token,
    create_refresh_token,
    get_current_user,
)
from backend.models.oauth_account import OAuthAccount
from backend.models.user import User, UserPreference
from backend.models.oauth_account import OAuthAccount
from backend.rate_limit import limiter
from backend.routers.auth._helpers import (
    _record_login_attempt_bg,
    _set_auth_cookies,
)
from backend.schemas.auth import MessageResponse
from backend.services.google_oauth import build_auth_url, exchange_code

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# Paste google_authorize, google_callback, google_unlink endpoints verbatim.
```

- [ ] **Step 5: Create `oidc.py`** (lines 1016-1201 of auth.py)

```python
"""OIDC provider endpoints (Langfuse SSO integration)."""

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_async_session
from backend.dependencies import (
    create_access_token,
    get_current_user,
)
from backend.models.user import User
from backend.services.oidc_provider import (
    build_discovery_document,
    exchange_auth_code,
    store_auth_code,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


def _oidc_enabled() -> bool:
    """Check if OIDC is configured (client secret is set)."""
    return bool(settings.OIDC_CLIENT_SECRET)


def _allowed_redirect_uris() -> set[str]:
    """Parse the comma-separated redirect URI whitelist from settings."""
    return {u.strip() for u in settings.OIDC_REDIRECT_URIS.split(",") if u.strip()}

# Paste oidc_discovery, oidc_authorize, oidc_token, oidc_userinfo endpoints verbatim.
```

- [ ] **Step 6: Create `admin.py`** (lines 1204-1263 of auth.py)

```python
"""Admin auth endpoints: email verification override, account recovery."""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user, require_admin
from backend.models.user import User
from backend.schemas.auth import (
    AdminRecoverAccountRequest,
    MessageResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# Paste admin_verify_email, admin_recover_account endpoints verbatim.
```

- [ ] **Step 7: Verify all sub-modules parse**

Run: `for f in backend/routers/auth/core.py backend/routers/auth/email_verification.py backend/routers/auth/password.py backend/routers/auth/oauth.py backend/routers/auth/oidc.py backend/routers/auth/admin.py; do uv run python -c "import ast; ast.parse(open('$f').read()); print('OK: $f')"; done`

Expected: `OK` for each file.

- [ ] **Step 8: Commit**

```bash
git add backend/routers/auth/core.py backend/routers/auth/email_verification.py backend/routers/auth/password.py backend/routers/auth/oauth.py backend/routers/auth/oidc.py backend/routers/auth/admin.py
git commit -m "refactor(auth): split endpoints into domain sub-modules (KAN-412)"
```

---

## Task 3: Auth Router — Create `__init__.py` and Delete Old File

**Files:**
- Create: `backend/routers/auth/__init__.py`
- Delete: `backend/routers/auth.py` (the original single file — now replaced by the package)

- [ ] **Step 1: Create `__init__.py`**

```python
"""Auth router package — combines domain sub-routers into a single router.

main.py import unchanged: ``from backend.routers.auth import router``
"""

from fastapi import APIRouter

from backend.routers.auth.admin import router as admin_router
from backend.routers.auth.core import router as core_router
from backend.routers.auth.email_verification import router as email_router
from backend.routers.auth.oauth import router as oauth_router
from backend.routers.auth.oidc import router as oidc_router
from backend.routers.auth.password import router as password_router

router = APIRouter()

router.include_router(core_router)
router.include_router(email_router)
router.include_router(password_router)
router.include_router(oauth_router)
router.include_router(oidc_router)
router.include_router(admin_router)

__all__ = ["router"]
```

- [ ] **Step 2: Delete the old single-file router**

```bash
git rm backend/routers/auth.py
```

**Important:** `git rm`, not `rm`. This ensures git tracks the deletion.

- [ ] **Step 3: Verify the app starts**

Run: `uv run python -c "from backend.routers.auth import router; print(f'Routes: {len(router.routes)}')"`

Expected: `Routes: 20` (or close — includes 20 endpoints plus any auto-generated OPTIONS routes)

- [ ] **Step 4: Run auth tests to verify URL-based tests still pass**

Run: `uv run pytest tests/api/test_auth.py -x -q --tb=short 2>&1 | head -30`

Expected: Tests may fail due to mock path changes (addressed in Task 4). Note which tests fail.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/auth/__init__.py
git commit -m "refactor(auth): wire __init__.py + delete monolith (KAN-412)"
```

---

## Task 4: Auth Router — Fix Test Mock Paths

**Files:**
- Modify: `tests/api/test_auth.py`

**Background:** `is_blocklisted`, `add_to_blocklist`, and `set_user_revocation` are imported into multiple sub-modules via `from backend.services.token_blocklist import ...`. Each sub-module holds its own binding of these names. `mock.patch` must target the **lookup site** — the sub-module where the function is called — not `_helpers` or `token_blocklist`.

Call sites after the split:
- `core.py` uses `is_blocklisted`, `add_to_blocklist` (in `refresh_token`, `logout`)
- `password.py` uses `set_user_revocation` (in `reset_password`, `change_password`, `delete_account`)
- `admin.py` does NOT use the blocklist (only `admin_verify_email` and `admin_recover_account` — neither touches Redis blocklist; verify with grep)

- [ ] **Step 1: Verify call sites with grep**

Run: `grep -rn "is_blocklisted\|add_to_blocklist\|set_user_revocation" backend/routers/auth/`

Expected output lists all call sites. Use this to determine exactly which sub-modules need patching.

- [ ] **Step 2: Update the autouse `_mock_blocklist` fixture**

Replace the fixture at `tests/api/test_auth.py:9-28` to patch at every sub-module call site:

```python
@pytest.fixture(autouse=True)
def _mock_blocklist():
    """Mock Redis blocklist for all auth API tests to avoid real Redis calls.

    Each sub-module imports these functions directly from token_blocklist,
    so each holds its own binding. We must patch at every lookup site.
    """
    with (
        # core.py — refresh_token, logout
        patch(
            "backend.routers.auth.core.is_blocklisted",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_check,
        patch(
            "backend.routers.auth.core.add_to_blocklist",
            new_callable=AsyncMock,
        ) as mock_add,
        # password.py — reset_password, change_password, delete_account
        patch(
            "backend.routers.auth.password.set_user_revocation",
            new_callable=AsyncMock,
        ) as mock_revoke,
        # Redis pool mock (unchanged)
        patch(
            "backend.services.redis_pool.get_redis",
            new_callable=AsyncMock,
            return_value=AsyncMock(),
        ),
    ):
        yield {
            "is_blocklisted": mock_check,
            "add_to_blocklist": mock_add,
            "set_user_revocation": mock_revoke,
        }
```

**Why:** `core.py` does `from backend.services.token_blocklist import is_blocklisted, add_to_blocklist`. This binds `is_blocklisted` and `add_to_blocklist` in `core`'s namespace. Patching at `backend.routers.auth.core.is_blocklisted` patches the name where it's looked up at call time. Same reasoning applies to `password.py`.

- [ ] **Step 3: Search for any other test files mocking these functions**

Run: `grep -rn "backend\.routers\.auth\.\(is_blocklisted\|add_to_blocklist\|set_user_revocation\)" tests/`

Expected: Only `tests/api/test_auth.py` matches. If others exist, update them to target sub-module paths.

- [ ] **Step 4: Run auth tests**

Run: `uv run pytest tests/api/test_auth.py -x -q --tb=short`

Expected: All tests pass.

- [ ] **Step 5: Run full test suite to check for collateral damage**

Run: `uv run pytest tests/unit/ tests/api/ -x -q --tb=short 2>&1 | tail -5`

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add tests/api/test_auth.py
git commit -m "test(auth): update mock paths after router split (KAN-412)"
```

---

## Task 5: Portfolio Router — Add Section Headers

**Files:**
- Modify: `backend/routers/portfolio.py`

**Important:** Do NOT move or reorder endpoints. Only add comment section headers above the existing endpoints where they naturally group. Moving 776 lines of endpoints is high-risk for losing decorators or duplicating functions.

- [ ] **Step 1: Add section header comments above existing endpoints**

For each group below, find the first endpoint in the group in `backend/routers/portfolio.py` and add the matching section header comment directly above it. Do not touch any endpoint bodies.

```python
# ── Transactions ─────────────────────────────────────────────────────────────
# (above first of: POST /transactions, GET /transactions, DELETE /transactions/{id})

# ── Positions & Holdings ─────────────────────────────────────────────────────
# (above first of: GET /positions, GET /dividends/{ticker})

# ── Summary & History ────────────────────────────────────────────────────────
# (above first of: GET /summary, GET /history, GET /health/history)

# ── Analytics & Health ───────────────────────────────────────────────────────
# (above first of: GET /health, GET /analytics, GET /rebalancing)

# ── Forecasts ────────────────────────────────────────────────────────────────
# (above first of: GET /{portfolio_id}/forecast, GET /{portfolio_id}/forecast/components)
```

- [ ] **Step 2: Run portfolio tests**

Run: `uv run pytest tests/api/ -k portfolio -x -q --tb=short`

Expected: All pass (no logic changes).

- [ ] **Step 3: Lint**

Run: `uv run ruff check --fix backend/routers/portfolio.py && uv run ruff format backend/routers/portfolio.py`

- [ ] **Step 4: Commit**

```bash
git add backend/routers/portfolio.py
git commit -m "refactor(portfolio): reorder endpoints with section headers (KAN-412)"
```

---

## Task 6: Portfolio Service — Create Sub-Modules

**Files:**
- Create: `backend/services/portfolio/fifo.py`
- Create: `backend/services/portfolio/core.py`
- Create: `backend/services/portfolio/analytics.py`

- [ ] **Step 0: Audit private helper usage**

Before the split, grep for every private helper that could be imported elsewhere:

```bash
grep -rn "_run_fifo\|_optimize\|_equal_weight_fallback\|_group_sectors\|_safe_round\|_get_transactions_for_ticker" backend/ tests/
```

Expected output: identifies who imports what. Any external import (outside `backend/services/portfolio.py` itself) must be re-exported in the new `__init__.py` (Task 7). Note the findings for Task 7 Step 1.

Also verify `backend/tools/portfolio.py` still works after split:

```bash
grep -n "from backend\.services\.portfolio" backend/tools/portfolio.py
```

Expected: imports from `backend.services.portfolio` (the package). All these names must exist in the new `__init__.py`.

- [ ] **Step 1: Create `fifo.py`**

Extract from `backend/services/portfolio.py`:
- `_run_fifo()` (pure FIFO engine, no DB)
- `_get_transactions_for_ticker()` (DB helper)
- `recompute_position()` (FIFO walk for single ticker)
- `get_positions_with_pnl()` (all positions with P&L)
- `list_transactions()` (paginated list)
- `delete_transaction()` (delete + recompute)

```python
"""Portfolio FIFO engine — cost basis, positions, transactions."""

from __future__ import annotations

import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

# ... (copy relevant imports from portfolio.py)

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.portfolio import Portfolio, Position, Transaction
from backend.models.price import StockPrice
from backend.models.stock import Stock
from backend.schemas.portfolio import PositionResponse
from backend.services.exceptions import PortfolioNotFoundError

logger = logging.getLogger(__name__)

# Paste _run_fifo, _get_transactions_for_ticker, recompute_position,
# get_positions_with_pnl, list_transactions, delete_transaction verbatim.
```

- [ ] **Step 2: Create `core.py`**

Extract from `backend/services/portfolio.py`:
- `get_or_create_portfolio()`
- `get_all_portfolio_ids()`
- `get_portfolio_summary()` (imports `get_positions_with_pnl` from `fifo`)
- `get_portfolio_history()`
- `get_health_history()`
- `snapshot_portfolio_value()`

```python
"""Portfolio core — CRUD, snapshots, history, summary."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.portfolio import Portfolio, PortfolioSnapshot, Position
from backend.models.price import StockPrice
from backend.models.stock import Stock
from backend.schemas.portfolio import PortfolioSummaryResponse, SectorAllocation
from backend.services.exceptions import PortfolioNotFoundError
from backend.services.portfolio.fifo import get_positions_with_pnl

logger = logging.getLogger(__name__)

# Paste get_or_create_portfolio, get_all_portfolio_ids, get_portfolio_summary,
# get_portfolio_history, get_health_history, snapshot_portfolio_value,
# _group_sectors verbatim.
```

**Note:** `_group_sectors` is used by `get_portfolio_summary` — keep it in `core.py`, not `analytics.py`.

- [ ] **Step 3: Create `analytics.py`**

Extract from `backend/services/portfolio.py`:
- `VALID_STRATEGIES`
- `compute_quantstats_portfolio()` (with `_safe_round` inner function)
- `compute_rebalancing()`
- `materialize_rebalancing()`
- `_optimize()`
- `_equal_weight_fallback()`

```python
"""Portfolio analytics — QuantStats, rebalancing, optimization."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.portfolio import Portfolio, Position, RebalancingSuggestion
from backend.models.price import StockPrice
from backend.services.portfolio.fifo import get_positions_with_pnl

logger = logging.getLogger(__name__)

VALID_STRATEGIES = ["equal_weight", "min_volatility", "max_sharpe"]

# Paste compute_quantstats_portfolio, compute_rebalancing, materialize_rebalancing,
# _optimize, _equal_weight_fallback verbatim.
```

**Dependency direction:** `analytics.py` imports from `fifo.py` directly (not via `__init__.py`). `core.py` imports from `fifo.py` directly. `fifo.py` has no sibling imports.

- [ ] **Step 4: Verify all sub-modules parse**

Run: `for f in backend/services/portfolio/fifo.py backend/services/portfolio/core.py backend/services/portfolio/analytics.py; do uv run python -c "import ast; ast.parse(open('$f').read()); print('OK: $f')"; done`

Expected: `OK` for each.

- [ ] **Step 5: Commit**

```bash
git add backend/services/portfolio/fifo.py backend/services/portfolio/core.py backend/services/portfolio/analytics.py
git commit -m "refactor(portfolio): split service into fifo/core/analytics (KAN-413)"
```

---

## Task 7: Portfolio Service — Create `__init__.py` and Delete Old File

**Files:**
- Create: `backend/services/portfolio/__init__.py`
- Delete: `backend/services/portfolio.py`

- [ ] **Step 1: Create `__init__.py`**

Re-export all public functions AND test-used private helpers:

```python
"""Portfolio service package — re-exports for backward compatibility.

External call sites continue to use:
    from backend.services.portfolio import get_or_create_portfolio
"""

from backend.services.portfolio.analytics import (
    VALID_STRATEGIES,
    _equal_weight_fallback,
    _optimize,
    compute_quantstats_portfolio,
    compute_rebalancing,
    materialize_rebalancing,
)
from backend.services.portfolio.core import (
    get_all_portfolio_ids,
    get_health_history,
    get_or_create_portfolio,
    get_portfolio_history,
    get_portfolio_summary,
    snapshot_portfolio_value,
)
from backend.services.portfolio.core import _group_sectors
from backend.services.portfolio.fifo import (
    _get_transactions_for_ticker,
    _run_fifo,
    delete_transaction,
    get_positions_with_pnl,
    list_transactions,
    recompute_position,
)

__all__ = [
    # core
    "get_or_create_portfolio",
    "get_all_portfolio_ids",
    "get_portfolio_summary",
    "get_portfolio_history",
    "get_health_history",
    "snapshot_portfolio_value",
    # fifo
    "recompute_position",
    "get_positions_with_pnl",
    "list_transactions",
    "delete_transaction",
    # analytics
    "VALID_STRATEGIES",
    "compute_quantstats_portfolio",
    "compute_rebalancing",
    "materialize_rebalancing",
    # test-used / consumer-used private helpers (re-exported to avoid mass import changes)
    # backend/tools/portfolio.py and backend/routers/portfolio.py both import these.
    "_run_fifo",
    "_get_transactions_for_ticker",
    "_group_sectors",
    "_optimize",
    "_equal_weight_fallback",
]
```

- [ ] **Step 2: Delete the old single-file service**

```bash
git rm backend/services/portfolio.py
```

- [ ] **Step 3: Verify all consumer imports work**

Run: `uv run python -c "from backend.services.portfolio import get_or_create_portfolio, _run_fifo, _group_sectors, _get_transactions_for_ticker, _optimize, _equal_weight_fallback, VALID_STRATEGIES; print('OK')"`

Expected: `OK`

Also verify downstream consumers:
```bash
uv run python -c "from backend.tools.portfolio import _run_fifo, _group_sectors, _get_transactions_for_ticker; print('tools OK')"
uv run python -c "from backend.routers.portfolio import router; print('router OK')"
```

Expected: Both print OK.

- [ ] **Step 4: Run all portfolio-related tests**

Run: `uv run pytest tests/unit/services/test_portfolio_service.py tests/unit/portfolio/ tests/unit/services/test_quantstats_portfolio.py tests/unit/services/test_rebalancing_optimizer.py -x -q --tb=short`

Expected: All pass (direct imports work via re-exports, and there are no mocks to fix in these files).

This includes `tests/unit/portfolio/test_portfolio.py` which imports `_run_fifo` and `_group_sectors` from `backend.tools.portfolio` — the chain `test → tools → services/__init__ → services.fifo/core` must work end-to-end.

- [ ] **Step 5: Commit**

```bash
git add backend/services/portfolio/__init__.py
git commit -m "refactor(portfolio): wire __init__.py + delete monolith (KAN-413)"
```

---

## Task 8: Portfolio Service — Fix Test Mock Paths

**Files:**
- Modify: `tests/unit/infra/test_user_context.py`
- Possibly modify: `tests/unit/services/test_portfolio_service.py`, `tests/unit/services/test_quantstats_portfolio.py`, `tests/unit/services/test_rebalancing_optimizer.py`

- [ ] **Step 1: Audit mock paths in all portfolio test files**

Run: `grep -rn "backend\.services\.portfolio\." tests/unit/services/test_portfolio_service.py tests/unit/services/test_quantstats_portfolio.py tests/unit/services/test_rebalancing_optimizer.py tests/unit/infra/test_user_context.py tests/unit/portfolio/`

For each match, determine whether it's:
- A **direct import** (`from backend.services.portfolio import ...`) — works via `__init__.py` re-export, no change needed
- A **mock.patch path** — must point to the sub-module lookup site (not the package)

For each mock, identify which sub-module the function lives in and update accordingly.

- [ ] **Step 2: Update mock paths in `test_user_context.py`**

`backend/agents/user_context.py` does lazy imports inside functions:
```python
from backend.services.portfolio import get_or_create_portfolio, get_positions_with_pnl
```

Since these are lazy imports that bind at call time into `user_context`'s local frame (not module namespace), mock at the **lookup site** in `user_context.py`:

| Old Path | New Path |
|---|---|
| `backend.services.portfolio.get_or_create_portfolio` | `backend.agents.user_context.get_or_create_portfolio` |
| `backend.services.portfolio.get_positions_with_pnl` | `backend.agents.user_context.get_positions_with_pnl` |

**Caveat:** Patching at `backend.agents.user_context.<name>` only works if the lazy import has already executed once (so the name exists on the module) OR if we manually inject the name. An alternative that's more robust: patch at the sub-module definition site:

| Alternative Path |
|---|
| `backend.services.portfolio.core.get_or_create_portfolio` |
| `backend.services.portfolio.fifo.get_positions_with_pnl` |

Use the definition-site path. It's more robust because `user_context.py` does `from backend.services.portfolio import ...` — this re-export path goes through `__init__.py` which imports from sub-modules. Patching at the sub-module affects all consumers.

Update all 5 occurrences (lines 80, 85, 121, 126, 159):

| Old (all 5) | New |
|---|---|
| `backend.services.portfolio.get_or_create_portfolio` | `backend.services.portfolio.core.get_or_create_portfolio` |
| `backend.services.portfolio.get_positions_with_pnl` | `backend.services.portfolio.fifo.get_positions_with_pnl` |

**Note:** Because `__init__.py` does `from backend.services.portfolio.core import get_or_create_portfolio`, both `backend.services.portfolio.core.get_or_create_portfolio` AND `backend.services.portfolio.get_or_create_portfolio` exist as separate bindings. Mocking the sub-module path is canonical because it's the definition site; mocking the package path requires knowing which consumers imported before patching. Prefer sub-module.

- [ ] **Step 3: Update other portfolio test mocks found in Step 1**

For each mock.patch path found in Step 1 (other than `test_user_context.py`), update to point to the sub-module where the function lives:
- `get_or_create_portfolio`, `get_all_portfolio_ids`, `get_portfolio_summary`, `get_portfolio_history`, `get_health_history`, `snapshot_portfolio_value` → `backend.services.portfolio.core.<name>`
- `_run_fifo`, `recompute_position`, `get_positions_with_pnl`, `list_transactions`, `delete_transaction` → `backend.services.portfolio.fifo.<name>`
- `compute_quantstats_portfolio`, `compute_rebalancing`, `materialize_rebalancing`, `_optimize`, `_equal_weight_fallback` → `backend.services.portfolio.analytics.<name>`

- [ ] **Step 4: Run user_context tests**

Run: `uv run pytest tests/unit/infra/test_user_context.py -x -q --tb=short`

Expected: All pass.

- [ ] **Step 5: Run portfolio service test suite**

Run: `uv run pytest tests/unit/services/test_portfolio_service.py tests/unit/services/test_quantstats_portfolio.py tests/unit/services/test_rebalancing_optimizer.py tests/unit/portfolio/ -x -q --tb=short`

Expected: All pass.

- [ ] **Step 6: Run full unit test suite**

Run: `uv run pytest tests/unit/ -x -q --tb=short 2>&1 | tail -5`

Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add tests/
git commit -m "test(portfolio): update mock paths after service split (KAN-413)"
```

---

## Task 9: CSRF Middleware — Implementation

**Files:**
- Create: `backend/middleware/csrf.py`
- Modify: `backend/middleware/__init__.py`
- Modify: `backend/dependencies.py`

- [ ] **Step 0: Ensure `tests/unit/middleware/` exists as a package**

```bash
mkdir -p tests/unit/middleware
touch tests/unit/middleware/__init__.py
```

- [ ] **Step 1: Write failing test for CSRF middleware**

Create `tests/unit/middleware/test_csrf.py`:

```python
"""Tests for CSRF middleware — double-submit cookie pattern."""

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from backend.middleware.csrf import CSRFMiddleware


def _make_app(exempt_paths: set[str] | None = None) -> Starlette:
    """Create a minimal Starlette app with CSRF middleware for testing."""

    async def echo(request: Request) -> Response:
        return JSONResponse({"ok": True})

    app = Starlette(routes=[
        Route("/protected", echo, methods=["POST", "GET", "DELETE"]),
        Route("/exempt", echo, methods=["POST"]),
        Route("/health", echo, methods=["GET"]),
    ])
    app.add_middleware(
        CSRFMiddleware,
        csrf_exempt_paths=exempt_paths or {"/exempt"},
    )
    return app


class TestCSRFMiddleware:
    """CSRF double-submit cookie validation."""

    def test_get_request_always_passes(self) -> None:
        """GET requests are safe methods — skip CSRF check."""
        client = TestClient(_make_app())
        response = client.get("/protected")
        assert response.status_code == 200

    def test_post_with_bearer_auth_skips_csrf(self) -> None:
        """Requests with Authorization header bypass CSRF (header auth is CSRF-safe)."""
        client = TestClient(_make_app())
        response = client.post(
            "/protected",
            headers={"Authorization": "Bearer some-token"},
        )
        assert response.status_code == 200

    def test_post_cookie_auth_missing_csrf_token_returns_403(self) -> None:
        """Cookie-auth POST without X-CSRF-Token header → 403."""
        client = TestClient(_make_app())
        client.cookies.set("access_token", "fake-jwt")
        response = client.post("/protected")
        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]

    def test_post_cookie_auth_mismatched_csrf_token_returns_403(self) -> None:
        """Cookie-auth POST with wrong X-CSRF-Token → 403."""
        client = TestClient(_make_app())
        client.cookies.set("access_token", "fake-jwt")
        client.cookies.set("csrf_token", "correct-token")
        response = client.post(
            "/protected",
            headers={"X-CSRF-Token": "wrong-token"},
        )
        assert response.status_code == 403

    def test_post_cookie_auth_valid_csrf_token_passes(self) -> None:
        """Cookie-auth POST with matching X-CSRF-Token → passes through."""
        client = TestClient(_make_app())
        client.cookies.set("access_token", "fake-jwt")
        client.cookies.set("csrf_token", "valid-token")
        response = client.post(
            "/protected",
            headers={"X-CSRF-Token": "valid-token"},
        )
        assert response.status_code == 200

    def test_exempt_path_skips_csrf(self) -> None:
        """Paths in csrf_exempt_paths skip CSRF check."""
        client = TestClient(_make_app(exempt_paths={"/exempt"}))
        client.cookies.set("access_token", "fake-jwt")
        response = client.post("/exempt")
        assert response.status_code == 200

    def test_options_request_always_passes(self) -> None:
        """OPTIONS requests (CORS preflight) skip CSRF."""
        client = TestClient(_make_app())
        client.cookies.set("access_token", "fake-jwt")
        response = client.options("/protected")
        # Starlette returns 400 for OPTIONS on non-CORS routes, but the point is
        # CSRF middleware should NOT block it with 403
        assert response.status_code != 403

    def test_delete_cookie_auth_valid_csrf_passes(self) -> None:
        """DELETE with valid CSRF token passes."""
        client = TestClient(_make_app())
        client.cookies.set("access_token", "fake-jwt")
        client.cookies.set("csrf_token", "delete-token")
        response = client.delete(
            "/protected",
            headers={"X-CSRF-Token": "delete-token"},
        )
        assert response.status_code == 200

    def test_empty_csrf_header_returns_403(self) -> None:
        """Empty X-CSRF-Token header is treated as missing."""
        client = TestClient(_make_app())
        client.cookies.set("access_token", "fake-jwt")
        client.cookies.set("csrf_token", "real-token")
        response = client.post(
            "/protected",
            headers={"X-CSRF-Token": ""},
        )
        assert response.status_code == 403

    def test_no_cookies_at_all_passes(self) -> None:
        """Request with no cookies at all is not cookie-auth — skip CSRF."""
        client = TestClient(_make_app())
        response = client.post("/protected")
        assert response.status_code == 200

    def test_refresh_only_cookie_still_enforces_csrf(self) -> None:
        """Request with only refresh_token cookie (no access_token) is still cookie-auth.

        Regression guard: an attacker with only the refresh cookie must not
        bypass CSRF by exploiting expired access tokens.
        """
        client = TestClient(_make_app())
        client.cookies.set("refresh_token", "fake-refresh")
        response = client.post("/protected")
        assert response.status_code == 403

    def test_lowercase_bearer_auth_skips_csrf(self) -> None:
        """Authorization scheme check is case-insensitive."""
        client = TestClient(_make_app())
        client.cookies.set("access_token", "fake-jwt")
        response = client.post(
            "/protected",
            headers={"Authorization": "bearer lowercase-token"},
        )
        assert response.status_code == 200

    def test_cookie_auth_header_present_but_missing_cookie_returns_403(self) -> None:
        """Attacker with forged header but no csrf cookie → 403.

        Guards against XSS scenarios where the attacker can set headers
        but cannot read the httpOnly csrf_token cookie.
        """
        client = TestClient(_make_app())
        client.cookies.set("access_token", "fake-jwt")
        # No csrf_token cookie set
        response = client.post(
            "/protected",
            headers={"X-CSRF-Token": "forged-header-value"},
        )
        assert response.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/middleware/test_csrf.py -x -q --tb=short`

Expected: FAIL — `ImportError: cannot import name 'CSRFMiddleware' from 'backend.middleware.csrf'`

- [ ] **Step 3: Implement `CSRFMiddleware`**

Create `backend/middleware/csrf.py`:

```python
"""CSRF middleware — double-submit cookie pattern.

Enforces CSRF token validation only on cookie-authenticated mutating
requests (POST, PUT, PATCH, DELETE). Requests with an Authorization
header (Bearer token) are CSRF-safe and skip validation.
"""

from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class CSRFMiddleware(BaseHTTPMiddleware):
    """Validate double-submit CSRF token on cookie-authenticated mutations.

    Args:
        app: The ASGI application.
        csrf_exempt_paths: Set of URL paths that skip CSRF validation.
    """

    def __init__(self, app, csrf_exempt_paths: set[str] | None = None) -> None:
        super().__init__(app)
        self.csrf_exempt_paths: set[str] = csrf_exempt_paths or set()

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request, enforcing CSRF on cookie-auth mutations."""
        # Safe methods never need CSRF
        if request.method in _SAFE_METHODS:
            return await call_next(request)

        # Exempt paths skip CSRF
        if request.url.path in self.csrf_exempt_paths:
            return await call_next(request)

        # Bearer auth is CSRF-safe — skip
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            return await call_next(request)

        # No auth cookies at all → not cookie-auth → skip
        # Check both access_token AND refresh_token — a request with only
        # refresh_token is still cookie-auth (access may have expired mid-flight).
        access_cookie = request.cookies.get("access_token")
        refresh_cookie = request.cookies.get("refresh_token")
        if not access_cookie and not refresh_cookie:
            return await call_next(request)

        # Cookie-auth mutating request → validate CSRF token
        csrf_cookie = request.cookies.get("csrf_token", "")
        csrf_header = request.headers.get("x-csrf-token", "")

        if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
            logger.warning(
                "CSRF validation failed: path=%s method=%s",
                request.url.path,
                request.method,
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token validation failed"},
            )

        return await call_next(request)
```

- [ ] **Step 4: Add COOKIE_CSRF_TOKEN constant to `dependencies.py`**

Add after the existing cookie constants (line ~62 of `backend/dependencies.py`):

```python
COOKIE_CSRF_TOKEN = "csrf_token"
```

- [ ] **Step 5: Export from `backend/middleware/__init__.py`**

Add to `backend/middleware/__init__.py`:

```python
from backend.middleware.csrf import CSRFMiddleware

__all__ = ["CSRFMiddleware"]
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/unit/middleware/test_csrf.py -x -q --tb=short`

Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add backend/middleware/csrf.py backend/middleware/__init__.py backend/dependencies.py tests/unit/middleware/test_csrf.py
git commit -m "feat(csrf): add double-submit cookie middleware (KAN-417)"
```

---

## Task 10: CSRF — Wire Into Auth Cookies and Main App

**Files:**
- Modify: `backend/routers/auth/_helpers.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Update `_set_auth_cookies` to include CSRF token**

In `backend/routers/auth/_helpers.py`, add `secrets` import and update `_set_auth_cookies`:

```python
import secrets

from backend.dependencies import (
    COOKIE_ACCESS_TOKEN,
    COOKIE_CSRF_TOKEN,
    COOKIE_PATH,
    COOKIE_REFRESH_TOKEN,
    COOKIE_SAMESITE,
)
```

Update `_set_auth_cookies`:

```python
def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Set httpOnly auth cookies + non-httpOnly CSRF cookie on the response.

    Args:
        response: FastAPI Response object.
        access_token: JWT access token.
        refresh_token: JWT refresh token.
    """
    response.set_cookie(
        key=COOKIE_ACCESS_TOKEN,
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key=COOKIE_REFRESH_TOKEN,
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )
    response.set_cookie(
        key=COOKIE_CSRF_TOKEN,
        value=secrets.token_urlsafe(32),
        httponly=False,  # Frontend must read this via document.cookie
        secure=settings.COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
```

Update `_clear_auth_cookies`:

```python
def _clear_auth_cookies(response: Response) -> None:
    """Clear auth cookies + CSRF cookie from the response."""
    response.delete_cookie(key=COOKIE_ACCESS_TOKEN, path=COOKIE_PATH)
    response.delete_cookie(key=COOKIE_REFRESH_TOKEN, path=COOKIE_PATH)
    response.delete_cookie(key=COOKIE_CSRF_TOKEN, path=COOKIE_PATH)
```

- [ ] **Step 2: Register CSRF middleware in `main.py`**

**Order matters.** Starlette wraps middleware in reverse registration order: **last registered = outermost**.

Desired stack (outermost → innermost):
1. `ErrorHandlerMiddleware` — catches all errors
2. `CORSMiddleware` — handles preflight OPTIONS (and CORS errors)
3. `CSRFMiddleware` — enforces CSRF on mutating cookie-auth
4. `HttpMetricsMiddleware` — measures processing time

Registration order (first added → innermost, last added → outermost) must be:
```python
app.add_middleware(HttpMetricsMiddleware)   # innermost
app.add_middleware(CSRFMiddleware, ...)
app.add_middleware(CORSMiddleware, ...)
app.add_middleware(ErrorHandlerMiddleware)  # outermost
```

The existing code registers `CORSMiddleware` then `HttpMetricsMiddleware` then `ErrorHandlerMiddleware` — this currently makes ErrorHandler outermost, then HttpMetrics, then CORS. CORS currently runs innermost which is already suboptimal, but the plan must preserve CORS being outside CSRF.

In `backend/main.py`, replace the existing middleware registration block (lines 310-322) with:

```python
from backend.middleware.csrf import CSRFMiddleware  # noqa: E402

# Middleware — added in reverse order of execution (last = outermost)
app.add_middleware(HttpMetricsMiddleware)
app.add_middleware(
    CSRFMiddleware,
    csrf_exempt_paths={
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",
        "/api/v1/auth/forgot-password",
        "/api/v1/auth/reset-password",
        "/api/v1/auth/google/callback",
        "/api/v1/health",
        "/api/v1/health/detail",
        "/docs",
        "/openapi.json",
    },
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
)
app.add_middleware(ErrorHandlerMiddleware)
```

**Note:** The existing `CORSMiddleware` block at lines 310-316 must be removed (this block replaces it). Make sure there's only ONE CORS registration after this change.

Final stack (outermost → innermost): **ErrorHandler → CORS → CSRF → HttpMetrics → app**.

- [ ] **Step 3: Verify app starts**

Run: `uv run python -c "from backend.main import app; print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/routers/auth/_helpers.py backend/main.py
git commit -m "feat(csrf): wire CSRF token into auth cookies + register middleware (KAN-417)"
```

---

## Task 11: CSRF — Frontend Integration

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add CSRF token reader utility**

Add a helper function to read the CSRF cookie from `document.cookie`:

```typescript
function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrf_token="));
  return match ? match.split("=")[1] : null;
}
```

- [ ] **Step 2: Attach X-CSRF-Token header on mutating requests**

Update the `request` function to include the CSRF token for POST/PATCH/DELETE:

```typescript
async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${path}`;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  // Attach CSRF token for mutating requests (cookie-auth only)
  const method = (options.method || "GET").toUpperCase();
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      headers["X-CSRF-Token"] = csrfToken;
    }
  }

  const config: RequestInit = {
    ...options,
    credentials: "include",
    headers,
  };

  // ... rest of the function unchanged
```

- [ ] **Step 3: Also update `loginRequest` and `logoutRequest`**

`loginRequest` (line 108) and `logoutRequest` (line 154) use raw `fetch` (not the `request` wrapper). Login is CSRF-exempt (pre-auth), but `logoutRequest` sends cookies and is a POST — it needs the CSRF token.

Update `logoutRequest`:

```typescript
export async function logoutRequest(): Promise<void> {
  const headers: Record<string, string> = {};
  const csrfToken = getCsrfToken();
  if (csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }
  await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    credentials: "include",
    headers,
  });
}
```

`loginRequest` and `registerRequest` don't need CSRF (they're exempt). No changes needed.

- [ ] **Step 4: Lint frontend**

Run: `cd frontend && npm run lint`

Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(csrf): attach X-CSRF-Token header in frontend API client (KAN-417)"
```

---

## Task 12: CSRF — Update Existing Auth Tests

**Files:**
- Modify: `tests/api/test_auth.py`

- [ ] **Step 1: Update `test_login_sets_cookies`**

Find the test at `tests/api/test_auth.py:110` that asserts login sets cookies. Add assertion for `csrf_token` presence + max_age match with access token TTL:

```python
# After existing cookie assertions:
set_cookie_headers = response.headers.getlist("set-cookie")
csrf_headers = [h for h in set_cookie_headers if h.startswith("csrf_token=")]
assert len(csrf_headers) == 1, "Login must set exactly one csrf_token cookie"

# Verify max_age matches access token TTL (regression guard: drift between CSRF and access cookie lifetimes)
from backend.config import settings
expected_max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
assert f"Max-Age={expected_max_age}" in csrf_headers[0], (
    f"CSRF cookie max_age must match access token TTL ({expected_max_age}s)"
)
```

- [ ] **Step 2: Update `test_login_cookies_are_httponly`**

This test iterates all `set-cookie` headers and asserts `httponly`. After CSRF, it will fail because `csrf_token` is `httpOnly=False`.

Update to check per-cookie:

```python
async def test_login_cookies_are_httponly(self, client: AsyncClient) -> None:
    """Auth cookies must be httpOnly; CSRF cookie must NOT be httpOnly."""
    # ... login ...
    cookies = response.headers.getlist("set-cookie")
    for cookie_header in cookies:
        if cookie_header.startswith("csrf_token="):
            assert "httponly" not in cookie_header.lower(), "CSRF cookie must not be httpOnly"
        else:
            assert "httponly" in cookie_header.lower(), f"Auth cookie missing httpOnly: {cookie_header}"
```

- [ ] **Step 3: Update `test_refresh_sets_cookies`**

Find the test at `tests/api/test_auth.py:231`. Add assertion that refresh also sets a new `csrf_token` cookie:

```python
set_cookie_headers = response.headers.getlist("set-cookie")
csrf_headers = [h for h in set_cookie_headers if h.startswith("csrf_token=")]
assert len(csrf_headers) == 1, "Refresh must set a new csrf_token cookie"
```

- [ ] **Step 4: Update `test_logout_clears_cookies`**

Find the test at `tests/api/test_auth.py:264`. Add assertion that `csrf_token` is explicitly cleared (not just rotated) — the Set-Cookie header must have `Max-Age=0` or an expiration in the past:

```python
set_cookie_headers = response.headers.getlist("set-cookie")
csrf_headers = [h for h in set_cookie_headers if h.startswith("csrf_token=")]
assert len(csrf_headers) == 1, "Logout must emit a csrf_token clear header"
# Logout MUST clear the cookie, not rotate it
assert "Max-Age=0" in csrf_headers[0] or 'expires=' in csrf_headers[0].lower(), (
    f"csrf_token cookie must be cleared on logout, got: {csrf_headers[0]}"
)
```

- [ ] **Step 5: Run auth tests**

Run: `uv run pytest tests/api/test_auth.py -x -q --tb=short`

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add tests/api/test_auth.py
git commit -m "test(csrf): update auth cookie assertions for CSRF token (KAN-417)"
```

---

## Task 13: CSRF — API Integration Tests

**Files:**
- Create: `tests/api/test_csrf.py`

- [ ] **Step 1: Write CSRF API integration tests**

```python
"""CSRF protection API integration tests.

Uses real Redis testcontainer (via session-scoped fixture in tests/conftest.py).
Each test gets a fresh DB via per-test TRUNCATE fixture.
"""

import uuid

import pytest
from httpx import AsyncClient


class TestCSRFProtection:
    """End-to-end CSRF validation for cookie-authenticated requests."""

    async def _register_and_login(self, client: AsyncClient) -> tuple[str, str]:
        """Register + login, return (email, csrf_token)."""
        email = f"csrf-{uuid.uuid4().hex[:8]}@test.com"
        password = "ValidPass1"
        register_resp = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        assert register_resp.status_code in (201, 409), (
            f"Unexpected register status: {register_resp.status_code}"
        )
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert login_resp.status_code == 200
        csrf_token = login_resp.cookies.get("csrf_token")
        assert csrf_token, "Login must set csrf_token cookie"
        return email, csrf_token

    async def test_mutating_request_with_valid_csrf_succeeds(self, client: AsyncClient) -> None:
        """POST with matching X-CSRF-Token passes."""
        _, csrf_token = await self._register_and_login(client)
        response = await client.post(
            "/api/v1/auth/resend-verification",
            headers={"X-CSRF-Token": csrf_token},
        )
        # 200 (already verified in dev) — the point is it's not 403
        assert response.status_code != 403

    async def test_mutating_request_without_csrf_returns_403(self, client: AsyncClient) -> None:
        """POST without X-CSRF-Token header → 403."""
        await self._register_and_login(client)
        response = await client.post("/api/v1/auth/resend-verification")
        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]

    async def test_mutating_request_with_wrong_csrf_returns_403(self, client: AsyncClient) -> None:
        """POST with wrong X-CSRF-Token → 403."""
        await self._register_and_login(client)
        response = await client.post(
            "/api/v1/auth/resend-verification",
            headers={"X-CSRF-Token": "wrong-value"},
        )
        assert response.status_code == 403

    async def test_bearer_auth_bypasses_csrf(self, client: AsyncClient) -> None:
        """Requests with Authorization Bearer skip CSRF (even without token)."""
        email, _ = await self._register_and_login(client)
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "ValidPass1"},
        )
        access_token = login_resp.json()["access_token"]

        response = await client.post(
            "/api/v1/auth/resend-verification",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code != 403

    async def test_refresh_issues_new_csrf_token(self, client: AsyncClient) -> None:
        """Refresh endpoint issues a new CSRF token (rotates on every refresh)."""
        email, _ = await self._register_and_login(client)
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "ValidPass1"},
        )
        old_csrf = login_resp.cookies.get("csrf_token")
        refresh_token = login_resp.json()["refresh_token"]

        refresh_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_resp.status_code == 200
        new_csrf = refresh_resp.cookies.get("csrf_token")
        assert new_csrf, "Refresh must set csrf_token cookie"
        assert new_csrf != old_csrf, "CSRF token must rotate on refresh"

    async def test_logout_clears_csrf_token(self, client: AsyncClient) -> None:
        """Logout MUST clear csrf_token cookie (not just rotate it)."""
        _, csrf_token = await self._register_and_login(client)
        response = await client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response.status_code == 204
        csrf_headers = [
            h for h in response.headers.getlist("set-cookie")
            if h.startswith("csrf_token=")
        ]
        assert csrf_headers, "Logout should emit csrf_token clear header"
        assert "Max-Age=0" in csrf_headers[0] or 'expires=' in csrf_headers[0].lower(), (
            f"csrf_token cookie must be cleared on logout, got: {csrf_headers[0]}"
        )

    async def test_cors_preflight_allows_x_csrf_token_header(self, client: AsyncClient) -> None:
        """CORS preflight OPTIONS must advertise X-CSRF-Token in allow_headers."""
        response = await client.options(
            "/api/v1/auth/resend-verification",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-CSRF-Token",
            },
        )
        # CORS middleware should reflect the allowed headers
        allow_headers = response.headers.get("access-control-allow-headers", "").lower()
        assert "x-csrf-token" in allow_headers, (
            f"CORS must allow X-CSRF-Token header, got: {allow_headers}"
        )
```

- [ ] **Step 2: Run CSRF API tests**

Run: `uv run pytest tests/api/test_csrf.py -x -q --tb=short`

Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add tests/api/test_csrf.py
git commit -m "test(csrf): add API integration tests for CSRF protection (KAN-417)"
```

---

## Task 14: Final Verification

- [ ] **Step 1: Lint all changed files**

Run: `uv run ruff check --fix backend/ tests/ && uv run ruff format backend/ tests/`

Expected: Zero errors.

- [ ] **Step 2: Run full backend test suite**

Run: `uv run pytest tests/unit/ -q --tb=short 2>&1 | tail -5`

Expected: All 1906+ tests pass.

- [ ] **Step 3: Run API tests**

Run: `uv run pytest tests/api/ -q --tb=short 2>&1 | tail -5`

Expected: All 38+ tests pass.

- [ ] **Step 4: Frontend lint + type check**

Run: `cd frontend && npm run lint && npx tsc --noEmit`

Expected: Zero errors.

- [ ] **Step 5: Verify app starts end-to-end**

Run: `uv run uvicorn backend.main:app --port 8181 &` then `sleep 3 && curl -s http://localhost:8181/health | python3 -m json.tool` then `kill %1`

Expected: `{"status": "healthy", ...}`

- [ ] **Step 6: Commit any lint fixes**

```bash
git add -A
git commit -m "chore: lint fixes after KAN-408 refactors"
```
