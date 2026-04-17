"""Celery application instance for background task processing."""

import asyncio
import logging
import threading

from celery import Celery
from celery.signals import (
    worker_process_init,
    worker_process_shutdown,
    worker_ready,
    worker_shutdown,
)

from backend.config import settings
from backend.observability.bootstrap import build_client_from_settings, obs_client_var

celery_app = Celery(
    "stock_signal_platform",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "backend.tasks.market_data",
        "backend.tasks.portfolio",
        "backend.tasks.warm_data",
        "backend.tasks.recommendations",
        "backend.tasks.forecasting",
        "backend.tasks.evaluation",
        "backend.tasks.alerts",
        "backend.tasks.pipeline",
        "backend.tasks.audit",
        "backend.tasks.convergence",
        "backend.tasks.seed_tasks",
        "backend.tasks.news_sentiment",
        "backend.tasks.dq_scan",
        "backend.tasks.retention",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="US/Eastern",
    enable_utc=True,
)

# ── Beat schedule ──────────────────────────────────────────────────────────────
from celery.schedules import crontab  # noqa: E402

celery_app.conf.beat_schedule = {
    # ── Intraday refresh (every 30 min during market hours) ──
    "intraday-refresh-all": {
        "task": "backend.tasks.market_data.intraday_refresh_all_task",
        "schedule": 30 * 60,  # 30 minutes in seconds
    },
    # ── Nightly pipeline chain (9:30 PM ET — after market data settles) ──
    "nightly-pipeline": {
        "task": "backend.tasks.market_data.nightly_pipeline_chain_task",
        "schedule": crontab(hour=21, minute=30),
    },
    # ── Daily portfolio snapshots (market close, 4 PM ET) ──
    "snapshot-all-portfolios-daily": {
        "task": "backend.tasks.portfolio.snapshot_all_portfolios_task",
        "schedule": crontab(hour=16, minute=30),
    },
    "snapshot-portfolio-health-daily": {
        "task": "backend.tasks.portfolio.snapshot_health_task",
        "schedule": crontab(hour=16, minute=45),  # 15 min after value snapshot
    },
    # ── Warm data sync ──
    "sync-analyst-consensus": {
        "task": "backend.tasks.warm_data.sync_analyst_consensus_task",
        "schedule": crontab(hour=6, minute=0),  # 6 AM ET
    },
    "sync-fred-indicators": {
        "task": "backend.tasks.warm_data.sync_fred_indicators_task",
        "schedule": crontab(hour=7, minute=0),  # 7 AM ET
    },
    "sync-institutional-holders": {
        "task": "backend.tasks.warm_data.sync_institutional_holders_task",
        "schedule": crontab(hour=2, minute=0, day_of_week=0),  # Sunday 2 AM ET
    },
    # ── Audit trail purge (3 AM ET daily) ──
    "purge-login-attempts-daily": {
        "task": "backend.tasks.audit.purge_login_attempts_task",
        "schedule": crontab(hour=3, minute=0),
    },
    "purge-deleted-accounts-daily": {
        "task": "backend.tasks.audit.purge_deleted_accounts_task",
        "schedule": crontab(hour=3, minute=15),
    },
    "model-retrain-weekly": {
        "task": "backend.tasks.forecasting.model_retrain_all_task",
        "schedule": crontab(hour=2, minute=0, day_of_week=0),  # Sunday 2 AM ET
    },
    # ── News sentiment pipeline (4x daily during market hours) ──
    "news-ingest": {
        "task": "backend.tasks.news_sentiment.news_ingest_task",
        "schedule": crontab(hour="6,10,14,18", minute=0),  # ET
    },
    "news-sentiment-scoring": {
        "task": "backend.tasks.news_sentiment.news_sentiment_scoring_task",
        "schedule": crontab(hour="7,11,15,19", minute=0),  # 1h after ingest
    },
    # ── Nightly DQ scan (4 AM ET daily) ──
    "dq-scan-daily": {
        "task": "backend.tasks.dq_scan.dq_scan_task",
        "schedule": crontab(hour=4, minute=0),
    },
    # ── Nightly retention purges ──
    "forecast-retention-daily": {
        "task": "backend.tasks.retention.purge_old_forecasts_task",
        "schedule": crontab(hour=3, minute=30),
    },
    "news-retention-daily": {
        "task": "backend.tasks.retention.purge_old_news_articles_task",
        "schedule": crontab(hour=3, minute=45),
    },
    # ── Weekly walk-forward backtest (Saturday 03:30 ET) ──
    "weekly-backtest": {
        "task": "backend.tasks.forecasting.run_backtest_task",
        # Saturday 03:30 ET — avoids 03:00 collision with purge-login-attempts-daily
        "schedule": crontab(hour=3, minute=30, day_of_week=6),
    },
}

