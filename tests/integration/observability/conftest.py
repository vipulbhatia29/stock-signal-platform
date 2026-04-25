"""Integration test fixtures for observability suite validation.

Provides factory-boy factories for obs models, session factory patching
(so anomaly rules + MCP tools hit the test DB), and a real ObservabilityClient
with DirectTarget for end-to-end SDK pipeline testing.
"""

import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import factory
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.dependencies import create_access_token
from backend.main import app
from backend.models.user import UserRole
from backend.observability.client import ObservabilityClient
from backend.observability.models.api_error_log import ApiErrorLog
from backend.observability.models.auth_event_log import AuthEventLog
from backend.observability.models.celery_worker_heartbeat import CeleryWorkerHeartbeat
from backend.observability.models.external_api_call import ExternalApiCallLog
from backend.observability.models.finding_log import FindingLog
from backend.observability.models.request_log import RequestLog
from backend.observability.service.event_writer import write_batch
from backend.observability.targets.direct import DirectTarget


# -- Factories ---------------------------------------------------------------
class RequestLogFactory(factory.Factory):
    """Factory for RequestLog model instances."""

    class Meta:
        model = RequestLog

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    ts = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    trace_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    span_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    method = "GET"
    path = "/api/v1/health"
    raw_path = "/api/v1/health"
    status_code = 200
    latency_ms = 42
    env = "dev"


class ApiErrorLogFactory(factory.Factory):
    """Factory for ApiErrorLog model instances."""

    class Meta:
        model = ApiErrorLog

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    ts = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    trace_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    span_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    status_code = 500
    error_type = "INTERNAL_SERVER"
    error_message = "test error"
    env = "dev"


class FindingLogFactory(factory.Factory):
    """Factory for FindingLog model instances."""

    class Meta:
        model = FindingLog

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    opened_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    kind = "http_5xx_elevated"
    attribution_layer = "HTTP"
    severity = "CRITICAL"
    status = "open"
    title = "Elevated 5xx error rate"
    evidence = factory.LazyFunction(lambda: {"count": 10, "threshold": 5})
    remediation_hint = "Check recent deployments"
    dedup_key = factory.LazyFunction(lambda: f"http_5xx_{uuid.uuid4().hex[:8]}")
    negative_check_count = 0
    env = "dev"


class CeleryHeartbeatFactory(factory.Factory):
    """Factory for CeleryWorkerHeartbeat model instances."""

    class Meta:
        model = CeleryWorkerHeartbeat

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    ts = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    trace_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    span_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    worker_name = "celery@worker-1"
    hostname = "worker-1"
    status = "active"
    tasks_in_flight = 2
    queue_names = factory.LazyFunction(lambda: ["celery", "default"])
    uptime_seconds = 3600
    env = "dev"


class AuthEventLogFactory(factory.Factory):
    """Factory for AuthEventLog model instances."""

    class Meta:
        model = AuthEventLog

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    ts = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    event_type = "jwt_verify"
    outcome = "success"
    user_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    ip_address = "127.0.0.1"
    env = "dev"


class ExternalApiCallFactory(factory.Factory):
    """Factory for ExternalApiCallLog model instances."""

    class Meta:
        model = ExternalApiCallLog

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    ts = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    trace_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    span_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    provider = "yfinance"
    endpoint = "/v8/finance/chart/AAPL"
    method = "GET"
    status_code = 200
    latency_ms = 350
    env = "dev"


# -- Core fixtures -----------------------------------------------------------
@pytest_asyncio.fixture
async def _patch_session_factory(db_url):
    """Reconfigure the EXISTING async_session_factory to use the test DB engine.

    42 modules do ``from backend.database import async_session_factory``, which
    creates local bindings that survive module-level attribute replacement.
    Using ``configure(bind=...)`` mutates the factory instance in-place, so ALL
    holders of a reference — anomaly rules, MCP tools, admin endpoints, retention
    tasks, writers — automatically use the test DB without individual patching.
    """
    test_engine = create_async_engine(db_url, echo=False, poolclass=NullPool)

    import backend.database

    original_factory = backend.database.async_session_factory
    # Save the original engine (bind) from the factory's kw dict
    original_bind = original_factory.kw.get("bind")

    # Reconfigure in-place — all modules holding a reference see the change
    original_factory.configure(bind=test_engine)

    yield

    # Restore original engine
    original_factory.configure(bind=original_bind)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def obs_db_session(db_url):
    """Async session for direct obs table reads/writes in assertions."""
    engine = create_async_engine(db_url, echo=False, poolclass=NullPool)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def obs_client(db_url, _patch_session_factory):
    """Real ObservabilityClient with DirectTarget for integration tests.

    Depends on _patch_session_factory so DirectTarget writes hit test DB.
    """
    target = DirectTarget(event_writer=write_batch)
    client = ObservabilityClient(
        target=target,
        spool_dir=Path(tempfile.mkdtemp()),
        spool_enabled=False,
        flush_interval_ms=100,
        buffer_size=1000,
        enabled=True,
    )
    # Do NOT call client.start() — that spawns a background flush loop which
    # races with explicit flush() calls.  Tests call flush() manually.
    # Patch app.state.obs_client so HTTP middleware (ObsHttpMiddleware) uses
    # the test client instead of the lifespan-created one.
    original_app_client = getattr(app.state, "obs_client", None)
    app.state.obs_client = client
    yield client
    app.state.obs_client = original_app_client


@pytest_asyncio.fixture
async def admin_user(db_session):
    """Create an admin user for admin endpoint tests."""
    from tests.conftest import UserFactory

    user = UserFactory.build(role=UserRole.ADMIN, email_verified=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_auth_headers(admin_user):
    """JWT cookie headers for an admin user (GET requests only)."""
    token = create_access_token(admin_user.id)
    return {"Cookie": f"access_token={token}"}


@pytest_asyncio.fixture
async def admin_mutating_headers(admin_user):
    """JWT cookie + CSRF headers for admin mutating requests (POST/PATCH/PUT/DELETE).

    CSRF middleware requires csrf_token cookie + X-CSRF-Token header to match.
    """
    token = create_access_token(admin_user.id)
    csrf_token = "test-csrf-token"
    return {
        "Cookie": f"access_token={token}; csrf_token={csrf_token}",
        "X-CSRF-Token": csrf_token,
    }


@pytest_asyncio.fixture(autouse=True)
async def _clean_obs_tables(db_url):
    """Truncate all observability tables before each test to prevent data leakage.

    Tests that don't use the ``client`` fixture miss its teardown-based truncation.
    This autouse fixture ensures obs tables are clean regardless of which fixtures
    a test pulls in.
    """
    engine = create_async_engine(db_url, echo=False, poolclass=NullPool)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as session:
        # Truncate all obs tables that factories touch
        await session.execute(
            text(
                "TRUNCATE TABLE observability.finding_log, "
                "observability.api_error_log, "
                "observability.request_log, "
                "observability.auth_event_log, "
                "observability.external_api_call_log, "
                "observability.celery_worker_heartbeat "
                "CASCADE"
            )
        )
        await session.commit()
    await engine.dispose()
    yield


async def insert_obs_rows(session: AsyncSession, rows) -> None:
    """Bulk insert factory-built obs model instances."""
    for row in rows:
        session.add(row)
    await session.commit()
