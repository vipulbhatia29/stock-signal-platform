from uuid import UUID

import pytest

from backend.observability.context import (
    current_parent_span_id,
    current_span_id,
    current_trace_id,
    parent_span_id_var,
    span_id_var,
    trace_id_var,
)
from backend.observability.span import span


def test_context_vars_default_none():
    assert current_trace_id() is None
    assert current_span_id() is None
    assert current_parent_span_id() is None


@pytest.mark.asyncio
async def test_span_sets_parent_link():
    root_trace = UUID("01234567-89ab-7def-8123-456789abcdef")
    trace_id_var.set(root_trace)
    try:
        async with span("outer") as outer:
            assert current_trace_id() == root_trace
            assert current_span_id() == outer.span_id
            assert current_parent_span_id() is None
            async with span("inner") as inner:
                assert inner.parent_span_id == outer.span_id
                assert current_span_id() == inner.span_id
            # after inner exits, current_span_id resumes outer
            assert current_span_id() == outer.span_id
    finally:
        trace_id_var.set(None)
        span_id_var.set(None)
        parent_span_id_var.set(None)


@pytest.mark.asyncio
async def test_span_restores_on_exception():
    """ContextVars restore correctly even if body raises inside span()."""
    trace_id_var.set(UUID("01234567-89ab-7def-8123-456789abcdef"))
    try:
        async with span("outer") as outer:
            try:
                async with span("failing"):
                    raise ValueError("boom")
            except ValueError:
                pass
            assert current_span_id() == outer.span_id
    finally:
        trace_id_var.set(None)
        span_id_var.set(None)
        parent_span_id_var.set(None)


@pytest.mark.asyncio
async def test_cors_expose_headers_includes_trace_id(client):
    """Frontend must be able to read X-Trace-Id via CORS expose-headers."""
    resp = await client.get("/api/v1/health", headers={"Origin": "http://localhost:3000"})
    expose = resp.headers.get("access-control-expose-headers", "")
    assert "x-trace-id" in expose.lower()


@pytest.mark.asyncio
async def test_trace_id_middleware_generates_new(client):
    """No X-Trace-Id on request → middleware generates a UUIDv7."""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    trace = resp.headers.get("X-Trace-Id")
    assert trace is not None
    # UUIDv7 has "7" in the 13th hex position.
    assert trace[14] == "7"


@pytest.mark.asyncio
async def test_trace_id_middleware_adopts_incoming(client):
    """Valid incoming X-Trace-Id is adopted."""
    incoming = "01234567-89ab-7def-8123-456789abcdef"
    resp = await client.get("/api/v1/health", headers={"X-Trace-Id": incoming})
    assert resp.headers["X-Trace-Id"] == incoming


@pytest.mark.asyncio
async def test_trace_id_middleware_rejects_malformed(client):
    """Garbage → generates new (does not echo untrusted input)."""
    resp = await client.get("/api/v1/health", headers={"X-Trace-Id": "not-a-uuid"})
    assert resp.status_code == 200
    assert resp.headers["X-Trace-Id"] != "not-a-uuid"