# ── Observability SDK — worker lifecycle signals (PR2a) ─────────────────────
_worker_obs_client = None
_worker_obs_loop: asyncio.AbstractEventLoop | None = None
_worker_obs_thread: threading.Thread | None = None

_obs_logger = logging.getLogger(__name__)


def _run_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Run an event loop on a daemon thread until stopped."""
    asyncio.set_event_loop(loop)
    loop.run_forever()


def _do_init_obs_client() -> None:
    """Start a persistent event loop on a daemon thread for obs client background tasks.

    Connected to BOTH ``worker_process_init`` (prefork children) AND ``worker_ready``
    (solo/threads pool). Guard prevents double-init when both fire.

    Why two signals? ``worker_process_init`` fires in each forked child process after
    fork — ContextVars and daemon threads don't survive fork(), so the client MUST be
    built in the process that runs tasks. ``worker_ready`` fires in the main process,
    which IS the task process for solo pool (dev). Connecting to both covers all pools.

    @tracked_task invokes via asyncio.run() per call — fresh loop per task.
    Pinning the obs client's flush loop to a dedicated, long-lived loop on a
    daemon thread survives across tasks + avoids loop-mismatch on shared state.

    Failure mode: if start() times out, fail-closed — tear down the loop/thread
    and leave obs_client_var unset. Emissions silently drop for the worker's lifetime.
    """
    global _worker_obs_client, _worker_obs_loop, _worker_obs_thread  # noqa: PLW0603
    if _worker_obs_client is not None:
        return  # already initialized (guard against double-fire)
    _worker_obs_loop = asyncio.new_event_loop()
    _worker_obs_thread = threading.Thread(
        target=_run_loop, args=(_worker_obs_loop,), daemon=True, name="obs-loop"
    )
    _worker_obs_thread.start()
    client = build_client_from_settings()
    fut = asyncio.run_coroutine_threadsafe(client.start(), _worker_obs_loop)
    try:
        fut.result(timeout=5.0)
    except Exception:  # noqa: BLE001 — TimeoutError, CancelledError, anything
        _obs_logger.warning(
            "obs.worker.start_failed — observability disabled for this worker",
            exc_info=True,
        )
        fut.cancel()
        _worker_obs_loop.call_soon_threadsafe(_worker_obs_loop.stop)
        _worker_obs_thread.join(timeout=2.0)
        _worker_obs_client = None
        _worker_obs_loop = None
        _worker_obs_thread = None
        return
    _worker_obs_client = client
    obs_client_var.set(_worker_obs_client)


def _do_shutdown_obs_client() -> None:
    """Drain and stop the worker-local observability client.

    Connected to BOTH ``worker_process_shutdown`` and ``worker_shutdown``.
    Guard prevents double-shutdown.
    """
    global _worker_obs_client, _worker_obs_loop, _worker_obs_thread  # noqa: PLW0603
    if _worker_obs_client is None or _worker_obs_loop is None:
        return
    try:
        asyncio.run_coroutine_threadsafe(_worker_obs_client.stop(), _worker_obs_loop).result(
            timeout=10.0
        )
    except Exception:  # noqa: BLE001
        pass  # shutdown must not raise
    _worker_obs_loop.call_soon_threadsafe(_worker_obs_loop.stop)
    if _worker_obs_thread:
        _worker_obs_thread.join(timeout=5.0)
    _worker_obs_client = None
    _worker_obs_loop = None
    _worker_obs_thread = None
    obs_client_var.set(None)


# Connect init to both signals — guard inside _do_init prevents double-fire.
@worker_process_init.connect
def _init_obs_on_process_init(**kwargs):  # type: ignore[no-untyped-def]
    """Prefork pool: fires in each forked child process."""
    from backend.core.logging import configure_structlog

    configure_structlog()
    _do_init_obs_client()


@worker_ready.connect
def _init_obs_on_worker_ready(**kwargs):  # type: ignore[no-untyped-def]
    """Solo/threads pool: fires in the main worker process."""
    from backend.core.logging import configure_structlog

    configure_structlog()
    _do_init_obs_client()


# Connect shutdown to both signals — guard inside _do_shutdown prevents double-fire.
@worker_process_shutdown.connect
def _shutdown_obs_on_process_shutdown(**kwargs):  # type: ignore[no-untyped-def]
    """Prefork pool: fires in each child process before exit."""
    _do_shutdown_obs_client()


@worker_shutdown.connect
def _shutdown_obs_on_worker_shutdown(**kwargs):  # type: ignore[no-untyped-def]
    """Solo/threads pool: fires when the main worker process shuts down."""
    _do_shutdown_obs_client()


# ── Trace propagation — signal handlers register on import (PR3) ──────────
from backend.tasks import celery_trace_propagation  # noqa: E402, F401
