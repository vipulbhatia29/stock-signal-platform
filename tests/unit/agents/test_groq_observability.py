"""Tests for observability instrumentation in GroqProvider."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.llm_client import LLMResponse
from backend.agents.observability import ObservabilityCollector


class TestGroqProviderObservability:
    """Tests for GroqProvider recording to ObservabilityCollector."""

    @pytest.mark.asyncio
    async def test_successful_call_records_request(self) -> None:
        """A successful Groq call should record a request event."""
        collector = ObservabilityCollector()
        from backend.agents.providers.groq import GroqProvider

        provider = GroqProvider(api_key="test-key", models=["model-a"], collector=collector)
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

        stats = collector.get_stats()
        assert stats["requests_by_model"]["model-a"] == 1

    @pytest.mark.asyncio
    async def test_cascade_records_event(self) -> None:
        """When a model fails and cascades, a cascade event should be recorded."""
        collector = ObservabilityCollector()
        from backend.agents.providers.groq import GroqProvider

        provider = GroqProvider(
            api_key="test-key", models=["model-a", "model-b"], collector=collector
        )
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

        stats = collector.get_stats()
        assert stats["cascade_count"] == 1
        assert stats["cascades_by_model"]["model-a"] == 1
        assert stats["requests_by_model"]["model-b"] == 1

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
