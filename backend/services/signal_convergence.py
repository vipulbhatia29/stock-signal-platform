"""Service layer for signal convergence — bulk queries, divergence detection, hit rates."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.convergence import SignalConvergenceDaily
from backend.models.forecast import ForecastResult
from backend.models.news_sentiment import NewsSentimentDaily
from backend.models.portfolio import Position
from backend.models.signal import SignalSnapshot
from backend.models.stock import Stock
from backend.tasks.convergence import (
    _classify_forecast,
    _classify_macd,
    _classify_piotroski,
    _classify_rsi,
    _classify_sma,
    _compute_convergence_label,
)

logger = logging.getLogger(__name__)

# News sentiment thresholds (from spec)
_NEWS_BULLISH_THRESHOLD = 0.3
_NEWS_BEARISH_THRESHOLD = -0.3


def classify_news_sentiment(sentiment: float | None) -> str:
    """Classify news sentiment direction.

    Args:
        sentiment: Aggregated daily sentiment score (-1.0 to 1.0) or None.

    Returns:
        'bullish' if >+0.3, 'bearish' if <-0.3, else 'neutral'.
    """
    if sentiment is None:
        return "neutral"
    if sentiment > _NEWS_BULLISH_THRESHOLD:
        return "bullish"
    if sentiment < _NEWS_BEARISH_THRESHOLD:
        return "bearish"
    return "neutral"


@dataclass
class SignalDirection:
    """Direction + raw value for one signal."""

    signal: str
    direction: str
    value: float | None = None


@dataclass
class DivergenceInfo:
    """Divergence detection result."""

    is_divergent: bool = False
    forecast_direction: str | None = None
    technical_majority: str | None = None
    historical_hit_rate: float | None = None
    sample_count: int | None = None


@dataclass
class TickerConvergence:
    """Full convergence result for a single ticker."""

    ticker: str
    date: date
    signals: list[SignalDirection] = field(default_factory=list)
    signals_aligned: int = 0
    convergence_label: str = "mixed"
    composite_score: float | None = None
    divergence: DivergenceInfo = field(default_factory=DivergenceInfo)


class SignalConvergenceService:
    """Computes convergence state from latest signals, forecasts, and sentiment.

    Designed for bulk queries — fetches all required data in batched SQL,
    then classifies in Python. No N+1 queries.
    """

    async def get_ticker_convergence(
        self,
        ticker: str,
        db: AsyncSession,
    ) -> TickerConvergence | None:
        """Get convergence for a single ticker.

        Args:
            ticker: Stock ticker symbol (uppercase).
            db: Async database session.

        Returns:
            TickerConvergence or None if no signal data exists.
        """
        results = await self.get_bulk_convergence([ticker], db)
        return results.get(ticker)

    async def get_bulk_convergence(
        self,
        tickers: list[str],
        db: AsyncSession,
    ) -> dict[str, TickerConvergence]:
        """Get convergence for multiple tickers in a single bulk query.

        Args:
            tickers: List of ticker symbols (uppercase).
            db: Async database session.

        Returns:
            Dict of ticker → TickerConvergence for tickers with signal data.
        """
        if not tickers:
            return {}

        # 1. Bulk fetch latest signals (one query, DISTINCT ON)
        signals_by_ticker = await self._fetch_latest_signals(tickers, db)

        # 2. Bulk fetch latest sentiment (one query)
        sentiment_by_ticker = await self._fetch_latest_sentiment(tickers, db)

        # 3. Bulk fetch latest 90-day forecast (one query)
        forecast_by_ticker = await self._fetch_latest_forecasts(tickers, db)

        # 4. Bulk fetch previous MACD histogram for rising/falling detection
        prev_macd_by_ticker = await self._fetch_prev_macd(tickers, db)

        # 5. Classify and compute for each ticker
        results: dict[str, TickerConvergence] = {}
        for ticker in tickers:
            signal = signals_by_ticker.get(ticker)
            if signal is None:
                continue

            sentiment_row = sentiment_by_ticker.get(ticker)
            news_sentiment_val = sentiment_row.stock_sentiment if sentiment_row else None

            forecast_row = forecast_by_ticker.get(ticker)
            prev_macd = prev_macd_by_ticker.get(ticker)
            convergence = self._compute_convergence(
                ticker, signal, news_sentiment_val, forecast_row, prev_macd
            )
            results[ticker] = convergence

        return results

    async def get_portfolio_convergence(
        self,
        portfolio_id: str,
        db: AsyncSession,
    ) -> list[tuple[TickerConvergence, float]]:
        """Get convergence for all positions in a portfolio.

        Args:
            portfolio_id: UUID of the portfolio.
            db: Async database session.

        Returns:
            List of (TickerConvergence, weight) tuples.
        """
        # Fetch positions with weights
        positions = await self._fetch_portfolio_positions(portfolio_id, db)
        if not positions:
            return []

        tickers = list(positions.keys())
        convergences = await self.get_bulk_convergence(tickers, db)

        return [(convergences[t], w) for t, w in positions.items() if t in convergences]

    async def get_sector_convergence(
        self,
        sector: str,
        db: AsyncSession,
    ) -> list[TickerConvergence]:
        """Get convergence for all active tickers in a sector.

        Uses equal-weight aggregation (each ticker counts equally).

        Args:
            sector: Sector name (e.g. "Technology").
            db: Async database session.

        Returns:
            List of TickerConvergence for tickers in the sector.
        """
        # Fetch tickers in this sector
        stmt = select(Stock.ticker).where(
            Stock.sector == sector,
            Stock.is_active.is_(True),
        )
        result = await db.execute(stmt)
        tickers = [row[0] for row in result.all()]
        if not tickers:
            return []

        convergences = await self.get_bulk_convergence(tickers, db)
        return list(convergences.values())

    async def get_convergence_history(
        self,
        ticker: str,
        db: AsyncSession,
        days: int = 90,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SignalConvergenceDaily], int]:
        """Get historical convergence data for a ticker.

        Args:
            ticker: Stock ticker symbol (uppercase).
            db: Async database session.
            days: Look-back window in calendar days.
            limit: Page size.
            offset: Page offset.

        Returns:
            Tuple of (rows, total_count).
        """
        since = date.today() - timedelta(days=days)
        base_filter = [
            SignalConvergenceDaily.ticker == ticker,
            SignalConvergenceDaily.date >= since,
        ]

        # Count
        count_stmt = select(func.count()).select_from(SignalConvergenceDaily).where(*base_filter)
        total = (await db.execute(count_stmt)).scalar() or 0

        # Data
        data_stmt = (
            select(SignalConvergenceDaily)
            .where(*base_filter)
            .order_by(SignalConvergenceDaily.date.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await db.execute(data_stmt)).scalars().all()
        return list(rows), total

    async def compute_divergence_hit_rate(
        self,
        ticker: str,
        forecast_direction: str,
        technical_majority: str,
        db: AsyncSession,
    ) -> tuple[float | None, int]:
        """Compute historical hit rate for a specific divergence pattern.

        Finds past cases where the forecast direction disagreed with the
        technical majority in the same way, and checks how often the
        forecast was correct (using actual_return_90d).

        Args:
            ticker: Stock ticker to check.
            forecast_direction: The forecast's direction ('bullish' or 'bearish').
            technical_majority: The technical majority direction.
            db: Async database session.

        Returns:
            Tuple of (hit_rate, sample_count). hit_rate is None if no samples.
        """
        # Find historical rows where the same divergence occurred
        stmt = select(SignalConvergenceDaily).where(
            SignalConvergenceDaily.ticker == ticker,
            SignalConvergenceDaily.forecast_direction == forecast_direction,
            SignalConvergenceDaily.convergence_label.in_(
                self._labels_for_direction(technical_majority)
            ),
            SignalConvergenceDaily.actual_return_90d.is_not(None),
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            return None, 0

        # Forecast was "right" if the actual return aligned with forecast direction
        correct = 0
        for row in rows:
            actual = row.actual_return_90d
            if actual is None:
                continue
            if forecast_direction == "bullish" and actual > 0:
                correct += 1
            elif forecast_direction == "bearish" and actual < 0:
                correct += 1

        sample_count = len(rows)
        hit_rate = correct / sample_count if sample_count > 0 else None
        return hit_rate, sample_count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_convergence(
        self,
        ticker: str,
        signal: SignalSnapshot,
        news_sentiment: float | None,
        forecast: ForecastResult | None = None,
        prev_macd_histogram: float | None = None,
    ) -> TickerConvergence:
        """Classify all signals and compute convergence for one ticker.

        Args:
            ticker: Stock ticker.
            signal: Latest SignalSnapshot row.
            news_sentiment: Daily aggregated sentiment or None.
            forecast: Latest 90-day ForecastResult or None.
            prev_macd_histogram: Previous day's MACD histogram for rising/falling.

        Returns:
            TickerConvergence with all fields populated.
        """
        # Extract piotroski from composite_weights JSONB (stored during signal computation)
        # JSONB numbers may deserialize as float — cast to int explicitly
        weights = signal.composite_weights or {}
        raw_pio = weights.get("piotroski")
        piotroski_score: int | None = int(raw_pio) if raw_pio is not None else None

        # Compute forecast predicted return from ForecastResult
        predicted_return: float | None = None
        if forecast and signal.current_price and signal.current_price > 0:
            predicted_return = (forecast.predicted_price / signal.current_price) - 1.0

        # Classify each signal
        rsi_dir = _classify_rsi(signal.rsi_value)
        macd_dir = _classify_macd(signal.macd_histogram, prev_macd_histogram)
        sma_dir = _classify_sma(signal.current_price, signal.sma_200)
        piotroski_dir = _classify_piotroski(piotroski_score)
        forecast_dir = _classify_forecast(predicted_return)
        news_dir = classify_news_sentiment(news_sentiment)

        directions_list = [
            SignalDirection("rsi", rsi_dir, signal.rsi_value),
            SignalDirection("macd", macd_dir, signal.macd_histogram),
            SignalDirection("sma", sma_dir, signal.sma_200),
            SignalDirection("piotroski", piotroski_dir, piotroski_score),
            SignalDirection("forecast", forecast_dir, predicted_return),
            SignalDirection("news", news_dir, news_sentiment),
        ]

        raw_dirs = [d.direction for d in directions_list]
        label = _compute_convergence_label(raw_dirs)

        # Count aligned signals (max of bullish or bearish count)
        bullish_count = raw_dirs.count("bullish")
        bearish_count = raw_dirs.count("bearish")
        aligned = max(bullish_count, bearish_count)

        # Detect divergence (forecast vs technical majority)
        # Technical majority = direction with most non-forecast, non-news signals
        tech_dirs = [d.direction for d in directions_list if d.signal not in ("forecast", "news")]
        tech_bullish = tech_dirs.count("bullish")
        tech_bearish = tech_dirs.count("bearish")

        if tech_bullish > tech_bearish:
            tech_majority = "bullish"
        elif tech_bearish > tech_bullish:
            tech_majority = "bearish"
        else:
            tech_majority = "neutral"

        divergence = DivergenceInfo()
        if (
            forecast_dir != "neutral"
            and tech_majority != "neutral"
            and forecast_dir != tech_majority
        ):
            divergence = DivergenceInfo(
                is_divergent=True,
                forecast_direction=forecast_dir,
                technical_majority=tech_majority,
            )

        return TickerConvergence(
            ticker=ticker,
            date=date.today(),
            signals=directions_list,
            signals_aligned=aligned,
            convergence_label=label,
            composite_score=signal.composite_score,
            divergence=divergence,
        )

    @staticmethod
    def _labels_for_direction(direction: str) -> list[str]:
        """Map a direction to convergence labels that represent it.

        Args:
            direction: 'bullish' or 'bearish'.

        Returns:
            List of convergence labels indicating that direction is dominant.
        """
        if direction == "bullish":
            return ["strong_bull", "weak_bull"]
        if direction == "bearish":
            return ["strong_bear", "weak_bear"]
        return ["mixed"]

    async def _fetch_latest_signals(
        self,
        tickers: list[str],
        db: AsyncSession,
    ) -> dict[str, SignalSnapshot]:
        """Bulk-fetch latest SignalSnapshot per ticker using DISTINCT ON.

        Uses PostgreSQL DISTINCT ON to get the most recent snapshot per ticker
        in a single query without fragile subquery-to-ORM mapping.

        Args:
            tickers: List of ticker symbols.
            db: Async database session.

        Returns:
            Dict of ticker → SignalSnapshot.
        """
        stmt = (
            select(SignalSnapshot)
            .distinct(SignalSnapshot.ticker)
            .where(SignalSnapshot.ticker.in_(tickers))
            .order_by(SignalSnapshot.ticker, SignalSnapshot.computed_at.desc())
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        return {row.ticker: row for row in rows}

    async def _fetch_prev_macd(
        self,
        tickers: list[str],
        db: AsyncSession,
    ) -> dict[str, float]:
        """Bulk-fetch 2nd-latest MACD histogram per ticker for rising/falling.

        Uses a window function to get row_number=2 (previous snapshot).

        Args:
            tickers: List of ticker symbols.
            db: Async database session.

        Returns:
            Dict of ticker → previous MACD histogram value.
        """
        subq = (
            select(
                SignalSnapshot.ticker,
                SignalSnapshot.macd_histogram,
                func.row_number()
                .over(
                    partition_by=SignalSnapshot.ticker,
                    order_by=SignalSnapshot.computed_at.desc(),
                )
                .label("rn"),
            )
            .where(SignalSnapshot.ticker.in_(tickers))
            .subquery()
        )
        stmt = select(subq.c.ticker, subq.c.macd_histogram).where(subq.c.rn == 2)
        result = await db.execute(stmt)
        return {
            row.ticker: float(row.macd_histogram)
            for row in result.all()
            if row.macd_histogram is not None
        }

    async def _fetch_latest_sentiment(
        self,
        tickers: list[str],
        db: AsyncSession,
    ) -> dict[str, NewsSentimentDaily]:
        """Bulk-fetch latest NewsSentimentDaily per ticker.

        Args:
            tickers: List of ticker symbols.
            db: Async database session.

        Returns:
            Dict of ticker → NewsSentimentDaily.
        """
        subq = (
            select(
                NewsSentimentDaily.ticker,
                func.max(NewsSentimentDaily.date).label("latest_date"),
            )
            .where(NewsSentimentDaily.ticker.in_(tickers))
            .group_by(NewsSentimentDaily.ticker)
            .subquery()
        )

        stmt = select(NewsSentimentDaily).join(
            subq,
            (NewsSentimentDaily.ticker == subq.c.ticker)
            & (NewsSentimentDaily.date == subq.c.latest_date),
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        return {row.ticker: row for row in rows}

    async def _fetch_latest_forecasts(
        self,
        tickers: list[str],
        db: AsyncSession,
    ) -> dict[str, ForecastResult]:
        """Bulk-fetch latest 90-day ForecastResult per ticker using DISTINCT ON.

        Args:
            tickers: List of ticker symbols.
            db: Async database session.

        Returns:
            Dict of ticker → ForecastResult (90-day horizon).
        """
        stmt = (
            select(ForecastResult)
            .distinct(ForecastResult.ticker)
            .where(
                ForecastResult.ticker.in_(tickers),
                ForecastResult.horizon_days == 90,
            )
            .order_by(
                ForecastResult.ticker,
                ForecastResult.forecast_date.desc(),
            )
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return {row.ticker: row for row in rows}

    async def _fetch_portfolio_positions(
        self,
        portfolio_id: str,
        db: AsyncSession,
    ) -> dict[str, float]:
        """Fetch positions and compute weights by current market value.

        Uses current_price from latest SignalSnapshot where available,
        falling back to avg_cost_basis when no signal data exists.

        Args:
            portfolio_id: UUID of the portfolio.
            db: Async database session.

        Returns:
            Dict of ticker → weight summing to ~1.0.
        """
        result = await db.execute(
            select(Position).where(
                Position.portfolio_id == portfolio_id,
                Position.quantity > 0,
            )
        )
        positions = result.scalars().all()
        if not positions:
            return {}

        # Fetch current prices from latest signals for market-value weighting
        tickers = [p.ticker for p in positions]
        price_map = await self._fetch_current_prices(tickers, db)

        total_value = 0.0
        pos_values: dict[str, float] = {}
        for p in positions:
            price = price_map.get(p.ticker) or float(p.avg_cost_basis or 0)
            mv = float(p.quantity) * price
            pos_values[p.ticker] = mv
            total_value += mv

        if total_value <= 0:
            return {}

        return {t: v / total_value for t, v in pos_values.items()}

    async def _fetch_current_prices(
        self,
        tickers: list[str],
        db: AsyncSession,
    ) -> dict[str, float]:
        """Bulk-fetch current prices from latest SignalSnapshot.

        Args:
            tickers: List of ticker symbols.
            db: Async database session.

        Returns:
            Dict of ticker → current_price.
        """
        stmt = (
            select(
                SignalSnapshot.ticker,
                SignalSnapshot.current_price,
            )
            .distinct(SignalSnapshot.ticker)
            .where(
                SignalSnapshot.ticker.in_(tickers),
                SignalSnapshot.current_price.is_not(None),
            )
            .order_by(SignalSnapshot.ticker, SignalSnapshot.computed_at.desc())
        )
        result = await db.execute(stmt)
        return {row.ticker: float(row.current_price) for row in result.all() if row.current_price}
