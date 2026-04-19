# tests/semgrep/test_observability_rules.py
#
# Intentionally-bad code snippets — each should trigger the corresponding
# observability Semgrep rule. Semgrep test convention: place
# `# ruleid: <rule-id>` on the line immediately before the offending statement.
#
# Run: semgrep --config .semgrep/observability-rules.yml --test tests/semgrep/

from __future__ import annotations

from datetime import datetime

import httpx
import requests
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Rule 1: obs-ban-direct-httpx-client
# ---------------------------------------------------------------------------


def bad_direct_httpx():
    # ruleid: obs-ban-direct-httpx-client
    client = httpx.AsyncClient(timeout=30)
    return client


# ---------------------------------------------------------------------------
# Rule 2: obs-ban-direct-requests
# ---------------------------------------------------------------------------


def bad_requests_get():
    # ruleid: obs-ban-direct-requests
    return requests.get("https://api.example.com/data")


def bad_requests_post():
    # ruleid: obs-ban-direct-requests
    return requests.post("https://api.example.com/data", json={})


# ---------------------------------------------------------------------------
# Rule 3: obs-ban-utcnow
# ---------------------------------------------------------------------------


def bad_utcnow():
    # ruleid: obs-ban-utcnow
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# Rule 7: obs-ban-str-exception-detail
# ---------------------------------------------------------------------------


def bad_str_exception():
    try:
        pass
    except Exception as e:
        # ruleid: obs-ban-str-exception-detail
        raise HTTPException(status_code=500, detail=str(e))


class ToolResult:
    def __init__(self, error: str | None = None):
        self.error = error


def bad_toolresult_str():
    try:
        pass
    except Exception as e:
        # ruleid: obs-ban-str-exception-detail
        return ToolResult(error=str(e))


# ---------------------------------------------------------------------------
# Rule 8: obs-warn-silent-except
# ---------------------------------------------------------------------------


def bad_silent_except():
    try:
        _ = 1 / 0
    # ruleid: obs-warn-silent-except
    except ZeroDivisionError:
        pass
