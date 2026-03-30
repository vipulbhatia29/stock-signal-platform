"""Celery task for generating in-app alerts from pipeline events."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session_factory
from backend.models.alert import InAppAlert
from backend.tasks import celery_app

logger = logging.getLogger(__name__)


def _is_downgrade(old_action: str, new_action: str) -> bool:
    """Return True if the signal change is a downgrade."""
    rank = {"BUY": 3, "WATCH": 2, "AVOID": 1, "SELL": 0}
    return rank.get(new_action, 0) < rank.get(old_action, 0)


async def _alert_exists_recently(
    db: AsyncSession,
    user_id: uuid.UUID,
    dedup_key: str,
    hours: int = 24,
) -> bool:
    """Check if a similar alert was created within the dedup window."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(InAppAlert.id)
        .where(
            InAppAlert.user_id == user_id,
            InAppAlert.dedup_key == dedup_key,
            InAppAlert.created_at > cutoff,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _create_alert(
    db: AsyncSession,
    alert_type: str,
    message: str,
    metadata_: dict | None = None,
    user_id: uuid.UUID | None = None,
    severity: str = "info",
    title: str = "",
    ticker: str | None = None,
    dedup_key: str | None = None,
) -> bool:
    """Create an InAppAlert row, skipping if dedup_key matches a recent alert.

    If user_id is None, creates alert for ALL users (system-wide alert).

    Returns:
        True if at least one alert was created, False if deduped.
    """
    if user_id is not None:
        if dedup_key:
            if await _alert_exists_recently(db, user_id, dedup_key):
                return False
        alert = InAppAlert(
            id=uuid.uuid4(),
            user_id=user_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            ticker=ticker,
            dedup_key=dedup_key,
            message=message,
            metadata_=metadata_,
            is_read=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(alert)
        return True
    else:
        from backend.models.user import User

        users_result = await db.execute(select(User.id))
        user_ids = [r[0] for r in users_result.all()]
        any_created = False
        for uid in user_ids:
            if dedup_key:
                if await _alert_exists_recently(db, uid, dedup_key):
                    continue
            alert = InAppAlert(
                id=uuid.uuid4(),
                user_id=uid,
                alert_type=alert_type,
                severity=severity,
                title=title,
                ticker=ticker,
                dedup_key=dedup_key,
                message=message,
                metadata_=metadata_,
                is_read=False,
                created_at=datetime.now(timezone.utc),
            )
            db.add(alert)
            any_created = True
        return any_created


async def _generate_alerts_async(
    pipeline_context: dict | None = None,
) -> dict:
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
        alerts_created += await _alert_new_buy_recommendations(db)
        alerts_created += await _alert_signal_flips(db)
        alerts_created += await _alert_divestment_rules(db)

        degraded = ctx.get("degraded", [])
        for ticker in degraded:
            if await _create_alert(
                db,
                alert_type="drift",
                message=(
                    f"{ticker} forecast model degraded — accuracy below "
                    "threshold, retraining queued"
                ),
                metadata_={
                    "ticker": ticker,
                    "route": f"/stocks/{ticker}",
                },
                severity="warning",
                title="Forecast Degraded",
                ticker=ticker,
                dedup_key=f"drift:{ticker}",
            ):
                alerts_created += 1

        price_status = ctx.get("price_refresh", {}).get("status")
        if price_status == "partial":
            if await _create_alert(
                db,
                alert_type="pipeline",
                message=(
                    "Nightly price refresh completed with some failures — check pipeline logs"
                ),
                metadata_={"route": "/dashboard"},
                severity="warning",
                title="Pipeline Issue",
                ticker=None,
                dedup_key="pipeline:partial",
            ):
                alerts_created += 1
        elif price_status == "failed":
            if await _create_alert(
                db,
                alert_type="pipeline",
                message=("Nightly price refresh failed — all tickers affected"),
                metadata_={"route": "/dashboard"},
                severity="critical",
                title="Pipeline Failed",
                ticker=None,
                dedup_key="pipeline:total",
            ):
                alerts_created += 1

        await db.commit()

    # Retention cleanup (separate session — after commit so new alerts aren't affected)
    async with async_session_factory() as cleanup_db:
        deleted = await _cleanup_old_read_alerts(cleanup_db)
        await cleanup_db.commit()

    logger.info(
        "Alert generation complete: %d created, %d old read alerts cleaned",
        alerts_created,
        deleted,
    )
    return {"alerts_created": alerts_created, "alerts_cleaned": deleted}


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
        if await _create_alert(
            db,
            user_id=rec.user_id,
            alert_type="recommendation",
            message=(
                f"New BUY signal for {rec.ticker} — composite score {rec.composite_score:.1f}/10"
            ),
            metadata_={
                "ticker": rec.ticker,
                "route": f"/stocks/{rec.ticker}",
            },
            severity="info",
            title="New BUY Signal",
            ticker=rec.ticker,
            dedup_key=f"buy:{rec.ticker}",
        ):
            created += 1

    return created


async def _alert_signal_flips(db: AsyncSession) -> int:
    """Create alerts when a stock's recommendation action flips.

    Compares the most recent recommendation to the previous one. If the
    action changed (e.g., WATCH -> BUY or BUY -> SELL), create an alert.

    Returns:
        Number of alerts created.
    """
    from backend.models.recommendation import RecommendationSnapshot

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
        if latest.action == previous.action:
            continue

        downgrade = _is_downgrade(previous.action, latest.action)
        severity = "warning" if downgrade else "info"
        title = "Score Downgrade" if downgrade else "Score Upgrade"
        direction = "downgrade" if downgrade else "upgrade"

        if await _create_alert(
            db,
            user_id=latest.user_id,
            alert_type="signal_change",
            message=(
                f"{ticker} signal changed: "
                f"{previous.action} → {latest.action} "
                f"(score {latest.composite_score:.1f}/10)"
            ),
            metadata_={
                "ticker": ticker,
                "route": f"/stocks/{ticker}",
            },
            severity=severity,
            title=title,
            ticker=ticker,
            dedup_key=f"signal_flip:{direction}:{ticker}",
        ):
            created += 1

    return created


async def _alert_divestment_rules(db: AsyncSession) -> int:
    """Generate alerts from divestment rule checks for all users with portfolios.

    Uses get_positions_with_pnl() for enriched positions (Position model has
    no current_price/sector — they come from JOINed Stock and StockPrice).

    Returns:
        Number of alerts created.
    """
    from backend.models.portfolio import Portfolio, Position
    from backend.models.signal import SignalSnapshot
    from backend.models.user import UserPreference
    from backend.services.portfolio import get_positions_with_pnl
    from backend.tools.divestment import check_divestment_rules

    TITLE_MAP = {
        "stop_loss": "Stop-Loss Triggered",
        "position_concentration": "Concentration Risk",
        "sector_concentration": "Sector Overweight",
        "weak_fundamentals": "Weak Fundamentals",
    }

    count = 0

    # Fetch all users who have at least one portfolio with positions
    user_result = await db.execute(
        select(Portfolio.user_id)
        .join(Position, Position.portfolio_id == Portfolio.id)
        .where(Position.closed_at.is_(None))
        .distinct()
    )
    user_ids = [row[0] for row in user_result.fetchall()]

    for uid in user_ids:
        # Fetch portfolio
        port_result = await db.execute(select(Portfolio).where(Portfolio.user_id == uid).limit(1))
        portfolio = port_result.scalar_one_or_none()
        if not portfolio:
            continue

        # Use the same service function the portfolio router uses
        positions = await get_positions_with_pnl(portfolio.id, db)
        if not positions:
            continue

        # Fetch preferences
        pref_result = await db.execute(select(UserPreference).where(UserPreference.user_id == uid))
        prefs = pref_result.scalar_one_or_none()
        if not prefs:
            continue

        # Build sector allocations (same logic as portfolio router)
        total_value = sum(p.market_value or 0 for p in positions)
        sector_buckets: dict[str, float] = {}
        for p in positions:
            sector = p.sector or "Unknown"
            sector_buckets[sector] = sector_buckets.get(sector, 0.0) + (p.market_value or 0)
        sector_allocations = [
            {
                "sector": s,
                "pct": round(v / total_value * 100, 2) if total_value > 0 else 0.0,
            }
            for s, v in sector_buckets.items()
        ]

        # Batch-fetch latest signals for all tickers (avoid N+1)
        tickers = [p.ticker for p in positions]
        subq = (
            select(
                SignalSnapshot.ticker,
                func.max(SignalSnapshot.computed_at).label("latest"),
            )
            .where(SignalSnapshot.ticker.in_(tickers))
            .group_by(SignalSnapshot.ticker)
            .subquery()
        )
        signal_result = await db.execute(
            select(
                SignalSnapshot.ticker,
                SignalSnapshot.composite_score,
            ).join(
                subq,
                (SignalSnapshot.ticker == subq.c.ticker)
                & (SignalSnapshot.computed_at == subq.c.latest),
            )
        )
        signal_map = {row.ticker: row.composite_score for row in signal_result}

        # Check each position
        for p in positions:
            pos_dict = {
                "ticker": p.ticker,
                "unrealized_pnl_pct": p.unrealized_pnl_pct,
                "allocation_pct": p.allocation_pct,
                "sector": p.sector,
            }
            signal = (
                {"composite_score": signal_map.get(p.ticker)} if p.ticker in signal_map else None
            )

            alerts = check_divestment_rules(pos_dict, sector_allocations, signal, prefs)
            for a in alerts:
                rule = a["rule"]
                if await _create_alert(
                    db,
                    alert_type="divestment",
                    message=a["message"],
                    metadata_={
                        "rule": rule,
                        "value": a["value"],
                        "threshold": a["threshold"],
                        "route": f"/stocks/{p.ticker}",
                    },
                    user_id=uid,
                    severity=a["severity"],
                    title=TITLE_MAP.get(rule, rule.replace("_", " ").title()),
                    ticker=p.ticker,
                    dedup_key=f"divestment:{rule}:{p.ticker}",
                ):
                    count += 1

    return count


async def _cleanup_old_read_alerts(db: AsyncSession) -> int:
    """Delete read alerts older than 90 days.

    Only deletes read alerts — unread alerts older than 90 days are
    preserved so users who haven't logged in still see critical
    notifications when they return.

    Returns:
        Number of alerts deleted.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    result = await db.execute(
        delete(InAppAlert).where(
            InAppAlert.is_read.is_(True),
            InAppAlert.created_at < cutoff,
        )
    )
    return result.rowcount or 0


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
