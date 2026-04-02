# tests/semgrep/test_rules_ok.py
#
# Code that should NOT trigger any stock-signal-rules. Each snippet has an
# `# ok: <rule-id>` comment in Semgrep test convention.
#
# Run: semgrep --config .semgrep/stock-signal-rules.yml --test tests/semgrep/

from __future__ import annotations

import hmac
import logging
import os
import subprocess

import jwt
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_REDIRECT_HOSTS = {"app.example.com", "localhost"}


# ---------------------------------------------------------------------------
# ok: no-str-exception-in-httpexception
# ---------------------------------------------------------------------------


def good_http_exception():
    try:
        _ = 1 / 0
    except Exception:
        logger.error("Division failed", exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid calculation")


def good_http_exception_404():
    raise HTTPException(status_code=404, detail="Resource not found")


# ---------------------------------------------------------------------------
# ok: no-str-exception-in-toolresult
# ---------------------------------------------------------------------------


class ToolResult:
    def __init__(self, error: str | None = None, output: str | None = None):
        self.error = error
        self.output = output


def good_tool_result():
    try:
        pass
    except Exception:
        logger.error("Tool execution failed", exc_info=True)
        return ToolResult(error="Tool execution failed. Please try again.")


# ---------------------------------------------------------------------------
# ok: async-endpoints-only
# ---------------------------------------------------------------------------


# ok: async-endpoints-only
@router.get("/async-good")
async def async_get_handler():
    return {"status": "ok"}


# ok: async-endpoints-only
@router.post("/async-good-post")
async def async_post_handler(body: dict):
    return body


# ok: async-endpoints-only
@router.delete("/async-good-delete")
async def async_delete_handler(item_id: int):
    return {"deleted": item_id}


# Non-endpoint sync functions are fine
def helper_function(x: int) -> int:
    return x * 2


# ok: async-endpoints-only — websocket is not get/post/put/delete/patch
@router.websocket("/ws")
async def websocket_handler():
    pass


# ---------------------------------------------------------------------------
# ok: no-pip-install
# ---------------------------------------------------------------------------


def good_subprocess():
    # ok: no-pip-install
    subprocess.run(["git", "status"], check=True)


def good_subprocess_uv():
    # ok: no-pip-install
    subprocess.run(["uv", "add", "requests"], check=True)


# ---------------------------------------------------------------------------
# ok: no-secrets-in-code
# ---------------------------------------------------------------------------

# ok: no-secrets-in-code — reads from environment, not hardcoded
DB_HOST = os.environ.get("DB_HOST", "localhost")
SOME_LABEL = "my-label"
DISPLAY_NAME = "My App Token"


# ---------------------------------------------------------------------------
# ok: no-stack-trace-in-response
# ---------------------------------------------------------------------------


def good_traceback_handling():
    try:
        pass
    except Exception:
        logger.error("Unexpected error", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


# ---------------------------------------------------------------------------
# ok: no-file-path-in-error
# ---------------------------------------------------------------------------


def good_error_response():
    raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# ok: jwt-no-algorithm-pinning
# ---------------------------------------------------------------------------


def good_jwt_decode(token: str, secret: str) -> dict:
    # ok: jwt-no-algorithm-pinning
    return jwt.decode(token, secret, algorithms=["HS256"])


def good_jwt_decode_rs256(token: str, pubkey: str) -> dict:
    # ok: jwt-no-algorithm-pinning
    return jwt.decode(token, pubkey, algorithms=["RS256"])


# ---------------------------------------------------------------------------
# ok: jwt-verify-disabled
# ---------------------------------------------------------------------------


def good_jwt_decode_with_options(token: str, secret: str) -> dict:
    # ok: jwt-verify-disabled — only verify_exp is relaxed, not verify_signature
    return jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        options={"verify_exp": False},
    )


# ---------------------------------------------------------------------------
# ok: no-timing-unsafe-compare
# ---------------------------------------------------------------------------


def good_token_compare(access_token: str, expected_token: str) -> bool:
    # ok: no-timing-unsafe-compare
    return hmac.compare_digest(access_token, expected_token)


def good_compare_plain_strings(a: str, b: str) -> bool:
    # ok: no-timing-unsafe-compare — neither variable name is sensitive
    return a == b


# ---------------------------------------------------------------------------
# ok: no-open-redirect
# ---------------------------------------------------------------------------


def good_redirect_literal() -> RedirectResponse:
    # ok: no-open-redirect
    return RedirectResponse(url="/dashboard", status_code=302)


def good_redirect_validated(next_url: str) -> RedirectResponse:
    # ok: no-open-redirect — validated against allowlist before redirect
    from urllib.parse import urlparse

    parsed = urlparse(next_url)
    if parsed.hostname not in ALLOWED_REDIRECT_HOSTS:
        raise HTTPException(status_code=400, detail="Invalid redirect target")
    # ok: no-open-redirect
    return RedirectResponse(url="/dashboard")


# ---------------------------------------------------------------------------
# ok: cookie-missing-secure-flag
# ---------------------------------------------------------------------------


def good_cookie_secure_true(response):
    # ok: cookie-missing-secure-flag
    response.set_cookie(key="access_token", value="abc", httponly=True, secure=True)


def good_cookie_secure_setting(response, settings):
    # ok: cookie-missing-secure-flag — secure= is a variable (settings.COOKIE_SECURE)
    response.set_cookie(
        key="refresh_token",
        value="xyz",
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
    )


# ---------------------------------------------------------------------------
# ok: no-unbounded-redis-key
# ---------------------------------------------------------------------------


async def good_redis_key_literal(redis):
    # ok: no-unbounded-redis-key
    await redis.set("health:ping", "pong", ex=60)


async def good_redis_key_variable(redis, key: str):
    # ok: no-unbounded-redis-key — not an f-string
    await redis.set(key, "data", ex=300)
