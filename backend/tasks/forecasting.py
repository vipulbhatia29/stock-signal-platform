"""Celery tasks for forecast model training and forecast refresh."""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

import backend.database as _db
from backend.config import settings
from backend.models.backtest import BacktestRun
from backend.models.forecast import ModelVersion
from backend.services.backtesting import BacktestEngine
from backend.services.feature_engineering import build_feature_dataframe
from backend.services.ticker_state import mark_stages_updated
from backend.services.ticker_universe import get_all_referenced_tickers
from backend.tasks import celery_app
from backend.tasks._asyncio_bridge import safe_asyncio_run
from backend.tasks.pipeline import PipelineRunner, tracked_task
from backend.tools.forecasting import MIN_DATA_POINTS

logger = logging.getLogger(__name__)

_runner = PipelineRunner()

MAX_NEW_MODELS_PER_NIGHT = 100


async def _fetch_ticker_prices(ticker: str, db: AsyncSession) -> pd.Series:
    """Fetch closing prices for a ticker from stock_prices.

    Args:
        ticker: Stock ticker symbol.
        db: Async database session.

    Returns:
        Series of adj_close prices with UTC DatetimeIndex, ordered by time.

    Raises:
        ValueError: If no price data exists for the ticker.
    """
    from backend.models.price import StockPrice

    result = await db.execute(
        select(StockPrice.time, StockPrice.adj_close)
        .where(StockPrice.ticker == ticker)
        .order_by(StockPrice.time.asc())
    )
    rows = result.all()
    if not rows:
        raise ValueError(f"No price data found for ticker {ticker!r}")

    df = pd.DataFrame(rows, columns=["time", "adj_close"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time")
    return df["adj_close"].astype(float)


async def _fetch_vix_and_spy(db: AsyncSession) -> tuple[pd.Series, pd.Series]:
    """Fetch VIX (yfinance) and SPY (DB first, then yfinance fallback) close series.

    VIX is always sourced from yfinance since we don't store it in stock_prices.
    SPY is fetched from the DB stock_prices table and falls back to yfinance if
    not present.

    Args:
        db: Async database session.

    Returns:
        Tuple of (vix_closes, spy_closes), both with UTC DatetimeIndex.

    Raises:
        RuntimeError: If VIX data cannot be downloaded from yfinance.
    """
    import yfinance as yf

    from backend.models.price import StockPrice

    # ── VIX — always from yfinance ─────────────────────────────────────────
    vix = await asyncio.to_thread(yf.download, "^VIX", period="1y", progress=False)
    if vix.empty:
        raise RuntimeError("Failed to download VIX data from yfinance")
    if isinstance(vix.columns, pd.MultiIndex):
        vix.columns = vix.columns.get_level_values(0)
    vix_closes = vix["Close"].copy()
    if vix_closes.index.tz is None:
        vix_closes.index = vix_closes.index.tz_localize("UTC")

    # ── SPY — DB first, yfinance fallback ─────────────────────────────────
    spy_result = await db.execute(
        select(StockPrice.time, StockPrice.adj_close)
        .where(StockPrice.ticker == "SPY")
        .order_by(StockPrice.time.asc())
    )
    spy_rows = spy_result.all()

    if spy_rows:
        spy_df = pd.DataFrame(spy_rows, columns=["time", "adj_close"])
        spy_df["time"] = pd.to_datetime(spy_df["time"], utc=True)
        spy_df = spy_df.set_index("time")
        spy_closes = spy_df["adj_close"].astype(float)
    else:
        logger.warning("No SPY data in DB — falling back to yfinance")
        spy_raw = await asyncio.to_thread(yf.download, "SPY", period="1y", progress=False)
        if spy_raw.empty:
            raise RuntimeError("Failed to download SPY data from yfinance")
        if isinstance(spy_raw.columns, pd.MultiIndex):
            spy_raw.columns = spy_raw.columns.get_level_values(0)
        spy_closes = spy_raw["Close"].copy()
        if spy_closes.index.tz is None:
            spy_closes.index = spy_closes.index.tz_localize("UTC")

    return vix_closes, spy_closes


async def _upsert_daily_feature_row(
    ticker: str, features_df: pd.DataFrame, db: AsyncSession
) -> None:
    """Upsert the latest (today's) feature row into historical_features.

    Takes the last row from features_df — forward return targets are set to
    None since future prices are unknown. Uses ON CONFLICT DO UPDATE on
    (date, ticker) so re-runs are idempotent.

    Args:
        ticker: Stock ticker symbol.
        features_df: DataFrame returned by build_feature_dataframe(); must be
            non-empty.
        db: Async database session.
    """
    from backend.models.historical_feature import HistoricalFeature

    last = features_df.iloc[-1]
    idx = features_df.index[-1]
    dt = idx.date() if hasattr(idx, "date") else idx

    values: dict = {
        "date": dt,
        "ticker": ticker,
        "momentum_21d": round(float(last["momentum_21d"]), 6),
        "momentum_63d": round(float(last["momentum_63d"]), 6),
        "momentum_126d": round(float(last["momentum_126d"]), 6),
        "rsi_value": round(float(last["rsi_value"]), 2),
        "macd_histogram": round(float(last["macd_histogram"]), 6),
        "sma_cross": int(last["sma_cross"]),
        "bb_position": int(last["bb_position"]),
        "volatility": round(float(last["volatility"]), 6),
        "sharpe_ratio": round(float(last["sharpe_ratio"]), 6),
        "vix_level": round(float(last["vix_level"]), 2),
        "spy_momentum_21d": round(float(last["spy_momentum_21d"]), 6),
        "stock_sentiment": None,
        "sector_sentiment": None,
        "macro_sentiment": None,
        "sentiment_confidence": None,
        "signals_aligned": None,
        "convergence_label": None,
        "forward_return_60d": None,
        "forward_return_90d": None,
    }

    stmt = pg_insert(HistoricalFeature).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["date", "ticker"],
        set_={k: stmt.excluded[k] for k in values if k not in ("date", "ticker")},
    )
    await db.execute(stmt)
    await db.commit()


@tracked_task("daily_features", trigger="scheduled")
async def _populate_daily_features_async(*, run_id: uuid.UUID) -> dict:
    """Compute and upsert today's feature row for every referenced ticker.

    Fetches VIX + SPY once, then for each ticker fetches close prices from
    the DB, runs build_feature_dataframe() in a thread (CPU-bound), and
    upserts only the latest row into historical_features. Tickers that fail
    are logged and skipped — the task continues for the remaining universe.

    Args:
        run_id: Pipeline run UUID injected by @tracked_task.

    Returns:
        Dict with status ("ok" | "disabled" | "degraded"), populated count,
        failed count, and list of failed tickers.
    """
    if not settings.DAILY_FEATURES_ENABLED:
        logger.info("DAILY_FEATURES_ENABLED=False — skipping")
        return {"status": "disabled"}

    async with _db.async_session_factory() as db:
        tickers = await get_all_referenced_tickers(db)
        if not tickers:
            logger.info("No tickers found — skipping daily feature population")
            return {"status": "ok", "populated": 0, "failed": 0, "failed_tickers": []}

        vix_closes, spy_closes = await _fetch_vix_and_spy(db)

    populated = 0
    failed: list[str] = []

    for ticker in tickers:
        try:
            async with _db.async_session_factory() as db:
                closes = await _fetch_ticker_prices(ticker, db)

            if len(closes) < 250:
                logger.debug(
                    "Skipping %s: only %d price rows (need 250+ for SMA warmup)",
                    ticker,
                    len(closes),
                )
                failed.append(ticker)
                continue

            features_df = await asyncio.to_thread(
                build_feature_dataframe,
                closes,
                vix_closes=vix_closes,
                spy_closes=spy_closes,
            )

            if features_df.empty:
                logger.warning("Empty feature DataFrame for %s — skipping", ticker)
                failed.append(ticker)
                continue

            async with _db.async_session_factory() as db:
                await _upsert_daily_feature_row(ticker, features_df, db)

            populated += 1
            logger.debug("Daily feature upserted for %s", ticker)

        except Exception:
            logger.exception("Daily feature population failed for %s", ticker)
            failed.append(ticker)

    status = "degraded" if failed else "ok"
    logger.info(
        "Daily feature population complete: populated=%d failed=%d status=%s",
        populated,
        len(failed),
        status,
    )
    return {
        "status": status,
        "populated": populated,
        "failed": len(failed),
        "failed_tickers": failed,
    }


@celery_app.task(name="backend.tasks.forecasting.populate_daily_features_task")
def populate_daily_features_task() -> dict:
    """Nightly task: compute today's feature row for every ticker (10:30 PM ET).

    Returns:
        Dict with status, populated count, failed count, and failed_tickers list.
    """
    logger.info("Starting daily feature population task")
    return safe_asyncio_run(_populate_daily_features_async())  # type: ignore[arg-type]


async def _get_price_data_counts(tickers: list[str], db: AsyncSession) -> dict[str, int]:
    """Count price data points per ticker (last 2 years) in a single query.

    Args:
        tickers: List of ticker symbols to check.
        db: Async database session.

    Returns:
        Dict mapping ticker to count of price data points.
    """
    from datetime import timedelta

    from sqlalchemy import func

    from backend.models.price import StockPrice

    two_years_ago = datetime.now(timezone.utc).date() - timedelta(days=730)
    result = await db.execute(
        select(StockPrice.ticker, func.count().label("cnt"))
        .where(StockPrice.ticker.in_(tickers), StockPrice.time >= two_years_ago)
        .group_by(StockPrice.ticker)
    )
    return {row.ticker: row.cnt for row in result.all()}


def _should_promote_challenger(
    champion_metrics: dict | None,
    challenger_metrics: dict,
) -> dict:
    """Decide whether a challenger model should replace the current champion.

    Promotion criteria (spec review O1):
    - Direction accuracy improves by ≥ CHAMPION_DIRECTION_THRESHOLD (default 1%)
    - OR CI containment improves by ≥ CHAMPION_CI_THRESHOLD (default 5%)
    - If no existing champion, always promote.
    - If CHAMPION_CHALLENGER_ENABLED=False, always promote.

    Args:
        champion_metrics: Current champion's metrics dict, or None if no champion.
        challenger_metrics: New challenger's metrics dict from training.

    Returns:
        Dict with "promote" (bool) and "reason" (str).
    """
    if not settings.CHAMPION_CHALLENGER_ENABLED:
        return {"promote": True, "reason": "champion/challenger disabled"}

    if champion_metrics is None:
        return {"promote": True, "reason": "no existing champion"}

    champ_dir = champion_metrics.get("direction_accuracy", 0.0)
    chall_dir = challenger_metrics.get("direction_accuracy", 0.0)
    dir_delta = chall_dir - champ_dir

    champ_ci = champion_metrics.get("ci_containment", 0.0)
    chall_ci = challenger_metrics.get("ci_containment", 0.0)
    ci_delta = chall_ci - champ_ci

    improved_metrics: list[str] = []
    dir_threshold = settings.CHAMPION_DIRECTION_THRESHOLD
    ci_threshold = settings.CHAMPION_CI_THRESHOLD

    if dir_delta >= dir_threshold:
        improved_metrics.append(f"direction_accuracy improved {dir_delta:+.4f} (≥{dir_threshold})")
    if ci_delta >= ci_threshold:
        improved_metrics.append(f"ci_containment improved {ci_delta:+.4f} (≥{ci_threshold})")

    if improved_metrics:
        return {"promote": True, "reason": "; ".join(improved_metrics)}

    return {
        "promote": False,
        "reason": (
            f"direction_accuracy delta={dir_delta:+.4f} (threshold={dir_threshold}), "
            f"ci_containment delta={ci_delta:+.4f} (threshold={ci_threshold})"
        ),
    }


@tracked_task("model_retrain", trigger="scheduled")
async def _model_retrain_all_async(*, run_id: uuid.UUID) -> dict:
    """Retrain forecast models for all tickers and generate forecasts.

    Loads all historical_features rows, trains a cross-ticker LightGBM+XGBoost
    ensemble for each horizon (60d, 90d), stores the serialised artifact as
    base64 in ModelVersion.hyperparameters, then predicts for every ticker.

    Returns:
        Dict with trained count, total tickers, and horizons trained.
    """
    import asyncio
    from datetime import timedelta

    import pandas as pd

    from backend.models.forecast import ForecastResult
    from backend.models.historical_feature import HistoricalFeature
    from backend.services.forecast_engine import FEATURE_NAMES, ForecastEngine

    engine = ForecastEngine()
    today = datetime.now(timezone.utc).date()

    # ── 1. Load training data ─────────────────────────────────────────────
    async with _db.async_session_factory() as db:
        tickers = await get_all_referenced_tickers(db)
        if not tickers:
            logger.info("No tickers to retrain")
            return {"trained": 0, "total": 0}

        result = await db.execute(
            select(HistoricalFeature)
            .where(HistoricalFeature.ticker.in_(tickers))
            .order_by(HistoricalFeature.date)
        )
        rows = result.scalars().all()

    if not rows:
        logger.warning("No historical features found — cannot train")
        return {"trained": 0, "total": 0}

    records = []
    for row in rows:
        record: dict = {"date": row.date, "ticker": row.ticker}
        for name in FEATURE_NAMES:
            record[name] = getattr(row, name, None)
        record["forward_return_60d"] = row.forward_return_60d
        record["forward_return_90d"] = row.forward_return_90d
        records.append(record)
    features_df = pd.DataFrame(records)

    # ── 2. Train one model bundle per horizon ────────────────────────────
    trained_models: dict[int, tuple[bytes, dict]] = {}
    for horizon in settings.DEFAULT_FORECAST_HORIZONS:
        try:
            artifact_bytes, metrics = await asyncio.to_thread(engine.train, features_df, horizon)
            trained_models[horizon] = (artifact_bytes, metrics)
            logger.info("Trained %dd model: %s", horizon, metrics)
        except Exception:
            logger.exception("Failed to train %dd model", horizon)

    if not trained_models:
        return {"trained": 0, "total": len(tickers)}

    # ── 3. Persist ModelVersion rows + predict for each ticker ───────────
    trained = 0
    async with _db.async_session_factory() as db:
        # Latest feature row per ticker (DISTINCT ON)
        latest_result = await db.execute(
            select(HistoricalFeature)
            .distinct(HistoricalFeature.ticker)
            .where(HistoricalFeature.ticker.in_(tickers))
            .order_by(HistoricalFeature.ticker, HistoricalFeature.date.desc())
        )
        latest_features = {row.ticker: row for row in latest_result.scalars().all()}

        # Latest close price per ticker
        from backend.models.price import StockPrice

        price_result = await db.execute(
            select(StockPrice.ticker, StockPrice.close)
            .distinct(StockPrice.ticker)
            .where(StockPrice.ticker.in_(tickers))
            .order_by(StockPrice.ticker, StockPrice.time.desc())
        )
        prices = {row.ticker: float(row.close) for row in price_result.all()}

        for horizon, (artifact_bytes, metrics) in trained_models.items():
            model_type = f"lightgbm_{horizon}d"

            # ── Champion/challenger gate ───────────────────────────────────
            champ_result = await db.execute(
                select(ModelVersion).where(
                    ModelVersion.model_type == model_type,
                    ModelVersion.is_active.is_(True),
                )
            )
            champion = champ_result.scalar_one_or_none()
            champion_metrics = champion.metrics if champion else None

            promotion = _should_promote_challenger(champion_metrics, metrics)

            if not promotion["promote"]:
                logger.info(
                    "Champion/challenger: keeping champion for %s — %s",
                    model_type,
                    promotion["reason"],
                )
                if champion:
                    updated = dict(champion.metrics or {})
                    updated["last_challenger_comparison"] = {
                        "challenger_metrics": metrics,
                        "decision": "kept_champion",
                        "reason": promotion["reason"],
                        "compared_at": datetime.now(timezone.utc).isoformat(),
                    }
                    champion.metrics = updated
                continue

            logger.info(
                "Champion/challenger: promoting challenger for %s — %s",
                model_type,
                promotion["reason"],
            )

            # Bump version number
            max_ver_result = await db.execute(
                select(func.max(ModelVersion.version)).where(
                    ModelVersion.model_type == model_type,
                )
            )
            max_ver = max_ver_result.scalar() or 0

            # Retire all previously active models of this type
            await db.execute(
                update(ModelVersion)
                .where(
                    ModelVersion.model_type == model_type,
                    ModelVersion.is_active.is_(True),
                )
                .values(is_active=False)
            )

            mv = ModelVersion(
                ticker="__universe__",
                model_type=model_type,
                version=max_ver + 1,
                is_active=True,
                trained_at=datetime.now(timezone.utc),
                training_data_start=features_df["date"].min(),
                training_data_end=features_df["date"].max(),
                data_points=len(features_df),
                hyperparameters={
                    "ensemble_weight_lgb": 0.5,
                    "ensemble_weight_xgb": 0.5,
                    "artifact_b64": base64.b64encode(artifact_bytes).decode("ascii"),
                },
                metrics=metrics,
                status="active",
                artifact_path=None,
            )
            db.add(mv)
            await db.flush()  # obtain mv.id before FK reference

            for ticker in tickers:
                feat_row = latest_features.get(ticker)
                base_price = prices.get(ticker)
                if feat_row is None or base_price is None:
                    continue

                feature_dict = {name: getattr(feat_row, name, None) for name in FEATURE_NAMES}
                try:
                    pred = await asyncio.to_thread(
                        engine.predict, feature_dict, artifact_bytes, None, False
                    )
                    fc = ForecastResult(
                        forecast_date=today,
                        ticker=ticker,
                        horizon_days=horizon,
                        model_version_id=mv.id,
                        expected_return_pct=round(pred["expected_return_pct"], 2),
                        return_lower_pct=round(pred["return_lower_pct"], 2),
                        return_upper_pct=round(pred["return_upper_pct"], 2),
                        target_date=today + timedelta(days=horizon),
                        confidence_score=round(pred["confidence"], 4),
                        direction=pred["direction"],
                        drivers=pred.get("drivers"),
                        base_price=base_price,
                        forecast_signal=pred.get("forecast_signal"),
                        created_at=datetime.now(timezone.utc),
                    )
                    db.add(fc)
                except Exception:
                    logger.exception("Failed to predict %s %dd", ticker, horizon)
                    continue

            await db.commit()
            trained += 1

    await mark_stages_updated(tickers, "forecast")
    await _runner.record_ticker_success(run_id, "__universe__")

    return {"trained": trained, "total": len(tickers), "horizons": list(trained_models.keys())}


@tracked_task("forecast_refresh", trigger="scheduled")
async def _forecast_refresh_async(*, run_id: uuid.UUID) -> dict:
    """Refresh forecasts using existing active models (no retraining).

    Loads each active ModelVersion's serialised artifact from
    ``hyperparameters["artifact_b64"]`` and runs predictions for all tickers
    that have a recent feature row.

    Returns:
        Dict with refreshed count and total tickers.
    """
    import asyncio
    from datetime import timedelta

    from backend.models.forecast import ForecastResult
    from backend.models.historical_feature import HistoricalFeature
    from backend.models.price import StockPrice
    from backend.services.forecast_engine import FEATURE_NAMES, ForecastEngine

    engine = ForecastEngine()
    today = datetime.now(timezone.utc).date()

    async with _db.async_session_factory() as db:
        # Active models (one per model_type)
        result = await db.execute(select(ModelVersion).where(ModelVersion.is_active.is_(True)))
        active_models = result.scalars().all()

        if not active_models:
            logger.info("No active models — skipping forecast refresh")
            return {"refreshed": 0, "total": 0}

        # Map horizon → ModelVersion for parseable model_types (e.g. "lightgbm_60d")
        model_by_horizon: dict[int, ModelVersion] = {}
        for mv in active_models:
            parts = mv.model_type.split("_")
            if len(parts) >= 2 and parts[-1].endswith("d"):
                try:
                    h = int(parts[-1][:-1])
                    model_by_horizon[h] = mv
                except ValueError:  # nosemgrep: semgrep.obs-warn-silent-except
                    logger.debug("Unparseable model_type horizon: %s", mv.model_type)

        if not model_by_horizon:
            logger.info("No models with parseable horizons — skipping")
            return {"refreshed": 0, "total": 0}

        all_tickers = await get_all_referenced_tickers(db)

        # Latest feature row per ticker (DISTINCT ON)
        latest_result = await db.execute(
            select(HistoricalFeature)
            .distinct(HistoricalFeature.ticker)
            .where(HistoricalFeature.ticker.in_(all_tickers))
            .order_by(HistoricalFeature.ticker, HistoricalFeature.date.desc())
        )
        latest_features = {row.ticker: row for row in latest_result.scalars().all()}

        # Latest close price per ticker
        price_result = await db.execute(
            select(StockPrice.ticker, StockPrice.close)
            .distinct(StockPrice.ticker)
            .where(StockPrice.ticker.in_(all_tickers))
            .order_by(StockPrice.ticker, StockPrice.time.desc())
        )
        prices = {row.ticker: float(row.close) for row in price_result.all()}

        refreshed = 0
        refreshed_tickers: list[str] = []

        for ticker in all_tickers:
            feat_row = latest_features.get(ticker)
            base_price = prices.get(ticker)
            if feat_row is None or base_price is None:
                continue

            feature_dict = {name: getattr(feat_row, name, None) for name in FEATURE_NAMES}

            for horizon, mv in model_by_horizon.items():
                artifact_b64: str | None = (mv.hyperparameters or {}).get("artifact_b64")
                if not artifact_b64:
                    logger.debug(
                        "No artifact stored for model %s (%s) — skipping %s",
                        mv.id,
                        mv.model_type,
                        ticker,
                    )
                    continue

                artifact_bytes = base64.b64decode(artifact_b64)
                try:
                    pred = await asyncio.to_thread(
                        engine.predict, feature_dict, artifact_bytes, None, False
                    )
                    fc = ForecastResult(
                        forecast_date=today,
                        ticker=ticker,
                        horizon_days=horizon,
                        model_version_id=mv.id,
                        expected_return_pct=round(pred["expected_return_pct"], 2),
                        return_lower_pct=round(pred["return_lower_pct"], 2),
                        return_upper_pct=round(pred["return_upper_pct"], 2),
                        target_date=today + timedelta(days=horizon),
                        confidence_score=round(pred["confidence"], 4),
                        direction=pred["direction"],
                        drivers=pred.get("drivers"),
                        base_price=base_price,
                        forecast_signal=pred.get("forecast_signal"),
                        created_at=datetime.now(timezone.utc),
                    )
                    db.add(fc)
                except Exception:
                    logger.exception("Failed to refresh %s %dd", ticker, horizon)
                    continue

            refreshed_tickers.append(ticker)
            refreshed += 1

        await db.commit()

        # ── Dispatch training for new tickers without features ────────────
        try:
            modeled_tickers = set(latest_features.keys())
            new_tickers = [t for t in all_tickers if t not in modeled_tickers]

            if new_tickers:
                counts = await _get_price_data_counts(new_tickers, db)
                dispatched = 0
                for ticker in new_tickers:
                    if dispatched >= MAX_NEW_MODELS_PER_NIGHT:
                        break
                    if counts.get(ticker, 0) >= MIN_DATA_POINTS:
                        retrain_single_ticker_task.delay(ticker)
                        dispatched += 1
                        logger.info(
                            "Dispatched first-time training for %s (%d data points)",
                            ticker,
                            counts[ticker],
                        )
                    else:
                        logger.debug(
                            "Skipping %s: only %d data points (need %d)",
                            ticker,
                            counts.get(ticker, 0),
                            MIN_DATA_POINTS,
                        )

                if dispatched:
                    logger.info("Dispatched training for %d new tickers", dispatched)
        except Exception:
            logger.warning("Failed to dispatch new-ticker training", exc_info=True)

        if refreshed_tickers:
            await mark_stages_updated(refreshed_tickers, "forecast")

    return {"refreshed": refreshed, "total": len(all_tickers)}


@celery_app.task(
    name="backend.tasks.forecasting.model_retrain_all_task",
)
def model_retrain_all_task() -> dict:
    """Weekly full retrain of all forecast models (Sunday 02:00 ET).

    Returns:
        Dict with training status and counts.
    """
    logger.info("Starting weekly full model retrain")

    return safe_asyncio_run(_model_retrain_all_async())  # type: ignore[arg-type]  # wrapper is async def, pyright sees Awaitable not Coroutine


@celery_app.task(
    name="backend.tasks.forecasting.forecast_refresh_task",
)
def forecast_refresh_task() -> dict:
    """Nightly forecast refresh using existing active forecast models (no retrain).

    Returns:
        Dict with refresh status and counts.
    """
    logger.info("Starting nightly forecast refresh")

    return safe_asyncio_run(_forecast_refresh_async())  # type: ignore[arg-type]  # wrapper is async def, pyright sees Awaitable not Coroutine


@tracked_task("single_ticker_retrain")
async def _retrain_single_ticker_async(ticker: str, *, run_id: uuid.UUID) -> dict:
    """Single-ticker retrain — delegates to full retrain since LightGBM is cross-ticker.

    LightGBM/XGBoost models are trained on the entire ticker universe so a
    single-ticker retrain makes no sense in isolation.  We dispatch a full
    retrain instead and return immediately.

    Args:
        ticker: Stock ticker that triggered the retrain request.
        run_id: Pipeline run ID injected by @tracked_task.

    Returns:
        Dict indicating that a full retrain was dispatched.
    """
    logger.info(
        "Single ticker retrain requested for %s — LightGBM is cross-ticker, "
        "triggering full retrain",
        ticker,
    )
    model_retrain_all_task.delay()
    return {"ticker": ticker, "status": "full_retrain_dispatched"}


@celery_app.task(
    name="backend.tasks.forecasting.retrain_single_ticker_task",
)
def retrain_single_ticker_task(ticker: str, priority: bool = False) -> dict:
    """Retrain a single ticker's forecast model.

    Args:
        ticker: Stock ticker to retrain.
        priority: If True, user-initiated retrain that bypasses the nightly
            sweep cap (Spec E.1). Passed through from ingest_ticker.

    Returns:
        Dict with training result.
    """
    logger.info("Retraining %s (priority=%s)", ticker, priority)

    return safe_asyncio_run(_retrain_single_ticker_async(ticker))  # type: ignore[arg-type]


@tracked_task("backtest")
async def _run_backtest_async(ticker: str | None, horizon_days: int, *, run_id: uuid.UUID) -> dict:
    """Async implementation of walk-forward backtest for one or all tickers.

    Args:
        ticker: Specific ticker symbol, or None to run for all referenced tickers.
        horizon_days: Forecast horizon to validate.

    Returns:
        Dict with status, completed count, failed count, horizon, and ticker.
    """
    if not settings.BACKTEST_ENABLED:
        logger.info("BACKTEST_ENABLED=False — skipping")
        return {"status": "disabled"}

    engine = BacktestEngine()
    completed = 0
    failed: list[str] = []
    successful_tickers: list[str] = []

    # Resolve the ticker universe in its own short-lived session so we never
    # hold a connection open while iterating below.
    async with _db.async_session_factory() as db:
        tickers = [ticker] if ticker else await get_all_referenced_tickers(db)

    for tkr in tickers:
        # Per-ticker session: the primary motivation is session-state
        # isolation — a SQLAlchemy InvalidRequestError / PendingRollbackError
        # from a poisoned transaction in one ticker must not bleed into
        # the next iteration's reads. (Per-ticker checkouts add modest
        # connection-pool churn vs the old single-session pattern, but
        # that trade-off is intentional.) The outer try/except also catches
        # transient session-acquisition failures (asyncpg connection drop,
        # pool timeout) so one bad checkout cannot abort the weekly chain.
        try:
            async with _db.async_session_factory() as db:
                try:
                    metrics = await engine.run_walk_forward(tkr, db, horizon_days=horizon_days)

                    # Look up the active model version for this ticker — required FK.
                    # Accept any active model type (no longer restricted to "prophet").
                    mv_result = await db.execute(
                        select(ModelVersion)
                        .where(
                            ModelVersion.ticker == tkr,
                            ModelVersion.is_active.is_(True),
                        )
                        .limit(1)
                    )
                    model_version = mv_result.scalar_one_or_none()
                    if model_version is None:
                        logger.warning(
                            "run_backtest_task: no active ModelVersion for %s — "
                            "cannot persist BacktestRun row; marking as failed",
                            tkr,
                        )
                        failed.append(tkr)
                        continue

                    today = datetime.now(timezone.utc).date()
                    values = {
                        "ticker": tkr,
                        "model_version_id": model_version.id,
                        "config_label": "walk_forward",
                        "train_start": model_version.training_data_start,
                        "train_end": model_version.training_data_end,
                        "test_start": today,
                        "test_end": today,
                        "horizon_days": horizon_days,
                        "num_windows": metrics.num_windows,
                        "mape": metrics.mape,
                        "mae": metrics.mae,
                        "rmse": metrics.rmse,
                        "direction_accuracy": metrics.direction_accuracy,
                        "ci_containment": metrics.ci_containment,
                    }
                    stmt = pg_insert(BacktestRun).values(values)
                    stmt = stmt.on_conflict_do_update(
                        constraint="uq_backtest_runs_ticker_mv_config_date_horizon",
                        set_={
                            **{
                                k: stmt.excluded[k]
                                for k in (
                                    "train_start",
                                    "train_end",
                                    "test_end",
                                    "num_windows",
                                    "mape",
                                    "mae",
                                    "rmse",
                                    "direction_accuracy",
                                    "ci_containment",
                                )
                            },
                            "updated_at": func.now(),
                        },
                    )
                    await db.execute(stmt)
                    await db.commit()
                    successful_tickers.append(tkr)
                    completed += 1

                except Exception:
                    await db.rollback()
                    logger.exception("Backtest failed for %s", tkr)
                    failed.append(tkr)
        except Exception:
            # Failure to acquire a session — log and skip this ticker so the
            # run continues. Without this guard a transient pool blip would
            # abort the entire weekly chain with hundreds of tickers unprocessed.
            logger.exception(
                "Failed to acquire session for backtest of %s — skipping",
                tkr,
            )
            failed.append(tkr)

    # ── Bulk-mark backtest stage for every successful ticker ──────────
    # Single bulk upsert outside the per-ticker session loop. Fire-and-forget
    # — observability state, must not roll back the BacktestRun rows we
    # already persisted above.
    if successful_tickers:
        await mark_stages_updated(successful_tickers, "backtest")

    status = "degraded" if failed else "ok"
    return {
        "status": status,
        "completed": completed,
        "failed": len(failed),
        "failed_tickers": failed,
        "horizon_days": horizon_days,
        "ticker": ticker,
    }


@celery_app.task(
    name="backend.tasks.forecasting.run_backtest_task",
    soft_time_limit=3300,
    time_limit=3600,
)
def run_backtest_task(ticker: str | None = None, horizon_days: int = 90) -> dict:
    """Run walk-forward backtest for a ticker or all active tickers.

    Args:
        ticker: Specific ticker, or None for all active tickers.
        horizon_days: Forecast horizon to backtest.

    Returns:
        Dict with backtest results summary.
    """
    logger.info("Backtest task started: ticker=%s, horizon=%d", ticker or "all", horizon_days)

    return safe_asyncio_run(_run_backtest_async(ticker, horizon_days))  # type: ignore[arg-type]
