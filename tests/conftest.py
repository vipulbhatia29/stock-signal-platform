"""Shared test fixtures: database, Redis, FastAPI client, factories, auth."""

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

# --- Set test-safe JWT secret BEFORE any backend imports ---
# backend.config validates JWT_SECRET_KEY at import time and raises ValueError
# if the insecure default is detected. Tests must provide an explicit secret.
if "JWT_SECRET_KEY" not in os.environ:
    os.environ["JWT_SECRET_KEY"] = "test-secret-do-not-use-in-production-32chars!"

# --- Observability SDK test defaults (PR2a) ---
os.environ.setdefault("OBS_TARGET_TYPE", "memory")
os.environ.setdefault("OBS_SPOOL_ENABLED", "false")
os.environ.setdefault("OBS_ENABLED", "true")

import factory
import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from backend.database import get_async_session
from backend.dependencies import create_access_token, hash_password
from backend.main import app
from backend.models import Base
from backend.models.audit import AdminAuditLog
from backend.models.backtest import BacktestRun
from backend.models.convergence import SignalConvergenceDaily
from backend.models.index import StockIndex, StockIndexMembership
from backend.models.news_sentiment import NewsArticle, NewsSentimentDaily
from backend.models.portfolio import Portfolio, Transaction
from backend.models.price import StockPrice
from backend.models.recommendation import RecommendationSnapshot
from backend.models.signal import SignalSnapshot
from backend.models.stock import Stock, Watchlist
from backend.models.user import User, UserPreference, UserRole


# ---------------------------------------------------------------------------
# Postgres container (session-scoped)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def postgres_container():
    """Start a real Postgres+TimescaleDB container via testcontainers."""
    if os.environ.get("CI"):
        pytest.fail(
            "Testcontainers disabled in CI — using service containers. "
            "Ensure this test directory has a conftest.py that overrides db_url."
        )
    with PostgresContainer(
        image="timescale/timescaledb:latest-pg16",
        username="test",
        password="test",
        dbname="test_stocksignal",
        driver="asyncpg",
    ) as pg:
        yield pg


@pytest.fixture(scope="session")
def db_url(postgres_container) -> str:
    """Get the database URL from the test container."""
    return postgres_container.get_connection_url()


# ---------------------------------------------------------------------------
# Redis container (session-scoped)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def redis_container():
    """Start a real Redis container via testcontainers."""
    if os.environ.get("CI"):
        pytest.fail(
            "Testcontainers disabled in CI — using service containers. "
            "Ensure REDIS_URL env var is set."
        )
    with RedisContainer(image="redis:7-alpine") as redis:
        yield redis


# ---------------------------------------------------------------------------
# Create tables once (session scope)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session", autouse=True)
async def _setup_database(db_url):
    """Create TimescaleDB extension and all tables once for the test session.

    No teardown DROP. Under pytest-xdist, each worker has its own pytest
    session, but all workers share the same database. A teardown that DROPs
    tables races with sibling workers still running tests: the first worker
    to finish wipes the schema out from under the others, causing
    'relation does not exist' errors on subsequent TRUNCATE / SELECT calls.

    Container lifecycle handles cleanup instead:
      - Local: testcontainers context manager destroys the container on exit.
      - CI: GitHub Actions service containers are torn down with the runner.
    """
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
        await conn.execute(sa.text("CREATE SCHEMA IF NOT EXISTS observability"))
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    yield


# ---------------------------------------------------------------------------
# Per-test client with isolated DB sessions
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def client(db_url) -> AsyncGenerator[AsyncClient, None]:
    """Provide an httpx AsyncClient backed by the test database.

    Each request gets a fresh session from a per-test engine,
    avoiding connection pool conflicts between test and cleanup.
    """
    engine = create_async_engine(db_url, echo=False, pool_size=5)
    test_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = _override_session

    # Disable rate limiting during tests
    app.state.limiter.enabled = False

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.state.limiter.enabled = True
    app.dependency_overrides.clear()

    # Clean up all data after each test
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(sa.text(f'TRUNCATE TABLE "{table.name}" CASCADE'))

    await engine.dispose()


