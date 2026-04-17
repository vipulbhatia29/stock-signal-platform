from uuid import UUID
import pytest
from backend.observability.context import (
    current_trace_id, current_span_id, current_parent_span_id,
    trace_id_var, span_id_var, parent_span_id_var,
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
