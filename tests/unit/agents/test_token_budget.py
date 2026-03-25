"""Tests for the async sliding-window token budget tracker."""

import pytest

from backend.agents.token_budget import ModelLimits, TokenBudget


@pytest.fixture
def budget():
    """Budget with two test models."""
    limits = {
        "model-a": ModelLimits(tpm=1000, rpm=10, tpd=10000, rpd=100),
        "model-b": ModelLimits(tpm=500, rpm=5, tpd=5000, rpd=50),
    }
    return TokenBudget(limits=limits)


class TestEstimateTokens:
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


class TestRecord:
    @pytest.mark.asyncio
    async def test_record_updates_window(self, budget):
        """Recording tokens reduces available budget."""
        await budget.record("model-a", 500)
        # 500 + 400 = 900 > 800 threshold
        assert await budget.can_afford("model-a", 400) is False
        # But 500 + 200 = 700 < 800 threshold
        assert await budget.can_afford("model-a", 200) is True


class TestLoadLimits:
    @pytest.mark.asyncio
    async def test_load_limits_from_model_configs(self):
        """load_limits populates from ModelConfig-like objects."""

        class FakeConfig:
            def __init__(self, name, tpm):
                self.model_name = name
                self.tpm_limit = tpm
                self.rpm_limit = 30
                self.tpd_limit = 100_000
                self.rpd_limit = 1_000

        budget = TokenBudget()
        budget.load_limits([FakeConfig("test-model", 500)])
        # Model is now tracked — large request exceeds threshold
        assert await budget.can_afford("test-model", 500) is False
        # Small request fits
        assert await budget.can_afford("test-model", 100) is True
