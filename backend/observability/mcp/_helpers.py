"""Shared helpers for observability MCP tools."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

_SINCE_RE = re.compile(r"^(\d+)(m|h|d)$")
_UNIT_MAP = {"m": "minutes", "h": "hours", "d": "days"}


def parse_since(since: str | None, *, default: str = "1h") -> datetime:
    """Parse a relative time string like '1h', '24h', '7d' into a UTC cutoff.

    Args:
        since: Relative time string. None or invalid falls back to default.
        default: Fallback relative time string.

    Returns:
        UTC datetime representing the start of the window.
    """
    raw = since or default
    match = _SINCE_RE.match(raw)
    if not match:
        logger.warning("Invalid since value %r, falling back to %s", since, default)
        match = _SINCE_RE.match(default)
        assert match  # default must be valid
    value, unit = int(match.group(1)), match.group(2)
    delta = timedelta(**{_UNIT_MAP[unit]: value})
    return datetime.now(timezone.utc) - delta


def clamp_limit(limit: int | None, *, default: int = 50, maximum: int = 500) -> int:
    """Clamp limit to [1, maximum], defaulting to 50.

    Args:
        limit: Requested limit. None uses default.
        default: Default limit value.
        maximum: Maximum allowed limit.

    Returns:
        Clamped integer limit.
    """
    if limit is None:
        return default
    return max(1, min(limit, maximum))


def build_envelope(
    tool_name: str,
    result: Any,
    *,
    total_count: int = 0,
    limit: int | None = None,
    since: datetime | None = None,
) -> dict[str, Any]:
    """Wrap tool output in the standard MCP envelope.

    Args:
        tool_name: Name of the tool.
        result: The tool's result payload.
        total_count: Total matching rows before truncation.
        limit: Applied limit (for truncation flag).
        since: Window start time.

    Returns:
        Standard envelope dict with tool, window, result, meta.
    """
    now = datetime.now(timezone.utc)
    return {
        "tool": tool_name,
        "window": {
            "from": (since or now).isoformat(),
            "to": now.isoformat(),
        },
        "result": result,
        "meta": {
            "total_count": total_count,
            "truncated": limit is not None and total_count > limit,
            "schema_version": "v1",
        },
    }
