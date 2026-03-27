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