# ---------------------------------------------------------------------------
# Per-test database session (for direct DB setup/assertions)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def db_session(db_url) -> AsyncGenerator[AsyncSession, None]:
    """Provide an async session for direct test setup and assertions."""
    engine = create_async_engine(db_url, echo=False)
    factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory_() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# Factories (factory-boy)
# ---------------------------------------------------------------------------
class UserFactory(factory.Factory):
    """Factory for User model instances."""

    class Meta:
        model = User

    id = factory.LazyFunction(uuid.uuid4)
    email = factory.Sequence(lambda n: f"user{n}@test.com")
    hashed_password = factory.LazyFunction(lambda: hash_password("TestPass1"))
    role = UserRole.USER
    is_active = True
    email_verified = True
    created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    updated_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))


class UserPreferenceFactory(factory.Factory):
    """Factory for UserPreference model instances."""

    class Meta:
        model = UserPreference

    id = factory.LazyFunction(uuid.uuid4)
    user_id = factory.LazyAttribute(lambda o: uuid.uuid4())
    timezone = "America/New_York"
    updated_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))


class StockFactory(factory.Factory):
    """Factory for Stock model instances."""

    class Meta:
        model = Stock

    id = factory.LazyFunction(uuid.uuid4)
    ticker = factory.Sequence(lambda n: f"TST{n}")
    name = factory.Faker("company")
    exchange = "NASDAQ"
    sector = "Technology"
    is_active = True
    created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    updated_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Authenticated client helper
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def authenticated_client(client: AsyncClient, db_url) -> AsyncClient:
    """Provide a client with a valid JWT Authorization header."""
    engine = create_async_engine(db_url, echo=False)
    factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory_() as session:
        user = UserFactory.build()
        session.add(user)
        pref = UserPreferenceFactory.build(user_id=user.id)
        session.add(pref)
        await session.commit()
    await engine.dispose()

    token = create_access_token(user.id)
    client.headers["Authorization"] = f"Bearer {token}"
    # Store user reference on the client so tests can access the user's ID
    client._test_user = user  # type: ignore[attr-defined]
    return client


# ---------------------------------------------------------------------------
# Additional factories for Session 2 (signals, prices, recommendations)
# ---------------------------------------------------------------------------
class StockPriceFactory(factory.Factory):
    """Factory for StockPrice model instances (daily OHLCV data)."""

    class Meta:
        model = StockPrice

    time = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    ticker = "AAPL"
    open = factory.LazyFunction(lambda: 150.0)
    high = factory.LazyFunction(lambda: 155.0)
    low = factory.LazyFunction(lambda: 148.0)
    close = factory.LazyFunction(lambda: 152.0)
    adj_close = factory.LazyFunction(lambda: 152.0)
    volume = 50_000_000
    source = "yfinance"


class SignalSnapshotFactory(factory.Factory):
    """Factory for SignalSnapshot model instances."""

    class Meta:
        model = SignalSnapshot

    computed_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    ticker = "AAPL"
    rsi_value = 55.0
    rsi_signal = "NEUTRAL"
    macd_value = 1.5
    macd_histogram = 0.3
    macd_signal_label = "BULLISH"
    sma_50 = 150.0
    sma_200 = 145.0
    sma_signal = "ABOVE_200"
    bb_upper = 160.0
    bb_lower = 140.0
    bb_position = "MIDDLE"
    annual_return = 0.15
    volatility = 0.22
    sharpe_ratio = 0.48
    change_pct = 1.5
    current_price = 150.0
    composite_score = 6.5
    composite_weights = {"rsi": 1.0, "macd": 1.5, "sma": 1.5, "sharpe": 0.5, "total": 4.5}


class RecommendationSnapshotFactory(factory.Factory):
    """Factory for RecommendationSnapshot model instances."""

    class Meta:
        model = RecommendationSnapshot

    generated_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    ticker = "AAPL"
    user_id = factory.LazyFunction(uuid.uuid4)
    action = "WATCH"
    confidence = "MEDIUM"
    composite_score = 6.5
    price_at_recommendation = 152.0
    reasoning = {"summary": "Mixed signals", "signals": {}}
    is_actionable = False
    acknowledged = False


class WatchlistFactory(factory.Factory):
    """Factory for Watchlist model instances."""

    class Meta:
        model = Watchlist

    id = factory.LazyFunction(uuid.uuid4)
    user_id = factory.LazyFunction(uuid.uuid4)
    ticker = "AAPL"
    added_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Additional factories for Session 5 (indexes)
