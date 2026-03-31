"""Tests for the Redis-backed sliding-window token budget tracker."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.observability.token_budget import ModelLimits, TokenBudget


@pytest.fixture
def mock_redis():
    """Fake Redis that stores sorted sets in-memory for testing."""
    return FakeRedis()


class FakeRedis:
    """Minimal in-memory Redis substitute for sorted-set + script operations."""

    def __init__(self):
        self._data: dict[str, list[tuple[float, str]]] = {}
        self._ttls: dict[str, int] = {}
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
            # Prune-and-sum script
            cutoff = float(args[1])
            entries = self._data.get(key, [])
            self._data[key] = [(s, m) for s, m in entries if s > cutoff]
            total = 0
            for _, member in self._data.get(key, []):
                count_str = member.rsplit(":", 1)[-1]
                total += int(count_str)
            return total
        elif "ZADD" in script:
            # Record script
            score = float(args[1])
            member = args[2]
            ttl = int(args[3])
            if key not in self._data:
                self._data[key] = []
            self._data[key].append((score, member))
            self._ttls[key] = ttl
            return 1
        return 0


@pytest.fixture
def budget(mock_redis):
    """Budget with two test models backed by fake Redis."""
    limits = {
        "model-a": ModelLimits(tpm=1000, rpm=10, tpd=10000, rpd=100),
        "model-b": ModelLimits(tpm=500, rpm=5, tpd=5000, rpd=50),
    }
    return TokenBudget(redis=mock_redis, limits=limits)


class TestEstimateTokens:
    """Tests for static token estimation."""

    def test_basic_estimate(self):
        """400 chars → 100 raw tokens * 1.2 margin = 120."""
        est = TokenBudget.estimate_tokens([{"content": "a" * 400}])
        assert est == 120

    def test_empty_messages(self):
        """Empty message list returns 0 tokens."""
        est = TokenBudget.estimate_tokens([])
        assert est == 0

    def test_multiple_messages(self):
        """Multiple messages are summed."""
        est = TokenBudget.estimate_tokens(
            [
                {"content": "a" * 200},
                {"content": "b" * 200},
            ]
        )
        assert est == 120  # 400 chars total


class TestCanAfford:
    """Tests for Redis-backed budget checking."""

    @pytest.mark.asyncio
    async def test_under_threshold_returns_true(self, budget):
        """Under 80% threshold → can afford."""
        assert await budget.can_afford("model-a", 100) is True

    @pytest.mark.asyncio
    async def test_at_80pct_threshold_returns_false(self, budget):
        """Recording enough to exceed 80% TPM threshold → can't afford."""
        await budget.record("model-a", 750)
        # 750 + 100 = 850 > 800 (80% of 1000)
        assert await budget.can_afford("model-a", 100) is False

    @pytest.mark.asyncio
    async def test_unknown_model_allowed(self, budget):
        """Unknown models with no limits are always allowed."""
        assert await budget.can_afford("unknown-model", 9999) is True

    @pytest.mark.asyncio
    async def test_rpm_limit_enforced(self, budget):
        """Recording 8 requests hits 80% of rpm=10 threshold."""
        for _ in range(8):
            await budget.record("model-a", 1)
        assert await budget.can_afford("model-a", 1) is False

    @pytest.mark.asyncio
    async def test_small_request_under_threshold(self, budget):
        """Small request that stays under threshold succeeds."""
        await budget.record("model-a", 500)
        # 500 + 200 = 700 < 800 threshold
        assert await budget.can_afford("model-a", 200) is True

    @pytest.mark.asyncio
    async def test_no_redis_fails_open(self):
        """Without Redis, all requests are allowed (fail-open)."""
        budget = TokenBudget(
            redis=None,
            limits={"model-a": ModelLimits(tpm=100, rpm=1, tpd=100, rpd=1)},
        )
        assert await budget.can_afford("model-a", 9999) is True

    @pytest.mark.asyncio
    async def test_redis_error_fails_open(self, budget):
        """Redis errors should fail open (allow the request)."""
        budget._redis.evalsha = AsyncMock(side_effect=ConnectionError("Redis down"))
        budget._prune_sha = "fake_sha"
        assert await budget.can_afford("model-a", 9999) is True

    @pytest.mark.asyncio
    async def test_noscript_recovery(self, budget):
        """After Redis error, cached SHAs are cleared so scripts re-register on next call."""
        # Populate both SHAs by calling can_afford + record
        await budget.record("model-a", 500)
        await budget.can_afford("model-a", 100)
        assert budget._prune_sha is not None
        assert budget._record_sha is not None

        # Simulate NOSCRIPT error (Redis restarted)
        original_evalsha = budget._redis.evalsha
        budget._redis.evalsha = AsyncMock(side_effect=Exception("NOSCRIPT"))
        await budget.can_afford("model-a", 100)  # fails open

        # SHAs should be invalidated
        assert budget._prune_sha is None
        assert budget._record_sha is None

        # Restore Redis — next call should re-register scripts and work
        budget._redis.evalsha = original_evalsha
        assert await budget.can_afford("model-a", 200) is True


class TestRecord:
    """Tests for recording token usage."""

    @pytest.mark.asyncio
    async def test_record_updates_window(self, budget):
        """Recording tokens reduces available budget."""
        await budget.record("model-a", 500)
        # 500 + 400 = 900 > 800 threshold
        assert await budget.can_afford("model-a", 400) is False
        # But 500 + 200 = 700 < 800 threshold
        assert await budget.can_afford("model-a", 200) is True

    @pytest.mark.asyncio
    async def test_record_no_redis_is_noop(self):
        """Recording without Redis is a silent no-op."""
        budget = TokenBudget(redis=None)
        await budget.record("model-a", 500)  # should not raise

    @pytest.mark.asyncio
    async def test_record_redis_error_logged(self, budget):
        """Redis errors during record are logged but don't raise."""
        budget._redis.evalsha = AsyncMock(side_effect=ConnectionError("Redis down"))
        budget._record_sha = "fake_sha"
        with patch("backend.observability.token_budget.logger") as mock_logger:
            await budget.record("model-a", 500)
            mock_logger.warning.assert_called_once()


class TestLoadLimits:
    """Tests for loading limits from model configs."""

    @pytest.mark.asyncio
    async def test_load_limits_from_model_configs(self, mock_redis):
        """load_limits populates from ModelConfig-like objects."""

        class FakeConfig:
            def __init__(self, name, tpm):
                self.model_name = name
                self.tpm_limit = tpm
                self.rpm_limit = 30
                self.tpd_limit = 100_000
                self.rpd_limit = 1_000

        budget = TokenBudget(redis=mock_redis)
        budget.load_limits([FakeConfig("test-model", 500)])
        # Model is now tracked — large request exceeds threshold
        assert await budget.can_afford("test-model", 500) is False
        # Small request fits
        assert await budget.can_afford("test-model", 100) is True


class TestSetRedis:
    """Tests for injecting Redis after construction."""

    @pytest.mark.asyncio
    async def test_set_redis_enables_tracking(self, mock_redis):
        """Setting Redis after construction enables budget tracking."""
        budget = TokenBudget(
            limits={"model-a": ModelLimits(tpm=100, rpm=10, tpd=1000, rpd=100)},
        )
        # No Redis → fail open
        assert await budget.can_afford("model-a", 9999) is True

        # Inject Redis → tracking works
        budget.set_redis(mock_redis)
        assert await budget.can_afford("model-a", 90) is False  # 90 > 80% of 100
