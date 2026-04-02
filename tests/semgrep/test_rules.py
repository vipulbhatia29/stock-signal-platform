# tests/semgrep/test_rules.py
#
# Intentionally-bad code snippets — each should trigger the corresponding
# Semgrep rule. Semgrep test convention: place `# ruleid: <rule-id>` on the
# line immediately before the offending statement.
#
# Run: semgrep --config .semgrep/stock-signal-rules.yml --test tests/semgrep/

from __future__ import annotations

import subprocess
import traceback

import jwt
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

router = APIRouter()


# ---------------------------------------------------------------------------
# Rule 1: no-str-exception-in-httpexception
# ---------------------------------------------------------------------------

def bad_http_exception():
    try:
        _ = 1 / 0
    except Exception as e:
        # ruleid: no-str-exception-in-httpexception
        raise HTTPException(status_code=400, detail=str(e))


def bad_http_exception_with_status():
    try:
        pass
    except ValueError as exc:
        # ruleid: no-str-exception-in-httpexception
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Rule 2: no-str-exception-in-toolresult
# ---------------------------------------------------------------------------

class ToolResult:
    def __init__(self, error: str | None = None, output: str | None = None):
        self.error = error
        self.output = output


def bad_tool_result():
    try:
        pass
    except Exception as e:
        # ruleid: no-str-exception-in-toolresult
        return ToolResult(error=str(e))


# ---------------------------------------------------------------------------
# Rule 3: async-endpoints-only
# ---------------------------------------------------------------------------

# ruleid: async-endpoints-only
@router.get("/sync-bad")
def sync_get_handler():
    return {"status": "bad"}


# ruleid: async-endpoints-only
@router.post("/sync-bad-post")
def sync_post_handler(body: dict):
    return body


# ruleid: async-endpoints-only
@router.delete("/sync-bad-delete")
def sync_delete_handler(item_id: int):
    return {"deleted": item_id}


# ---------------------------------------------------------------------------
# Rule 4: no-pip-install
# ---------------------------------------------------------------------------

def bad_install():
    # ruleid: no-pip-install
    subprocess.run(["pip", "install", "requests"], check=True)


def bad_install_upgrade():
    # ruleid: no-pip-install
    subprocess.run(["pip", "install", "--upgrade", "numpy"], check=False)


# ---------------------------------------------------------------------------
# Rule 5: no-secrets-in-code  (mutable module state skipped — see TODO in rules)
# ---------------------------------------------------------------------------

# ruleid: no-secrets-in-code
JWT_SECRET = "super-secret-signing-key-do-not-commit"  # noqa: S105

# ruleid: no-secrets-in-code
API_KEY = "sk-1234567890abcdef"  # noqa: S105

# ruleid: no-secrets-in-code
database_password = "hunter2"  # noqa: S105


# ---------------------------------------------------------------------------
# Rule 6: no-stack-trace-in-response
# ---------------------------------------------------------------------------

def bad_traceback_response():
    try:
        pass
    except Exception:
        # ruleid: no-stack-trace-in-response
        raise HTTPException(status_code=500, detail=traceback.format_exc())


# ---------------------------------------------------------------------------
# Rule 7: no-file-path-in-error
# ---------------------------------------------------------------------------

def bad_file_path_response():
    # ruleid: no-file-path-in-error
    raise HTTPException(status_code=500, detail=__file__)


# ---------------------------------------------------------------------------
# Rule 8: jwt-no-algorithm-pinning
# ---------------------------------------------------------------------------

def bad_jwt_decode(token: str, secret: str) -> dict:
    # ruleid: jwt-no-algorithm-pinning
    return jwt.decode(token, secret)


# ---------------------------------------------------------------------------
# Rule 9: jwt-verify-disabled
# ---------------------------------------------------------------------------

def bad_jwt_no_verify(token: str, secret: str) -> dict:
    import jwt
    # ruleid: jwt-verify-disabled
    return jwt.decode(  # nosemgrep
        token, secret, options={"verify_signature": False}
    )


# ---------------------------------------------------------------------------
# Rule 10: no-timing-unsafe-compare
# ---------------------------------------------------------------------------

def bad_token_compare(access_token: str, expected_token: str) -> bool:
    # ruleid: no-timing-unsafe-compare
    return access_token == expected_token


def bad_secret_compare(api_secret: str, incoming: str) -> bool:
    # ruleid: no-timing-unsafe-compare
    return api_secret == incoming


# ---------------------------------------------------------------------------
# Rule 11: no-open-redirect
# ---------------------------------------------------------------------------

def bad_open_redirect(next_url: str) -> RedirectResponse:
    # ruleid: no-open-redirect
    return RedirectResponse(url=next_url, status_code=302)


def bad_open_redirect_variable(redirect_target: str) -> RedirectResponse:
    # ruleid: no-open-redirect
    return RedirectResponse(url=redirect_target)


# ---------------------------------------------------------------------------
# Rule 12: cookie-missing-secure-flag
# ---------------------------------------------------------------------------

def bad_cookie(response):
    # ruleid: cookie-missing-secure-flag
    response.set_cookie(key="access_token", value="abc", httponly=True)


def bad_cookie_no_secure(response):
    # ruleid: cookie-missing-secure-flag
    response.set_cookie(
        key="refresh_token",
        value="xyz",
        httponly=True,
        samesite="lax",
    )


# ---------------------------------------------------------------------------
# Rule 13: no-unbounded-redis-key
# ---------------------------------------------------------------------------

async def bad_redis_key(redis, ticker: str, user_id: str):
    # ruleid: no-unbounded-redis-key
    await redis.set(f"signal:{ticker}:{user_id}", "value", ex=300)


async def bad_redis_key_simple(redis, user_input: str):
    # ruleid: no-unbounded-redis-key
    await redis.set(f"cache:{user_input}", "data")
