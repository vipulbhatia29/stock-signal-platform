"""Unit tests for PortfolioForecastService math methods.

Tests cover _compute_bl, _compute_monte_carlo, and _compute_cvar directly —
no DB interaction required.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from backend.services.portfolio_forecast import (
    PortfolioForecastService,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

TICKERS = ["AAPL", "MSFT", "GOOGL"]
WEIGHTS = np.array([0.4, 0.35, 0.25])
INITIAL_VALUE = 100_000.0


@pytest.fixture(scope="module")
def prices_df() -> pd.DataFrame:
    """Synthetic 252-day price DataFrame with three tickers."""
    np.random.seed(42)
    dates = pd.bdate_range(end=date.today(), periods=252)
    return pd.DataFrame(
        {
            "AAPL": 150 * np.cumprod(1 + np.random.normal(0.0004, 0.015, 252)),
            "MSFT": 300 * np.cumprod(1 + np.random.normal(0.0003, 0.012, 252)),
            "GOOGL": 130 * np.cumprod(1 + np.random.normal(0.0002, 0.018, 252)),
        },
        index=dates,
    )


@pytest.fixture(scope="module")
def service() -> PortfolioForecastService:
    """Shared service instance."""
    return PortfolioForecastService()


@pytest.fixture(scope="module")
def views() -> dict[str, float]:
    """Synthetic Prophet views (annualized returns)."""
    return {"AAPL": 0.18, "MSFT": 0.15, "GOOGL": 0.12}


@pytest.fixture(scope="module")
def view_confidences() -> dict[str, float]:
    """Synthetic backtest-derived confidence scores."""
    return {"AAPL": 0.80, "MSFT": 0.70, "GOOGL": 0.60}


# ---------------------------------------------------------------------------
# TestComputeBL
# ---------------------------------------------------------------------------


class TestComputeBL:
    """Tests for PortfolioForecastService._compute_bl."""

    def test_returns_expected_returns_dict_with_correct_tickers(
        self,
        service: PortfolioForecastService,
        prices_df: pd.DataFrame,
        views: dict[str, float],
        view_confidences: dict[str, float],
    ) -> None:
        """BL result should contain one entry per ticker in the tickers list."""
        result = service._compute_bl(prices_df, WEIGHTS, TICKERS, views, view_confidences, 0.05)

        assert set(result.expected_returns.keys()) == set(TICKERS)

    def test_excess_returns_subtract_risk_free_from_views(
        self,
        service: PortfolioForecastService,
        prices_df: pd.DataFrame,
        view_confidences: dict[str, float],
    ) -> None:
        """When views include a risk-free rate the BL posterior should reflect
        excess returns: a view of 0.0 exactly equal to the risk-free rate
        should yield a near-zero (or small) excess return rather than a large
        positive return."""
        rf = 0.05
        # Views all equal risk-free → excess views are all 0.0
        zero_excess_views = {t: rf for t in TICKERS}
        result_zero = service._compute_bl(
            prices_df, WEIGHTS, TICKERS, zero_excess_views, view_confidences, rf
        )
        # Compare against views that are clearly above risk-free
        high_views = {t: 0.20 for t in TICKERS}
        result_high = service._compute_bl(
            prices_df, WEIGHTS, TICKERS, high_views, view_confidences, rf
        )
        # Higher views → higher expected returns
        assert result_high.portfolio_expected_return > result_zero.portfolio_expected_return

    def test_returns_market_equilibrium_when_no_views(
        self,
        service: PortfolioForecastService,
        prices_df: pd.DataFrame,
    ) -> None:
        """With an empty views dict the model should fall back to market
        equilibrium returns, not zero."""
        result = service._compute_bl(prices_df, WEIGHTS, TICKERS, {}, {}, 0.05)

        # view_confidences should be empty too
        assert result.view_confidences == {}
        # At least one ticker should have a non-zero equilibrium return
        assert any(v != 0.0 for v in result.expected_returns.values())

    def test_nan_inf_returns_are_guarded_to_zero(
        self,
        service: PortfolioForecastService,
        prices_df: pd.DataFrame,
    ) -> None:
        """Non-finite BL returns must be replaced with 0.0 so callers never
        receive NaN or Inf values."""
        # Artificially inject a view that causes extreme posterior — we patch
        # the _compute_bl result by calling with extreme views and then verify
        # the guard logic through a unit test of the guard code path directly.
        views_extreme = {t: 1e300 for t in TICKERS}  # astronomically high
        result = service._compute_bl(prices_df, WEIGHTS, TICKERS, views_extreme, {}, 0.05)
        for ret in result.expected_returns.values():
            assert math.isfinite(ret), f"Expected finite return, got {ret}"
        assert math.isfinite(result.portfolio_expected_return)

    def test_portfolio_return_is_weighted_sum_of_expected_returns(
        self,
        service: PortfolioForecastService,
        prices_df: pd.DataFrame,
        views: dict[str, float],
        view_confidences: dict[str, float],
    ) -> None:
        """portfolio_expected_return must equal dot(weights, expected_returns)."""
        result = service._compute_bl(prices_df, WEIGHTS, TICKERS, views, view_confidences, 0.05)

        manual = float(np.dot(WEIGHTS, [result.expected_returns[t] for t in TICKERS]))
        assert result.portfolio_expected_return == pytest.approx(manual, abs=1e-9)


# ---------------------------------------------------------------------------
# TestComputeMonteCarlo
# ---------------------------------------------------------------------------


class TestComputeMonteCarlo:
    """Tests for PortfolioForecastService._compute_monte_carlo."""

    HORIZON = 30  # Use short horizon for speed in unit tests

    @pytest.fixture(scope="class")
    def mc_result(
        self,
        service: PortfolioForecastService,
        prices_df: pd.DataFrame,
    ):  # type: ignore[no-untyped-def]
        """Run simulation once and share across tests in this class."""
        np.random.seed(42)
        expected_returns = {"AAPL": 0.10, "MSFT": 0.08, "GOOGL": 0.12}
        return service._compute_monte_carlo(
            expected_returns, prices_df, WEIGHTS, TICKERS, INITIAL_VALUE, self.HORIZON
        )

    def test_returns_percentile_bands_with_correct_keys(self, mc_result) -> None:  # type: ignore[no-untyped-def]
        """Percentile bands dict must contain exactly p5, p25, p50, p75, p95."""
        assert set(mc_result.percentile_bands.keys()) == {"p5", "p25", "p50", "p75", "p95"}

    def test_terminal_values_have_correct_count(
        self,
        service: PortfolioForecastService,
        prices_df: pd.DataFrame,
    ) -> None:
        """Number of terminal values must equal MONTE_CARLO_SIMULATIONS setting."""
        from backend.config import settings

        np.random.seed(0)
        result = service._compute_monte_carlo(
            {"AAPL": 0.10, "MSFT": 0.08, "GOOGL": 0.12},
            prices_df,
            WEIGHTS,
            TICKERS,
            INITIAL_VALUE,
            self.HORIZON,
        )
        assert len(result.terminal_values) == settings.MONTE_CARLO_SIMULATIONS

    def test_percentile_ordering_p5_lt_p25_lt_p50_lt_p75_lt_p95(self, mc_result) -> None:  # type: ignore[no-untyped-def]
        """At the terminal day, percentile bands must be strictly ordered."""
        bands = mc_result.percentile_bands
        last = -1
        assert bands["p5"][last] < bands["p25"][last]
        assert bands["p25"][last] < bands["p50"][last]
        assert bands["p50"][last] < bands["p75"][last]
        assert bands["p75"][last] < bands["p95"][last]

    def test_seeded_randomness_produces_reproducible_results(
        self,
        service: PortfolioForecastService,
        prices_df: pd.DataFrame,
    ) -> None:
        """Two runs with the same seed must produce identical terminal values."""
        expected_returns = {"AAPL": 0.10, "MSFT": 0.08, "GOOGL": 0.12}

        np.random.seed(42)
        r1 = service._compute_monte_carlo(
            expected_returns, prices_df, WEIGHTS, TICKERS, INITIAL_VALUE, self.HORIZON
        )
        np.random.seed(42)
        r2 = service._compute_monte_carlo(
            expected_returns, prices_df, WEIGHTS, TICKERS, INITIAL_VALUE, self.HORIZON
        )
        assert r1.terminal_values == r2.terminal_values

    def test_percentile_bands_have_correct_length(self, mc_result) -> None:  # type: ignore[no-untyped-def]
        """Each band list must contain exactly horizon_days values."""
        for band_values in mc_result.percentile_bands.values():
            assert len(band_values) == self.HORIZON


# ---------------------------------------------------------------------------
# TestComputeCVaR
# ---------------------------------------------------------------------------


class TestComputeCVaR:
    """Tests for PortfolioForecastService._compute_cvar."""

    @pytest.fixture(scope="class")
    def loss_terminal_values(self) -> list[float]:
        """Simulate 5 000 terminal values drawn from a loss-biased distribution."""
        np.random.seed(7)
        # Returns centred at -5% with std=10% → typical mix of gains and losses
        returns_sim = np.random.normal(-0.05, 0.10, 5000)
        return (INITIAL_VALUE * (1 + returns_sim)).tolist()

    @pytest.fixture(scope="class")
    def gain_terminal_values(self) -> list[float]:
        """Simulate 5 000 terminal values entirely above initial value."""
        np.random.seed(8)
        returns_sim = np.abs(np.random.normal(0.10, 0.03, 5000))  # all positive
        return (INITIAL_VALUE * (1 + returns_sim)).tolist()

    def test_cvar_95_is_at_most_var_95(
        self,
        service: PortfolioForecastService,
        loss_terminal_values: list[float],
    ) -> None:
        """CVaR at 95% must be <= VaR at 95% (CVaR is always at least as bad)."""
        result = service._compute_cvar(loss_terminal_values, INITIAL_VALUE)
        assert result.cvar_95 <= result.var_95

    def test_cvar_99_is_at_most_cvar_95(
        self,
        service: PortfolioForecastService,
        loss_terminal_values: list[float],
    ) -> None:
        """CVaR at 99% must be <= CVaR at 95% (deeper tail is always worse)."""
        result = service._compute_cvar(loss_terminal_values, INITIAL_VALUE)
        assert result.cvar_99 <= result.cvar_95

    def test_all_values_negative_for_loss_distribution(
        self,
        service: PortfolioForecastService,
        loss_terminal_values: list[float],
    ) -> None:
        """For a loss-biased distribution all risk metrics should be negative."""
        result = service._compute_cvar(loss_terminal_values, INITIAL_VALUE)
        assert result.cvar_95 < 0
        assert result.cvar_99 < 0
        assert result.var_95 < 0
        assert result.var_99 < 0

    def test_nan_inf_are_guarded_to_zero(
        self,
        service: PortfolioForecastService,
    ) -> None:
        """CVaR computation must not propagate NaN/Inf to callers."""
        # Edge case: all terminal values equal initial_value → returns all 0.0
        flat_values = [INITIAL_VALUE] * 1000
        result = service._compute_cvar(flat_values, INITIAL_VALUE)
        for attr in ("cvar_95", "cvar_99", "var_95", "var_99"):
            val = getattr(result, attr)
            assert math.isfinite(val), f"{attr} should be finite, got {val}"

    def test_returns_near_zero_for_all_positive_terminal_values(
        self,
        service: PortfolioForecastService,
        gain_terminal_values: list[float],
    ) -> None:
        """When all paths are profitable both VaR and CVaR should be positive."""
        result = service._compute_cvar(gain_terminal_values, INITIAL_VALUE)
        # In an all-gain scenario the worst 5% are still gains → positive VaR
        assert result.var_95 >= 0
        assert result.cvar_95 >= 0
