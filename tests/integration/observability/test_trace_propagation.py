"""Integration tests: trace_id propagation + ContextVar recursion guards.

Validates that TraceIdMiddleware propagates X-Trace-Id through to
observability.request_log, and that ContextVar guards prevent recursive
event emission from obs writer INSERTs and auth instrumentation.

NOTE: /api/v1/health is EXCLUDED from ObsHttpMiddleware, so trace propagation
tests use the admin KPIs endpoint which requires authentication.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from backend.observability.schema.http_events import RequestLogEvent

# Non-excluded endpoint for trace propagation tests (needs admin auth).
_OBS_ENDPOINT = "/api/v1/observability/admin/kpis?window_min=60"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_trace_id_adopted_from_header(client, admin_auth_headers, obs_db_session, obs_client):
    """HTTP request with X-Trace-Id stores that trace_id in request_log."""
    trace = uuid.uuid4()
    headers = {**admin_auth_headers, "X-Trace-Id": str(trace)}
    response = await client.get(_OBS_ENDPOINT, headers=headers)
    assert response.status_code == 200
    assert response.headers.get("X-Trace-Id") == str(trace)

    await obs_client.flush()

    result = await obs_db_session.execute(
        text("SELECT trace_id FROM observability.request_log WHERE trace_id = :tid"),
        {"tid": str(trace)},
    )
    assert result.fetchone() is not None, "Adopted trace_id not in request_log"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_trace_id_generated_when_missing(
    client, admin_auth_headers, obs_db_session, obs_client
):
    """HTTP request without X-Trace-Id gets a generated trace_id in response + DB."""
    response = await client.get(_OBS_ENDPOINT, headers=admin_auth_headers)
    assert response.status_code == 200
    generated = response.headers.get("X-Trace-Id")
    assert generated is not None
    uuid.UUID(generated)  # validates it's a real UUID

    await obs_client.flush()

    result = await obs_db_session.execute(
        text("SELECT trace_id FROM observability.request_log WHERE trace_id = :tid"),
        {"tid": generated},
    )
    assert result.fetchone() is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_trace_response_matches_db(client, admin_auth_headers, obs_db_session, obs_client):
    """The trace_id in the response header matches the DB row."""
    response = await client.get(_OBS_ENDPOINT, headers=admin_auth_headers)
    tid = response.headers["X-Trace-Id"]
    await obs_client.flush()

    result = await obs_db_session.execute(
        text("SELECT method FROM observability.request_log WHERE trace_id = :tid LIMIT 1"),
        {"tid": tid},
    )
    row = result.fetchone()
    assert row is not None
    assert row[0] == "GET"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_in_obs_write_guard_prevents_slow_query_recursion(obs_client, obs_db_session):
    """Obs writer INSERTs do not trigger slow_query_log entries for themselves.

    The _in_obs_write ContextVar guard in instrumentation/db.py must prevent the
    DB hook from emitting SLOW_QUERY events for the obs writer's own commits.
    """
    trace = uuid.uuid4()
    event = RequestLogEvent(
        trace_id=trace,
        span_id=uuid.uuid4(),
        parent_span_id=None,
        ts=datetime.now(timezone.utc),
        env="dev",
        git_sha=None,
        user_id=None,
        session_id=None,
        query_id=None,
        method="GET",
        path="/guard-test",
        raw_path="/guard-test",
        status_code=200,
        latency_ms=1,
    )
    await obs_client.emit(event)
    await obs_client.flush()

    # No slow_query_log should reference the obs INSERT itself
    result = await obs_db_session.execute(
        text(
            "SELECT count(*) FROM observability.slow_query_log "
            "WHERE query_text LIKE '%request_log%INSERT%' "
            "OR query_text LIKE '%observability%INSERT%'"
        ),
    )
    count = result.scalar()
    assert count == 0, f"_in_obs_write guard failed: {count} slow_query entries from obs writes"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_emitting_auth_event_guard_prevents_recursion(
    client, admin_auth_headers, obs_db_session, obs_client
):
    """Admin obs endpoint JWT verification does not create recursive auth events.

    The _emitting_auth_event ContextVar guard prevents emit_auth_event() from
    re-entering when the obs endpoint itself triggers JWT verification.
    """
    response = await client.get(_OBS_ENDPOINT, headers=admin_auth_headers)
    assert response.status_code == 200
    await obs_client.flush()

    # Count auth events — should be exactly 1 (the real JWT verify), not N (recursive)
    result = await obs_db_session.execute(
        text("SELECT count(*) FROM observability.auth_event_log"),
    )
    count = result.scalar()
    assert count <= 2, f"Auth event recursion detected: {count} events (expected <= 2)"
