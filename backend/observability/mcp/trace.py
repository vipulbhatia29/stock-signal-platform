"""MCP tool: get_trace.

Reconstructs a full cross-layer distributed trace as a span tree by querying
all observability tables that carry a trace_id column. Queries are executed
in parallel via asyncio.gather.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select

from backend.database import async_session_factory
from backend.observability.mcp._helpers import build_envelope
from backend.observability.models import (
    AgentIntentLog,
    AgentReasoningLog,
    ApiErrorLog,
    AuthEventLog,
    CacheOperationLog,
    ExternalApiCallLog,
    OAuthEventLog,
    RequestLog,
    SlowQueryLog,
)

logger = logging.getLogger(__name__)


def _ts_iso(ts: Any) -> str | None:
    """Convert a datetime to ISO 8601 string, or None."""
    if ts is None:
        return None
    return ts.isoformat()


async def _fetch_request_spans(trace_id: str) -> list[dict[str, Any]]:
    """Fetch RequestLog spans for the given trace_id."""
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(RequestLog).where(RequestLog.trace_id == trace_id)))
            .scalars()
            .all()
        )
    spans = []
    for r in rows:
        spans.append(
            {
                "span_id": r.span_id,
                "parent_span_id": None,  # root span — no parent in RequestLog
                "kind": "http",
                "ts": _ts_iso(r.ts),
                "latency_ms": r.latency_ms,
                "details": {
                    "method": r.method,
                    "path": r.path,
                    "status_code": r.status_code,
                    "environment_snapshot": r.environment_snapshot,
                },
            }
        )
    return spans


async def _fetch_api_error_spans(trace_id: str) -> list[dict[str, Any]]:
    """Fetch ApiErrorLog spans for the given trace_id."""
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(ApiErrorLog).where(ApiErrorLog.trace_id == trace_id)))
            .scalars()
            .all()
        )
    return [
        {
            "span_id": r.span_id,
            "parent_span_id": r.parent_span_id,
            "kind": "http_error",
            "ts": _ts_iso(r.ts),
            "latency_ms": None,
            "details": {
                "status_code": r.status_code,
                "error_type": r.error_type,
                "error_message": r.error_message,
                "stack_trace": r.stack_trace,
                "stack_signature": r.stack_signature,
            },
        }
        for r in rows
    ]


async def _fetch_external_api_spans(trace_id: str) -> list[dict[str, Any]]:
    """Fetch ExternalApiCallLog spans for the given trace_id."""
    async with async_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(ExternalApiCallLog).where(ExternalApiCallLog.trace_id == trace_id)
                )
            )
            .scalars()
            .all()
        )
    return [
        {
            "span_id": r.span_id,
            "parent_span_id": r.parent_span_id,
            "kind": "external_api",
            "ts": _ts_iso(r.ts),
            "latency_ms": r.latency_ms,
            "details": {
                "provider": r.provider,
                "endpoint": r.endpoint,
                "status_code": r.status_code,
                "error_reason": r.error_reason,
                "stack_signature": r.stack_signature,
            },
        }
        for r in rows
    ]


async def _fetch_slow_query_spans(trace_id: str) -> list[dict[str, Any]]:
    """Fetch SlowQueryLog spans for the given trace_id."""
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(SlowQueryLog).where(SlowQueryLog.trace_id == trace_id)))
            .scalars()
            .all()
        )
    return [
        {
            "span_id": r.span_id,
            "parent_span_id": r.parent_span_id,
            "kind": "db.query",
            "ts": _ts_iso(r.ts),
            "latency_ms": r.duration_ms,
            "details": {
                "query_text": r.query_text,
                "duration_ms": r.duration_ms,
                "source_file": r.source_file,
                "rows_affected": r.rows_affected,
            },
        }
        for r in rows
    ]


async def _fetch_auth_spans(trace_id: str) -> list[dict[str, Any]]:
    """Fetch AuthEventLog spans for the given trace_id."""
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(AuthEventLog).where(AuthEventLog.trace_id == trace_id)))
            .scalars()
            .all()
        )
    return [
        {
            "span_id": r.span_id or r.id,
            "parent_span_id": None,
            "kind": "auth",
            "ts": _ts_iso(r.ts),
            "latency_ms": None,
            "details": {
                "event_type": r.event_type,
                "outcome": r.outcome,
                "failure_reason": r.failure_reason,
            },
        }
        for r in rows
    ]


async def _fetch_oauth_spans(trace_id: str) -> list[dict[str, Any]]:
    """Fetch OAuthEventLog spans for the given trace_id."""
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(OAuthEventLog).where(OAuthEventLog.trace_id == trace_id)))
            .scalars()
            .all()
        )
    return [
        {
            "span_id": r.span_id or r.id,
            "parent_span_id": None,
            "kind": "oauth",
            "ts": _ts_iso(r.ts),
            "latency_ms": None,
            "details": {
                "provider": r.provider,
                "action": r.action,
                "status": r.status,
                "error_reason": r.error_reason,
            },
        }
        for r in rows
    ]


async def _fetch_agent_intent_spans(trace_id: str) -> list[dict[str, Any]]:
    """Fetch AgentIntentLog spans for the given trace_id."""
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(AgentIntentLog).where(AgentIntentLog.trace_id == trace_id)))
            .scalars()
            .all()
        )
    return [
        {
            "span_id": r.span_id,
            "parent_span_id": None,
            "kind": "agent.intent",
            "ts": _ts_iso(r.ts),
            "latency_ms": None,
            "details": {
                "intent": r.intent,
                "confidence": r.confidence,
                "out_of_scope": r.out_of_scope,
                "decline_reason": r.decline_reason,
            },
        }
        for r in rows
    ]


async def _fetch_agent_reasoning_spans(trace_id: str) -> list[dict[str, Any]]:
    """Fetch AgentReasoningLog spans for the given trace_id."""
    async with async_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(AgentReasoningLog).where(AgentReasoningLog.trace_id == trace_id)
                )
            )
            .scalars()
            .all()
        )
    return [
        {
            "span_id": r.span_id,
            "parent_span_id": r.parent_span_id,
            "kind": "agent.reasoning",
            "ts": _ts_iso(r.ts),
            "latency_ms": None,
            "details": {
                "loop_step": r.loop_step,
                "reasoning_type": r.reasoning_type,
                "content_summary": r.content_summary,
                "termination_reason": r.termination_reason,
            },
        }
        for r in rows
    ]


async def _fetch_cache_spans(trace_id: str) -> list[dict[str, Any]]:
    """Fetch CacheOperationLog spans for the given trace_id."""
    async with async_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(CacheOperationLog).where(CacheOperationLog.trace_id == trace_id)
                )
            )
            .scalars()
            .all()
        )
    return [
        {
            "span_id": r.span_id,
            "parent_span_id": None,
            "kind": "cache",
            "ts": _ts_iso(r.ts),
            "latency_ms": r.latency_ms,
            "details": {
                "operation": r.operation,
                "key_pattern": r.key_pattern,
                "hit": r.hit,
                "error_reason": r.error_reason,
            },
        }
        for r in rows
    ]


def _build_span_tree(spans: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Build a parent-child span tree from a flat list of spans.

    Args:
        spans: Flat list of span dicts, each with span_id and parent_span_id.

    Returns:
        Root span dict with nested children, or None if no spans.
    """
    if not spans:
        return None

    by_id: dict[str, dict[str, Any]] = {}
    for span in spans:
        sid = span.get("span_id")
        if sid:
            span["children"] = []
            by_id[sid] = span

    roots = []
    for span in by_id.values():
        parent_id = span.get("parent_span_id")
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(span)
        else:
            roots.append(span)

    if len(roots) == 1:
        return roots[0]

    # Prefer the HTTP root span if multiple roots
    http_roots = [r for r in roots if r.get("kind") == "http"]
    if http_roots:
        return http_roots[0]

    # Fallback: return the earliest span as root
    sorted_roots = sorted(roots, key=lambda s: s.get("ts") or "")
    return sorted_roots[0] if sorted_roots else None


