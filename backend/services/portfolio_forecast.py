"""Portfolio forecast — Black-Litterman, Monte Carlo simulation, CVaR.

Uses PyPortfolioOpt for BL and Ledoit-Wolf covariance. Monte Carlo uses
Cholesky decomposition for correlated random walks.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings

logger = logging.getLogger(__name__)

TRADING_DAYS = 252


@dataclass
class BLResult:
    """Black-Litterman computation result."""

    expected_returns: dict[str, float]  # ticker -> annualized return as decimal
    portfolio_expected_return: float
    view_confidences: dict[str, float]  # ticker -> 0.0-0.95, absent if no Prophet view
    risk_free_rate: float


@dataclass
class MonteCarloResult:
    """Monte Carlo simulation result."""

    percentile_bands: dict[str, list[float]]  # keys: p5, p25, p50, p75, p95
    terminal_values: list[float]  # raw terminal portfolio values per path
    simulation_days: int
    initial_value: float


@dataclass
class CVaRResult:
    """Conditional Value at Risk result."""

    cvar_95: float  # expected loss in worst 5% scenarios (negative decimal, e.g. -0.12)
    cvar_99: float  # expected loss in worst 1% scenarios
    var_95: float  # Value at Risk at 95% confidence
    var_99: float  # Value at Risk at 99% confidence


@dataclass
class PortfolioForecastResult:
    """Full portfolio forecast result returned by PortfolioForecastService."""

    bl: BLResult
    monte_carlo: MonteCarloResult
    cvar: CVaRResult
    forecast_date: date
    horizon_days: int
    tickers: list[str] = field(default_factory=list)


class PortfolioForecastService:
    """Computes portfolio-level forecasts using BL + Monte Carlo + CVaR."""

    async def compute_forecast(
        self,
        portfolio_id: str,
        db: AsyncSession,
        horizon_days: int = 90,
    ) -> PortfolioForecastResult:
        """Compute full portfolio forecast.

        Args:
            portfolio_id: UUID of the portfolio.
            db: Async database session.
            horizon_days: Forecast horizon in trading days.

        Returns:
            PortfolioForecastResult with BL, Monte Carlo, and CVaR.

        Raises:
            ValueError: If the portfolio has no active positions or no price data.
        """
        # 1. Fetch portfolio positions + weights
        positions = await self._fetch_positions(portfolio_id, db)
        if not positions:
            raise ValueError("Portfolio has no active positions")

        tickers = list(positions.keys())
        weights = np.array(list(positions.values()))

        logger.info(
            "Computing forecast for portfolio %s, %d tickers, %d days",
            portfolio_id,
            len(tickers),
            horizon_days,
        )

        # 2. Fetch historical prices (252 trading days)
        prices_df = await self._fetch_prices(tickers, db)

        # 3. Get Prophet views + backtest MAPE for confidence
        views, view_confidences = await self._fetch_model_views(tickers, db)

        # 4. Get risk-free rate
        risk_free_rate = await self._fetch_risk_free_rate(db)

        # 5. Black-Litterman
        bl_result = self._compute_bl(
            prices_df, weights, tickers, views, view_confidences, risk_free_rate
        )

        # 6. Monte Carlo
        portfolio_value = await self._fetch_portfolio_value(portfolio_id, db)
        mc_result = self._compute_monte_carlo(
            bl_result.expected_returns,
            prices_df,
            weights,
            tickers,
            portfolio_value,
            horizon_days,
        )

        # 7. CVaR from Monte Carlo terminal values
        cvar_result = self._compute_cvar(mc_result.terminal_values, portfolio_value)

        return PortfolioForecastResult(
            bl=bl_result,
            monte_carlo=mc_result,
            cvar=cvar_result,
            forecast_date=datetime.now(timezone.utc).date(),
            horizon_days=horizon_days,
            tickers=tickers,
        )

    def _compute_bl(
        self,
        prices_df: pd.DataFrame,
        weights: np.ndarray,
        tickers: list[str],
        views: dict[str, float],
        view_confidences: dict[str, float],
        risk_free_rate: float,
    ) -> BLResult:
        """Compute Black-Litterman expected returns.

        Uses PyPortfolioOpt's BlackLittermanModel with:
        - Ledoit-Wolf shrinkage covariance
        - Views as Prophet predicted excess returns (subtract risk-free)
        - Confidence = min(0.95, max(0.1, 1.0 - backtest_mape))

        Args:
            prices_df: Historical adjusted close prices (rows=dates, cols=tickers).
            weights: Portfolio weights aligned with tickers list.
            tickers: List of ticker symbols.
            views: Dict of ticker → annualized predicted return.
            view_confidences: Dict of ticker → confidence in [0.1, 0.95].
            risk_free_rate: Annual risk-free rate as decimal.

        Returns:
            BLResult with expected returns and portfolio return.
        """
        from pypfopt import BlackLittermanModel, risk_models
        from pypfopt.expected_returns import mean_historical_return

        # Covariance via Ledoit-Wolf shrinkage
        cov_matrix = risk_models.CovarianceShrinkage(prices_df).ledoit_wolf()

        # Market equilibrium returns (CAPM proxy via historical mean)
        market_returns = mean_historical_return(prices_df)

        # Convert Prophet views to excess returns
        excess_views: dict[str, float] = {}
        for ticker in tickers:
            if ticker in views:
                excess_views[ticker] = views[ticker] - risk_free_rate

        if not excess_views:
            # No views — return market equilibrium
            eq_returns = {t: float(market_returns.get(t, 0.0)) for t in tickers}
            portfolio_return = float(np.dot(weights, [eq_returns.get(t, 0.0) for t in tickers]))
            return BLResult(
                expected_returns=eq_returns,
                portfolio_expected_return=portfolio_return,
                view_confidences={},
                risk_free_rate=risk_free_rate,
            )

        # Build BL model with calibrated view confidences (Idzorek method)
        # Confidences are 0-1 values derived from backtest MAPE
        conf_list = [view_confidences.get(t, 0.5) for t in excess_views]
        bl = BlackLittermanModel(
            cov_matrix,
            pi=market_returns,
            absolute_views=excess_views,
            risk_aversion=settings.BL_RISK_AVERSION,
            omega="idzorek",
            view_confidences=conf_list,
        )
        bl_returns = bl.bl_returns()

        expected = {t: float(bl_returns.get(t, 0.0)) for t in tickers}
        portfolio_return = float(np.dot(weights, [expected.get(t, 0.0) for t in tickers]))

        # Guard NaN/Inf
        for t in list(expected.keys()):
            if not math.isfinite(expected[t]):
                logger.warning("Non-finite BL return for %s, defaulting to 0", t)
                expected[t] = 0.0
        if not math.isfinite(portfolio_return):
            portfolio_return = 0.0

        return BLResult(
            expected_returns=expected,
            portfolio_expected_return=portfolio_return,
            view_confidences=view_confidences,
            risk_free_rate=risk_free_rate,
        )

    def _compute_monte_carlo(
        self,
        expected_returns: dict[str, float],
        prices_df: pd.DataFrame,
        weights: np.ndarray,
        tickers: list[str],
        initial_value: float,
        horizon_days: int,
    ) -> MonteCarloResult:
        """Run Monte Carlo simulation with correlated random walks.

        Uses Cholesky decomposition for correlation. BL returns are
        annualized → daily (÷252). Volatility from covariance matrix.

        Args:
            expected_returns: Annualized BL expected returns per ticker.
            prices_df: Historical prices for covariance estimation.
            weights: Portfolio weights aligned with tickers list.
            tickers: List of ticker symbols.
            initial_value: Starting portfolio dollar value.
            horizon_days: Number of trading days to simulate.

        Returns:
            MonteCarloResult with percentile bands and terminal values.
        """
        n_sims = settings.MONTE_CARLO_SIMULATIONS
        n_assets = len(tickers)

        # Daily returns from prices
        daily_returns = prices_df.pct_change().dropna()

        # Daily drift from BL annualized returns
        daily_drift = np.array([expected_returns.get(t, 0.0) / TRADING_DAYS for t in tickers])

        # Daily covariance → Cholesky
        cov_daily = daily_returns.cov().values
        try:
            cholesky = np.linalg.cholesky(cov_daily)
        except np.linalg.LinAlgError:
            # Not positive definite — add small regularisation diagonal
            cov_daily = cov_daily + np.eye(n_assets) * 1e-6
            cholesky = np.linalg.cholesky(cov_daily)

        # Vectorised Monte Carlo: generate all random draws at once
        # cholesky @ z gives correlated returns with correct covariance (no extra vol scaling)
        # Shape: (n_sims, horizon_days, n_assets)
        rng = np.random.default_rng()
        z_all = rng.standard_normal((n_sims, horizon_days, n_assets))
        # Apply Cholesky to get correlated returns: (n_sims, horizon_days, n_assets)
        correlated = z_all @ cholesky.T  # broadcast: each (n_assets,) × cholesky.T
        daily_returns_sim = daily_drift + correlated  # add drift

        # Cumulative product along time axis for asset growth
        asset_growth = np.cumprod(1 + daily_returns_sim, axis=1)  # (n_sims, horizon_days, n_assets)
        # Portfolio value at each timestep: weighted sum of asset growth × initial value
        portfolio_paths = initial_value * (asset_growth @ weights)  # (n_sims, horizon_days)

        # Percentile bands (time series across simulations)
        percentile_bands: dict[str, list[float]] = {
            "p5": np.percentile(portfolio_paths, 5, axis=0).tolist(),
            "p25": np.percentile(portfolio_paths, 25, axis=0).tolist(),
            "p50": np.percentile(portfolio_paths, 50, axis=0).tolist(),
            "p75": np.percentile(portfolio_paths, 75, axis=0).tolist(),
            "p95": np.percentile(portfolio_paths, 95, axis=0).tolist(),
        }

        # Terminal values (last day of each simulation)
        terminal_values: list[float] = portfolio_paths[:, -1].tolist()

        return MonteCarloResult(
            percentile_bands=percentile_bands,
            terminal_values=terminal_values,
            simulation_days=horizon_days,
            initial_value=initial_value,
        )

    def _compute_cvar(self, terminal_values: list[float], initial_value: float) -> CVaRResult:
        """Compute CVaR from Monte Carlo terminal values.

        Args:
            terminal_values: Terminal portfolio values from simulation.
            initial_value: Starting portfolio value.

        Returns:
            CVaRResult with 95% and 99% levels as percentage losses.
        """
        returns = np.array([(tv - initial_value) / initial_value for tv in terminal_values])

        # VaR: percentile cutoff of the return distribution
        var_95 = float(np.percentile(returns, 5))  # 5th percentile of returns
        var_99 = float(np.percentile(returns, 1))  # 1st percentile

        # CVaR: mean of returns at or below VaR threshold
        below_95 = returns[returns <= var_95]
        below_99 = returns[returns <= var_99]

        cvar_95 = float(np.mean(below_95)) if len(below_95) > 0 else var_95
        cvar_99 = float(np.mean(below_99)) if len(below_99) > 0 else var_99

        def _safe(val: float, name: str) -> float:
            if not math.isfinite(val):
                logger.warning("Non-finite %s, defaulting to 0", name)
                return 0.0
            return val

        return CVaRResult(
            cvar_95=_safe(cvar_95, "cvar_95"),
            cvar_99=_safe(cvar_99, "cvar_99"),
            var_95=_safe(var_95, "var_95"),
            var_99=_safe(var_99, "var_99"),
        )

    # ── Data fetching helpers ──────────────────────────────────────────────

    async def _fetch_positions(self, portfolio_id: str, db: AsyncSession) -> dict[str, float]:
        """Fetch positions and compute weights by market value proportion.

        Args:
            portfolio_id: UUID of the portfolio.
            db: Async database session.

        Returns:
            Dict of ticker → weight summing to 1.0, or empty dict if no positions.
        """
        from backend.models.portfolio import Position

        result = await db.execute(
            select(Position).where(
                Position.portfolio_id == portfolio_id,
                Position.quantity > 0,
            )
        )
        positions = result.scalars().all()
        if not positions:
            return {}

        # Weight by market value (quantity × avg_cost_basis as proxy)
        total_value = sum(float(p.quantity) * float(p.avg_cost_basis or 0) for p in positions)
        if total_value <= 0:
            return {}

        return {
            p.ticker: (float(p.quantity) * float(p.avg_cost_basis or 0)) / total_value
            for p in positions
        }

    async def _fetch_prices(self, tickers: list[str], db: AsyncSession) -> pd.DataFrame:
        """Fetch 252 trading days of adjusted close prices.

        Args:
            tickers: List of ticker symbols.
            db: Async database session.

        Returns:
            DataFrame with dates as index and tickers as columns.

        Raises:
            ValueError: If no price data is available.
        """
        from backend.models.price import StockPrice

        lookback_start = datetime.now(timezone.utc).date() - timedelta(days=400)
        since = datetime.combine(lookback_start, datetime.min.time())
        result = await db.execute(
            select(StockPrice.ticker, StockPrice.time, StockPrice.adj_close)
            .where(
                StockPrice.ticker.in_(tickers),
                StockPrice.time >= since,
            )
            .order_by(StockPrice.time)
        )
        rows = result.all()
        if not rows:
            raise ValueError("No price data available for portfolio tickers")

        df = pd.DataFrame(rows, columns=["ticker", "date", "adj_close"])
        df["adj_close"] = df["adj_close"].astype(float)
        pivot = df.pivot_table(index="date", columns="ticker", values="adj_close")
        pivot = pivot.dropna(axis=0, how="any").tail(TRADING_DAYS)

        # Validate that all requested tickers survived the pivot + dropna.
        # A ticker is dropped when it has no price data in the lookback window
        # or when its prices have gaps that cause the row-wise dropna to remove
        # every date where it appeared.
        available = set(pivot.columns.tolist())
        missing = set(tickers) - available
        if missing:
            logger.warning(
                "Tickers dropped from price pivot (no data or gaps): %s — "
                "BL computation will proceed with %d/%d tickers",
                sorted(missing),
                len(available),
                len(tickers),
            )

        return pivot

    async def _fetch_model_views(
        self, tickers: list[str], db: AsyncSession
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Fetch model predicted returns and backtest MAPE for view confidence.

        Reads expected_return_pct directly from ForecastResult (return-based schema).
        Accepts any active model type (lightgbm, xgboost, prophet, etc.).
        Confidence = min(0.95, max(0.1, 1 - mape)).

        Args:
            tickers: List of ticker symbols.
            db: Async database session.

        Returns:
            Tuple of (views dict, confidence dict). Tickers without forecasts
            are omitted from both dicts.
        """
        from backend.models.backtest import BacktestRun
        from backend.models.forecast import ForecastResult, ModelVersion

        # 1. Bulk fetch active model versions (any model type)
        mv_result = await db.execute(
            select(ModelVersion)
            .distinct(ModelVersion.ticker)
            .where(
                ModelVersion.ticker.in_(tickers),
                ModelVersion.is_active.is_(True),
            )
            .order_by(ModelVersion.ticker, ModelVersion.trained_at.desc())
        )
        mv_by_ticker = {mv.ticker: mv for mv in mv_result.scalars().all()}
        if not mv_by_ticker:
            return {}, {}

        mv_ids = [mv.id for mv in mv_by_ticker.values()]

        # 2. Bulk fetch latest 90-day forecasts for those model versions
        fr_result = await db.execute(
            select(ForecastResult)
            .distinct(ForecastResult.ticker)
            .where(
                ForecastResult.model_version_id.in_(mv_ids),
                ForecastResult.horizon_days == 90,
            )
            .order_by(ForecastResult.ticker, ForecastResult.forecast_date.desc())
        )
        fc_by_ticker = {fc.ticker: fc for fc in fr_result.scalars().all()}

        # 3. Bulk fetch latest backtest MAPE
        bt_result = await db.execute(
            select(BacktestRun.ticker, BacktestRun.mape)
            .distinct(BacktestRun.ticker)
            .where(BacktestRun.ticker.in_(tickers))
            .order_by(BacktestRun.ticker, BacktestRun.created_at.desc())
        )
        mape_by_ticker = {
            row.ticker: float(row.mape) for row in bt_result.all() if row.mape is not None
        }

        # 4. Compute views and confidences in Python
        views: dict[str, float] = {}
        confidences: dict[str, float] = {}

        for ticker in tickers:
            forecast = fc_by_ticker.get(ticker)
            if forecast is None:
                continue

            predicted_return = float(forecast.expected_return_pct) / 100.0
            annualized = (1 + predicted_return) ** (TRADING_DAYS / 90) - 1
            views[ticker] = annualized

            mape = mape_by_ticker.get(ticker)
            confidences[ticker] = min(0.95, max(0.1, 1.0 - mape)) if mape is not None else 0.5

        return views, confidences

    async def _fetch_risk_free_rate(self, db: AsyncSession) -> float:  # noqa: ARG002
        """Return the current risk-free rate.

        Returns a default of 5% until a macro-data ingestion pipeline is wired
        up to supply live DFF values.

        Args:
            db: Async database session (reserved for future macro lookup).

        Returns:
            Annualised risk-free rate as a decimal (e.g. 0.05 for 5%).
        """
        return 0.05  # Default 5%

    async def _fetch_portfolio_value(self, portfolio_id: str, db: AsyncSession) -> float:
        """Fetch current portfolio market value from the latest snapshot.

        Args:
            portfolio_id: UUID of the portfolio.
            db: Async database session.

        Returns:
            Portfolio total value in dollars. Defaults to $10 000 if no
            snapshot is found.
        """
        from backend.models.portfolio import PortfolioSnapshot

        result = await db.execute(
            select(PortfolioSnapshot.total_value)
            .where(PortfolioSnapshot.portfolio_id == portfolio_id)
            .order_by(PortfolioSnapshot.snapshot_date.desc())
            .limit(1)
        )
        value = result.scalar_one_or_none()
        return float(value) if value else 10_000.0  # Default $10K
