"""Tests for observability query service."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.observability_queries import (
    get_assessment_history,
    get_kpis,
    get_latest_assessment,
    get_query_detail,
    get_query_list,
)


@pytest.fixture
def mock_db():
    """Create a mock async database session."""
    db = AsyncMock()
    return db


class TestGetKPIs:
    """Tests for get_kpis service function."""

    @pytest.mark.asyncio
    async def test_returns_all_kpi_fields(self, mock_db):
        """Should return dict with all 5 KPI fields."""
        # Mock: queries_today=0, cost=0, latency=0, no assessment, no fallback
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_db.execute.return_value = mock_result

        # Override for the fallback rate query (returns a Row)
        fb_row = MagicMock()
        fb_row.total = 0
        fb_row.failures = 0
        fb_result = MagicMock()
        fb_result.scalar.return_value = 0
        fb_result.one.return_value = fb_row

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 5:  # fallback rate is 5th query
                return fb_result
            return mock_result

        mock_db.execute = mock_execute

        result = await get_kpis(mock_db)

        assert "queries_today" in result
        assert "avg_latency_ms" in result
        assert "avg_cost_per_query" in result
        assert "pass_rate" in result
        assert "fallback_rate_pct" in result

    @pytest.mark.asyncio
    async def test_zero_queries_returns_zero_cost(self, mock_db):
        """Should return 0 avg cost when no queries today."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0

        fb_row = MagicMock()
        fb_row.total = 0
        fb_row.failures = 0
        fb_result = MagicMock()
        fb_result.one.return_value = fb_row
        fb_result.scalar.return_value = None

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 5:
                return fb_result
            return mock_result

        mock_db.execute = mock_execute

        result = await get_kpis(mock_db)
        assert result["avg_cost_per_query"] == 0.0


class TestGetQueryDetail:
    """Tests for get_query_detail service function."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_data(self, mock_db):
        """Should return None when no log rows found for query_id."""
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = empty_result

        result = await get_query_detail(mock_db, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_steps_sorted_by_time(self, mock_db):
        """Should merge LLM and tool rows sorted by timestamp."""
        qid = uuid.uuid4()
        t1 = datetime(2026, 3, 28, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 28, 10, 0, 1, tzinfo=timezone.utc)

        llm_row = MagicMock()
        llm_row.created_at = t2
        llm_row.provider = "groq"
        llm_row.model = "llama-3.3-70b"
        llm_row.latency_ms = 500
        llm_row.cost_usd = Decimal("0.001")
        llm_row.session_id = uuid.uuid4()

        tool_row = MagicMock()
        tool_row.created_at = t1
        tool_row.tool_name = "analyze_stock"
        tool_row.latency_ms = 200
        tool_row.cache_hit = False

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:  # LLM rows
                result.scalars.return_value.all.return_value = [llm_row]
            elif call_count == 2:  # Tool rows
                result.scalars.return_value.all.return_value = [tool_row]
            elif call_count == 3:  # Query text
                result.scalar.return_value = "What about AAPL?"
            return result

        mock_db.execute = mock_execute

        result = await get_query_detail(mock_db, qid)
        assert result is not None
        assert len(result["steps"]) == 2
        # Tool came first (t1 < t2)
        assert result["steps"][0]["action"] == "tool.analyze_stock"
        assert result["steps"][1]["action"] == "llm.groq.llama-3.3-70b"


class TestGetQueryDetailUserScoping:
    """Tests for user scoping in get_query_detail."""

    @pytest.mark.asyncio
    async def test_returns_none_when_user_has_no_access(self, mock_db):
        """Should return None when user_id is set and query belongs to another user."""
        # Both LLM and tool queries return empty (user-scoped filter excludes them)
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = empty_result

        result = await get_query_detail(mock_db, uuid.uuid4(), user_id=uuid.uuid4())
        assert result is None


class TestGetQueryList:
    """Tests for get_query_list service function."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_queries(self, mock_db):
        """Should return empty items list with correct pagination when no data."""
        # Count query returns 0
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        # Rows query returns empty
        rows_result = MagicMock()
        rows_result.all.return_value = []

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # count
                return count_result
            return rows_result

        mock_db.execute = mock_execute

        result = await get_query_list(mock_db)
        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["size"] == 25

    @pytest.mark.asyncio
    async def test_returns_items_with_batched_tool_data(self, mock_db):
        """Should return query list items with tool and message data from batch queries."""
        qid = uuid.uuid4()
        t1 = datetime(2026, 3, 28, 10, 0, 0, tzinfo=timezone.utc)

        # Main query row
        main_row = MagicMock()
        main_row.query_id = qid
        main_row.timestamp = t1
        main_row.llm_models = ["llama-3.3-70b"]
        main_row.llm_calls = 2
        main_row.total_cost_usd = Decimal("0.002")
        main_row.agent_type = "react_v2"

        # Tool batch row
        tool_row = MagicMock()
        tool_row.query_id = qid
        tool_row.tool_name = "analyze_stock"
        tool_row.cnt = 1
        tool_row.total_latency = 300

        # Message batch row
        msg_row = MagicMock()
        msg_row.query_id = qid
        msg_row.content = "Tell me about AAPL"

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:  # count
                result.scalar.return_value = 1
            elif call_count == 2:  # main rows
                result.all.return_value = [main_row]
            elif call_count == 3:  # tool batch
                result.all.return_value = [tool_row]
            elif call_count == 4:  # message batch
                result.all.return_value = [msg_row]
            return result

        mock_db.execute = mock_execute

        result = await get_query_list(mock_db)
        assert result["total"] == 1
        assert len(result["items"]) == 1
        item = result["items"][0]
        assert item["query_id"] == qid
        assert item["tools_used"] == ["analyze_stock"]
        assert item["query_text"] == "Tell me about AAPL"
        assert item["db_calls"] == 1
        assert item["external_calls"] == 0


class TestGetLatestAssessment:
    """Tests for get_latest_assessment service function."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_runs(self, mock_db):
        """Should return None when no assessment runs exist."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result_mock

        result = await get_latest_assessment(mock_db)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_run_summary(self, mock_db):
        """Should return dict with assessment run fields."""
        run = MagicMock()
        run.id = uuid.uuid4()
        run.trigger = "weekly"
        run.total_queries = 17
        run.passed_queries = 15
        run.pass_rate = 0.88
        run.total_cost_usd = 0.05
        run.started_at = datetime(2026, 3, 28, 0, 0, tzinfo=timezone.utc)
        run.completed_at = datetime(2026, 3, 28, 0, 5, tzinfo=timezone.utc)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = run
        mock_db.execute.return_value = result_mock

        result = await get_latest_assessment(mock_db)
        assert result is not None
        assert result["trigger"] == "weekly"
        assert result["pass_rate"] == 0.88


class TestGetAssessmentHistory:
    """Tests for get_assessment_history service function."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_runs(self, mock_db):
        """Should return empty list when no runs exist."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = result_mock

        result = await get_assessment_history(mock_db)
        assert result == []
