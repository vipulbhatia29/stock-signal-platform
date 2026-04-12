"""Nightly data quality scanner — detects anomalies and persists findings."""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session_factory
from backend.models.dq_check_history import DqCheckHistory
from backend.tasks import celery_app
from backend.tasks.pipeline import tracked_task

logger = logging.getLogger(__name__)


@celery_app.task(name="backend.tasks.dq_scan.dq_scan_task")
@tracked_task("dq_scan", trigger="scheduled")
def dq_scan_task(run_id: uuid.UUID | None = None) -> dict:
    """Run all data quality checks and persist findings.

    Returns:
        Dict with status, total findings count, and critical findings count.
    """
    return asyncio.run(_dq_scan_async())


async def _dq_scan_async() -> dict:
    """Execute 10 DQ checks, persist findings, create alerts for critical ones.

    Returns:
        Dict with status, findings count, and critical count.
    """
    findings: list[dict] = []
    async with async_session_factory() as db:
        findings += await _check_negative_prices(db)
        findings += await _check_rsi_out_of_range(db)
        findings += await _check_composite_score_out_of_range(db)
        findings += await _check_null_sectors(db)
        findings += await _check_forecast_extreme_ratios(db)
        findings += await _check_orphan_positions(db)
        findings += await _check_duplicate_signals(db)
        findings += await _check_stale_universe_coverage(db)
        findings += await _check_negative_volume(db)
        findings += await _check_bollinger_violations(db)

        # Persist findings
        for f in findings:
            db.add(
                DqCheckHistory(
                    check_name=f["check"],
                    severity=f["severity"],
                    ticker=f.get("ticker"),
                    message=f["message"],
                    metadata_=f.get("metadata"),
                )
            )
        await db.commit()

    # Create alerts for critical findings
    critical = [f for f in findings if f["severity"] == "critical"]
    if critical:
        from backend.tasks.alerts import _create_alert

        async with async_session_factory() as db:
            for f in critical:
                await _create_alert(
                    db,
                    alert_type="data_quality",
                    message=f["message"],
                    title=f["check"],
                    severity="critical",
                    ticker=f.get("ticker"),
                    dedup_key=f"dq:{f['check']}:{f.get('ticker', 'global')}",
                )
            await db.commit()

    return {"status": "ok", "findings": len(findings), "critical": len(critical)}


# ── Individual check functions ────────────────────────────────────────────────


async def _check_negative_prices(db: AsyncSession) -> list[dict]:
    """Check for negative close/adj_close prices.

    Args:
        db: Async database session.

    Returns:
        List of finding dicts for each bad row found.
    """
    result = await db.execute(
        text(
            "SELECT ticker, time, close FROM stock_prices "
            "WHERE close < 0 OR adj_close < 0 LIMIT 100"
        )
    )
    rows = result.all()
    return [
        {
            "check": "negative_prices",
            "severity": "critical",
            "ticker": r[0],
            "message": f"Negative price for {r[0]} at {r[1]}: close={r[2]}",
        }
        for r in rows
    ]


async def _check_rsi_out_of_range(db: AsyncSession) -> list[dict]:
    """Check for RSI values outside [0, 100].

    Args:
        db: Async database session.

    Returns:
        List of finding dicts for each out-of-range RSI value.
    """
    result = await db.execute(
        text(
            "SELECT ticker, computed_at, rsi_value FROM signal_snapshots "
            "WHERE rsi_value IS NOT NULL AND (rsi_value < 0 OR rsi_value > 100) LIMIT 50"
        )
    )
    rows = result.all()
    return [
        {
            "check": "rsi_out_of_range",
            "severity": "high",
            "ticker": r[0],
            "message": f"RSI {r[2]:.1f} for {r[0]} at {r[1]}",
        }
        for r in rows
    ]


async def _check_composite_score_out_of_range(db: AsyncSession) -> list[dict]:
    """Check for composite scores outside [0, 10].

    Args:
        db: Async database session.

    Returns:
        List of finding dicts for each out-of-range composite score.
    """
    result = await db.execute(
        text(
            "SELECT ticker, composite_score FROM signal_snapshots "
            "WHERE composite_score IS NOT NULL "
            "AND (composite_score < 0 OR composite_score > 10) LIMIT 50"
        )
    )
    rows = result.all()
    return [
        {
            "check": "composite_score_out_of_range",
            "severity": "high",
            "ticker": r[0],
            "message": f"Composite score {r[1]:.1f} for {r[0]}",
        }
        for r in rows
    ]


async def _check_null_sectors(db: AsyncSession) -> list[dict]:
    """Check for active stocks with NULL sector.

    Args:
        db: Async database session.

    Returns:
        List of finding dicts for each active stock missing a sector.
    """
    result = await db.execute(
        text("SELECT ticker FROM stocks WHERE is_active = true AND sector IS NULL LIMIT 50")
    )
    rows = result.all()
    return [
        {
            "check": "null_sector",
            "severity": "medium",
            "ticker": r[0],
            "message": f"Active stock {r[0]} has NULL sector",
        }
        for r in rows
    ]


