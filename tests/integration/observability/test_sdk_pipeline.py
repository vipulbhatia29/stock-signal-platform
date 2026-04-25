"""Integration tests: SDK emit -> buffer -> flush -> DirectTarget -> DB persistence.

Validates that ObservabilityClient correctly routes typed events through the
buffer/flush pipeline and that DirectTarget persists them to the correct
observability schema tables via write_batch.
"""

import hashlib
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.observability.client import ObservabilityClient
from backend.observability.schema.agent_events import AgentIntentEvent
from backend.observability.schema.auth_events import (
    AuthEventLogEvent,
    AuthEventType,
    AuthOutcome,
)
from backend.observability.schema.external_api_events import ExternalApiCallEvent
from backend.observability.schema.http_events import RequestLogEvent
from backend.observability.service.event_writer import write_batch
from backend.observability.targets.direct import DirectTarget


def _base_fields(trace_id: uuid.UUID) -> dict:
    """Common fields for all ObsEventBase subclasses."""
    return {
        "trace_id": trace_id,
        "span_id": uuid.uuid4(),
        "parent_span_id": None,
        "ts": datetime.now(timezone.utc),
        "env": "dev",
        "git_sha": None,
        "user_id": None,
        "session_id": None,
        "query_id": None,
    }


@pytest.mark.asyncio
@pytest.mark.integration
async def test_emit_request_log_persists(obs_client, obs_db_session):
    """Emitting a RequestLogEvent writes a row to request_log table."""
    trace = uuid.uuid4()
    event = RequestLogEvent(
        **_base_fields(trace),
        method="GET",
        path="/api/v1/health",
        raw_path="/api/v1/health",
        status_code=200,
        latency_ms=15,
    )
    await obs_client.emit(event)
    await obs_client.flush()

    result = await obs_db_session.execute(
        text("SELECT trace_id FROM observability.request_log WHERE trace_id = :tid"),
        {"tid": str(trace)},
    )
    assert result.fetchone() is not None, "REQUEST_LOG not found in request_log"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_emit_auth_event_persists(obs_client, obs_db_session):
    """Emitting an AuthEventLogEvent writes a row to auth_event_log table."""
    trace = uuid.uuid4()
    event = AuthEventLogEvent(
        **_base_fields(trace),
        auth_event_type=AuthEventType.JWT_VERIFY_FAILURE,
        outcome=AuthOutcome.SUCCESS,
    )
    await obs_client.emit(event)
    await obs_client.flush()

    result = await obs_db_session.execute(
        text("SELECT id FROM observability.auth_event_log WHERE trace_id = :tid"),
        {"tid": str(trace)},
    )
    assert result.fetchone() is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_emit_external_api_call_persists(obs_client, obs_db_session):
    """Emitting an ExternalApiCallEvent writes to external_api_call_log table."""
    trace = uuid.uuid4()
    event = ExternalApiCallEvent(
        **_base_fields(trace),
        provider="yfinance",
        endpoint="/v8/finance/chart/AAPL",
        method="GET",
        status_code=200,
        latency_ms=350,
    )
    await obs_client.emit(event)
    await obs_client.flush()

    result = await obs_db_session.execute(
        text("SELECT provider FROM observability.external_api_call_log WHERE trace_id = :tid"),
        {"tid": str(trace)},
    )
    row = result.fetchone()
    assert row is not None
    assert row[0] == "yfinance"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_emit_agent_intent_persists(obs_client, obs_db_session):
    """Emitting an AgentIntentEvent writes to agent_intent_log table."""
    trace = uuid.uuid4()
    query_text = "What is AAPL's forecast?"
    event = AgentIntentEvent(
        **_base_fields(trace),
        intent="stock_analysis",
        confidence=0.95,
        out_of_scope=False,
        query_text_hash=hashlib.sha256(query_text.encode()).hexdigest(),
    )
    await obs_client.emit(event)
    await obs_client.flush()

    result = await obs_db_session.execute(
        text("SELECT id FROM observability.agent_intent_log WHERE trace_id = :tid"),
        {"tid": str(trace)},
    )
    assert result.fetchone() is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_emit_mixed_batch_routes_correctly(obs_client, obs_db_session):
    """Batch of different event types routes each to the correct table."""
    traces = {
        "request": uuid.uuid4(),
        "auth": uuid.uuid4(),
        "external": uuid.uuid4(),
    }

    await obs_client.emit(
        RequestLogEvent(
            **_base_fields(traces["request"]),
            method="GET",
            path="/t",
            raw_path="/t",
            status_code=200,
            latency_ms=10,
        )
    )
    await obs_client.emit(
        AuthEventLogEvent(
            **_base_fields(traces["auth"]),
            auth_event_type=AuthEventType.TOKEN_REFRESH,
            outcome=AuthOutcome.SUCCESS,
        )
    )
    await obs_client.emit(
        ExternalApiCallEvent(
            **_base_fields(traces["external"]),
            provider="finnhub",
            endpoint="/news",
            method="GET",
            status_code=200,
            latency_ms=50,
        )
    )
    await obs_client.flush()

    table_map = {
        "request": "observability.request_log",
        "auth": "observability.auth_event_log",
        "external": "observability.external_api_call_log",
    }
    for key, table in table_map.items():
        result = await obs_db_session.execute(
            text(f"SELECT 1 FROM {table} WHERE trace_id = :tid"),
            {"tid": str(traces[key])},
        )
        assert result.fetchone() is not None, f"{key} event not in {table}"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_obs_disabled_no_writes(obs_db_session, _patch_session_factory):
    """When enabled=False, no events are written to the database."""
    target = DirectTarget(event_writer=write_batch)
    client = ObservabilityClient(
        target=target,
        spool_dir=Path(tempfile.mkdtemp()),
        spool_enabled=False,
        flush_interval_ms=100,
        buffer_size=1000,
        enabled=False,
    )
    # No start() — consistent with obs_client fixture (avoids flush loop race).
    # enabled=False means start() is a no-op anyway, but skipping prevents
    # copy-paste into enabled=True contexts.
    event = RequestLogEvent(
        **_base_fields(uuid.uuid4()),
        method="GET",
        path="/disabled",
        raw_path="/disabled",
        status_code=200,
        latency_ms=1,
    )
    await client.emit(event)
    await client.flush()

    result = await obs_db_session.execute(
        text("SELECT count(*) FROM observability.request_log WHERE path = '/disabled'"),
    )
    assert result.scalar() == 0
