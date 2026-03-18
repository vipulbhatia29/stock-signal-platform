"""Tests for LLMClient and provider abstraction."""

from datetime import datetime, timezone

import pytest

from backend.agents.llm_client import (
    AllProvidersFailedError,
    LLMClient,
    LLMProvider,
    LLMResponse,
    ProviderHealth,
    RetryPolicy,
)


class FakeProvider(LLMProvider):
    """A fake provider for testing."""

    def __init__(self, name="fake", response=None, error=None):
        self._name = name
        self._response = response
        self._error = error
        self.health = ProviderHealth(provider=name)

    @property
    def name(self) -> str:
        """Provider name."""
        return self._name

    def get_chat_model(self):
        """Return None — fake provider has no real model."""
        return None

    async def chat(self, messages, tools, stream=False):
        """Return fake response or raise error."""
        if self._error:
            raise self._error
        return self._response or LLMResponse(
            content="Test response",
            tool_calls=[],
            model=f"{self._name}-model",
            prompt_tokens=100,
            completion_tokens=50,
        )


@pytest.mark.asyncio
async def test_llm_client_first_provider_succeeds():
    """LLMClient uses first available provider."""
    provider = FakeProvider("groq")
    client = LLMClient(providers=[provider])
    response = await client.chat(messages=[{"role": "user", "content": "Hi"}], tools=[])
    assert response.content == "Test response"
    assert response.model == "groq-model"


@pytest.mark.asyncio
async def test_llm_client_fallback_on_error():
    """LLMClient falls through to next provider on error."""
    bad = FakeProvider("groq", error=Exception("down"))
    good = FakeProvider("anthropic")
    client = LLMClient(providers=[bad, good], retry_policy=RetryPolicy(max_retries=1))
    response = await client.chat(messages=[{"role": "user", "content": "Hi"}], tools=[])
    assert response.model == "anthropic-model"


@pytest.mark.asyncio
async def test_llm_client_all_fail():
    """LLMClient raises AllProvidersFailedError when all providers fail."""
    bad1 = FakeProvider("groq", error=Exception("down"))
    bad2 = FakeProvider("anthropic", error=Exception("down"))
    client = LLMClient(providers=[bad1, bad2], retry_policy=RetryPolicy(max_retries=1))
    with pytest.raises(AllProvidersFailedError):
        await client.chat(messages=[], tools=[])


@pytest.mark.asyncio
async def test_llm_client_skips_exhausted_provider():
    """LLMClient skips providers marked as exhausted."""
    exhausted = FakeProvider("groq")
    exhausted.health.is_exhausted = True
    exhausted.health.exhausted_until = datetime(2099, 1, 1, tzinfo=timezone.utc)
    good = FakeProvider("anthropic")
    client = LLMClient(providers=[exhausted, good])
    response = await client.chat(messages=[], tools=[])
    assert response.model == "anthropic-model"


def test_provider_health_defaults():
    """ProviderHealth has sane defaults."""
    h = ProviderHealth(provider="groq")
    assert h.is_exhausted is False
    assert h.consecutive_failures == 0


def test_retry_policy_defaults():
    """RetryPolicy has sane defaults."""
    p = RetryPolicy()
    assert p.max_retries == 3
    assert p.base_delay == 1.0
    assert p.backoff_factor == 2.0


def test_llm_response_has_tool_calls():
    """LLMResponse.has_tool_calls detects tool calls."""
    with_tools = LLMResponse(
        content="", tool_calls=[{"id": "1", "name": "test"}],
        model="m", prompt_tokens=0, completion_tokens=0,
    )
    without_tools = LLMResponse(
        content="Hi", tool_calls=[],
        model="m", prompt_tokens=0, completion_tokens=0,
    )
    assert with_tools.has_tool_calls is True
    assert without_tools.has_tool_calls is False


def test_get_active_chat_model():
    """get_active_chat_model returns first healthy provider's model."""
    p = FakeProvider("groq")
    client = LLMClient(providers=[p])
    model = client.get_active_chat_model()
    assert model is None  # FakeProvider returns None
