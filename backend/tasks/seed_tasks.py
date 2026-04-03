"""Celery task wrappers for all seed scripts.

Each task wraps an async seed function via asyncio.run() bridge.
Tasks use bind=True to report progress via self.update_state().
"""

import asyncio
import logging

from backend.tasks import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="backend.tasks.seed_tasks.seed_sp500_task")
def seed_sp500_task(self, dry_run: bool = False) -> dict:
    """Sync S&P 500 constituents.

    Args:
        dry_run: If True, show what would be synced without writing.

    Returns:
        Dict with status and result.
    """
    from scripts.sync_sp500 import main

    self.update_state(state="PROGRESS", meta={"step": "syncing_sp500", "progress": 0})
    result = asyncio.run(main(dry_run=dry_run))
    return {"status": "complete", "result": result}


@celery_app.task(bind=True, name="backend.tasks.seed_tasks.seed_indexes_task")
def seed_indexes_task(self, dry_run: bool = False) -> dict:
    """Sync index constituents (Nasdaq 100, Dow 30, Russell 2000).

    Args:
        dry_run: If True, show what would be synced without writing.

    Returns:
        Dict with status and result.
    """
    from scripts.sync_indexes import main

    self.update_state(state="PROGRESS", meta={"step": "syncing_indexes", "progress": 0})
    result = asyncio.run(main(dry_run=dry_run))
    return {"status": "complete", "result": result}


@celery_app.task(bind=True, name="backend.tasks.seed_tasks.seed_etfs_task")
def seed_etfs_task(self) -> dict:
    """Seed ETF universe.

    Returns:
        Dict with status and result.
    """
    from scripts.seed_etfs import main

    self.update_state(state="PROGRESS", meta={"step": "seeding_etfs", "progress": 0})
    result = asyncio.run(main())
    return {"status": "complete", "result": result}


@celery_app.task(bind=True, name="backend.tasks.seed_tasks.seed_prices_task")
def seed_prices_task(
    self,
    tickers: list[str] | None = None,
    use_universe: bool = False,
    period: str = "10y",
    dry_run: bool = False,
) -> dict:
    """Seed historical price data.

    Args:
        tickers: Explicit list of tickers. If None, uses universe if use_universe=True.
        use_universe: If True, pull all tickers from the stock universe.
        period: yfinance period string (e.g. "10y", "1y", "6mo").
        dry_run: If True, show what would be ingested without writing.

    Returns:
        Dict with status and result.
    """
    from scripts.seed_prices import main

    self.update_state(state="PROGRESS", meta={"step": "seeding_prices", "progress": 0})
    result = asyncio.run(
        main(tickers=tickers, use_universe=use_universe, period=period, dry_run=dry_run)
    )
    return {"status": "complete", "result": result}


@celery_app.task(bind=True, name="backend.tasks.seed_tasks.seed_dividends_task")
def seed_dividends_task(
    self,
    tickers: list[str] | None = None,
    use_universe: bool = False,
    dry_run: bool = False,
) -> dict:
    """Seed historical dividend data.

    Args:
        tickers: Explicit list of tickers. If None, uses universe if use_universe=True.
        use_universe: If True, pull all tickers from the stock universe.
        dry_run: If True, show what would be ingested without writing.

    Returns:
        Dict with status and result.
    """
    from scripts.seed_dividends import main

    self.update_state(state="PROGRESS", meta={"step": "seeding_dividends", "progress": 0})
    result = asyncio.run(main(tickers=tickers, use_universe=use_universe, dry_run=dry_run))
    return {"status": "complete", "result": result}


@celery_app.task(bind=True, name="backend.tasks.seed_tasks.seed_fundamentals_task")
def seed_fundamentals_task(
    self,
    tickers: list[str] | None = None,
    use_universe: bool = False,
    dry_run: bool = False,
) -> dict:
    """Seed fundamental financial data.

    Args:
        tickers: Explicit list of tickers. If None, uses universe if use_universe=True.
        use_universe: If True, pull all tickers from the stock universe.
        dry_run: If True, show what would be ingested without writing.

    Returns:
        Dict with status and result.
    """
    from scripts.seed_fundamentals import main

    self.update_state(state="PROGRESS", meta={"step": "seeding_fundamentals", "progress": 0})
    result = asyncio.run(main(tickers=tickers, use_universe=use_universe, dry_run=dry_run))
    return {"status": "complete", "result": result}


