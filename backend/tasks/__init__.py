"""Celery application instance for background task processing."""

from celery import Celery

from backend.config import settings

celery_app = Celery(
    "stock_signal_platform",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["backend.tasks.market_data", "backend.tasks.portfolio"],
)

celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.timezone = "UTC"
celery_app.conf.enable_utc = True

# ── Beat schedule ──────────────────────────────────────────────────────────────
from celery.schedules import crontab  # noqa: E402

celery_app.conf.beat_schedule = {
    "refresh-all-watchlist-tickers": {
        "task": "backend.tasks.market_data.refresh_all_watchlist_tickers_task",
        "schedule": 30 * 60,  # 30 minutes in seconds
    },
    "snapshot-all-portfolios-daily": {
        "task": "backend.tasks.portfolio.snapshot_all_portfolios_task",
        "schedule": crontab(hour=21, minute=0),  # 9 PM UTC ≈ 4 PM ET (market close)
    },
}