# ---------------------------------------------------------------------------
class StockIndexFactory(factory.Factory):
    """Factory for StockIndex model instances."""

    class Meta:
        model = StockIndex

    id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"Test Index {n}")
    slug = factory.Sequence(lambda n: f"test-index-{n}")
    description = "A test index"
    created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    updated_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))


class StockIndexMembershipFactory(factory.Factory):
    """Factory for StockIndexMembership model instances."""

    class Meta:
        model = StockIndexMembership

    id = factory.LazyFunction(uuid.uuid4)
    ticker = "AAPL"
    index_id = factory.LazyFunction(uuid.uuid4)
    added_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Additional factories for Phase 3 (portfolio)
# ---------------------------------------------------------------------------
class PortfolioFactory(factory.Factory):
    """Factory for Portfolio model instances."""

    class Meta:
        model = Portfolio

    id = factory.LazyFunction(uuid.uuid4)
    user_id = factory.LazyFunction(uuid.uuid4)
    name = "My Portfolio"
    description = None
    created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    updated_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))


class TransactionFactory(factory.Factory):
    """Factory for Transaction model instances."""

    class Meta:
        model = Transaction

    id = factory.LazyFunction(uuid.uuid4)
    portfolio_id = factory.LazyFunction(uuid.uuid4)
    ticker = "AAPL"
    transaction_type = "BUY"
    shares = 10
    price_per_share = 150
    transacted_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    notes = None
    created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Forecast Intelligence factories (Phase 8.6+)
# ---------------------------------------------------------------------------
class BacktestRunFactory(factory.Factory):
    """Factory for BacktestRun model instances."""

    class Meta:
        model = BacktestRun

    id = factory.LazyFunction(uuid.uuid4)
    ticker = "AAPL"
    model_version_id = factory.LazyFunction(uuid.uuid4)
    config_label = "baseline"
    train_start = factory.LazyFunction(lambda: datetime(2022, 1, 1).date())
    train_end = factory.LazyFunction(lambda: datetime(2023, 12, 31).date())
    test_start = factory.LazyFunction(lambda: datetime(2024, 1, 1).date())
    test_end = factory.LazyFunction(lambda: datetime(2024, 12, 31).date())
    horizon_days = 90
    num_windows = 12
    mape = 0.08
    mae = 15.2
    rmse = 18.5
    direction_accuracy = 0.64
    ci_containment = 0.78
    market_regime = "bull"


class SignalConvergenceDailyFactory(factory.Factory):
    """Factory for SignalConvergenceDaily model instances."""

    class Meta:
        model = SignalConvergenceDaily

    date = factory.LazyFunction(lambda: datetime(2026, 4, 1).date())
    ticker = "AAPL"
    rsi_direction = "bullish"
    macd_direction = "bullish"
    sma_direction = "bullish"
    piotroski_direction = "neutral"
    forecast_direction = "bullish"
    signals_aligned = 4
    convergence_label = "strong_bull"
    composite_score = 8.5


class NewsArticleFactory(factory.Factory):
    """Factory for NewsArticle model instances."""

    class Meta:
        model = NewsArticle

    published_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    id = factory.LazyFunction(uuid.uuid4)
    ticker = "AAPL"
    headline = factory.Faker("sentence")
    source = "finnhub"
    dedupe_hash = factory.LazyFunction(lambda: uuid.uuid4().hex)


class NewsSentimentDailyFactory(factory.Factory):
    """Factory for NewsSentimentDaily model instances."""

    class Meta:
        model = NewsSentimentDaily

    date = factory.LazyFunction(lambda: datetime(2026, 4, 1).date())
    ticker = "AAPL"
    stock_sentiment = 0.5
    sector_sentiment = 0.2
    macro_sentiment = -0.1
    article_count = 5
    confidence = 0.8
    quality_flag = "ok"


class AdminAuditLogFactory(factory.Factory):
    """Factory for AdminAuditLog model instances."""

    class Meta:
        model = AdminAuditLog

    id = factory.LazyFunction(uuid.uuid4)
    user_id = factory.LazyFunction(uuid.uuid4)
    action = "pipeline_trigger"
    target = "backtest_all"
