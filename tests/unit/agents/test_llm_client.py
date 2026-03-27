"""Tests for LLMClient and provider abstraction."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from backend.agents.llm_client import (
    AllModelsExhaustedError,
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
        content="",
        tool_calls=[{"id": "1", "name": "test"}],
        model="m",
        prompt_tokens=0,
        completion_tokens=0,
    )
    without_tools = LLMResponse(
        content="Hi",
        tool_calls=[],
        model="m",
        prompt_tokens=0,
        completion_tokens=0,
    )
    assert with_tools.has_tool_calls is True
    assert without_tools.has_tool_calls is False


def test_get_active_chat_model():
    """get_active_chat_model returns first healthy provider's model."""
    p = FakeProvider("groq")
    client = LLMClient(providers=[p])
    model = client.get_active_chat_model()
    assert model is None  # FakeProvider returns None


# ─── Tier routing tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier_routing_uses_tier_providers():
    """LLMClient with tier_config routes to correct provider per tier."""
    default_resp = LLMResponse("default", [], "default-model", 10, 5)
    planner_resp = LLMResponse("planner", [], "planner-model", 20, 10)

    default_provider = FakeProvider("default", response=default_resp)
    planner_provider = FakeProvider("planner", response=planner_resp)

    client = LLMClient(
        providers=[default_provider],
        tier_config={"planner": [planner_provider]},
    )

    # With tier → uses planner provider
    result = await client.chat(
        messages=[{"role": "user", "content": "plan"}], tools=[], tier="planner"
    )
    assert result.content == "planner"
    assert result.model == "planner-model"

    # Without tier → uses default provider
    result = await client.chat(messages=[{"role": "user", "content": "hi"}], tools=[])
    assert result.content == "default"


@pytest.mark.asyncio
async def test_tier_fallback_to_default():
    """If tier not found in config, falls back to default providers."""
    resp = LLMResponse("fallback", [], "model", 10, 5)
    default_provider = FakeProvider("default", response=resp)

    client = LLMClient(
        providers=[default_provider],
        tier_config={"planner": []},  # empty planner tier
    )

    # Unknown tier → falls back to default
    result = await client.chat(
        messages=[{"role": "user", "content": "test"}],
        tools=[],
        tier="unknown_tier",
    )
    assert result.content == "fallback"


@pytest.mark.asyncio
async def test_backward_compat_no_tier_config():
    """Old constructor style (no tier_config) still works."""
    resp = LLMResponse("ok", [], "model", 10, 5)
    p = FakeProvider("groq", response=resp)
    client = LLMClient(providers=[p])

    result = await client.chat(messages=[{"role": "user", "content": "hi"}], tools=[])
    assert result.content == "ok"


# ─── ProviderHealth bug regression ───────────────────────────────────────────


def test_mark_exhausted_sets_future_time():
    """mark_exhausted with retry_after should set exhausted_until in the future."""
    health = ProviderHealth(provider="groq")
    health.mark_exhausted(retry_after=60.0)
    assert health.is_exhausted is True
    assert health.exhausted_until is not None
    assert health.exhausted_until > datetime.now(timezone.utc)


def test_mark_exhausted_without_retry_after():
    """mark_exhausted without retry_after leaves exhausted_until as None."""
    health = ProviderHealth(provider="groq")
    health.mark_exhausted()
    assert health.is_exhausted is True
    assert health.exhausted_until is None


def test_is_available_after_exhaustion_expires():
    """is_available returns True once exhausted_until has passed."""
    health = ProviderHealth(provider="groq")
    health.is_exhausted = True
    health.exhausted_until = datetime(2020, 1, 1, tzinfo=timezone.utc)  # in the past
    assert health.is_available() is True
    assert health.is_exhausted is False  # reset by is_available


# ─── AllModelsExhaustedError ─────────────────────────────────────────────────


def test_all_models_exhausted_error_exists():
    """AllModelsExhaustedError is importable and is an Exception."""
    assert issubclass(AllModelsExhaustedError, Exception)


# ─── Cross-provider cascade recording ─────────────────────────────────────────


def _make_mock_provider(name: str, *, fail: bool = False) -> MagicMock:
    """Create a mock LLMProvider."""
    provider = MagicMock()
    type(provider).name = PropertyMock(return_value=name)
    provider.health = ProviderHealth(provider=name)
    if fail:
        provider.chat = AsyncMock(side_effect=Exception(f"{name} down"))
    else:
        provider.chat = AsyncMock(
            return_value=LLMResponse(
                content="ok",
                tool_calls=[],
                model=f"{name}-model",
                prompt_tokens=10,
                completion_tokens=5,
            )
        )
    return provider


class TestCrossProviderCascade:
    """Tests for LLMClient recording cascades when providers fail."""

    @pytest.mark.asyncio
    async def test_cross_provider_cascade_recorded(self) -> None:
        """When provider A fails and B succeeds, cascade should be recorded for A."""
        collector = AsyncMock()
        provider_a = _make_mock_provider("groq", fail=True)
        provider_b = _make_mock_provider("anthropic")
        client = LLMClient(providers=[provider_a, provider_b], collector=collector)

        result = await client.chat(messages=[{"role": "user", "content": "hi"}], tools=[])

        assert result.content == "ok"
        collector.record_cascade.assert_awaited_once()
        call_kwargs = collector.record_cascade.call_args[1]
        assert call_kwargs["from_model"] == "groq"
        assert call_kwargs["provider"] == "groq"

    @pytest.mark.asyncio
    async def test_no_collector_no_error(self) -> None:
        """LLMClient with no collector should not raise on cascade."""
        provider_a = _make_mock_provider("groq", fail=True)
        provider_b = _make_mock_provider("anthropic")
        client = LLMClient(providers=[provider_a, provider_b])  # no collector

        result = await client.chat(messages=[{"role": "user", "content": "hi"}], tools=[])
        assert result.content == "ok"

    @pytest.mark.asyncio
    async def test_tier_passed_to_cascade(self) -> None:
        """Tier should be passed through to cascade recording."""
        collector = AsyncMock()
        provider_a = _make_mock_provider("groq", fail=True)
        provider_b = _make_mock_provider("anthropic")
        client = LLMClient(
            providers=[provider_a, provider_b],
            tier_config={"synthesizer": [provider_a, provider_b]},
            collector=collector,
        )

        await client.chat(
            messages=[{"role": "user", "content": "hi"}], tools=[], tier="synthesizer"
        )

        call_kwargs = collector.record_cascade.call_args[1]
        assert call_kwargs["tier"] == "synthesizer"
