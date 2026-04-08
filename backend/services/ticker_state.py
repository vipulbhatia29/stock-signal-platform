"""Per-ticker, per-stage ingestion freshness service."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import async_session_factory
from backend.models.ticker_ingestion_state import TickerIngestionState

logger = logging.getLogger(__name__)

Stage = Literal[
    "prices",
    "signals",
    "fundamentals",
    "forecast",
    "forecast_retrain",
    "news",
    "sentiment",
    "convergence",
    "backtest",
    "recommendation",
]

StageStatus = Literal["green", "yellow", "red", "unknown"]

# Stage → column name. "forecast_retrain" targets forecast_retrained_at.
_STAGE_COLUMNS: dict[Stage, str] = {
    "prices": "prices_updated_at",
    "signals": "signals_updated_at",
    "fundamentals": "fundamentals_updated_at",
    "forecast": "forecast_updated_at",
    "forecast_retrain": "forecast_retrained_at",
    "news": "news_updated_at",
    "sentiment": "sentiment_updated_at",
    "convergence": "convergence_updated_at",
    "backtest": "backtest_updated_at",
    "recommendation": "recommendation_updated_at",
}


@dataclass(frozen=True, slots=True)
class ReadinessState:
    """Per-ticker freshness snapshot with per-stage status buckets."""

    ticker: str
    stages: dict[Stage, StageStatus]
    timestamps: dict[Stage, datetime | None]
    overall: StageStatus  # worst-stage wins


@dataclass(frozen=True, slots=True)
class ReadinessRow:
    """Flat row for the universe health dashboard."""

    ticker: str
    prices: StageStatus
    signals: StageStatus
    fundamentals: StageStatus
    forecast: StageStatus
    forecast_retrain: StageStatus
    news: StageStatus
    sentiment: StageStatus
    convergence: StageStatus
    backtest: StageStatus
    recommendation: StageStatus
    overall: StageStatus


async def mark_stage_updated(
    ticker: str,
    stage: Stage,
    db: AsyncSession | None = None,
) -> None:
    """Idempotent upsert of the stage timestamp for a ticker.

    Safe to call concurrently — uses ON CONFLICT DO UPDATE. Fire-and-forget:
    errors are logged at warning but never propagated, so an observability
    write failure cannot kill an ingestion task.

    When ``db`` is provided, the upsert runs on the caller's transaction —
    the caller owns commit semantics and no errors are swallowed (a failed
    upsert here would have already broken the caller's transaction). When
    ``db`` is None, a fresh session is opened from the factory, committed,
    and any error is logged at warning level.

    Args:
        ticker: Stock ticker symbol.
        stage: Which pipeline stage just completed.
        db: Optional caller-owned session. When provided, no commit is issued
            and exceptions are NOT swallowed. When None, opens a fresh session
            and swallows errors (fire-and-forget).
    """
    now = datetime.now(timezone.utc)
    col = _STAGE_COLUMNS[stage]
    values: dict[str, object] = {
        "ticker": ticker,
        col: now,
        "created_at": now,
        "updated_at": now,
    }
    stmt = insert(TickerIngestionState).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker"],
        set_={col: now, "updated_at": now},
    )
    if db is not None:
        await db.execute(stmt)
        return
    try:
        async with async_session_factory() as session:
            await session.execute(stmt)
            await session.commit()
    except Exception:
        logger.warning("Failed to mark stage %s for ticker %s", stage, ticker, exc_info=True)


async def mark_stages_updated(
    tickers: list[str],
    stage: Stage,
    db: AsyncSession | None = None,
) -> None:
    """Bulk upsert of a stage timestamp for many tickers in a single statement.

    Eliminates the N round-trips of looping ``mark_stage_updated`` over a
    universe of tickers (relevant for the nightly convergence + backtest
    chains). Same dual-mode session handling as :func:`mark_stage_updated`.

    Input is uppercased and de-duplicated before the upsert: Postgres
    ``INSERT ... ON CONFLICT DO UPDATE`` raises ``cardinality_violation``
    if a single statement contains two rows with the same conflict key,
    so callers that derive their list from joins or retries cannot be
    trusted to deliver unique tickers.

    Args:
        tickers: List of stock ticker symbols. Empty list is a no-op.
            Duplicates and case variants are collapsed.
        stage: Which pipeline stage just completed for all of them.
        db: Optional caller-owned session. When provided, no commit is issued
            and exceptions are NOT swallowed. When None, opens a fresh session
            and swallows errors (fire-and-forget).
    """
    if not tickers:
        return
    # Dedup + normalize case so a single statement cannot hit the same PK
    # twice (Postgres `cardinality_violation`). dict.fromkeys preserves the
    # first-seen order, which makes the resulting SQL stable for tests.
    unique_tickers = list(dict.fromkeys(t.upper().strip() for t in tickers if t))
    if not unique_tickers:
        return
    now = datetime.now(timezone.utc)
    col = _STAGE_COLUMNS[stage]
    rows: list[dict[str, object]] = [
        {"ticker": t, col: now, "created_at": now, "updated_at": now} for t in unique_tickers
    ]
    stmt = insert(TickerIngestionState).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker"],
        set_={col: now, "updated_at": now},
    )
    if db is not None:
        await db.execute(stmt)
        return
    try:
        async with async_session_factory() as session:
            await session.execute(stmt)
            await session.commit()
    except Exception:
        logger.warning(
            "Failed to bulk mark stage %s for %d tickers",
            stage,
            len(unique_tickers),
            exc_info=True,
        )


async def get_ticker_readiness(ticker: str) -> ReadinessState:
    """Return freshness status for a single ticker across all stages.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        ReadinessState with per-stage status and the worst-stage overall.
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(TickerIngestionState).where(TickerIngestionState.ticker == ticker)
        )
        row = result.scalar_one_or_none()

    return _compute_readiness(ticker, row)


