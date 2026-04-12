"""Tests for PyPortfolioOpt rebalancing — compute_rebalancing() and helpers."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from backend.services.portfolio import (
    VALID_STRATEGIES,
    _equal_weight_fallback,
    _optimize,
    compute_rebalancing,
)


class TestOptimize:
    """Tests for the _optimize() helper that calls PyPortfolioOpt."""

    @pytest.fixture()
    def price_matrix(self) -> pd.DataFrame:
        """Generate a 100-day price matrix for 5 tickers."""
        np.random.seed(42)
        dates = pd.bdate_range("2025-01-01", periods=100)
        data = {}
        for ticker in ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]:
            data[ticker] = 100 + np.cumsum(np.random.randn(100) * 1.5)
        return pd.DataFrame(data, index=dates)

    def test_min_volatility_returns_weights(self, price_matrix):
        """min_volatility produces valid weights summing to ~1."""
        weights = _optimize(price_matrix, "min_volatility")
        assert isinstance(weights, dict)
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_max_sharpe_returns_weights(self, price_matrix):
        """max_sharpe produces valid weights summing to ~1."""
        weights = _optimize(price_matrix, "max_sharpe")
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_risk_parity_returns_weights(self, price_matrix):
        """risk_parity (HRP) produces valid weights summing to ~1."""
        weights = _optimize(price_matrix, "risk_parity")
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_all_weights_non_negative(self, price_matrix):
        """No short selling — all weights >= 0."""
        for strategy in VALID_STRATEGIES:
            weights = _optimize(price_matrix, strategy)
            for w in weights.values():
                assert w >= 0, f"{strategy}: negative weight {w}"

    def test_clean_weights_removes_tiny_positions(self, price_matrix):
        """clean_weights(cutoff=0.001) zeroes out tiny allocations."""
        weights = _optimize(price_matrix, "min_volatility")
        for w in weights.values():
            assert w == 0 or w >= 0.001


class TestEqualWeightFallback:
    """Tests for the equal-weight fallback."""

    def test_empty_positions(self):
        """No positions → empty list."""
        assert _equal_weight_fallback([], "min_volatility") == []

    def test_equal_weights(self):
        """3 positions → each gets 1/3 target weight."""
        positions = []
        for ticker in ["AAPL", "MSFT", "GOOGL"]:
            p = MagicMock()
            p.ticker = ticker
            p.shares = 10
            p.market_value = 1000.0
            positions.append(p)

        result = _equal_weight_fallback(positions, "min_volatility")
        assert len(result) == 3
        for s in result:
            assert s["target_weight"] == pytest.approx(1 / 3, abs=0.001)
            assert s["strategy"] == "min_volatility"

    def test_action_computed_correctly(self):
        """Under-weight → BUY_MORE, over-weight → REDUCE."""
        p1 = MagicMock(ticker="AAPL", shares=10, market_value=500.0)
        p2 = MagicMock(ticker="MSFT", shares=10, market_value=1500.0)

        result = _equal_weight_fallback([p1, p2], "max_sharpe")
        actions = {s["ticker"]: s["action"] for s in result}
        assert actions["AAPL"] == "BUY_MORE"
        assert actions["MSFT"] == "REDUCE"


class TestComputeRebalancing:
    """Tests for compute_rebalancing() with mocked DB."""

    @pytest.mark.asyncio
    async def test_single_position_returns_fallback(self):
        """With only 1 position, falls back to equal-weight."""
        db = AsyncMock()
        p = MagicMock(ticker="AAPL", shares=10, market_value=1000.0)

        with patch(
            "backend.services.portfolio.analytics.get_positions_with_pnl",
            return_value=[p],
        ):
            result = await compute_rebalancing(uuid4(), "min_volatility", db)

        assert len(result) == 1
        assert result[0]["target_weight"] == 1.0

    @pytest.mark.asyncio
    async def test_no_positions_returns_fallback(self):
        """No positions → empty list."""
        db = AsyncMock()
        with patch(
            "backend.services.portfolio.analytics.get_positions_with_pnl",
            return_value=[],
        ):
            result = await compute_rebalancing(uuid4(), "min_volatility", db)

        assert result == []


class TestValidStrategies:
    """Tests for strategy validation."""

    def test_valid_strategies_tuple(self):
        """All three strategies are defined."""
        assert "min_volatility" in VALID_STRATEGIES
        assert "max_sharpe" in VALID_STRATEGIES
        assert "risk_parity" in VALID_STRATEGIES
        assert len(VALID_STRATEGIES) == 3
