"""Celery task for generating in-app alerts from pipeline events."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session_factory
from backend.models.alert import InAppAlert
from backend.tasks import celery_app

logger = logging.getLogger(__name__)


async def _generate_alerts_async(pipeline_context: dict | None = None) -> dict:
    """Generate in-app alerts based on pipeline results and signal changes.

    Args:
        pipeline_context: Optional dict with pipeline run results
            (e.g., drift detections, new recommendations, failures).

    Returns:
        Dict with count of alerts created.
    """
    ctx = pipeline_context or {}
    alerts_created = 0

    async with async_session_factory() as db:
        # 1. New BUY recommendations
        alerts_created += await _alert_new_buy_recommendations(db)

        # 2. Signal flips (action changed from yesterday)
        alerts_created += await _alert_signal_flips(db)

        # 3. Model drift events (from pipeline context)
        degraded = ctx.get("degraded", [])
        for ticker in degraded:
            await _create_alert(
                db,
                alert_type="drift",
                message=(
                    f"{ticker} forecast model degraded — accuracy below "
                    "threshold, retraining queued"
                ),
                metadata_={"ticker": ticker, "route": f"/stocks/{ticker}"},
            )
            alerts_created += 1

        # 4. Pipeline partial failures
        price_status = ctx.get("price_refresh", {}).get("status")
        if price_status == "partial":
            await _create_alert(
                db,
                alert_type="pipeline",
                message="Nightly price refresh completed with some failures — check pipeline logs",
                metadata_={"route": "/dashboard"},
            )
            alerts_created += 1
        elif price_status == "failed":
            await _create_alert(
                db,
                alert_type="pipeline",
                message="Nightly price refresh failed — all tickers affected",
                metadata_={"route": "/dashboard"},
            )
            alerts_created += 1

        await db.commit()

    logger.info("Alert generation complete: %d alerts created", alerts_created)
    return {"alerts_created": alerts_created}


async def _alert_new_buy_recommendations(db: AsyncSession) -> int:
    """Create alerts for new BUY recommendations from the last 24 hours.

    Returns:
        Number of alerts created.
    """
    from backend.models.recommendation import RecommendationSnapshot

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await db.execute(
        select(RecommendationSnapshot).where(
            RecommendationSnapshot.action == "BUY",
            RecommendationSnapshot.generated_at >= cutoff,
            RecommendationSnapshot.is_actionable.is_(True),
        )
    )
    new_buys = result.scalars().all()

    created = 0
    for rec in new_buys:
        await _create_alert(
            db,
            user_id=rec.user_id,
            alert_type="signal_change",
            message=(
                f"New BUY signal for {rec.ticker} — composite score {rec.composite_score:.1f}/10"
            ),
            metadata_={"ticker": rec.ticker, "route": f"/stocks/{rec.ticker}"},
        )
        created += 1

    return created


async def _alert_signal_flips(db: AsyncSession) -> int:
    """Create alerts when a stock's recommendation action flips.

    Compares the most recent recommendation to the previous one. If the
    action changed (e.g., WATCH → BUY or BUY → SELL), create an alert.

    Returns:
        Number of alerts created.
    """
    from backend.models.recommendation import RecommendationSnapshot

    # Get the latest 2 recommendations per ticker for all users
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    result = await db.execute(
        select(RecommendationSnapshot)
        .where(RecommendationSnapshot.generated_at >= cutoff)
        .order_by(
            RecommendationSnapshot.ticker,
            RecommendationSnapshot.user_id,
            RecommendationSnapshot.generated_at.desc(),
        )
    )
    recs = result.scalars().all()

    # Group by (user_id, ticker) and check for flips
    groups: dict[tuple, list] = {}
    for rec in recs:
        key = (str(rec.user_id), rec.ticker)
        groups.setdefault(key, []).append(rec)

    created = 0
    for (user_id_str, ticker), group in groups.items():
        if len(group) < 2:
            continue
        latest = group[0]
        previous = group[1]
        if latest.action != previous.action:
            await _create_alert(
                db,
                user_id=latest.user_id,
                alert_type="signal_change",
                message=(
                    f"{ticker} signal changed: {previous.action} → {latest.action} "
                    f"(score {latest.composite_score:.1f}/10)"
                ),
                metadata_={"ticker": ticker, "route": f"/stocks/{ticker}"},
            )
            created += 1

    return created


async def _create_alert(
    db: AsyncSession,
    alert_type: str,
    message: str,
    metadata_: dict | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    """Create an InAppAlert row.

    If user_id is None, creates alert for ALL users (system-wide alert).

    Args:
        db: Async database session.
        alert_type: Alert type string.
        message: Human-readable message.
        metadata_: Optional JSONB metadata for deep-linking.
        user_id: Target user, or None for all users.
    """
    if user_id is not None:
        alert = InAppAlert(
            id=uuid.uuid4(),
            user_id=user_id,
            alert_type=alert_type,
            message=message,
            metadata_=metadata_,
            is_read=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(alert)
    else:
        # System-wide alert: create for all users
        from backend.models.user import User

        users_result = await db.execute(select(User.id))
        user_ids = [r[0] for r in users_result.all()]
        for uid in user_ids:
            alert = InAppAlert(
                id=uuid.uuid4(),
                user_id=uid,
                alert_type=alert_type,
                message=message,
                metadata_=metadata_,
                is_read=False,
                created_at=datetime.now(timezone.utc),
            )
            db.add(alert)


@celery_app.task(name="backend.tasks.alerts.generate_alerts_task")
def generate_alerts_task(pipeline_context: dict | None = None) -> dict:
    """Generate in-app alerts from pipeline events.

    Args:
        pipeline_context: Optional pipeline run results.

    Returns:
        Dict with alert creation counts.
    """
    logger.info("Starting alert generation")
    return asyncio.run(_generate_alerts_async(pipeline_context))
