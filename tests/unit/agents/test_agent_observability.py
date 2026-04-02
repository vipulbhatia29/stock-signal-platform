"""Consolidated observability tests for agent layer.

Covers:
  - ObservabilityCollector: DB-backed reads, fire-and-forget writes, cascade log
  - ObservabilityWriter: write_event() for llm_call and tool_execution event types
  - ExecutorObservability: executor recording tool execution events
  - GroqProviderObservability: GroqProvider recording to ObservabilityCollector

Merged from:
  - test_observability.py
  - test_observability_writer.py
  - test_executor_observability.py
  - test_groq_observability.py
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.observability.collector import ObservabilityCollector

# ─────────────────────────────────────────────────────────────────────────────
# Shared fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def collector_with_writer():
    """Return (collector, mock_writer) pair with writer injected."""
    collector = ObservabilityCollector()
    writer = AsyncMock()
    collector.set_db_writer(writer)
    return collector, writer


class _FakeRow:
    """Fake SA result row with attribute access."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ─────────────────────────────────────────────────────────────────────────────
# ObservabilityCollector — DB-backed reads
# ─────────────────────────────────────────────────────────────────────────────


class TestGetStats:
    """Tests for DB-backed get_stats()."""

    @pytest.mark.asyncio
    async def test_get_stats_empty_db(self) -> None:
        """Empty DB returns zero counts."""
        collector = ObservabilityCollector()
        db = AsyncMock()

        empty_result = MagicMock()
        empty_result.all.return_value = []
        db.execute = AsyncMock(return_value=empty_result)

        stats = await collector.get_stats(db)
        assert stats["requests_by_model"] == {}
        assert stats["cascade_count"] == 0
        assert stats["cascades_by_model"] == {}
        assert stats["rpm_by_model"] == {}
        assert stats["cascade_log"] == []

    @pytest.mark.asyncio
    async def test_get_stats_with_data(self) -> None:
        """Stats reflect DB query results."""
        collector = ObservabilityCollector()
        db = AsyncMock()

        req_result = MagicMock()
        req_result.all.return_value = [_FakeRow(model="llama-70b", cnt=10)]
        casc_result = MagicMock()
        casc_result.all.return_value = [_FakeRow(model="llama-70b", cnt=2)]
        rpm_result = MagicMock()
        rpm_result.all.return_value = [_FakeRow(model="llama-70b", cnt=5)]

        db.execute = AsyncMock(side_effect=[req_result, casc_result, rpm_result])

        stats = await collector.get_stats(db)
        assert stats["requests_by_model"]["llama-70b"] == 10
        assert stats["cascade_count"] == 2
        assert stats["cascades_by_model"]["llama-70b"] == 2
        assert stats["rpm_by_model"]["llama-70b"] == 5