async def get_universe_health() -> list[ReadinessRow]:
    """Return freshness status for every ticker in the universe.

    Returns:
        One ReadinessRow per ticker in ticker_ingestion_state, sorted by
        overall status (red first) then ticker ascending.
    """
    async with async_session_factory() as session:
        result = await session.execute(select(TickerIngestionState))
        rows = list(result.scalars())

    readiness = [_compute_readiness(r.ticker, r) for r in rows]
    priority = {"red": 0, "yellow": 1, "unknown": 2, "green": 3}
    ordered = sorted(readiness, key=lambda r: (priority[r.overall], r.ticker))
    return [_to_row(r) for r in ordered]


def _compute_readiness(ticker: str, row: TickerIngestionState | None) -> ReadinessState:
    """Compute per-stage status from a row (or absence thereof).

    Args:
        ticker: Stock ticker symbol.
        row: The TickerIngestionState row, or None if not found.

    Returns:
        ReadinessState with per-stage status buckets and overall worst-stage.
    """
    sla = settings.staleness_slas
    now = datetime.now(timezone.utc)

    def status_for(ts: datetime | None, green: timedelta, yellow: timedelta) -> StageStatus:
        """Bucket a timestamp against green/yellow SLA thresholds."""
        if ts is None:
            return "unknown"
        age = now - ts
        if age <= green:
            return "green"
        if age <= yellow:
            return "yellow"
        return "red"

    timestamps: dict[Stage, datetime | None] = {
        "prices": row.prices_updated_at if row else None,
        "signals": row.signals_updated_at if row else None,
        "fundamentals": row.fundamentals_updated_at if row else None,
        "forecast": row.forecast_updated_at if row else None,
        "forecast_retrain": row.forecast_retrained_at if row else None,
        "news": row.news_updated_at if row else None,
        "sentiment": row.sentiment_updated_at if row else None,
        "convergence": row.convergence_updated_at if row else None,
        "backtest": row.backtest_updated_at if row else None,
        "recommendation": row.recommendation_updated_at if row else None,
    }

    stages: dict[Stage, StageStatus] = {
        "prices": status_for(timestamps["prices"], sla.prices, sla.prices * 2),
        "signals": status_for(timestamps["signals"], sla.signals, sla.signals * 2),
        "fundamentals": status_for(
            timestamps["fundamentals"], sla.fundamentals, sla.fundamentals * 2
        ),
        "forecast": status_for(timestamps["forecast"], sla.forecast, sla.forecast * 2),
        "forecast_retrain": status_for(
            timestamps["forecast_retrain"],
            sla.forecast_retrain,
            sla.forecast_retrain * 2,
        ),
        "news": status_for(timestamps["news"], sla.news, sla.news * 2),
        "sentiment": status_for(timestamps["sentiment"], sla.sentiment, sla.sentiment * 2),
        "convergence": status_for(timestamps["convergence"], sla.convergence, sla.convergence * 2),
        "backtest": status_for(timestamps["backtest"], sla.backtest, sla.backtest * 2),
        "recommendation": status_for(
            timestamps["recommendation"], sla.recommendation, sla.recommendation * 2
        ),
    }

    overall = _worst(stages.values())
    return ReadinessState(ticker=ticker, stages=stages, timestamps=timestamps, overall=overall)


def _worst(values: Iterable[StageStatus]) -> StageStatus:
    """Return the worst stage status (red > yellow > unknown > green).

    Args:
        values: Iterable of stage status strings.

    Returns:
        The worst status across all values.
    """
    priority = {"red": 0, "yellow": 1, "unknown": 2, "green": 3}
    # cast: min() over a Literal iterable is widened to str by pyright; the
    # default literal "unknown" is itself a StageStatus, so the call is sound.
    return cast("StageStatus", min(values, key=lambda s: priority[s], default="unknown"))


def _to_row(r: ReadinessState) -> ReadinessRow:
    """Flatten a ReadinessState into a dashboard row (all 10 stages included).

    Args:
        r: The ReadinessState to flatten.

    Returns:
        ReadinessRow suitable for the admin health dashboard, with one
        StageStatus column per pipeline stage plus the worst-stage overall.
    """
    s = r.stages
    return ReadinessRow(
        ticker=r.ticker,
        prices=s["prices"],
        signals=s["signals"],
        fundamentals=s["fundamentals"],
        forecast=s["forecast"],
        forecast_retrain=s["forecast_retrain"],
        news=s["news"],
        sentiment=s["sentiment"],
        convergence=s["convergence"],
        backtest=s["backtest"],
        recommendation=s["recommendation"],
        overall=r.overall,
    )
