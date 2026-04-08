"""Unit tests for the weekly-backtest Celery beat schedule entry (B2.4).

No database session required — asserts against the in-memory Celery config only.
"""

from celery.schedules import crontab


def test_weekly_beat_schedule_registered():
    """weekly-backtest entry must be present in the beat_schedule config.

    Verifies the entry is registered and points to the correct task.
    """
    from backend.tasks import celery_app

    assert "weekly-backtest" in celery_app.conf.beat_schedule
    entry = celery_app.conf.beat_schedule["weekly-backtest"]
    assert entry["task"] == "backend.tasks.forecasting.run_backtest_task"


def test_weekly_beat_schedule_is_saturday_0330():
    """weekly-backtest schedule must be Saturday (day_of_week=6) at 03:30.

    Validates the crontab schedule matches the spec: Saturday 03:30 ET.
    Moved from 03:00 to 03:30 to avoid collision with purge-login-attempts-daily
    which runs at 03:00 daily (including Saturdays).
    """
    from backend.tasks import celery_app

    entry = celery_app.conf.beat_schedule["weekly-backtest"]
    schedule = entry["schedule"]

    assert isinstance(schedule, crontab), f"Expected crontab, got {type(schedule).__name__}"
    # crontab stores schedule parts as ints or strings depending on Celery version;
    # compare as int to be version-agnostic.
    assert int(schedule._orig_hour) == 3, f"Expected hour=3, got {schedule._orig_hour}"
    assert int(schedule._orig_minute) == 30, f"Expected minute=30, got {schedule._orig_minute}"
    assert int(schedule._orig_day_of_week) == 6, (
        f"Expected day_of_week=6 (Saturday), got {schedule._orig_day_of_week}"
    )
