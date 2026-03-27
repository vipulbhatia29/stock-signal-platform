"""Celery task for nightly recommendation generation."""

import asyncio
import logging

from backend.database import async_session_factory
from backend.tasks import celery_app
from backend.tasks.pipeline import PipelineRunner

logger = logging.getLogger(__name__)

_runner = PipelineRunner()


async def _generate_recommendations_async() -> dict:
    """Generate recommendations for all users with portfolios/watchlists.

    For each user, gets their watchlist + portfolio tickers, loads the latest
    signal snapshot, runs generate_recommendation(), and stores the result.

    Returns:
        Dict with run status and counts.
    """
    from sqlalchemy import distinct, select

    from backend.models.portfolio import Portfolio, Position
    from backend.models.signal import SignalSnapshot
    from backend.models.stock import Watchlist
    from backend.models.user import User
    from backend.services.recommendations import generate_recommendation, store_recommendation
    from backend.services.signals import SignalResult
    from backend.services.stock_data import get_latest_price

    async with async_session_factory() as db:
        # Get all users
        users_result = await db.execute(select(User))
        users = users_result.scalars().all()

        if not users:
            logger.info("No users found — skipping recommendation generation")
            return {"status": "no_users", "recommendations": 0}

        total_recs = 0
        total_errors = 0

        for user in users:
            # Collect tickers from watchlist + portfolio positions
            user_tickers: set[str] = set()

            # Watchlist tickers
            wl_result = await db.execute(
                select(distinct(Watchlist.ticker)).where(Watchlist.user_id == user.id)
            )
            for row in wl_result.all():
                user_tickers.add(row[0])

            # Portfolio position tickers
            port_result = await db.execute(select(Portfolio.id).where(Portfolio.user_id == user.id))
            portfolio_ids = [r[0] for r in port_result.all()]

            if portfolio_ids:
                pos_result = await db.execute(
                    select(distinct(Position.ticker)).where(
                        Position.portfolio_id.in_(portfolio_ids),
                        Position.shares > 0,
                    )
                )
                for row in pos_result.all():
                    user_tickers.add(row[0])

            if not user_tickers:
                continue

            # Generate recommendation for each ticker with fresh signals
            for ticker in user_tickers:
                try:
                    # Get latest signal snapshot
                    sig_result = await db.execute(
                        select(SignalSnapshot)
                        .where(SignalSnapshot.ticker == ticker)
                        .order_by(SignalSnapshot.computed_at.desc())
                        .limit(1)
                    )
                    snapshot = sig_result.scalar_one_or_none()

                    if snapshot is None:
                        continue

                    signal = SignalResult(
                        ticker=snapshot.ticker,
                        rsi_value=snapshot.rsi_value,
                        rsi_signal=snapshot.rsi_signal,
                        macd_value=snapshot.macd_value,
                        macd_histogram=snapshot.macd_histogram,
                        macd_signal_label=snapshot.macd_signal_label,
                        sma_50=snapshot.sma_50,
                        sma_200=snapshot.sma_200,
                        sma_signal=snapshot.sma_signal,
                        bb_upper=snapshot.bb_upper,
                        bb_lower=snapshot.bb_lower,
                        bb_position=snapshot.bb_position,
                        annual_return=snapshot.annual_return,
                        volatility=snapshot.volatility,
                        sharpe_ratio=snapshot.sharpe_ratio,
                        composite_score=snapshot.composite_score,
                        composite_weights=snapshot.composite_weights,
                    )
                    price = await get_latest_price(ticker, db)

                    if price is None or price <= 0:
                        continue

                    rec = generate_recommendation(signal, current_price=price)
                    await store_recommendation(rec, str(user.id), db)
                    total_recs += 1

                except Exception:
                    total_errors += 1
                    logger.exception(
                        "Failed to generate recommendation for %s (user %s)",
                        ticker,
                        user.id,
                    )

        status = "success" if total_errors == 0 else "partial"
        logger.info(
            "Recommendation generation complete: %d generated, %d errors",
            total_recs,
            total_errors,
        )
        return {
            "status": status,
            "recommendations": total_recs,
            "errors": total_errors,
        }


@celery_app.task(
    name="backend.tasks.recommendations.generate_recommendations_task",
)
def generate_recommendations_task() -> dict:
    """Nightly recommendation generation for all users.

    Returns:
        Dict with generation status and counts.
    """
    logger.info("Starting nightly recommendation generation")
    return asyncio.run(_generate_recommendations_async())