@celery_app.task(bind=True, name="backend.tasks.seed_tasks.seed_forecasts_task")
def seed_forecasts_task(
    self,
    tickers: list[str] | None = None,
    use_universe: bool = False,
    dry_run: bool = False,
) -> dict:
    """Seed initial forecast data.

    Args:
        tickers: Explicit list of tickers. If None, uses universe if use_universe=True.
        use_universe: If True, pull all tickers from the stock universe.
        dry_run: If True, show what would be computed without writing.

    Returns:
        Dict with status and result.
    """
    from scripts.seed_forecasts import main

    self.update_state(state="PROGRESS", meta={"step": "seeding_forecasts", "progress": 0})
    result = asyncio.run(main(tickers=tickers, use_universe=use_universe, dry_run=dry_run))
    return {"status": "complete", "result": result}


@celery_app.task(bind=True, name="backend.tasks.seed_tasks.seed_reason_tier_task")
def seed_reason_tier_task(self) -> dict:
    """Seed reason tier classifications.

    Returns:
        Dict with status and result.
    """
    from scripts.seed_reason_tier import seed_reason_tier

    self.update_state(state="PROGRESS", meta={"step": "seeding_reason_tier", "progress": 0})
    result = asyncio.run(seed_reason_tier())
    return {"status": "complete", "result": result}


@celery_app.task(bind=True, name="backend.tasks.seed_tasks.seed_portfolio_task")
def seed_portfolio_task(self, csv_path: str, email: str, password: str) -> dict:
    """Seed a portfolio from a CSV file.

    MANUAL-ONLY — not included in automated batch runs.
    Provide explicit csv_path, email, and password each invocation.

    Args:
        csv_path: Absolute path to the CSV file with portfolio holdings.
        email: User email to assign the portfolio to.
        password: User password (used to look up or create the user).

    Returns:
        Dict with status and result.
    """
    from scripts.seed_portfolio import seed

    self.update_state(state="PROGRESS", meta={"step": "seeding_portfolio", "progress": 0})
    result = asyncio.run(seed(csv_path, email, password))
    return {"status": "complete", "result": result}


# ── Admin user seed ────────────────────────────────────────────────────────────


async def _seed_admin_user() -> dict:
    """Create admin user from environment variables.

    Reads ADMIN_EMAIL and ADMIN_PASSWORD from settings.
    Idempotent — skips if admin already exists with the admin role,
    and promotes if user exists with a non-admin role.

    Returns:
        Dict with status and email (or reason if skipped).
    """
    import bcrypt
    from sqlalchemy import select

    from backend.config import settings
    from backend.database import async_session_factory
    from backend.models.user import User, UserRole

    admin_email = getattr(settings, "ADMIN_EMAIL", "")
    admin_password = getattr(settings, "ADMIN_PASSWORD", "")

    if not admin_email or not admin_password:
        return {"status": "skipped", "reason": "ADMIN_EMAIL or ADMIN_PASSWORD not set"}

    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.email == admin_email))
        existing = result.scalar_one_or_none()

        if existing:
            if existing.role != UserRole.ADMIN:
                existing.role = UserRole.ADMIN
                await session.commit()
                return {"status": "promoted", "email": admin_email}
            return {"status": "exists", "email": admin_email}

        hashed = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt()).decode()
        user = User(
            email=admin_email,
            hashed_password=hashed,
            role=UserRole.ADMIN,
            is_active=True,
            email_verified=True,
        )
        session.add(user)
        await session.commit()
        return {"status": "created", "email": admin_email}


@celery_app.task(bind=True, name="backend.tasks.seed_tasks.seed_admin_user_task")
def seed_admin_user_task(self) -> dict:
    """Create admin user from environment variables.

    Reads ADMIN_EMAIL and ADMIN_PASSWORD from settings.
    Idempotent — skips if admin already exists.

    Returns:
        Dict with status and email (or reason if skipped).
    """
    return asyncio.run(_seed_admin_user())
