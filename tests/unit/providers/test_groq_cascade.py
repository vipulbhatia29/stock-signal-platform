"""Tests for GroqProvider multi-model cascade."""

import threading
from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.llm_client import AllModelsExhaustedError, LLMClient, LLMResponse
from backend.agents.providers.groq import GroqProvider, RoundRobinPool, _classify_error
from backend.observability.token_budget import ModelLimits, TokenBudget


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


class TestRoundRobinPool:
    def test_rotates_start_position(self):
        """Three calls cycle through all starting positions."""
        pool = RoundRobinPool(["a", "b", "c"])
        assert pool.ordered_models() == ["a", "b", "c"]
        assert pool.ordered_models() == ["b", "c", "a"]
        assert pool.ordered_models() == ["c", "a", "b"]
        assert pool.ordered_models() == ["a", "b", "c"]

    def test_single_model(self):
        """Single model always returns same list."""
        pool = RoundRobinPool(["only"])
        assert pool.ordered_models() == ["only"]
        assert pool.ordered_models() == ["only"]

    def test_thread_safety(self):
        """50 concurrent calls produce valid rotations."""
        pool = RoundRobinPool(["a", "b", "c"])
        results: list[list[str]] = []
        lock = threading.Lock()

        def call():
            order = pool.ordered_models()
            with lock:
                results.append(order)

        threads = [threading.Thread(target=call) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 50
        valid_rotations = [["a", "b", "c"], ["b", "c", "a"], ["c", "a", "b"]]
        for r in results:
            assert r in valid_rotations


class TestRoundRobin:
    @pytest.mark.asyncio
    async def test_round_robin_rotates_model_order(self):
        """With round_robin=True, first model tried rotates each call."""
        provider = GroqProvider(
            api_key="test-key",
            models=["m1", "m2", "m3"],
            round_robin=True,
        )
        models_tried: list[str] = []

        async def capture_call(model, messages, tools, stream):
            models_tried.append(model)
            return _make_response(model)

        with patch.object(provider, "_call_model", side_effect=capture_call):
            # reset_pin between calls to simulate separate requests
            r1 = await provider.chat([{"role": "user", "content": "hi"}], [])
            provider.reset_pin()
            r2 = await provider.chat([{"role": "user", "content": "hi"}], [])
            provider.reset_pin()
            r3 = await provider.chat([{"role": "user", "content": "hi"}], [])

        assert r1.model == "m1"
        assert r2.model == "m2"
        assert r3.model == "m3"

    @pytest.mark.asyncio
    async def test_round_robin_disabled(self):
        """With round_robin=False, always starts with first model."""
        provider = GroqProvider(
            api_key="test-key",
            models=["m1", "m2"],
            round_robin=False,
        )
        with patch.object(
            provider, "_call_model", new_callable=AsyncMock, return_value=_make_response("m1")
        ):
            r1 = await provider.chat([{"role": "user", "content": "hi"}], [])
            provider.reset_pin()
            r2 = await provider.chat([{"role": "user", "content": "hi"}], [])
        assert r1.model == "m1"
        assert r2.model == "m1"


class TestModelPinning:
    @pytest.mark.asyncio
    async def test_pin_on_first_success(self):
        """After first successful call, subsequent calls use the same model."""
        provider = GroqProvider(
            api_key="test-key",
            models=["m1", "m2", "m3"],
            round_robin=True,
        )

        async def capture_call(model, messages, tools, stream):
            return _make_response(model)

        with patch.object(provider, "_call_model", side_effect=capture_call):
            r1 = await provider.chat([{"role": "user", "content": "q1"}], [])
            r2 = await provider.chat([{"role": "user", "content": "q2"}], [])
            r3 = await provider.chat([{"role": "user", "content": "q3"}], [])

        assert r1.model == r2.model == r3.model

    @pytest.mark.asyncio
    async def test_reset_pin_allows_rotation(self):
        """After reset_pin(), next call rotates normally."""
        provider = GroqProvider(
            api_key="test-key",
            models=["m1", "m2", "m3"],
            round_robin=True,
        )

        async def succeed(model, messages, tools, stream):
            return _make_response(model)

        with patch.object(provider, "_call_model", side_effect=succeed):
            await provider.chat([{"role": "user", "content": "q1"}], [])
            provider.reset_pin()
            r2 = await provider.chat([{"role": "user", "content": "q2"}], [])

        assert r2.model == "m2"

    @pytest.mark.asyncio
    async def test_pin_cascades_on_failure(self):
        """If pinned model fails, cascade to next and re-pin."""
        provider = GroqProvider(
            api_key="test-key",
            models=["m1", "m2"],
            round_robin=True,
        )
        call_count = 0

        async def fail_then_succeed(model, messages, tools, stream):
            nonlocal call_count
            call_count += 1
            if call_count <= 2 and model == "m1":
                raise Exception("rate limit 429")
            return _make_response(model)

        with patch.object(provider, "_call_model", side_effect=fail_then_succeed):
            r1 = await provider.chat([{"role": "user", "content": "q1"}], [])
            r2 = await provider.chat([{"role": "user", "content": "q2"}], [])

        assert r1.model == "m2"
        assert r2.model == "m2"


class TestLLMClientResetPin:
    def test_reset_pin_delegates_to_providers(self):
        """reset_pin() calls reset_pin() on all providers that support it."""
        provider = GroqProvider(
            api_key="test-key",
            models=["m1", "m2"],
            round_robin=True,
        )
        provider.pin_model("m1")
        assert provider._pinned_model == "m1"

        client = LLMClient(providers=[provider])
        client.reset_pin()
        assert provider._pinned_model is None

    def test_reset_pin_skips_providers_without_method(self):
        """reset_pin() doesn't fail on providers without the method."""
        from backend.agents.llm_client import LLMProvider, ProviderHealth

        class DummyProvider(LLMProvider):
            """Dummy provider without reset_pin."""

            health = ProviderHealth(provider="dummy")

            @property
            def name(self) -> str:
                return "dummy"

            def get_chat_model(self):
                return None

            async def chat(self, messages, tools, stream=False):
                pass

        client = LLMClient(providers=[DummyProvider()])
        client.reset_pin()


class TestBudgetCompression:
    @pytest.mark.asyncio
    async def test_compresses_on_budget_exhaustion(self):
        """When model is over budget, compress messages and retry."""
        from backend.agents.message_compressor import MessageCompressor

        budget_obj = TokenBudget(
            redis=FakeRedis(),
            limits={"m1": ModelLimits(tpm=10000, rpm=30, tpd=100000, rpd=1000)},
        )
        await budget_obj.record("m1", 5000)

        compressor = MessageCompressor()
        provider = GroqProvider(
            api_key="test-key",
            models=["m1"],
            token_budget=budget_obj,
            compressor=compressor,
        )

        # Build messages with compressible content: history + large tool results
        big_messages: list[dict] = [
            {"role": "system", "content": "system prompt"},
        ]
        # 5 history turns (compressible via stage 2)
        for i in range(5):
            big_messages.append({"role": "user", "content": f"old question {i} " * 50})
            big_messages.append({"role": "assistant", "content": f"old answer {i} " * 50})
        # Current query + tool results (compressible via stage 3)
        big_messages.append({"role": "user", "content": "current query"})
        big_messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {"name": "tool_1", "arguments": "{}"},
                    }
                ],
            }
        )
        big_messages.append(
            {
                "role": "tool",
                "tool_call_id": "tc_1",
                "content": "data " * 3000,  # 15000 chars of tool result
            }
        )

        with patch.object(
            provider,
            "_call_model",
            new_callable=AsyncMock,
            return_value=_make_response("m1"),
        ) as mock_call:
            result = await provider.chat(big_messages, [])
            assert result.model == "m1"
            # Verify compression happened: total content is smaller
            original_total = sum(len(m.get("content", "")) for m in big_messages)
            compressed_msgs = mock_call.call_args[0][1]
            compressed_total = sum(len(m.get("content", "")) for m in compressed_msgs)
            assert compressed_total < original_total

    @pytest.mark.asyncio
    async def test_cascades_when_compression_insufficient(self):
        """When compression can't bring cost under budget, cascade to next model."""
        from backend.agents.message_compressor import MessageCompressor

        budget_obj = TokenBudget(
            redis=FakeRedis(),
            limits={
                "m1": ModelLimits(tpm=100, rpm=30, tpd=100000, rpd=1000),
                "m2": ModelLimits(tpm=10000, rpm=30, tpd=100000, rpd=1000),
            },
        )
        await budget_obj.record("m1", 95)

        compressor = MessageCompressor()
        provider = GroqProvider(
            api_key="test-key",
            models=["m1", "m2"],
            token_budget=budget_obj,
            compressor=compressor,
            round_robin=False,
        )

        messages = [
            {"role": "system", "content": "x " * 200},
            {"role": "user", "content": "analyze this"},
        ]

        with patch.object(
            provider,
            "_call_model",
            new_callable=AsyncMock,
            return_value=_make_response("m2"),
        ):
            result = await provider.chat(messages, [])
            assert result.model == "m2"

    @pytest.mark.asyncio
    async def test_no_compression_without_compressor(self):
        """Without compressor injected, budget skip works as before."""
        budget_obj = TokenBudget(
            redis=FakeRedis(),
            limits={
                "m1": ModelLimits(tpm=100, rpm=30, tpd=100000, rpd=1000),
                "m2": ModelLimits(tpm=10000, rpm=30, tpd=100000, rpd=1000),
            },
        )
        await budget_obj.record("m1", 95)

        provider = GroqProvider(
            api_key="test-key",
            models=["m1", "m2"],
            token_budget=budget_obj,
            round_robin=False,
        )

        with patch.object(
            provider,
            "_call_model",
            new_callable=AsyncMock,
            return_value=_make_response("m2"),
        ):
            result = await provider.chat([{"role": "user", "content": "hi"}], [])
            assert result.model == "m2"