class TestGetTierHealth:
    """Tests for DB-backed tier health classification."""

    @pytest.mark.asyncio
    async def test_healthy_no_failures(self) -> None:
        """A model with only successes in the last 5 min is 'healthy'."""
        collector = ObservabilityCollector()
        db = AsyncMock()

        fail_result = MagicMock()
        fail_result.all.return_value = []
        succ_result = MagicMock()
        succ_result.all.return_value = [_FakeRow(model="llama-70b", cnt=5)]
        lat_result = MagicMock()
        lat_result.all.return_value = [_FakeRow(model="llama-70b", avg_ms=100, p95_ms=150)]
        casc_result = MagicMock()
        casc_result.all.return_value = []

        db.execute = AsyncMock(side_effect=[fail_result, succ_result, lat_result, casc_result])

        health = await collector.get_tier_health(db)
        entry = next(t for t in health["tiers"] if t["model"] == "llama-70b")
        assert entry["status"] == "healthy"
        assert entry["successes_5m"] == 5

    @pytest.mark.asyncio
    async def test_degraded_few_failures(self) -> None:
        """A model with 1-3 recent failures is 'degraded'."""
        collector = ObservabilityCollector()
        db = AsyncMock()

        fail_result = MagicMock()
        fail_result.all.return_value = [_FakeRow(model="llama-70b", cnt=2)]
        succ_result = MagicMock()
        succ_result.all.return_value = [_FakeRow(model="llama-70b", cnt=5)]
        lat_result = MagicMock()
        lat_result.all.return_value = [_FakeRow(model="llama-70b", avg_ms=100, p95_ms=150)]
        casc_result = MagicMock()
        casc_result.all.return_value = [_FakeRow(model="llama-70b", cnt=2)]

        db.execute = AsyncMock(side_effect=[fail_result, succ_result, lat_result, casc_result])

        health = await collector.get_tier_health(db)
        entry = next(t for t in health["tiers"] if t["model"] == "llama-70b")
        assert entry["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_down_many_failures(self) -> None:
        """A model with 4+ recent failures is 'down'."""
        collector = ObservabilityCollector()
        db = AsyncMock()

        fail_result = MagicMock()
        fail_result.all.return_value = [_FakeRow(model="llama-70b", cnt=5)]
        succ_result = MagicMock()
        succ_result.all.return_value = []
        lat_result = MagicMock()
        lat_result.all.return_value = []
        casc_result = MagicMock()
        casc_result.all.return_value = [_FakeRow(model="llama-70b", cnt=5)]

        db.execute = AsyncMock(side_effect=[fail_result, succ_result, lat_result, casc_result])

        health = await collector.get_tier_health(db)
        entry = next(t for t in health["tiers"] if t["model"] == "llama-70b")
        assert entry["status"] == "down"

    @pytest.mark.asyncio
    async def test_disabled_status(self) -> None:
        """A manually disabled model shows 'disabled' regardless of DB data."""
        collector = ObservabilityCollector()
        collector.toggle_model("llama-70b", enabled=False)
        db = AsyncMock()

        fail_result = MagicMock()
        fail_result.all.return_value = []
        succ_result = MagicMock()
        succ_result.all.return_value = []
        lat_result = MagicMock()
        lat_result.all.return_value = []
        casc_result = MagicMock()
        casc_result.all.return_value = []

        db.execute = AsyncMock(side_effect=[fail_result, succ_result, lat_result, casc_result])

        health = await collector.get_tier_health(db)
        entry = next(t for t in health["tiers"] if t["model"] == "llama-70b")
        assert entry["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_health_summary_counts(self) -> None:
        """Health summary counts models by status."""
        collector = ObservabilityCollector()
        collector.toggle_model("model-b", enabled=False)
        db = AsyncMock()

        fail_result = MagicMock()
        fail_result.all.return_value = []
        succ_result = MagicMock()
        succ_result.all.return_value = [_FakeRow(model="model-a", cnt=3)]
        lat_result = MagicMock()
        lat_result.all.return_value = [_FakeRow(model="model-a", avg_ms=100, p95_ms=150)]
        casc_result = MagicMock()
        casc_result.all.return_value = []

        db.execute = AsyncMock(side_effect=[fail_result, succ_result, lat_result, casc_result])

        health = await collector.get_tier_health(db)
        assert health["summary"]["total"] == 2
        assert health["summary"]["healthy"] == 1
        assert health["summary"]["disabled"] == 1


class TestToggleModel:
    """Tests for model enable/disable (still in-memory)."""

    def test_toggle_disable(self) -> None:
        """Disabling a model adds it to disabled set."""
        collector = ObservabilityCollector()
        collector.toggle_model("llama-70b", enabled=False)
        assert "llama-70b" in collector._disabled_models

    def test_toggle_enable(self) -> None:
        """Re-enabling a model removes it from disabled set."""
        collector = ObservabilityCollector()
        collector.toggle_model("llama-70b", enabled=False)
        collector.toggle_model("llama-70b", enabled=True)
        assert "llama-70b" not in collector._disabled_models


class TestFallbackRate:
    """Tests for DB-backed fallback_rate_last_60s()."""

    @pytest.mark.asyncio
    async def test_fallback_rate_empty(self) -> None:
        """No data returns 0.0."""
        collector = ObservabilityCollector()
        db = AsyncMock()
        result = MagicMock()
        result.one.return_value = _FakeRow(total=0, failures=0)
        db.execute = AsyncMock(return_value=result)

        assert await collector.fallback_rate_last_60s(db) == 0.0

    @pytest.mark.asyncio
    async def test_fallback_rate_all_success(self) -> None:
        """Only successes returns 0.0."""
        collector = ObservabilityCollector()
        db = AsyncMock()
        result = MagicMock()
        result.one.return_value = _FakeRow(total=10, failures=0)
        db.execute = AsyncMock(return_value=result)

        assert await collector.fallback_rate_last_60s(db) == 0.0

    @pytest.mark.asyncio
    async def test_fallback_rate_mixed(self) -> None:
        """3 failures + 7 successes returns 0.3."""
        collector = ObservabilityCollector()
        db = AsyncMock()
        result = MagicMock()
        result.one.return_value = _FakeRow(total=10, failures=3)
        db.execute = AsyncMock(return_value=result)

        rate = await collector.fallback_rate_last_60s(db)
        assert abs(rate - 0.3) < 0.01


class TestRecordCascadeLog:
    """Tests for in-memory cascade log (kept for admin debugging)."""

    @pytest.mark.asyncio
    async def test_cascade_appended_to_log(self) -> None:
        """Cascade events appear in the in-memory cascade log."""
        collector = ObservabilityCollector()
        await collector.record_cascade(
            from_model="llama-70b",
            reason="rate_limit",
            provider="groq",
            tier="planner",
        )
        assert len(collector._cascade_log) == 1
        assert collector._cascade_log[0]["model"] == "llama-70b"
        assert collector._cascade_log[0]["reason"] == "rate_limit"


class TestLoopStepPassthrough:
    """Tests for loop_step parameter propagation through the collector."""

    @pytest.mark.asyncio
    async def test_record_request_passes_loop_step(self, collector_with_writer) -> None:
        """loop_step parameter flows through to DB writer data dict."""
        collector, writer = collector_with_writer
        await collector.record_request(
            model="test-model",
            provider="test",
            tier="reason",
            latency_ms=100,
            prompt_tokens=50,
            completion_tokens=25,
            loop_step=3,
        )
        await asyncio.sleep(0.05)
        writer.assert_called_once()
        call_data = writer.call_args[0][1]
        assert call_data["loop_step"] == 3

    @pytest.mark.asyncio
    async def test_record_tool_execution_passes_loop_step(self, collector_with_writer) -> None:
        """loop_step parameter flows through record_tool_execution to DB writer."""
        collector, writer = collector_with_writer
        await collector.record_tool_execution(
            tool_name="analyze_stock",
            latency_ms=200,
            status="ok",
            loop_step=7,
        )
        await asyncio.sleep(0.05)
        writer.assert_called_once()
        call_data = writer.call_args[0][1]
        assert call_data["loop_step"] == 7

    @pytest.mark.asyncio
    async def test_record_request_loop_step_defaults_none(self, collector_with_writer) -> None:
        """loop_step defaults to None when not provided."""
        collector, writer = collector_with_writer
        await collector.record_request(
            model="test-model",
            provider="test",
            tier="reason",
            latency_ms=100,
            prompt_tokens=50,
            completion_tokens=25,
        )
        await asyncio.sleep(0.05)
        writer.assert_called_once()
        call_data = writer.call_args[0][1]
        assert call_data["loop_step"] is None


# ─────────────────────────────────────────────────────────────────────────────
# ObservabilityWriter — write_event()
# ─────────────────────────────────────────────────────────────────────────────


# -- WriteEvent helpers (patch paths as constants) --
_W = "backend.observability.writer"
_FACTORY = f"{_W}.async_session_factory"
_SID = f"{_W}.current_session_id"
_QID = f"{_W}.current_query_id"
_AT = f"{_W}.current_agent_type"
_AI = f"{_W}.current_agent_instance_id"


def _llm_payload(**overrides: object) -> dict:
    """Base LLM call event payload."""
    base = {
        "provider": "groq",
        "model": "llama-3.3-70b",
        "tier": "planner",
        "latency_ms": 150,
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "error": None,
    }
    base.update(overrides)
    return base


def _tool_payload(**overrides: object) -> dict:
    """Base tool execution event payload."""
    base = {
        "tool_name": "analyze_stock",
        "latency_ms": 300,
        "status": "ok",
        "result_size_bytes": 1024,
        "params": {"ticker": "AAPL"},
        "error": None,
    }
    base.update(overrides)
    return base


@pytest.fixture
def mock_db_session():
    """Return (mock_session, mock_context_manager) for write_event tests."""
    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_session, mock_cm


async def _call_write_event(
    mock_cm: AsyncMock,
    event_type: str,
    data: dict,
    *,
    agent_type: str | None = None,
    agent_instance_id: str | None = None,
) -> AsyncMock:
    """Call write_event with all patches applied. Returns mock_session."""
    from backend.observability.writer import write_event

    mock_session = mock_cm.__aenter__.return_value
    with (
        patch(_FACTORY, return_value=mock_cm),
        patch(_SID) as m_sid,
        patch(_QID) as m_qid,
        patch(_AT) as m_at,
        patch(_AI) as m_ai,
    ):
        m_sid.get.return_value = uuid.uuid4()
        m_qid.get.return_value = uuid.uuid4()
        m_at.get.return_value = agent_type
        m_ai.get.return_value = agent_instance_id
        await write_event(event_type, data)
    return mock_session


class TestWriteEvent:
    """Tests for write_event function."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "event_type,data",
        [
            ("llm_call", _llm_payload()),
            ("tool_execution", _tool_payload()),
        ],
        ids=["llm_call", "tool_execution"],
    )
    async def test_writes_row_and_commits(
        self, mock_db_session: tuple, event_type: str, data: dict
    ) -> None:
        """Should insert a row and commit for both event types."""
        mock_session, mock_cm = mock_db_session
        session = await _call_write_event(mock_cm, event_type, data)
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_db_error_does_not_raise(self, mock_db_session: tuple) -> None:
        """DB write failures should be swallowed (logged, not raised)."""
        from backend.observability.writer import write_event

        _, mock_cm = mock_db_session
        mock_cm.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
        with patch(_FACTORY, return_value=mock_cm):
            await write_event("llm_call", _llm_payload())

    @pytest.mark.asyncio
    async def test_unknown_event_type_logs_warning(self, mock_db_session: tuple) -> None:
        """Unknown event type should log warning and return without writing."""
        from backend.observability.writer import write_event

        mock_session, mock_cm = mock_db_session
        with (
            patch(_FACTORY, return_value=mock_cm),
            patch(_SID) as m_sid,
            patch(_QID) as m_qid,
        ):
            m_sid.get.return_value = None
            m_qid.get.return_value = None
            await write_event("unknown_type", {"foo": "bar"})
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_writes_cost_usd_on_llm_call(self, mock_db_session: tuple) -> None:
        """cost_usd should be set on the LLMCallLog row when provided."""
        _, mock_cm = mock_db_session
        session = await _call_write_event(mock_cm, "llm_call", _llm_payload(cost_usd=0.0012))
        assert session.add.call_args[0][0].cost_usd == 0.0012

    @pytest.mark.asyncio
    async def test_writes_cache_hit_on_tool_execution(self, mock_db_session: tuple) -> None:
        """cache_hit should be set on ToolExecutionLog row."""
        _, mock_cm = mock_db_session
        session = await _call_write_event(
            mock_cm,
            "tool_execution",
            _tool_payload(latency_ms=0, status="success", result_size_bytes=512, cache_hit=True),
        )
        assert session.add.call_args[0][0].cache_hit is True

    @pytest.mark.asyncio
    async def test_writes_agent_type_from_contextvar(self, mock_db_session: tuple) -> None:
        """agent_type should be populated from ContextVar."""
        _, mock_cm = mock_db_session
        session = await _call_write_event(
            mock_cm,
            "llm_call",
            _llm_payload(),
            agent_type="stock",
            agent_instance_id="abc-123",
        )
        row = session.add.call_args[0][0]
        assert row.agent_type == "stock"
        assert row.agent_instance_id == "abc-123"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "event_type,data,step",
        [
            ("llm_call", _llm_payload(loop_step=5), 5),
            ("tool_execution", _tool_payload(loop_step=2), 2),
        ],
        ids=["llm_call", "tool_execution"],
    )
    async def test_writes_loop_step(
        self, mock_db_session: tuple, event_type: str, data: dict, step: int
    ) -> None:
        """loop_step should be set on the row when provided."""
        _, mock_cm = mock_db_session
        session = await _call_write_event(mock_cm, event_type, data)
        assert session.add.call_args[0][0].loop_step == step

    @pytest.mark.asyncio
    async def test_writes_status_on_llm_call(self, mock_db_session: tuple) -> None:
        """status field should be written on LLMCallLog when provided."""
        _, mock_cm = mock_db_session
        session = await _call_write_event(mock_cm, "llm_call", _llm_payload(status="error"))
        assert session.add.call_args[0][0].status == "error"

    @pytest.mark.asyncio
    async def test_defaults_status_to_completed(self, mock_db_session: tuple) -> None:
        """status should default to 'completed' when not present in data."""
        _, mock_cm = mock_db_session
        session = await _call_write_event(mock_cm, "llm_call", _llm_payload())
        assert session.add.call_args[0][0].status == "completed"

    @pytest.mark.asyncio
    async def test_writes_langfuse_trace_id(self, mock_db_session: tuple) -> None:
        """langfuse_trace_id should be written on LLMCallLog when provided."""
        trace_id = str(uuid.uuid4())
        _, mock_cm = mock_db_session
        session = await _call_write_event(
            mock_cm, "llm_call", _llm_payload(langfuse_trace_id=trace_id)
        )
        assert session.add.call_args[0][0].langfuse_trace_id == trace_id

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "attr,expected_substr",
        [("input_summary", "AAPL"), ("output_summary", "8.5")],
        ids=["input_summary", "output_summary"],
    )
    async def test_writes_summaries_on_tool(
        self, mock_db_session: tuple, attr: str, expected_substr: str
    ) -> None:
        """input_summary and output_summary should contain expected content."""
        _, mock_cm = mock_db_session
        session = await _call_write_event(
            mock_cm,
            "tool_execution",
            _tool_payload(result={"score": 8.5}),
        )
        assert expected_substr in getattr(session.add.call_args[0][0], attr)


# ─────────────────────────────────────────────────────────────────────────────
# ExecutorObservability — executor recording tool execution events
# ─────────────────────────────────────────────────────────────────────────────


class TestExecutorObservability:
    """Tests for executor recording tool execution events."""

    @pytest.mark.asyncio
    async def test_successful_tool_records_event(self) -> None:
        """A successful tool execution should record to collector."""
        from backend.agents.executor import execute_plan
        from backend.tools.base import ToolResult

        collector = ObservabilityCollector()
        collector.record_tool_execution = AsyncMock()

        tool_executor = AsyncMock(
            return_value=ToolResult(status="ok", data={"ticker": "AAPL", "price": 150.0})
        )

        steps = [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}]
        await execute_plan(steps, tool_executor, collector=collector)

        collector.record_tool_execution.assert_called_once()
        call_kwargs = collector.record_tool_execution.call_args[1]
        assert call_kwargs["tool_name"] == "analyze_stock"
        assert call_kwargs["status"] == "ok"
        assert call_kwargs["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_failed_tool_records_error(self) -> None:
        """A failed tool execution should record error to collector."""
        from backend.agents.executor import execute_plan

        collector = ObservabilityCollector()
        collector.record_tool_execution = AsyncMock()

        tool_executor = AsyncMock(side_effect=Exception("tool crashed"))

        steps = [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}]
        await execute_plan(steps, tool_executor, collector=collector)

        collector.record_tool_execution.assert_called_once()
        call_kwargs = collector.record_tool_execution.call_args[1]
        assert call_kwargs["tool_name"] == "analyze_stock"
        assert call_kwargs["status"] == "error"
        assert call_kwargs["error"] == "Tool execution failed. Please try again."

    @pytest.mark.asyncio
    async def test_no_collector_still_works(self) -> None:
        """Executor without collector should work as before."""
        from backend.agents.executor import execute_plan
        from backend.tools.base import ToolResult

        tool_executor = AsyncMock(return_value=ToolResult(status="ok", data={"ticker": "AAPL"}))

        steps = [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}]
        result = await execute_plan(steps, tool_executor)
        assert result["tool_calls"] == 1
        assert len(result["results"]) == 1

    @pytest.mark.asyncio
    async def test_cache_hit_records_with_cache_hit_true(self) -> None:
        """A cache hit should record tool execution with cache_hit=True and latency_ms=0."""
        from backend.agents.executor import execute_plan
        from backend.tools.base import ToolResult

        collector = ObservabilityCollector()
        collector.record_tool_execution = AsyncMock()

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value='{"status": "ok", "ticker": "AAPL"}')

        tool_executor = AsyncMock(return_value=ToolResult(status="ok", data={}))

        steps = [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}]
        await execute_plan(
            steps,
            tool_executor,
            collector=collector,
            cache=mock_cache,
            session_id="test-session",
        )

        collector.record_tool_execution.assert_called_once()
        call_kwargs = collector.record_tool_execution.call_args[1]
        assert call_kwargs["cache_hit"] is True
        assert call_kwargs["latency_ms"] == 0
        assert call_kwargs["tool_name"] == "analyze_stock"
        tool_executor.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_records_with_cache_hit_false(self) -> None:
        """A normal (non-cached) tool execution should record cache_hit=False."""
        from backend.agents.executor import execute_plan
        from backend.tools.base import ToolResult

        collector = ObservabilityCollector()
        collector.record_tool_execution = AsyncMock()

        tool_executor = AsyncMock(
            return_value=ToolResult(status="ok", data={"ticker": "AAPL", "price": 150.0})
        )

        steps = [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}]
        await execute_plan(steps, tool_executor, collector=collector)

        collector.record_tool_execution.assert_called_once()
        call_kwargs = collector.record_tool_execution.call_args[1]
        assert call_kwargs["cache_hit"] is False


# ─────────────────────────────────────────────────────────────────────────────
# GroqProviderObservability — GroqProvider recording to ObservabilityCollector
# ─────────────────────────────────────────────────────────────────────────────


class TestGroqProviderObservability:
    """Tests for GroqProvider recording to ObservabilityCollector."""

    @pytest.mark.asyncio
    async def test_successful_call_records_request(self) -> None:
        """A successful Groq call should fire a DB write for the request."""
        from backend.agents.llm_client import LLMResponse
        from backend.agents.providers.groq import GroqProvider

        collector = ObservabilityCollector()
        writer = AsyncMock()
        collector.set_db_writer(writer)

        provider = GroqProvider(api_key="test-key", models=["model-a"])
        provider.collector = collector
        mock_response = LLMResponse(
            content="hello",
            tool_calls=[],
            model="model-a",
            prompt_tokens=10,
            completion_tokens=5,
        )
        with patch.object(
            provider, "_call_model", new_callable=AsyncMock, return_value=mock_response
        ):
            await provider.chat(messages=[{"role": "user", "content": "hi"}], tools=[])

        await asyncio.sleep(0.05)
        writer.assert_called()
        call_data = writer.call_args[0][1]
        assert call_data["model"] == "model-a"
        assert call_data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_cascade_records_event(self) -> None:
        """When a model fails and cascades, cascade + success events should be recorded."""
        from backend.agents.llm_client import LLMResponse
        from backend.agents.providers.groq import GroqProvider

        collector = ObservabilityCollector()
        writer = AsyncMock()
        collector.set_db_writer(writer)

        provider = GroqProvider(api_key="test-key", models=["model-a", "model-b"])
        provider.collector = collector
        mock_response = LLMResponse(
            content="hello",
            tool_calls=[],
            model="model-b",
            prompt_tokens=10,
            completion_tokens=5,
        )
        call_count = 0

        async def _side_effect(model_name, messages, tools, stream):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("rate limit exceeded")
            return mock_response

        with patch.object(provider, "_call_model", side_effect=_side_effect):
            await provider.chat(messages=[{"role": "user", "content": "hi"}], tools=[])

        await asyncio.sleep(0.05)

        assert len(collector._cascade_log) == 1
        assert collector._cascade_log[0]["model"] == "model-a"
        assert writer.call_count == 2

    @pytest.mark.asyncio
    async def test_no_collector_still_works(self) -> None:
        """GroqProvider without collector should work as before."""
        from backend.agents.llm_client import LLMResponse
        from backend.agents.providers.groq import GroqProvider

        provider = GroqProvider(api_key="test-key", models=["model-a"])
        mock_response = LLMResponse(
            content="hello",
            tool_calls=[],
            model="model-a",
            prompt_tokens=10,
            completion_tokens=5,
        )
        with patch.object(
            provider, "_call_model", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await provider.chat(messages=[{"role": "user", "content": "hi"}], tools=[])
        assert result.content == "hello"
