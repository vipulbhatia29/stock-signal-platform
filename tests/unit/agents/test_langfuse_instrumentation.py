"""Tests for Langfuse instrumentation in react_loop and LLMClient."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.llm_client import LLMClient
from backend.agents.react_loop import react_loop


class TestReactLoopLangfuseSpans:
    """Tests for Langfuse span instrumentation in react_loop."""

    @pytest.mark.asyncio
    async def test_creates_iteration_span_when_trace_provided(self):
        """Should create a span named 'react.iteration.1' when langfuse_trace is given."""
        mock_trace = MagicMock()
        mock_span = MagicMock()
        mock_trace.span.return_value = mock_span

        # LLM returns final answer (no tool calls) on first iteration
        mock_response = MagicMock()
        mock_response.content = "Here is your answer."
        mock_response.has_tool_calls = False
        mock_response.model = "llama-3.3-70b"
        mock_response.prompt_tokens = 100
        mock_response.completion_tokens = 50
        mock_response.usage_dict.return_value = {}

        async def mock_llm_chat(msgs, tools):
            return mock_response

        events = []
        async for event in react_loop(
            query="What about AAPL?",
            session_messages=[],
            tools=[],
            tool_executor=AsyncMock(),
            llm_chat=mock_llm_chat,
            user_context={},
            langfuse_trace=mock_trace,
        ):
            events.append(event)

        # Should have created a span
        mock_trace.span.assert_called_once()
        call_kwargs = mock_trace.span.call_args
        assert call_kwargs[1]["name"] == "react.iteration.1"

        # Should rename to synthesis and end
        mock_span.update.assert_called_once_with(name="synthesis")
        mock_span.end.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_error_when_langfuse_trace_is_none(self):
        """Should not crash when langfuse_trace is None."""
        mock_response = MagicMock()
        mock_response.content = "Answer"
        mock_response.has_tool_calls = False
        mock_response.model = "test"
        mock_response.prompt_tokens = 10
        mock_response.completion_tokens = 5
        mock_response.usage_dict.return_value = {}

        async def mock_llm_chat(msgs, tools):
            return mock_response

        events = []
        async for event in react_loop(
            query="test",
            session_messages=[],
            tools=[],
            tool_executor=AsyncMock(),
            llm_chat=mock_llm_chat,
            user_context={},
            langfuse_trace=None,
        ):
            events.append(event)

        # Should complete without error
        assert any(e.type == "done" for e in events)


class TestLLMClientLangfuseGeneration:
    """Tests for Langfuse generation recording in LLMClient."""

    @pytest.mark.asyncio
    async def test_records_generation_via_langfuse_service(self):
        """Should call LangfuseService.record_generation after successful LLM call."""
        mock_langfuse = MagicMock()
        mock_langfuse.enabled = True
        mock_trace = MagicMock()
        mock_langfuse.get_trace_ref.return_value = mock_trace

        mock_provider = MagicMock()
        mock_provider.name = "groq"
        mock_provider.health.is_available.return_value = True
        mock_provider._compute_cost.return_value = 0.001

        mock_response = MagicMock()
        mock_response.model = "llama-3.3-70b"
        mock_response.content = "Test response"
        mock_response.prompt_tokens = 100
        mock_response.completion_tokens = 50
        mock_provider.chat = AsyncMock(return_value=mock_response)

        client = LLMClient(
            providers=[mock_provider],
            langfuse_service=mock_langfuse,
        )

        qid = uuid.uuid4()
        with patch("backend.request_context.current_query_id") as mock_ctx:
            mock_ctx.get.return_value = qid

            await client.chat(messages=[{"role": "user", "content": "test"}], tools=[])

        mock_langfuse.get_trace_ref.assert_called_once_with(qid)
        mock_langfuse.record_generation.assert_called_once()
        call_kwargs = mock_langfuse.record_generation.call_args[1]
        assert call_kwargs["trace"] is mock_trace
        assert call_kwargs["name"] == "llm.groq.llama-3.3-70b"
        assert call_kwargs["cost_usd"] == 0.001

    @pytest.mark.asyncio
    async def test_no_generation_when_langfuse_disabled(self):
        """Should skip generation recording when langfuse is not enabled."""
        mock_langfuse = MagicMock()
        mock_langfuse.enabled = False

        mock_provider = MagicMock()
        mock_provider.name = "groq"
        mock_provider.health.is_available.return_value = True

        mock_response = MagicMock()
        mock_response.model = "test"
        mock_response.content = "ok"
        mock_response.prompt_tokens = 10
        mock_response.completion_tokens = 5
        mock_provider.chat = AsyncMock(return_value=mock_response)

        client = LLMClient(providers=[mock_provider], langfuse_service=mock_langfuse)
        await client.chat(messages=[{"role": "user", "content": "test"}], tools=[])

        mock_langfuse.get_trace_ref.assert_not_called()
        mock_langfuse.record_generation.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_crash_when_langfuse_is_none(self):
        """Should work fine without any langfuse_service."""
        mock_provider = MagicMock()
        mock_provider.name = "groq"
        mock_provider.health.is_available.return_value = True

        mock_response = MagicMock()
        mock_response.model = "test"
        mock_response.content = "ok"
        mock_response.prompt_tokens = 10
        mock_response.completion_tokens = 5
        mock_provider.chat = AsyncMock(return_value=mock_response)

        client = LLMClient(providers=[mock_provider])
        result = await client.chat(messages=[{"role": "user", "content": "test"}], tools=[])
        assert result.content == "ok"
