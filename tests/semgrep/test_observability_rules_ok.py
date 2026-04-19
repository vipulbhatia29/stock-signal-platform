# tests/semgrep/test_observability_rules_ok.py
#
# Code that should NOT trigger any observability rules. Each snippet has an
# `# ok: <rule-id>` comment in Semgrep test convention.
#
# Run: semgrep --config .semgrep/observability-rules.yml --test tests/semgrep/

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ok: obs-ban-utcnow
# ---------------------------------------------------------------------------


def good_now_utc():
    # ok: obs-ban-utcnow
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# ok: obs-ban-str-exception-detail
# ---------------------------------------------------------------------------


def good_http_exception():
    try:
        pass
    except Exception:
        logger.exception("Something failed")
        # ok: obs-ban-str-exception-detail
        raise HTTPException(status_code=500, detail="Internal error")


# ---------------------------------------------------------------------------
# ok: obs-warn-silent-except
# ---------------------------------------------------------------------------


def good_except_with_logging():
    try:
        _ = 1 / 0
    except ZeroDivisionError:
        # ok: obs-warn-silent-except
        logger.warning("Division by zero", exc_info=True)
