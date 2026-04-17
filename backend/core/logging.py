"""Structured JSON logging configuration — structlog.

Per spec §2.4 — canonical fields on every log line: timestamp (ISO-8601 UTC),
level, logger, message, trace_id (from ContextVar, nullable — omitted if None),
span_id.

Call ``configure_structlog()`` once at FastAPI startup and once at Celery
worker_ready. Test fixtures can pass a custom ``output`` buffer.
"""
from __future__ import annotations

import logging
import sys
from typing import IO, Any

import structlog

from backend.observability.context import current_span_id, current_trace_id


def _inject_trace_context(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Add trace_id and span_id from ContextVars if present.

    Args:
        logger: The bound logger instance (unused, required by structlog processor API).
        method_name: The log method name, e.g. ``"info"`` (unused).
        event_dict: The mutable event dictionary being built up by the processor chain.

    Returns:
        The event_dict, potentially enriched with ``trace_id`` and/or ``span_id``.
    """
    tid = current_trace_id()
    sid = current_span_id()
    if tid is not None:
        event_dict["trace_id"] = str(tid)
    if sid is not None:
        event_dict["span_id"] = str(sid)
    return event_dict


def configure_structlog(output: IO[str] | None = None) -> None:
    """Configure structlog with JSON rendering and trace context injection.

    Installs a processor chain that emits one JSON object per log line with
    canonical fields: ``timestamp``, ``level``, ``event``, and optionally
    ``trace_id`` / ``span_id`` when the corresponding ContextVars are set.

    Call once at application startup (FastAPI lifespan or Celery worker_ready).
    Tests can pass a ``StringIO`` buffer via ``output`` to capture log lines.

    Args:
        output: Writable text stream for log output. Defaults to sys.stdout.
    """
    dest = output or sys.stdout
    logging.basicConfig(
        format="%(message)s",
        stream=dest,
        level=logging.INFO,
        force=True,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _inject_trace_context,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=dest),
        cache_logger_on_first_use=False,
    )