async def get_trace(trace_id: str) -> dict[str, Any]:
    """Reconstruct a full cross-layer trace as a span tree.

    Queries all observability tables with trace_id columns in parallel
    and assembles the results into a parent-child span tree.

    Args:
        trace_id: UUID string of the trace to reconstruct.

    Returns:
        Standard MCP envelope with trace_id and root_span tree.
    """
    all_span_groups = await asyncio.gather(
        _fetch_request_spans(trace_id),
        _fetch_api_error_spans(trace_id),
        _fetch_external_api_spans(trace_id),
        _fetch_slow_query_spans(trace_id),
        _fetch_auth_spans(trace_id),
        _fetch_oauth_spans(trace_id),
        _fetch_agent_intent_spans(trace_id),
        _fetch_agent_reasoning_spans(trace_id),
        _fetch_cache_spans(trace_id),
    )

    all_spans: list[dict[str, Any]] = []
    for group in all_span_groups:
        all_spans.extend(group)

    root_span = _build_span_tree(all_spans)

    if root_span is None and all_spans:
        # Fallback: flat list ordered by ts
        sorted_spans = sorted(all_spans, key=lambda s: s.get("ts") or "")
        result: dict[str, Any] = {
            "trace_id": trace_id,
            "root_span": None,
            "flat_spans": sorted_spans,
            "span_count": len(sorted_spans),
        }
    else:
        result = {
            "trace_id": trace_id,
            "root_span": root_span,
            "span_count": len(all_spans),
        }

    return build_envelope("get_trace", result)
