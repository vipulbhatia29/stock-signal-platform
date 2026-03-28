"""Tests for GroqProvider multi-model cascade."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.llm_client import AllModelsExhaustedError, LLMResponse
from backend.agents.providers.groq import GroqProvider, _classify_error
from backend.agents.token_budget import ModelLimits, TokenBudget


class FakeRedis:
    """Minimal in-memory Redis substitute for sorted-set + script operations."""

    def __init__(self):
        self._data: dict[str, list[tuple[float, str]]] = {}
        self._scripts: dict[str, str] = {}
        self._next_sha = 0

    async def script_load(self, script: str) -> str:
        """Store script and return a fake SHA."""
        sha = f"sha_{self._next_sha}"
        self._next_sha += 1
        self._scripts[sha] = script
        return sha

    async def evalsha(self, sha: str, numkeys: int, *args) -> int:
        """Execute the cached Lua script logic in Python."""
        script = self._scripts[sha]
        key = args[0]
        if "ZREMRANGEBYSCORE" in script and "ZADD" not in script:
            cutoff = float(args[1])
            entries = self._data.get(key, [])
            self._data[key] = [(s, m) for s, m in entries if s > cutoff]
            total = 0
            for _, member in self._data.get(key, []):
                total += int(member.rsplit(":", 1)[-1])
            return total
        elif "ZADD" in script:
            score = float(args[1])
            member = args[2]
            if key not in self._data:
                self._data[key] = []
            self._data[key].append((score, member))
            return 1
        return 0


@pytest.fixture
def budget():
    """Budget with limits for test models backed by fake Redis."""
    return TokenBudget(
        redis=FakeRedis(),
        limits={
            "model-1": ModelLimits(tpm=10000, rpm=30, tpd=100000, rpd=1000),
            "model-2": ModelLimits(tpm=5000, rpm=30, tpd=50000, rpd=1000),
        },
    )


@pytest.fixture
def provider(budget):
    """GroqProvider with two cascade models and budget."""
    return GroqProvider(
        api_key="test-key",
        models=["model-1", "model-2"],
        token_budget=budget,
    )


def _make_response(model: str = "model-1") -> LLMResponse:
    """Create a successful LLMResponse."""
    return LLMResponse(
        content="ok",
        tool_calls=[],
        model=model,
        prompt_tokens=10,
        completion_tokens=5,
    )


class TestCascade:
    @pytest.mark.asyncio
    async def test_first_model_succeeds(self, provider):
        """First model succeeds → returned immediately."""
        with patch.object(
            provider, "_call_model", new_callable=AsyncMock, return_value=_make_response("model-1")
        ):
            result = await provider.chat([{"role": "user", "content": "hi"}], [])
            assert result.model == "model-1"

    @pytest.mark.asyncio
    async def test_cascade_on_api_error(self, provider):
        """First model fails → cascades to second model."""
        call_count = 0

        async def mock_call(model, messages, tools, stream):
            """Fail on first call, succeed on second."""
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("rate limit exceeded 429")
            return _make_response(model)

        with patch.object(provider, "_call_model", side_effect=mock_call):
            result = await provider.chat([{"role": "user", "content": "hi"}], [])
            assert result.model == "model-2"

    @pytest.mark.asyncio
    async def test_all_models_exhausted(self, provider):
        """All models fail → AllModelsExhaustedError."""
        with patch.object(
            provider,
            "_call_model",
            new_callable=AsyncMock,
            side_effect=Exception("fail"),
        ):
            with pytest.raises(AllModelsExhaustedError, match="2 Groq models exhausted"):
                await provider.chat([{"role": "user", "content": "hi"}], [])

    @pytest.mark.asyncio
    async def test_auth_error_stops_cascade(self, provider):
        """Auth errors should not cascade — all models share the same key."""
        with patch.object(
            provider,
            "_call_model",
            new_callable=AsyncMock,
            side_effect=Exception("401 auth error invalid api key"),
        ):
            with pytest.raises(AllModelsExhaustedError) as exc_info:
                await provider.chat([{"role": "user", "content": "hi"}], [])
            # Should only have tried model-1 (auth stops cascade)
            assert "model-1(auth)" in str(exc_info.value)
            assert "model-2" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_budget_skip(self, provider, budget):
        """Models over budget are skipped."""
        # Exhaust model-1's budget
        await budget.record("model-1", 9000)  # 90% of 10000 TPM

        with patch.object(
            provider, "_call_model", new_callable=AsyncMock, return_value=_make_response("model-2")
        ):
            result = await provider.chat([{"role": "user", "content": "hi"}], [])
            assert result.model == "model-2"

    @pytest.mark.asyncio
    async def test_no_budget_allows_all(self):
        """Without token_budget, all models are tried."""
        provider = GroqProvider(
            api_key="test-key",
            models=["model-1"],
            token_budget=None,
        )
        with patch.object(
            provider, "_call_model", new_callable=AsyncMock, return_value=_make_response("model-1")
        ):
            result = await provider.chat([{"role": "user", "content": "hi"}], [])
            assert result.model == "model-1"

    @pytest.mark.asyncio
    async def test_budget_recorded_on_success(self, provider, budget):
        """Successful calls record actual token usage."""
        response = _make_response("model-1")
        with patch.object(provider, "_call_model", new_callable=AsyncMock, return_value=response):
            await provider.chat([{"role": "user", "content": "hi"}], [])
        # 10 prompt + 5 completion = 15 tokens recorded
        # After recording, budget should reflect the usage
        # 15 + 7990 = 8005 > 8000 (80% of 10000)
        assert await budget.can_afford("model-1", 7990) is False


class TestClassifyError:
    def test_rate_limit(self):
        """Rate limit errors are classified correctly."""
        assert _classify_error(Exception("429 rate limit exceeded")) == "rate_limit"
        assert _classify_error(Exception("Too many requests")) == "rate_limit"

    def test_context_length(self):
        """Context length errors are classified correctly."""
        assert _classify_error(Exception("context length exceeded")) == "context_length"
        assert _classify_error(Exception("too long for this model token limit")) == "context_length"

    def test_auth(self):
        """Auth errors are classified correctly."""
        assert _classify_error(Exception("401 unauthorized")) == "auth"
        assert _classify_error(Exception("Invalid API key")) == "auth"

    def test_transient(self):
        """Transient errors are classified correctly."""
        assert _classify_error(Exception("connection timeout")) == "transient"
        assert _classify_error(Exception("503 service unavailable")) == "transient"

    def test_permanent(self):
        """Unknown errors default to permanent."""
        assert _classify_error(Exception("something weird")) == "permanent"


class TestProviderInterface:
    def test_name(self, provider):
        """Provider name is 'groq'."""
        assert provider.name == "groq"

    def test_default_single_model(self):
        """Default constructor uses single model."""
        p = GroqProvider(api_key="test")
        assert p._models == ["llama-3.3-70b-versatile"]
