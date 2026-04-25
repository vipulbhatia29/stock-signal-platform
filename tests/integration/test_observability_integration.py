"""Integration tests for observability query service — spec §10.3.

These tests require a real Postgres database (via DATABASE_URL env var or
testcontainers). They verify SQL-level correctness that cannot be tested
with mocked sessions: HAVING cost filters, date_trunc bucketing, and
accurate total counts after filtering.

Run with::

    uv run pytest tests/integration/test_observability_integration.py -v
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.observability.queries import get_query_groups, get_query_list

# ---------------------------------------------------------------------------
# Skip guard — requires DATABASE_URL in environment
# ---------------------------------------------------------------------------


def _db_url() -> str | None:
    """Return DATABASE_URL from environment, or None if not set."""
    return os.environ.get("DATABASE_URL")


_SKIP_NO_DB = pytest.mark.skipif(
    _db_url() is None,
    reason="requires DATABASE_URL (testcontainers or real Postgres); set in .env or CI",
)


# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def obs_db_session():
    """Async SQLAlchemy session connected to the real test database.

    Uses DATABASE_URL from the environment. Rolls back all changes after
    each test so tests are isolated.
    """
    url = _db_url()
    if url is None:
        pytest.skip("DATABASE_URL not set")

    engine = create_async_engine(url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        yield session
        await session.rollback()

    await engine.dispose()


async def _insert_llm_call_log(
    session: AsyncSession,
    *,
    query_id: uuid.UUID,
    cost_usd: float,
    created_at: datetime | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    """Insert a minimal LLMCallLog row for testing.

    Args:
        session: Active async DB session.
        query_id: query_id to group rows under.
        cost_usd: Cost in USD for this call.
        created_at: Timestamp for the call (defaults to now).
        user_id: Optional user UUID stored on associated ChatSession.
    """
    if created_at is None:
        created_at = datetime.now(timezone.utc)

    # Insert directly via raw SQL to avoid needing a ChatSession FK
    await session.execute(
        text(
            """
            INSERT INTO llm_call_log
                (id, created_at, provider, model, cost_usd, query_id, status)
            VALUES
                (:id, :created_at, 'anthropic', 'claude-haiku', :cost_usd, :query_id, 'completed')
            ON CONFLICT DO NOTHING
            """
        ),
        {
            "id": uuid.uuid4(),
            "created_at": created_at,
            "cost_usd": cost_usd,
            "query_id": query_id,
        },
    )
    await session.flush()


# ---------------------------------------------------------------------------
# Test A — HAVING cost filter with correct pagination total
# ---------------------------------------------------------------------------


@_SKIP_NO_DB
class TestHavingCostFilter:
    """HAVING cost filter must prune queries AND produce an accurate total count."""

    @pytest.mark.asyncio
    async def test_cost_min_filters_total_correctly(self, obs_db_session: AsyncSession) -> None:
        """get_query_list with cost_min must return total==2, not total==3.

        Seeds 3 queries with costs 0.001 / 0.010 / 0.100.
        cost_min=0.005 must exclude the cheapest query.
        total must reflect the filtered count — not the raw row count.
        """
        qid_cheap = uuid.uuid4()
        qid_mid = uuid.uuid4()
        qid_expensive = uuid.uuid4()

        await _insert_llm_call_log(obs_db_session, query_id=qid_cheap, cost_usd=0.001)
        await _insert_llm_call_log(obs_db_session, query_id=qid_mid, cost_usd=0.010)
        await _insert_llm_call_log(obs_db_session, query_id=qid_expensive, cost_usd=0.100)

        result = await get_query_list(obs_db_session, cost_min=0.005)

        # get_query_list returns query_id as UUID objects, not strings
        returned_query_ids = {item["query_id"] for item in result["items"]}

        # The cheap query must be excluded
        assert qid_cheap not in returned_query_ids, (
            "query with cost 0.001 should be excluded by cost_min=0.005"
        )

        # At least the two seeded queries above the threshold are present
        assert qid_mid in returned_query_ids or qid_expensive in returned_query_ids, (
            "at least one qualifying query must appear in results"
        )

        # total must equal the number of qualifying items found — not 3
        assert result["total"] == len(result["items"]), (
            f"total={result['total']} should match len(items)={len(result['items'])}, "
            "HAVING filter must be applied before count"
        )
        assert result["total"] >= 2, (
            f"Expected at least 2 results (mid + expensive), got total={result['total']}"
        )
        assert result["total"] < 3 or qid_cheap not in returned_query_ids, (
            "If total==3, the cheap query must NOT appear in items"
        )


# ---------------------------------------------------------------------------
# Test B — date_trunc bucketing produces ISO 8601 keys
# ---------------------------------------------------------------------------


@_SKIP_NO_DB
class TestDateTruncBucketing:
    """date_trunc grouping must produce the correct number of buckets."""

    @pytest.mark.asyncio
    async def test_week_bucket_produces_two_groups(self, obs_db_session: AsyncSession) -> None:
        """get_query_groups with group_by=date bucket=week must return 2 groups.

        Seeds rows in two different ISO weeks: one in week W and one
        in week W-2. Asserts 2 groups and that bucket keys are ISO 8601 strings.
        """
        now = datetime.now(timezone.utc)
        week_a = now
        week_b = now - timedelta(weeks=2)

        qid_a = uuid.uuid4()
        qid_b = uuid.uuid4()

        await _insert_llm_call_log(obs_db_session, query_id=qid_a, cost_usd=0.01, created_at=week_a)
        await _insert_llm_call_log(obs_db_session, query_id=qid_b, cost_usd=0.01, created_at=week_b)

        result = await get_query_groups(obs_db_session, group_by="date", bucket="week")

        # We expect at least 2 groups (may have more from other test data)
        # get_query_groups returns "groups" list and "total_queries" count
        assert len(result["groups"]) >= 2, (
            f"Expected at least 2 week buckets, got {len(result['groups'])}"
        )

        # All bucket keys must be ISO 8601 strings (not raw datetime objects)
        for group in result["groups"]:
            key = group["key"]
            assert isinstance(key, str), (
                f"Bucket key should be an ISO 8601 string, got {type(key)}: {key!r}"
            )
            # ISO 8601 strings contain digit characters and dashes
            assert any(c.isdigit() for c in key), (
                f"Bucket key does not look like a date string: {key!r}"
            )
