"""Tests for observability DB write functions."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest


class TestWriteEvent:
    """Tests for write_event function."""

    @pytest.mark.asyncio
    async def test_writes_llm_call_log(self) -> None:
        """Should insert an LLMCallLog row."""
        from backend.agents.observability_writer import write_event

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        patch_factory = "backend.agents.observability_writer.async_session_factory"
        patch_sid = "backend.agents.observability_writer.current_session_id"
        patch_qid = "backend.agents.observability_writer.current_query_id"
        with patch(patch_factory, return_value=mock_cm):
            with patch(patch_sid) as mock_sid:
                with patch(patch_qid) as mock_qid:
                    mock_sid.get.return_value = uuid.uuid4()
                    mock_qid.get.return_value = uuid.uuid4()
                    await write_event(
                        "llm_call",
                        {
                            "provider": "groq",
                            "model": "llama-3.3-70b",
                            "tier": "planner",
                            "latency_ms": 150,
                            "prompt_tokens": 100,
                            "completion_tokens": 50,
                            "error": None,
                        },
                    )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_writes_tool_execution_log(self) -> None:
        """Should insert a ToolExecutionLog row."""
        from backend.agents.observability_writer import write_event

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        patch_factory = "backend.agents.observability_writer.async_session_factory"
        patch_sid = "backend.agents.observability_writer.current_session_id"
        patch_qid = "backend.agents.observability_writer.current_query_id"
        with patch(patch_factory, return_value=mock_cm):
            with patch(patch_sid) as mock_sid:
                with patch(patch_qid) as mock_qid:
                    mock_sid.get.return_value = uuid.uuid4()
                    mock_qid.get.return_value = uuid.uuid4()
                    await write_event(
                        "tool_execution",
                        {
                            "tool_name": "analyze_stock",
                            "latency_ms": 300,
                            "status": "ok",
                            "result_size_bytes": 1024,
                            "params": {"ticker": "AAPL"},
                            "error": None,
                        },
                    )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_db_error_does_not_raise(self) -> None:
        """DB write failures should be swallowed (logged, not raised)."""
        from backend.agents.observability_writer import write_event

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        patch_factory = "backend.agents.observability_writer.async_session_factory"
        with patch(patch_factory, return_value=mock_cm):
            # Should not raise
            await write_event(
                "llm_call",
                {
                    "provider": "groq",
                    "model": "llama-3.3-70b",
                    "tier": "planner",
                    "latency_ms": 150,
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "error": None,
                },
            )

    @pytest.mark.asyncio
    async def test_unknown_event_type_logs_warning(self) -> None:
        """Unknown event type should log warning and return without writing."""
        from backend.agents.observability_writer import write_event

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        patch_factory = "backend.agents.observability_writer.async_session_factory"
        patch_sid = "backend.agents.observability_writer.current_session_id"
        patch_qid = "backend.agents.observability_writer.current_query_id"
        with patch(patch_factory, return_value=mock_cm):
            with patch(patch_sid) as mock_sid:
                with patch(patch_qid) as mock_qid:
                    mock_sid.get.return_value = None
                    mock_qid.get.return_value = None
                    await write_event("unknown_type", {"foo": "bar"})

        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_writes_cost_usd_on_llm_call(self) -> None:
        """cost_usd should be set on the LLMCallLog row when provided."""
        from backend.agents.observability_writer import write_event

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        patch_factory = "backend.agents.observability_writer.async_session_factory"
        patch_sid = "backend.agents.observability_writer.current_session_id"
        patch_qid = "backend.agents.observability_writer.current_query_id"
        patch_at = "backend.agents.observability_writer.current_agent_type"
        patch_ai = "backend.agents.observability_writer.current_agent_instance_id"
        with (
            patch(patch_factory, return_value=mock_cm),
            patch(patch_sid) as m_sid,
            patch(patch_qid) as m_qid,
            patch(patch_at) as m_at,
            patch(patch_ai) as m_ai,
        ):
            m_sid.get.return_value = uuid.uuid4()
            m_qid.get.return_value = uuid.uuid4()
            m_at.get.return_value = None
            m_ai.get.return_value = None
            await write_event(
                "llm_call",
                {
                    "provider": "groq",
                    "model": "llama-3.3-70b",
                    "tier": "planner",
                    "latency_ms": 150,
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "cost_usd": 0.0012,
                    "error": None,
                },
            )

        row = mock_session.add.call_args[0][0]
        assert row.cost_usd == 0.0012

    @pytest.mark.asyncio
    async def test_writes_cache_hit_on_tool_execution(self) -> None:
        """cache_hit should be set on ToolExecutionLog row."""
        from backend.agents.observability_writer import write_event

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        patch_factory = "backend.agents.observability_writer.async_session_factory"
        patch_sid = "backend.agents.observability_writer.current_session_id"
        patch_qid = "backend.agents.observability_writer.current_query_id"
        patch_at = "backend.agents.observability_writer.current_agent_type"
        patch_ai = "backend.agents.observability_writer.current_agent_instance_id"
        with (
            patch(patch_factory, return_value=mock_cm),
            patch(patch_sid) as m_sid,
            patch(patch_qid) as m_qid,
            patch(patch_at) as m_at,
            patch(patch_ai) as m_ai,
        ):
            m_sid.get.return_value = uuid.uuid4()
            m_qid.get.return_value = uuid.uuid4()
            m_at.get.return_value = None
            m_ai.get.return_value = None
            await write_event(
                "tool_execution",
                {
                    "tool_name": "analyze_stock",
                    "latency_ms": 0,
                    "status": "success",
                    "result_size_bytes": 512,
                    "params": {"ticker": "AAPL"},
                    "error": None,
                    "cache_hit": True,
                },
            )

        row = mock_session.add.call_args[0][0]
        assert row.cache_hit is True

    @pytest.mark.asyncio
    async def test_writes_agent_type_from_contextvar(self) -> None:
        """agent_type should be populated from ContextVar."""
        from backend.agents.observability_writer import write_event

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        patch_factory = "backend.agents.observability_writer.async_session_factory"
        patch_sid = "backend.agents.observability_writer.current_session_id"
        patch_qid = "backend.agents.observability_writer.current_query_id"
        patch_at = "backend.agents.observability_writer.current_agent_type"
        patch_ai = "backend.agents.observability_writer.current_agent_instance_id"
        with (
            patch(patch_factory, return_value=mock_cm),
            patch(patch_sid) as m_sid,
            patch(patch_qid) as m_qid,
            patch(patch_at) as m_at,
            patch(patch_ai) as m_ai,
        ):
            m_sid.get.return_value = uuid.uuid4()
            m_qid.get.return_value = uuid.uuid4()
            m_at.get.return_value = "stock"
            m_ai.get.return_value = "abc-123"
            await write_event(
                "llm_call",
                {
                    "provider": "groq",
                    "model": "llama-3.3-70b",
                    "tier": "planner",
                    "latency_ms": 150,
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "error": None,
                },
            )

        row = mock_session.add.call_args[0][0]
        assert row.agent_type == "stock"
        assert row.agent_instance_id == "abc-123"

    @pytest.mark.asyncio
    async def test_writes_loop_step_on_llm_call(self) -> None:
        """loop_step should be set on the LLMCallLog row when provided."""
        from backend.agents.observability_writer import write_event

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        patch_factory = "backend.agents.observability_writer.async_session_factory"
        patch_sid = "backend.agents.observability_writer.current_session_id"
        patch_qid = "backend.agents.observability_writer.current_query_id"
        patch_at = "backend.agents.observability_writer.current_agent_type"
        patch_ai = "backend.agents.observability_writer.current_agent_instance_id"
        with (
            patch(patch_factory, return_value=mock_cm),
            patch(patch_sid) as m_sid,
            patch(patch_qid) as m_qid,
            patch(patch_at) as m_at,
            patch(patch_ai) as m_ai,
        ):
            m_sid.get.return_value = uuid.uuid4()
            m_qid.get.return_value = uuid.uuid4()
            m_at.get.return_value = None
            m_ai.get.return_value = None
            await write_event(
                "llm_call",
                {
                    "provider": "groq",
                    "model": "llama-3.3-70b",
                    "tier": "planner",
                    "latency_ms": 150,
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "error": None,
                    "loop_step": 5,
                },
            )

        row = mock_session.add.call_args[0][0]
        assert row.loop_step == 5

    @pytest.mark.asyncio
    async def test_writes_loop_step_on_tool_execution(self) -> None:
        """loop_step should be set on the ToolExecutionLog row when provided."""
        from backend.agents.observability_writer import write_event

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        patch_factory = "backend.agents.observability_writer.async_session_factory"
        patch_sid = "backend.agents.observability_writer.current_session_id"
        patch_qid = "backend.agents.observability_writer.current_query_id"
        patch_at = "backend.agents.observability_writer.current_agent_type"
        patch_ai = "backend.agents.observability_writer.current_agent_instance_id"
        with (
            patch(patch_factory, return_value=mock_cm),
            patch(patch_sid) as m_sid,
            patch(patch_qid) as m_qid,
            patch(patch_at) as m_at,
            patch(patch_ai) as m_ai,
        ):
            m_sid.get.return_value = uuid.uuid4()
            m_qid.get.return_value = uuid.uuid4()
            m_at.get.return_value = None
            m_ai.get.return_value = None
            await write_event(
                "tool_execution",
                {
                    "tool_name": "analyze_stock",
                    "latency_ms": 300,
                    "status": "ok",
                    "result_size_bytes": 1024,
                    "params": {"ticker": "AAPL"},
                    "error": None,
                    "loop_step": 2,
                },
            )

        row = mock_session.add.call_args[0][0]
        assert row.loop_step == 2

    @pytest.mark.asyncio
    async def test_writes_status_on_llm_call(self) -> None:
        """status field should be written on LLMCallLog when provided."""
        from backend.agents.observability_writer import write_event

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        patch_factory = "backend.agents.observability_writer.async_session_factory"
        patch_sid = "backend.agents.observability_writer.current_session_id"
        patch_qid = "backend.agents.observability_writer.current_query_id"
        patch_at = "backend.agents.observability_writer.current_agent_type"
        patch_ai = "backend.agents.observability_writer.current_agent_instance_id"
        with (
            patch(patch_factory, return_value=mock_cm),
            patch(patch_sid) as m_sid,
            patch(patch_qid) as m_qid,
            patch(patch_at) as m_at,
            patch(patch_ai) as m_ai,
        ):
            m_sid.get.return_value = uuid.uuid4()
            m_qid.get.return_value = uuid.uuid4()
            m_at.get.return_value = None
            m_ai.get.return_value = None
            await write_event(
                "llm_call",
                {
                    "provider": "groq",
                    "model": "llama-3.3-70b",
                    "tier": "planner",
                    "latency_ms": 150,
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "error": None,
                    "status": "error",
                },
            )

        row = mock_session.add.call_args[0][0]
        assert row.status == "error"

    @pytest.mark.asyncio
    async def test_defaults_status_to_completed(self) -> None:
        """status should default to 'completed' when not present in data."""
        from backend.agents.observability_writer import write_event

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        patch_factory = "backend.agents.observability_writer.async_session_factory"
        patch_sid = "backend.agents.observability_writer.current_session_id"
        patch_qid = "backend.agents.observability_writer.current_query_id"
        patch_at = "backend.agents.observability_writer.current_agent_type"
        patch_ai = "backend.agents.observability_writer.current_agent_instance_id"
        with (
            patch(patch_factory, return_value=mock_cm),
            patch(patch_sid) as m_sid,
            patch(patch_qid) as m_qid,
            patch(patch_at) as m_at,
            patch(patch_ai) as m_ai,
        ):
            m_sid.get.return_value = uuid.uuid4()
            m_qid.get.return_value = uuid.uuid4()
            m_at.get.return_value = None
            m_ai.get.return_value = None
            await write_event(
                "llm_call",
                {
                    "provider": "groq",
                    "model": "llama-3.3-70b",
                    "tier": "planner",
                    "latency_ms": 150,
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "error": None,
                },
            )

        row = mock_session.add.call_args[0][0]
        assert row.status == "completed"

    @pytest.mark.asyncio
    async def test_writes_langfuse_trace_id(self) -> None:
        """langfuse_trace_id should be written on LLMCallLog when provided."""
        from backend.agents.observability_writer import write_event

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        trace_id = str(uuid.uuid4())
        patch_factory = "backend.agents.observability_writer.async_session_factory"
        patch_sid = "backend.agents.observability_writer.current_session_id"
        patch_qid = "backend.agents.observability_writer.current_query_id"
        patch_at = "backend.agents.observability_writer.current_agent_type"
        patch_ai = "backend.agents.observability_writer.current_agent_instance_id"
        with (
            patch(patch_factory, return_value=mock_cm),
            patch(patch_sid) as m_sid,
            patch(patch_qid) as m_qid,
            patch(patch_at) as m_at,
            patch(patch_ai) as m_ai,
        ):
            m_sid.get.return_value = uuid.uuid4()
            m_qid.get.return_value = uuid.uuid4()
            m_at.get.return_value = None
            m_ai.get.return_value = None
            await write_event(
                "llm_call",
                {
                    "provider": "groq",
                    "model": "llama-3.3-70b",
                    "tier": "planner",
                    "latency_ms": 150,
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "error": None,
                    "langfuse_trace_id": trace_id,
                },
            )

        row = mock_session.add.call_args[0][0]
        assert row.langfuse_trace_id == trace_id

    @pytest.mark.asyncio
    async def test_writes_input_summary_on_tool(self) -> None:
        """input_summary should be a sanitized string of params containing the ticker."""
        from backend.agents.observability_writer import write_event

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        patch_factory = "backend.agents.observability_writer.async_session_factory"
        patch_sid = "backend.agents.observability_writer.current_session_id"
        patch_qid = "backend.agents.observability_writer.current_query_id"
        patch_at = "backend.agents.observability_writer.current_agent_type"
        patch_ai = "backend.agents.observability_writer.current_agent_instance_id"
        with (
            patch(patch_factory, return_value=mock_cm),
            patch(patch_sid) as m_sid,
            patch(patch_qid) as m_qid,
            patch(patch_at) as m_at,
            patch(patch_ai) as m_ai,
        ):
            m_sid.get.return_value = uuid.uuid4()
            m_qid.get.return_value = uuid.uuid4()
            m_at.get.return_value = None
            m_ai.get.return_value = None
            await write_event(
                "tool_execution",
                {
                    "tool_name": "analyze_stock",
                    "latency_ms": 300,
                    "status": "ok",
                    "result_size_bytes": 1024,
                    "params": {"ticker": "AAPL"},
                    "result": {"score": 8.5},
                    "error": None,
                },
            )

        row = mock_session.add.call_args[0][0]
        assert "AAPL" in row.input_summary

    @pytest.mark.asyncio
    async def test_writes_output_summary_on_tool(self) -> None:
        """output_summary should be a sanitized string of result containing the score."""
        from backend.agents.observability_writer import write_event

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        patch_factory = "backend.agents.observability_writer.async_session_factory"
        patch_sid = "backend.agents.observability_writer.current_session_id"
        patch_qid = "backend.agents.observability_writer.current_query_id"
        patch_at = "backend.agents.observability_writer.current_agent_type"
        patch_ai = "backend.agents.observability_writer.current_agent_instance_id"
        with (
            patch(patch_factory, return_value=mock_cm),
            patch(patch_sid) as m_sid,
            patch(patch_qid) as m_qid,
            patch(patch_at) as m_at,
            patch(patch_ai) as m_ai,
        ):
            m_sid.get.return_value = uuid.uuid4()
            m_qid.get.return_value = uuid.uuid4()
            m_at.get.return_value = None
            m_ai.get.return_value = None
            await write_event(
                "tool_execution",
                {
                    "tool_name": "analyze_stock",
                    "latency_ms": 300,
                    "status": "ok",
                    "result_size_bytes": 1024,
                    "params": {"ticker": "AAPL"},
                    "result": {"score": 8.5},
                    "error": None,
                },
            )

        row = mock_session.add.call_args[0][0]
        assert "8.5" in row.output_summary