async def _check_forecast_extreme_ratios(db: AsyncSession) -> list[dict]:
    """Check for forecasts with extreme predicted/current price ratios (>10x or <0.1x).

    Args:
        db: Async database session.

    Returns:
        List of finding dicts for each extreme forecast ratio.
    """
    result = await db.execute(
        text(
            "SELECT fr.ticker, fr.predicted_price, sp.close "
            "FROM forecast_results fr "
            "JOIN LATERAL ("
            "  SELECT close FROM stock_prices WHERE ticker = fr.ticker "
            "  ORDER BY time DESC LIMIT 1"
            ") sp ON true "
            "WHERE sp.close > 0 AND ("
            "  fr.predicted_price > 10 * sp.close OR fr.predicted_price < 0.1 * sp.close"
            ") LIMIT 50"
        )
    )
    rows = result.all()
    return [
        {
            "check": "forecast_extreme_ratio",
            "severity": "high",
            "ticker": r[0],
            "message": f"Extreme forecast for {r[0]}: predicted={r[1]:.2f}, current={r[2]:.2f}",
        }
        for r in rows
    ]


async def _check_orphan_positions(db: AsyncSession) -> list[dict]:
    """Check for positions referencing inactive or missing stocks.

    Args:
        db: Async database session.

    Returns:
        List of finding dicts for each orphaned position.
    """
    result = await db.execute(
        text(
            "SELECT p.ticker FROM position p "
            "LEFT JOIN stocks s ON s.ticker = p.ticker "
            "WHERE s.ticker IS NULL OR s.is_active = false LIMIT 50"
        )
    )
    rows = result.all()
    return [
        {
            "check": "orphan_position",
            "severity": "high",
            "ticker": r[0],
            "message": f"Position for inactive/missing stock {r[0]}",
        }
        for r in rows
    ]


async def _check_duplicate_signals(db: AsyncSession) -> list[dict]:
    """Check for duplicate signal snapshots (same ticker + computed_at).

    Args:
        db: Async database session.

    Returns:
        List of finding dicts for each duplicate signal group.
    """
    result = await db.execute(
        text(
            "SELECT ticker, computed_at, COUNT(*) as cnt FROM signal_snapshots "
            "GROUP BY ticker, computed_at HAVING COUNT(*) > 1 LIMIT 50"
        )
    )
    rows = result.all()
    return [
        {
            "check": "duplicate_signals",
            "severity": "medium",
            "ticker": r[0],
            "message": f"Duplicate signals for {r[0]} at {r[1]} (count={r[2]})",
        }
        for r in rows
    ]


async def _check_stale_universe_coverage(db: AsyncSession) -> list[dict]:
    """Check for tickers in the canonical universe with stale signals.

    Args:
        db: Async database session.

    Returns:
        List of finding dicts for each ticker with stale signals.
    """
    from backend.config import settings

    sla = settings.staleness_slas
    result = await db.execute(
        text(
            "SELECT tis.ticker, tis.signals_updated_at FROM ticker_ingestion_state tis "
            "WHERE tis.signals_updated_at < NOW() - :sla"
        ),
        {"sla": sla.signals},
    )
    rows = result.all()
    return [
        {
            "check": "stale_signals",
            "severity": "medium",
            "ticker": r[0],
            "message": f"Stale signals for {r[0]}: last updated {r[1]}",
        }
        for r in rows
    ]


async def _check_negative_volume(db: AsyncSession) -> list[dict]:
    """Check for negative volume values.

    Args:
        db: Async database session.

    Returns:
        List of finding dicts for each negative volume row.
    """
    result = await db.execute(
        text("SELECT ticker, time, volume FROM stock_prices WHERE volume < 0 LIMIT 100")
    )
    rows = result.all()
    return [
        {
            "check": "negative_volume",
            "severity": "critical",
            "ticker": r[0],
            "message": f"Negative volume for {r[0]} at {r[1]}: volume={r[2]}",
        }
        for r in rows
    ]


async def _check_bollinger_violations(db: AsyncSession) -> list[dict]:
    """Check for bollinger band violations where lower > upper.

    Args:
        db: Async database session.

    Returns:
        List of finding dicts for each bollinger band violation.
    """
    result = await db.execute(
        text(
            "SELECT ticker, computed_at, bb_upper, bb_lower FROM signal_snapshots "
            "WHERE bb_lower IS NOT NULL AND bb_upper IS NOT NULL "
            "AND bb_lower > bb_upper LIMIT 50"
        )
    )
    rows = result.all()
    return [
        {
            "check": "bollinger_violation",
            "severity": "high",
            "ticker": r[0],
            "message": f"BB violation for {r[0]} at {r[1]}: lower={r[3]} > upper={r[2]}",
        }
        for r in rows
    ]
