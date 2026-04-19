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
    "llm-call-log-retention-daily": {
        "task": "backend.tasks.retention.purge_old_llm_call_log_task",
        "schedule": crontab(hour=4, minute=15),
    },
    "tool-execution-log-retention-daily": {
        "task": "backend.tasks.retention.purge_old_tool_execution_log_task",
        "schedule": crontab(hour=4, minute=30),
    },
    "pipeline-runs-retention-daily": {
        "task": "backend.tasks.retention.purge_old_pipeline_runs_task",
        "schedule": crontab(hour=4, minute=45),
    },
    "dq-check-history-retention-daily": {
        "task": "backend.tasks.retention.purge_old_dq_check_history_task",
        "schedule": crontab(hour=5, minute=0),
    },
    # ── Obs 1b: HTTP layer retention ──
    "purge-request-logs-daily": {
        "task": "backend.tasks.retention.purge_old_request_logs_task",
        "schedule": crontab(hour=5, minute=15),
    },
    "purge-api-error-logs-daily": {
        "task": "backend.tasks.retention.purge_old_api_error_logs_task",
        "schedule": crontab(hour=5, minute=30),
    },
    # ── Obs 1b: Auth layer retention ──
    "purge-auth-event-logs-daily": {
        "task": "backend.tasks.retention.purge_old_auth_event_logs_task",
        "schedule": crontab(hour=5, minute=45),
    },
    "purge-oauth-event-logs-daily": {
        "task": "backend.tasks.retention.purge_old_oauth_event_logs_task",
        "schedule": crontab(hour=6, minute=0),
    },
    "purge-email-send-logs-daily": {
        "task": "backend.tasks.retention.purge_old_email_send_logs_task",
        "schedule": crontab(hour=6, minute=15),
    },
    # ── Obs 1b: DB + Cache layer retention ──
    "purge-slow-query-logs-daily": {
        "task": "backend.tasks.retention.purge_old_slow_query_logs_task",
        "schedule": crontab(hour=6, minute=30),
    },
    "purge-cache-operation-logs-daily": {
        "task": "backend.tasks.retention.purge_old_cache_operation_logs_task",
        "schedule": crontab(hour=6, minute=45),
    },
    "purge-db-pool-events-daily": {
        "task": "backend.tasks.retention.purge_old_db_pool_events_task",
        "schedule": crontab(hour=7, minute=5),
    },
    "purge-schema-migration-logs-daily": {
        "task": "backend.tasks.retention.purge_old_schema_migration_logs_task",
        "schedule": crontab(hour=7, minute=20),
    },
    # ── Obs 1b: Celery layer retention ──
    "purge-celery-heartbeats-daily": {
        "task": "backend.tasks.retention.purge_old_celery_heartbeats_task",
        "schedule": crontab(hour=7, minute=30),
    },
    "purge-beat-schedule-runs-daily": {
        "task": "backend.tasks.retention.purge_old_beat_schedule_runs_task",
        "schedule": crontab(hour=7, minute=45),
    },
    "purge-celery-queue-depths-daily": {
        "task": "backend.tasks.retention.purge_old_celery_queue_depths_task",
        "schedule": crontab(hour=8, minute=0),
    },
    # ── Obs 1b: Celery layer — queue depth polling ──
    "poll-queue-depths": {
        "task": "backend.tasks.observability.poll_queue_depths",
        "schedule": 60,  # every 60 seconds
    },
    # ── Obs 1b: Agent layer retention ──
    "purge-agent-intent-logs-daily": {
        "task": "backend.tasks.retention.purge_old_agent_intent_logs_task",
        "schedule": crontab(hour=8, minute=15),
    },
    "purge-agent-reasoning-logs-daily": {
        "task": "backend.tasks.retention.purge_old_agent_reasoning_logs_task",
        "schedule": crontab(hour=8, minute=30),
    },
    "purge-provider-health-snapshots-daily": {
        "task": "backend.tasks.retention.purge_old_provider_health_snapshots_task",
        "schedule": crontab(hour=8, minute=45),
    },
    # ── Obs 1b: Frontend + Deploy layer retention ──
    "purge-frontend-error-logs-daily": {
        "task": "backend.tasks.retention.purge_old_frontend_error_logs_task",
        "schedule": crontab(hour=9, minute=0),
    },
    "purge-deploy-events-daily": {
        "task": "backend.tasks.retention.purge_old_deploy_events_task",
        "schedule": crontab(hour=9, minute=15),
    },
    # ── Obs 1b: Agent layer — provider health snapshot ──
    "snapshot-provider-health": {
        "task": "backend.tasks.observability.snapshot_provider_health",
        "schedule": 60,  # every 60 seconds
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

    # Start heartbeat background thread (PR4)
    try:
        from backend.observability.instrumentation.celery import start_heartbeat

        sender = kwargs.get("sender")
        worker_name = getattr(sender, "hostname", "unknown") if sender else "unknown"
        start_heartbeat(worker_name)
    except Exception:  # noqa: BLE001 — heartbeat must not block worker startup
        _obs_logger.debug("obs.celery_heartbeat.start_failed", exc_info=True)


# Connect shutdown to both signals — guard inside _do_shutdown prevents double-fire.
@worker_process_shutdown.connect
def _shutdown_obs_on_process_shutdown(**kwargs):  # type: ignore[no-untyped-def]
    """Prefork pool: fires in each child process before exit."""
    _do_shutdown_obs_client()


@worker_shutdown.connect
def _shutdown_obs_on_worker_shutdown(**kwargs):  # type: ignore[no-untyped-def]
    """Solo/threads pool: fires when the main worker process shuts down."""
    # Stop heartbeat before obs client (PR4)
    try:
        from backend.observability.instrumentation.celery import stop_heartbeat

        sender = kwargs.get("sender")
        worker_name = getattr(sender, "hostname", "unknown") if sender else "unknown"
        stop_heartbeat(worker_name)
    except Exception:  # noqa: BLE001
        pass
    _do_shutdown_obs_client()


# ── Queue depth polling task (PR4) — NOT @tracked_task (avoids recursion) ──
@celery_app.task(name="backend.tasks.observability.poll_queue_depths")
def poll_queue_depths_task() -> dict:
    """Poll Redis queue depths and emit CELERY_QUEUE_DEPTH events.

    Uses Redis LLEN (O(1)). Runs every 60s via beat schedule.
    NOT a @tracked_task to avoid infinite recursion.
    """
    try:
        from backend.observability.instrumentation.celery import emit_queue_depth

        emit_queue_depth()
    except Exception:  # noqa: BLE001 — queue depth must not crash worker
        _obs_logger.debug("obs.queue_depth.poll_failed", exc_info=True)
    return {"status": "ok"}


# ── Provider health snapshot task (PR5) — NOT @tracked_task ──────────────
@celery_app.task(name="backend.tasks.observability.snapshot_provider_health")
def snapshot_provider_health_task() -> dict:
    """Snapshot all LLM provider health states every 60s.

    Iterates all configured providers and emits PROVIDER_HEALTH_SNAPSHOT events.
    NOT a @tracked_task to avoid recursion.
    """
    # LLMClient is request-scoped (FastAPI lifespan), not accessible from Celery.
    # Provider health snapshot emission is deferred to 1c when a shared provider
    # registry is available. Schema + table are ready for population.
    _obs_logger.debug("obs.provider_health.snapshot — no-op (deferred to 1c)")
    return {"status": "deferred"}


# ── Trace propagation — signal handlers register on import (PR3) ──────────
from backend.tasks import celery_trace_propagation  # noqa: E402, F401
