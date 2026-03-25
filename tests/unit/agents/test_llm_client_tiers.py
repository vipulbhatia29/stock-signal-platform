"""Tests for LLM client tier routing, fallback chain, and cascade error handling."""

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


class _FakeProvider(LLMProvider):
    """Configurable fake provider for tier routing tests."""

    def __init__(self, name: str = "fake", response: LLMResponse | None = None, error=None):
        self._name = name
        self._response = response
        self._error = error
        self.health = ProviderHealth(provider=name)
        self.call_count = 0

    @property
    def name(self) -> str:
        """Provider name."""
        return self._name

    def get_chat_model(self):
        """Not used in these tests."""
        return None

    async def chat(self, messages, tools, stream=False):
        """Return fake response or raise error."""
        self.call_count += 1
        if self._error:
            raise self._error
        return self._response or LLMResponse("ok", [], f"{self._name}-model", 10, 5)


def _resp(content: str, model: str = "m") -> LLMResponse:
    """Helper to build LLMResponse."""
    return LLMResponse(
        content=content, tool_calls=[], model=model, prompt_tokens=10, completion_tokens=5
    )


class TestTierRouting:
    @pytest.mark.asyncio
    async def test_planner_tier_uses_planner_provider(self):
        """Planner tier routes to the planner-specific provider."""
        default = _FakeProvider("default", response=_resp("default"))
        planner = _FakeProvider("planner", response=_resp("planned"))

        client = LLMClient(
            providers=[default],
            tier_config={"planner": [planner]},
        )
        result = await client.chat(
            messages=[{"role": "user", "content": "plan"}], tools=[], tier="planner"
        )
        assert result.content == "planned"
        assert planner.call_count == 1
        assert default.call_count == 0

    @pytest.mark.asyncio
    async def test_synthesizer_tier_independent(self):
        """Synthesizer tier is independent from planner tier."""
        planner = _FakeProvider("planner", response=_resp("plan"))
        synth = _FakeProvider("synth", response=_resp("synthesis"))
        default = _FakeProvider("default", response=_resp("default"))

        client = LLMClient(
            providers=[default],
            tier_config={"planner": [planner], "synthesizer": [synth]},
        )

        plan_result = await client.chat(messages=[], tools=[], tier="planner")
        synth_result = await client.chat(messages=[], tools=[], tier="synthesizer")

        assert plan_result.content == "plan"
        assert synth_result.content == "synthesis"

    @pytest.mark.asyncio
    async def test_unknown_tier_falls_back_to_default(self):
        """Unknown tier name falls back to default providers."""
        default = _FakeProvider("default", response=_resp("fallback"))
        client = LLMClient(providers=[default], tier_config={})

        result = await client.chat(messages=[], tools=[], tier="nonexistent")
        assert result.content == "fallback"
        assert default.call_count == 1


class TestFallbackChain:
    @pytest.mark.asyncio
    async def test_tier_provider_failure_tries_next(self):
        """Within a tier, failing first provider falls to second."""
        bad = _FakeProvider("bad-groq", error=Exception("down"))
        good = _FakeProvider("good-anthropic", response=_resp("recovered"))

        client = LLMClient(
            providers=[_FakeProvider("unused")],
            tier_config={"planner": [bad, good]},
            retry_policy=RetryPolicy(max_retries=1),
        )

        result = await client.chat(messages=[], tools=[], tier="planner")
        assert result.content == "recovered"
        assert bad.call_count >= 1
        assert good.call_count == 1

    @pytest.mark.asyncio
    async def test_all_tier_providers_fail(self):
        """All providers in a tier failing raises AllProvidersFailedError."""
        bad1 = _FakeProvider("groq", error=Exception("fail"))
        bad2 = _FakeProvider("anthropic", error=Exception("fail"))

        client = LLMClient(
            providers=[_FakeProvider("unused")],
            tier_config={"planner": [bad1, bad2]},
            retry_policy=RetryPolicy(max_retries=1),
        )

        with pytest.raises(AllProvidersFailedError):
            await client.chat(messages=[], tools=[], tier="planner")


class TestAllModelsExhaustedError:
    def test_is_exception(self):
        """AllModelsExhaustedError is an Exception subclass."""
        err = AllModelsExhaustedError("all gone")
        assert isinstance(err, Exception)
        assert str(err) == "all gone"

    def test_can_be_caught(self):
        """AllModelsExhaustedError can be caught as Exception."""
        try:
            raise AllModelsExhaustedError("test")
        except Exception as e:
            assert "test" in str(e)
