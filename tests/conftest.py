"""Shared test fixtures: database, Redis, FastAPI client, factories, auth."""

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

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
from backend.models.index import StockIndex, StockIndexMembership
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
    with RedisContainer(image="redis:7-alpine") as redis:
        yield redis


# ---------------------------------------------------------------------------
# Create tables once (session scope)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session", autouse=True)
async def _setup_database(db_url):
    """Create TimescaleDB extension and all tables once for the test session."""
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    yield
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


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
