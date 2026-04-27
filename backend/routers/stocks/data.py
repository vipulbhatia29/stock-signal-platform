"""Stock data read endpoints — prices, signals, fundamentals, news, intelligence.

These endpoints return stock data for individual tickers. All require JWT
authentication and a valid ticker in the database.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.price import StockPrice
from backend.models.user import User
from backend.routers.stocks._helpers import require_stock
from backend.schemas.intelligence import StockIntelligenceResponse
from backend.schemas.stock import (
    BenchmarkComparisonResponse,
    BenchmarkSeries,
    BollingerResponse,
    FundamentalsResponse,
    IngestStageStatus,
    IngestStateResponse,
    IngestStateStages,
    MACDResponse,
    OHLCResponse,
    PiotroskiBreakdown,
    PriceFormat,
    PricePeriod,
    PricePointResponse,
    ReturnsResponse,
    RSIResponse,
    SignalResponse,
    SMAResponse,
    StageInfo,
    StockAnalyticsResponse,
)
from backend.services.signals import get_latest_signals as get_latest_signals_svc
from backend.services.stock_data import (
    ensure_stock_exists,
    fetch_fundamentals,
    fetch_prices_delta,
)
from backend.tools.intelligence import (
    fetch_eps_revisions,
    fetch_insider_transactions,
    fetch_next_earnings_date,
    fetch_short_interest,
    fetch_upgrades_downgrades,
)
from backend.validation import TickerPath

logger = logging.getLogger(__name__)

router = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
# Refresh debounce constants
# ─────────────────────────────────────────────────────────────────────────────

REFRESH_DEBOUNCE_KEY = "refresh:debounce:{ticker}"
REFRESH_DEBOUNCE_TTL = 300  # 5 minutes


async def _try_dispatch_refresh(ticker: str) -> bool:
    """Dispatch a background refresh if not recently dispatched.

    Uses Redis SETNX with 5-min TTL to debounce. Returns True if a refresh
    was dispatched (or Redis is unavailable — fail-open), False if debounced.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        True if refresh was dispatched, False if debounced.
    """
    try:
        from backend.services.redis_pool import get_redis

        redis = await get_redis()
        acquired = await redis.set(
            REFRESH_DEBOUNCE_KEY.format(ticker=ticker.upper()),
            "1",
            ex=REFRESH_DEBOUNCE_TTL,
            nx=True,
        )
        if not acquired:
            return False  # debounced — already dispatched recently
    except Exception:
        logger.warning("Redis unavailable for refresh debounce %s", ticker, exc_info=True)
        # fail-open: dispatch anyway

    from backend.tasks.market_data import refresh_ticker_task

    refresh_ticker_task.delay(ticker)
    logger.info("Dispatched background refresh for stale ticker %s", ticker)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Price history
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{ticker}/prices", response_model=None)
async def get_prices(
    ticker: TickerPath,
    period: PricePeriod = Query(
        default=PricePeriod.ONE_YEAR, description="How far back to fetch prices"
    ),
    response_format: PriceFormat = Query(
        default=PriceFormat.LIST,
        alias="format",
        description="Response format: 'list' (default) or 'ohlc' for candlestick arrays",
    ),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> list[PricePointResponse] | OHLCResponse:
    """Get historical OHLCV prices for a stock.

    Returns daily price data from our database. The 'period' parameter
    controls how far back to look:
      - 1mo: last month (good for short-term trends)
      - 1y:  last year (good for seeing seasonal patterns)
      - 10y: last decade (good for long-term performance)

    The 'format' parameter controls the response shape:
      - list (default): array of {time, open, high, low, close, volume} objects
      - ohlc: parallel arrays grouped by field, optimized for candlestick charts

    The cutoff date is calculated by subtracting the period from today.
    For example, if period=1y and today is 2026-03-01, we return all
    prices from 2025-03-01 onwards.
    """
    await require_stock(ticker, db)

    period_days = {
        PricePeriod.ONE_MONTH: 30,
        PricePeriod.THREE_MONTHS: 90,
        PricePeriod.SIX_MONTHS: 180,
        PricePeriod.ONE_YEAR: 365,
        PricePeriod.TWO_YEARS: 730,
        PricePeriod.FIVE_YEARS: 1825,
        PricePeriod.TEN_YEARS: 3650,
    }
    cutoff = datetime.now(timezone.utc) - timedelta(days=period_days[period])

    result = await db.execute(
        select(StockPrice)
        .where(StockPrice.ticker == ticker.upper())
        .where(StockPrice.time >= cutoff)
        .order_by(StockPrice.time.asc())
    )

    rows = list(result.scalars().all())

    if response_format == PriceFormat.OHLC:
        return OHLCResponse(
            ticker=ticker.upper(),
            period=period.value,
            count=len(rows),
            timestamps=[r.time for r in rows],
            open=[float(r.open) for r in rows],
            high=[float(r.high) for r in rows],
            low=[float(r.low) for r in rows],
            close=[float(r.close) for r in rows],
            volume=[r.volume for r in rows],
        )

    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Signals
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{ticker}/signals", response_model=SignalResponse)
async def get_signals(
    ticker: TickerPath,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> SignalResponse:
    """Get the latest technical signals for a stock.

    Returns the most recently computed signal snapshot, which includes:
      - RSI: momentum indicator (oversold/neutral/overbought)
      - MACD: trend direction (bullish/bearish)
      - SMA: long-term trend (golden cross, death cross, etc.)
      - Bollinger Bands: volatility position
      - Returns: annualized return, volatility, Sharpe ratio
      - Composite Score: overall signal strength (0-10)

    Signals are flagged as "stale" if they're older than 24 hours,
    meaning they should be recomputed for accurate recommendations.
    """
    cache = getattr(request.app.state, "cache", None)
    cache_key = f"app:signals:{ticker.upper()}"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return SignalResponse.model_validate_json(cached)

    stock = await require_stock(ticker, db)

    snapshot = await get_latest_signals_svc(ticker, db)

    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No signals computed for '{ticker.upper()}'. "
            "Signals need to be computed first via the signal engine.",
        )

    is_stale = False
    is_refreshing = False
    if snapshot.computed_at:
        age = datetime.now(timezone.utc) - snapshot.computed_at.replace(tzinfo=timezone.utc)
        is_stale = age > timedelta(hours=24)

    # Auto-dispatch background refresh for stale signals (Spec C.4)
    if is_stale:
        await _try_dispatch_refresh(ticker)
        is_refreshing = True  # optimistic: either we dispatched or another request did

    response = SignalResponse(
        ticker=snapshot.ticker,
        computed_at=snapshot.computed_at,
        rsi=RSIResponse(value=snapshot.rsi_value, signal=snapshot.rsi_signal),
        macd=MACDResponse(
            value=snapshot.macd_value,
            histogram=snapshot.macd_histogram,
            signal=snapshot.macd_signal_label,
        ),
        sma=SMAResponse(
            sma_50=snapshot.sma_50,
            sma_200=snapshot.sma_200,
            signal=snapshot.sma_signal,
        ),
        bollinger=BollingerResponse(
            upper=snapshot.bb_upper,
            lower=snapshot.bb_lower,
            position=snapshot.bb_position,
        ),
        returns=ReturnsResponse(
            annual_return=snapshot.annual_return,
            volatility=snapshot.volatility,
            sharpe=snapshot.sharpe_ratio,
        ),
        composite_score=snapshot.composite_score,
        current_price=snapshot.current_price,
        change_pct=snapshot.change_pct,
        market_cap=stock.market_cap,
        is_stale=is_stale,
        is_refreshing=is_refreshing,
    )
    if cache and not is_stale:
        from backend.services.cache import CacheTier

        await cache.set(cache_key, response.model_dump_json(), CacheTier.STANDARD)
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Fundamentals
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{ticker}/fundamentals", response_model=FundamentalsResponse)
async def get_fundamentals(
    ticker: TickerPath,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> FundamentalsResponse:
    """Get fundamental financial metrics for a stock.

    Returns enriched fundamental data from the database (materialized
    during ingestion) including valuation ratios, growth rates, margins,
    analyst targets, and Piotroski F-Score.

    Note: Data is refreshed on each ingest. If fields are null, run
    ingest first. ETFs, SPACs, or very new listings may have missing data.
    """
    stock = await require_stock(ticker, db)
    t = ticker.upper().strip()

    cache = getattr(request.app.state, "cache", None)
    cache_key = f"app:fundamentals:{t}"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return FundamentalsResponse.model_validate_json(cached)

    result = await asyncio.get_event_loop().run_in_executor(None, fetch_fundamentals, t)

    response = FundamentalsResponse(
        ticker=result.ticker,
        pe_ratio=result.pe_ratio,
        peg_ratio=result.peg_ratio,
        fcf_yield=result.fcf_yield,
        debt_to_equity=result.debt_to_equity,
        piotroski_score=result.piotroski_score,
        piotroski_breakdown=PiotroskiBreakdown(**(result.piotroski_breakdown or {})),
        revenue_growth=stock.revenue_growth,
        gross_margins=stock.gross_margins,
        operating_margins=stock.operating_margins,
        profit_margins=stock.profit_margins,
        return_on_equity=stock.return_on_equity,
        market_cap=stock.market_cap,
        analyst_target_mean=stock.analyst_target_mean,
        analyst_target_high=stock.analyst_target_high,
        analyst_target_low=stock.analyst_target_low,
        analyst_buy=stock.analyst_buy,
        analyst_hold=stock.analyst_hold,
        analyst_sell=stock.analyst_sell,
    )
    if cache:
        from backend.services.cache import CacheTier

        await cache.set(cache_key, response.model_dump_json(), CacheTier.STABLE)
    return response


# ─────────────────────────────────────────────────────────────────────────────
# News
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{ticker}/news")
async def get_stock_news(
    ticker: TickerPath,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """Get recent news articles for a stock from multiple sources."""
    import asyncio
    from datetime import datetime, timezone

    from backend.schemas.intelligence import StockNewsResponse
    from backend.services.cache import CacheTier
    from backend.tools.news import (
        fetch_google_news_rss,
        fetch_yfinance_news,
        merge_and_deduplicate,
    )

    await require_stock(ticker, db)
    t = ticker.upper()

    cache = getattr(request.app.state, "cache", None)
    cache_key = f"app:news:{t}"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return StockNewsResponse.model_validate_json(cached)

    yf_articles = await asyncio.to_thread(fetch_yfinance_news, t)
    google_articles = await fetch_google_news_rss(t)
    merged = merge_and_deduplicate(yf_articles + google_articles)

    response = StockNewsResponse(
        ticker=t,
        articles=merged,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
    if cache:
        await cache.set(cache_key, response.model_dump_json(), CacheTier.VOLATILE)
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Intelligence
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{ticker}/intelligence")
async def get_stock_intelligence(
    ticker: TickerPath,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> StockIntelligenceResponse:
    """Get analyst upgrades, insider transactions, earnings calendar, EPS revisions.

    Fetches five data sources from Yahoo Finance in parallel. Each source is
    independently fault-tolerant — if one fails (e.g. network timeout, Yahoo
    rate-limit on cold start), it is replaced by a safe empty default so the
    other sources are still returned. This prevents intermittent 500 errors on
    the first request when the yfinance HTTP session is not yet warmed up.
    """
    from backend.services.cache import CacheTier

    await require_stock(ticker, db)
    t = ticker.upper()

    cache = getattr(request.app.state, "cache", None)
    cache_key = f"app:intelligence:{t}"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return StockIntelligenceResponse.model_validate_json(cached)

    # Fetch all five sources concurrently.
    # return_exceptions=True ensures a failure in one source does not cancel
    # the others and does not propagate as an unhandled 500 to the caller.
    results = await asyncio.gather(
        asyncio.to_thread(fetch_upgrades_downgrades, t),
        asyncio.to_thread(fetch_insider_transactions, t),
        asyncio.to_thread(fetch_next_earnings_date, t),
        asyncio.to_thread(fetch_eps_revisions, t),
        asyncio.to_thread(fetch_short_interest, t),
        return_exceptions=True,
    )

    upgrades_raw, insider_raw, earnings_raw, eps_raw, short_raw = results

    # Resolve each result: if an exception escaped the tool's own try/except
    # (e.g. yfinance network failure on cold start), substitute a safe default
    # and log the error so it can be investigated.
    if isinstance(upgrades_raw, BaseException):
        logger.error("fetch_upgrades_downgrades failed for %s", t, exc_info=upgrades_raw)
        upgrades_raw = []
    if isinstance(insider_raw, BaseException):
        logger.error("fetch_insider_transactions failed for %s", t, exc_info=insider_raw)
        insider_raw = []
    if isinstance(earnings_raw, BaseException):
        logger.error("fetch_next_earnings_date failed for %s", t, exc_info=earnings_raw)
        earnings_raw = None
    if isinstance(eps_raw, BaseException):
        logger.error("fetch_eps_revisions failed for %s", t, exc_info=eps_raw)
        eps_raw = None
    if isinstance(short_raw, BaseException):
        logger.error("fetch_short_interest failed for %s", t, exc_info=short_raw)
        short_raw = None

    response = StockIntelligenceResponse(
        ticker=t,
        upgrades_downgrades=upgrades_raw,
        insider_transactions=insider_raw,
        next_earnings_date=earnings_raw,
        eps_revisions=eps_raw,
        short_interest=short_raw,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
    if cache:
        await cache.set(cache_key, response.model_dump_json(), CacheTier.VOLATILE)
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark comparison
# ─────────────────────────────────────────────────────────────────────────────

# Maps index tickers to human-readable names
_BENCHMARK_INDICES: dict[str, str] = {
    "^GSPC": "S&P 500",
    "^IXIC": "NASDAQ Composite",
}

_STALENESS_HOURS = 24


async def _ensure_index_fresh(
    index_ticker: str,
    db: AsyncSession,
) -> bool:
    """Ensure a benchmark index has recent price data in the DB.

    Returns True if the index is available, False if ingestion failed.
    """
    try:
        await ensure_stock_exists(index_ticker, db)
    except (ValueError, Exception):
        logger.warning("Could not create Stock record for %s", index_ticker)
        return False

    # Check staleness — fetch delta if data is old or missing
    from sqlalchemy import func as sa_func

    result = await db.execute(
        select(sa_func.max(StockPrice.time)).where(StockPrice.ticker == index_ticker.upper())
    )
    max_time = result.scalar_one_or_none()

    if max_time is None or (
        datetime.now(timezone.utc) - max_time.replace(tzinfo=timezone.utc)
    ) > timedelta(hours=_STALENESS_HOURS):
        try:
            await fetch_prices_delta(index_ticker, db)
        except (ValueError, Exception):
            logger.warning("Failed to fetch prices for %s", index_ticker)
            # If we have *some* data, still usable; if none, not available
            return max_time is not None

    return True


@router.get(
    "/{ticker}/benchmark",
    response_model=BenchmarkComparisonResponse,
    summary="Benchmark comparison",
    description="Compare a stock's price performance against S&P 500 and NASDAQ, "
    "normalized to percentage change from the start of the period.",
    responses={
        404: {"description": "Stock not found or no price data"},
    },
)
async def get_benchmark(
    ticker: TickerPath,
    request: Request,
    period: PricePeriod = Query(
        default=PricePeriod.ONE_YEAR,
        description="How far back to compare",
    ),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> BenchmarkComparisonResponse:
    """Compare a stock's performance against S&P 500 and NASDAQ.

    Fetches price history for the requested ticker plus the two major
    indices, normalizes each series to percentage change from the first
    available date, and aligns all series to their common trading dates.

    If an index cannot be fetched, the response includes only the
    available series (graceful degradation).
    """
    stock = await require_stock(ticker, db)
    t = ticker.upper()

    # ── Cache check ───────────────────────────────────────────────────
    cache = getattr(request.app.state, "cache", None)
    cache_key = f"app:benchmark:{t}:{period.value}"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return BenchmarkComparisonResponse.model_validate_json(cached)

    # ── Ensure benchmark indices are fresh (parallel) ─────────────────
    index_results = await asyncio.gather(
        *[_ensure_index_fresh(idx, db) for idx in _BENCHMARK_INDICES],
    )

    # ── Query price data ──────────────────────────────────────────────
    period_days = {
        PricePeriod.ONE_MONTH: 30,
        PricePeriod.THREE_MONTHS: 90,
        PricePeriod.SIX_MONTHS: 180,
        PricePeriod.ONE_YEAR: 365,
        PricePeriod.TWO_YEARS: 730,
        PricePeriod.FIVE_YEARS: 1825,
        PricePeriod.TEN_YEARS: 3650,
    }
    cutoff = datetime.now(timezone.utc) - timedelta(days=period_days[period])

    # Tickers to query: always the stock, plus available indices
    tickers_to_query = [t]
    for idx_ticker, available in zip(_BENCHMARK_INDICES, index_results):
        if available:
            tickers_to_query.append(idx_ticker.upper())

    result = await db.execute(
        select(StockPrice)
        .where(StockPrice.ticker.in_(tickers_to_query))
        .where(StockPrice.time >= cutoff)
        .order_by(StockPrice.time.asc())
    )
    rows = list(result.scalars().all())

    # ── Group by ticker ───────────────────────────────────────────────
    prices_by_ticker: dict[str, list[tuple[datetime, float]]] = {}
    for row in rows:
        prices_by_ticker.setdefault(row.ticker, []).append((row.time, float(row.close)))

    # The stock must have price data
    if t not in prices_by_ticker or len(prices_by_ticker[t]) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No price data for '{t}' in the requested period.",
        )

    # ── Find common dates (intersection) ──────────────────────────────
    date_sets = [{d.date() for d, _ in series} for series in prices_by_ticker.values()]
    common_dates = sorted(set.intersection(*date_sets)) if date_sets else []

    if not common_dates:
        # Fall back to stock dates only
        common_dates = sorted({d.date() for d, _ in prices_by_ticker[t]})

    common_date_set = set(common_dates)

    # ── Build normalized series ───────────────────────────────────────
    series_list: list[BenchmarkSeries] = []

    # Name map: stock name from DB, indices from constant
    name_map: dict[str, str] = {t: stock.name or t}
    name_map.update({k.upper(): v for k, v in _BENCHMARK_INDICES.items()})

    for stk, price_list in prices_by_ticker.items():
        # Filter to common dates and sort
        filtered = sorted(
            [(d, c) for d, c in price_list if d.date() in common_date_set],
            key=lambda x: x[0],
        )
        if not filtered:
            continue

        first_close = filtered[0][1]
        if first_close == 0:
            continue  # avoid division by zero

        dates = [d for d, _ in filtered]
        pct = [(c - first_close) / first_close for _, c in filtered]

        series_list.append(
            BenchmarkSeries(
                ticker=stk,
                name=name_map.get(stk, stk),
                dates=dates,
                pct_change=pct,
            )
        )

    response = BenchmarkComparisonResponse(
        ticker=t,
        period=period.value,
        series=series_list,
    )

    # ── Cache ─────────────────────────────────────────────────────────
    if cache:
        from backend.services.cache import CacheTier

        await cache.set(cache_key, response.model_dump_json(), CacheTier.STANDARD)

    return response


# ─────────────────────────────────────────────────────────────────────────────
# Per-stock analytics (QuantStats)
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{ticker}/analytics",
    response_model=StockAnalyticsResponse,
    summary="Per-stock QuantStats analytics",
)
async def get_stock_analytics(
    ticker: TickerPath,
    db: AsyncSession = Depends(get_async_session),
    _user: User = Depends(get_current_user),
) -> StockAnalyticsResponse:
    """Return the latest QuantStats analytics for a stock from signal_snapshots."""
    from backend.models.signal import SignalSnapshot

    t = ticker.upper()
    await require_stock(t, db)

    result = await db.execute(
        select(SignalSnapshot)
        .where(SignalSnapshot.ticker == t)
        .order_by(SignalSnapshot.computed_at.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()

    if snapshot is None:
        return StockAnalyticsResponse(ticker=t)

    return StockAnalyticsResponse(
        ticker=t,
        sortino=snapshot.sortino,
        max_drawdown=snapshot.max_drawdown,
        alpha=snapshot.alpha,
        beta=snapshot.beta,
        data_days=snapshot.data_days,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Ingest state (Spec G.1)
# ─────────────────────────────────────────────────────────────────────────────


def _classify_stage(updated_at: datetime | None, sla_hours: float) -> IngestStageStatus:
    """Classify stage freshness against SLA threshold."""
    if updated_at is None:
        return IngestStageStatus.MISSING
    age_secs = (datetime.now(timezone.utc) - updated_at).total_seconds()
    if age_secs <= sla_hours * 3600:
        return IngestStageStatus.FRESH
    if age_secs <= 2 * sla_hours * 3600:
        return IngestStageStatus.STALE
    return IngestStageStatus.PENDING


@router.get(
    "/{ticker}/ingest-state",
    response_model=IngestStateResponse,
    summary="Get per-stage ingest freshness for a ticker",
    description=(
        "Returns 7-stage freshness breakdown with SLA-based classification. "
        "Backs the IngestProgressToast and StalenessBadge on stock detail."
    ),
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "Ticker not found in ingestion state table"},
    },
)
async def get_ingest_state(
    ticker: TickerPath,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> IngestStateResponse:
    """Return per-stage ingest freshness for one ticker."""
    from backend.config import settings
    from backend.models.ticker_ingestion_state import TickerIngestionState

    t = ticker.upper()
    row = (
        await db.execute(select(TickerIngestionState).where(TickerIngestionState.ticker == t))
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail="Ticker not found")

    slas = settings.staleness_slas

    def _stage(col_name: str, sla_hours: float) -> StageInfo:
        ts = getattr(row, col_name, None)
        return StageInfo(updated_at=ts, status=_classify_stage(ts, sla_hours))

    def _sla_hours(td: timedelta) -> float:
        return td.total_seconds() / 3600

    stages = IngestStateStages(
        prices=_stage("prices_updated_at", _sla_hours(slas.prices)),
        signals=_stage("signals_updated_at", _sla_hours(slas.signals)),
        fundamentals=_stage("fundamentals_updated_at", _sla_hours(slas.fundamentals)),
        forecast=_stage("forecast_updated_at", _sla_hours(slas.forecast)),
        news=_stage("news_updated_at", _sla_hours(slas.news)),
        sentiment=_stage("sentiment_updated_at", _sla_hours(slas.sentiment)),
        convergence=_stage("convergence_updated_at", _sla_hours(slas.convergence)),
    )

    all_stages = [
        stages.prices,
        stages.signals,
        stages.fundamentals,
        stages.forecast,
        stages.news,
        stages.sentiment,
        stages.convergence,
    ]
    fresh_count = sum(1 for s in all_stages if s.status == IngestStageStatus.FRESH)
    completion = round(fresh_count / 7 * 100)

    if fresh_count == 7:
        overall = "ready"
    elif any(
        s.status in (IngestStageStatus.PENDING, IngestStageStatus.MISSING) for s in all_stages
    ):
        overall = "ingesting"
    else:
        overall = "stale"

    return IngestStateResponse(
        ticker=t,
        stages=stages,
        overall_status=overall,
        completion_pct=completion,
    )
