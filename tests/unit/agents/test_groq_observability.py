"""Tests for observability instrumentation in GroqProvider."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.llm_client import LLMResponse
from backend.observability.collector import ObservabilityCollector


class TestGroqProviderObservability:
    """Tests for GroqProvider recording to ObservabilityCollector."""

    @pytest.mark.asyncio
    async def test_successful_call_records_request(self) -> None:
        """A successful Groq call should fire a DB write for the request."""
        collector = ObservabilityCollector()
        writer = AsyncMock()
        collector.set_db_writer(writer)

        from backend.agents.providers.groq import GroqProvider

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

        # Wait for fire-and-forget task
        await asyncio.sleep(0.05)
        writer.assert_called()
        call_data = writer.call_args[0][1]
        assert call_data["model"] == "model-a"
        assert call_data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_cascade_records_event(self) -> None:
        """When a model fails and cascades, cascade + success events should be recorded."""
        collector = ObservabilityCollector()
        writer = AsyncMock()
        collector.set_db_writer(writer)

        from backend.agents.providers.groq import GroqProvider

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

        # Wait for fire-and-forget tasks
        await asyncio.sleep(0.05)

        # Cascade recorded in in-memory log
        assert len(collector._cascade_log) == 1
        assert collector._cascade_log[0]["model"] == "model-a"

        # DB writer called for cascade (error) + success
        assert writer.call_count == 2

    @pytest.mark.asyncio
    async def test_no_collector_still_works(self) -> None:
        """GroqProvider without collector should work as before."""
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
