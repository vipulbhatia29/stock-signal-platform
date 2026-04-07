"""Celery application instance for background task processing."""

from celery import Celery

from backend.config import settings

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
    ],
)

celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.timezone = "US/Eastern"
celery_app.conf.enable_utc = True

# ── Beat schedule ──────────────────────────────────────────────────────────────
from celery.schedules import crontab  # noqa: E402

celery_app.conf.beat_schedule = {
    # ── Intraday refresh (every 30 min during market hours) ──
    "refresh-all-watchlist-tickers": {
        "task": "backend.tasks.market_data.refresh_all_watchlist_tickers_task",
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
    # ── Biweekly model retrain (every other Sunday 2 AM ET) ──
    # ── Audit trail purge (3 AM ET daily) ──
    "purge-login-attempts-daily": {
        "task": "backend.tasks.audit.purge_login_attempts_task",
        "schedule": crontab(hour=3, minute=0),
    },
    "purge-deleted-accounts-daily": {
        "task": "backend.tasks.audit.purge_deleted_accounts_task",
        "schedule": crontab(hour=3, minute=15),
    },
    "model-retrain-biweekly": {
        "task": "backend.tasks.forecasting.model_retrain_all_task",
        "schedule": crontab(hour=2, minute=0, day_of_week=0),  # Sunday 2 AM ET
        # Biweekly filtering handled at task level (check last retrain date)
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
    # ── Weekly walk-forward backtest (Saturday 03:00 ET) ──
    "weekly-backtest": {
        "task": "backend.tasks.forecasting.run_backtest_task",
        "schedule": crontab(hour=3, minute=0, day_of_week=6),  # Saturday 03:00
    },
}
