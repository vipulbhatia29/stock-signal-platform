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
    get_query_groups,
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
        main_row.duration_ms = 300
        main_row.status_code = 0
        main_row.eval_score = None

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
        assert item["status"] == "completed"
        assert item["score"] is None


def _make_query_row(
    qid: uuid.UUID | None = None,
    timestamp: datetime | None = None,
    llm_calls: int = 1,
    total_cost_usd: Decimal | None = None,
    agent_type: str = "react_v2",
    duration_ms: int = 100,
    status_code: int = 0,
    eval_score: float | None = None,
) -> MagicMock:
    """Helper to build a mock main query row with all required fields."""
    row = MagicMock()
    row.query_id = qid or uuid.uuid4()
    row.timestamp = timestamp or datetime(2026, 3, 28, 10, 0, 0, tzinfo=timezone.utc)
    row.llm_models = ["llama-3.3-70b"]
    row.llm_calls = llm_calls
    row.total_cost_usd = total_cost_usd or Decimal("0.001")
    row.agent_type = agent_type
    row.duration_ms = duration_ms
    row.status_code = status_code
    row.eval_score = eval_score
    return row


def _setup_query_list_mock(mock_db, rows: list, total: int | None = None):
    """Wire up mock_db.execute for get_query_list with given main rows.

    Returns the mock so callers can inspect calls if needed.
    """
    if total is None:
        total = len(rows)

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:  # count
            result.scalar.return_value = total
        elif call_count == 2:  # main rows
            result.all.return_value = rows
        else:  # tool batch / message batch — empty
            result.all.return_value = []
        return result

    mock_db.execute = mock_execute


class TestGetQueryListSort:
    """Tests for get_query_list sorting."""

    @pytest.mark.asyncio
    async def test_sort_by_timestamp_desc(self, mock_db):
        """Should return items sorted by timestamp descending (default)."""
        t1 = datetime(2026, 3, 28, 9, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 28, 10, 0, 0, tzinfo=timezone.utc)
        rows = [
            _make_query_row(timestamp=t2),
            _make_query_row(timestamp=t1),
        ]
        _setup_query_list_mock(mock_db, rows)

        result = await get_query_list(mock_db)
        assert len(result["items"]) == 2
        assert result["items"][0]["timestamp"] == t2
        assert result["items"][1]["timestamp"] == t1

    @pytest.mark.asyncio
    async def test_sort_by_timestamp_asc(self, mock_db):
        """Should return items sorted by timestamp ascending when requested."""
        t1 = datetime(2026, 3, 28, 9, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 28, 10, 0, 0, tzinfo=timezone.utc)
        rows = [
            _make_query_row(timestamp=t1),
            _make_query_row(timestamp=t2),
        ]
        _setup_query_list_mock(mock_db, rows)

        result = await get_query_list(mock_db, sort_by="timestamp", sort_order="asc")
        assert len(result["items"]) == 2
        assert result["items"][0]["timestamp"] == t1
        assert result["items"][1]["timestamp"] == t2

    @pytest.mark.asyncio
    async def test_sort_by_total_cost_usd(self, mock_db):
        """Should accept sort_by=total_cost_usd without error."""
        rows = [
            _make_query_row(total_cost_usd=Decimal("0.010")),
            _make_query_row(total_cost_usd=Decimal("0.001")),
        ]
        _setup_query_list_mock(mock_db, rows)

        result = await get_query_list(mock_db, sort_by="total_cost_usd")
        assert len(result["items"]) == 2
        assert result["items"][0]["total_cost_usd"] == 0.01

    @pytest.mark.asyncio
    async def test_sort_by_llm_calls(self, mock_db):
        """Should accept sort_by=llm_calls without error."""
        rows = [
            _make_query_row(llm_calls=5),
            _make_query_row(llm_calls=2),
        ]
        _setup_query_list_mock(mock_db, rows)

        result = await get_query_list(mock_db, sort_by="llm_calls")
        assert len(result["items"]) == 2
        assert result["items"][0]["llm_calls"] == 5

    @pytest.mark.asyncio
    async def test_sort_by_score_nulls_last(self, mock_db):
        """Should sort by eval score with NULLs after scored items."""
        rows = [
            _make_query_row(eval_score=0.85),
            _make_query_row(eval_score=None),
        ]
        _setup_query_list_mock(mock_db, rows)

        result = await get_query_list(mock_db, sort_by="score", sort_order="desc")
        assert result["items"][0]["score"] == 0.85
        assert result["items"][1]["score"] is None

    @pytest.mark.asyncio
    async def test_sort_by_duration_ms(self, mock_db):
        """Should accept sort_by=duration_ms without error."""
        rows = [
            _make_query_row(duration_ms=500),
            _make_query_row(duration_ms=100),
        ]
        _setup_query_list_mock(mock_db, rows)

        result = await get_query_list(mock_db, sort_by="duration_ms")
        assert len(result["items"]) == 2


class TestGetQueryListStatusFilter:
    """Tests for get_query_list status derivation and filtering."""

    @pytest.mark.asyncio
    async def test_status_filter_error(self, mock_db):
        """Should filter to only error-status queries via HAVING."""
        rows = [_make_query_row(status_code=3)]
        _setup_query_list_mock(mock_db, rows, total=1)

        result = await get_query_list(mock_db, status="error")
        assert len(result["items"]) == 1
        assert result["items"][0]["status"] == "error"

    @pytest.mark.asyncio
    async def test_status_filter_completed(self, mock_db):
        """Should filter to only completed-status queries via HAVING."""
        rows = [_make_query_row(status_code=0)]
        _setup_query_list_mock(mock_db, rows, total=1)

        result = await get_query_list(mock_db, status="completed")
        assert len(result["items"]) == 1
        assert result["items"][0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_derived_status_worst_wins(self, mock_db):
        """Should map status_code to the worst status string."""
        rows = [
            _make_query_row(status_code=3),  # error
            _make_query_row(status_code=2),  # declined
            _make_query_row(status_code=1),  # timeout
            _make_query_row(status_code=0),  # completed
        ]
        _setup_query_list_mock(mock_db, rows, total=4)

        result = await get_query_list(mock_db)
        statuses = [item["status"] for item in result["items"]]
        assert statuses == ["error", "declined", "timeout", "completed"]


class TestGetQueryListCostFilter:
    """Tests for get_query_list cost filters."""

    @pytest.mark.asyncio
    async def test_cost_min_filter(self, mock_db):
        """Should apply cost_min HAVING filter and return matching items."""
        rows = [_make_query_row(total_cost_usd=Decimal("0.050"))]
        _setup_query_list_mock(mock_db, rows, total=1)

        result = await get_query_list(mock_db, cost_min=0.01)
        assert result["total"] == 1
        assert len(result["items"]) == 1

    @pytest.mark.asyncio
    async def test_cost_max_filter(self, mock_db):
        """Should apply cost_max HAVING filter and return matching items."""
        rows = [_make_query_row(total_cost_usd=Decimal("0.001"))]
        _setup_query_list_mock(mock_db, rows, total=1)

        result = await get_query_list(mock_db, cost_max=0.01)
        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_cost_min_and_max(self, mock_db):
        """Should apply both cost_min and cost_max HAVING filters."""
        rows = [_make_query_row(total_cost_usd=Decimal("0.005"))]
        _setup_query_list_mock(mock_db, rows, total=1)

        result = await get_query_list(mock_db, cost_min=0.001, cost_max=0.01)
        assert result["total"] == 1
        assert len(result["items"]) == 1


class TestGetQueryListEvalScore:
    """Tests for get_query_list eval score LEFT JOIN."""

    @pytest.mark.asyncio
    async def test_eval_score_present(self, mock_db):
        """Should populate score when eval_results match the query_id."""
        rows = [_make_query_row(eval_score=0.92)]
        _setup_query_list_mock(mock_db, rows)

        result = await get_query_list(mock_db)
        assert result["items"][0]["score"] == 0.92

    @pytest.mark.asyncio
    async def test_eval_score_absent(self, mock_db):
        """Should return None score when no eval match exists."""
        rows = [_make_query_row(eval_score=None)]
        _setup_query_list_mock(mock_db, rows)

        result = await get_query_list(mock_db)
        assert result["items"][0]["score"] is None

    @pytest.mark.asyncio
    async def test_eval_score_passthrough_decimal(self, mock_db):
        """Score value from DB should be passed through as a float, not truncated.

        The actual SQL formula ``(grounding + reasoning) / 2`` is exercised by
        integration tests (requires a real DB). Unit tests verify only that
        whatever value the query layer returns is forwarded unchanged.
        """
        rows = [_make_query_row(eval_score=0.70)]
        _setup_query_list_mock(mock_db, rows)

        result = await get_query_list(mock_db)
        # 0.70 should arrive as 0.7 — not 0.0, not 1.4 (double-counted)
        assert result["items"][0]["score"] == pytest.approx(0.70), (
            "Score must be forwarded as-is; double-application of formula would yield 1.4"
        )

    @pytest.mark.asyncio
    async def test_eval_score_boundary_values(self, mock_db):
        """Score values at boundaries (0.0 and 1.0) should be passed through correctly."""
        for boundary in (0.0, 1.0):
            rows = [_make_query_row(eval_score=boundary)]
            _setup_query_list_mock(mock_db, rows)

            result = await get_query_list(mock_db)
            assert result["items"][0]["score"] == pytest.approx(boundary), (
                f"Boundary score {boundary} should not be transformed"
            )

    # Note: the arithmetic correctness of the SQL formula
    # ``(grounding_score + reasoning_coherence_score) / 2 = 0.7``
    # when both scores exist is verified by integration tests in
    # tests/integration/test_observability_integration.py, not here —
    # unit tests with a mocked DB cannot execute real SQL expressions.


class TestGetQueryDetailSummaries:
    """Tests for input_summary/output_summary population and Langfuse URL in get_query_detail."""

    @pytest.mark.asyncio
    async def test_query_detail_tool_summaries_populated(self, mock_db):
        """Tool steps should carry input_summary and output_summary from DB columns."""
        qid = uuid.uuid4()
        t1 = datetime(2026, 3, 28, 10, 0, 0, tzinfo=timezone.utc)

        tool_row = MagicMock()
        tool_row.created_at = t1
        tool_row.tool_name = "analyze_stock"
        tool_row.latency_ms = 150
        tool_row.cache_hit = False
        tool_row.input_summary = "ticker=AAPL"
        tool_row.output_summary = "score=8.5, signal=BUY"

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:  # LLM rows — empty
                result.scalars.return_value.all.return_value = []
            elif call_count == 2:  # Tool rows
                result.scalars.return_value.all.return_value = [tool_row]
            return result

        mock_db.execute = mock_execute

        result = await get_query_detail(mock_db, qid)
        assert result is not None
        step = result["steps"][0]
        assert step["input_summary"] == "ticker=AAPL"
        assert step["output_summary"] == "score=8.5, signal=BUY"

    @pytest.mark.asyncio
    async def test_query_detail_llm_summaries_derived(self, mock_db):
        """LLM steps should have derived input_summary and output_summary strings."""
        qid = uuid.uuid4()
        t1 = datetime(2026, 3, 28, 10, 0, 0, tzinfo=timezone.utc)

        llm_row = MagicMock()
        llm_row.created_at = t1
        llm_row.provider = "anthropic"
        llm_row.model = "claude-3-haiku"
        llm_row.latency_ms = 800
        llm_row.cost_usd = Decimal("0.0025")
        llm_row.completion_tokens = 150
        llm_row.session_id = uuid.uuid4()
        llm_row.langfuse_trace_id = None

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:  # LLM rows
                result.scalars.return_value.all.return_value = [llm_row]
            elif call_count == 2:  # Tool rows — empty
                result.scalars.return_value.all.return_value = []
            elif call_count == 3:  # Query text
                result.scalar.return_value = "Analyze TSLA"
            return result

        mock_db.execute = mock_execute

        result = await get_query_detail(mock_db, qid)
        assert result is not None
        step = result["steps"][0]
        assert step["input_summary"] == "→ anthropic/claude-3-haiku"
        assert "150 tokens" in step["output_summary"]
        assert "800ms" in step["output_summary"]
        assert "$0.0025" in step["output_summary"]

    @pytest.mark.asyncio
    async def test_query_detail_langfuse_url_constructed(self, mock_db):
        """Should construct Langfuse deep-link URL when trace_id and secret key present."""
        from unittest.mock import patch

        qid = uuid.uuid4()
        trace_id = "trace-abc-123"
        t1 = datetime(2026, 3, 28, 10, 0, 0, tzinfo=timezone.utc)

        llm_row = MagicMock()
        llm_row.created_at = t1
        llm_row.provider = "groq"
        llm_row.model = "llama-3.3-70b"
        llm_row.latency_ms = 500
        llm_row.cost_usd = Decimal("0.001")
        llm_row.completion_tokens = 100
        llm_row.session_id = uuid.uuid4()
        llm_row.langfuse_trace_id = trace_id

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalars.return_value.all.return_value = [llm_row]
            elif call_count == 2:
                result.scalars.return_value.all.return_value = []
            elif call_count == 3:
                result.scalar.return_value = "Tell me about TSLA"
            return result

        mock_db.execute = mock_execute

        with patch("backend.services.observability_queries.settings") as mock_settings:
            mock_settings.LANGFUSE_SECRET_KEY = "sk-test-secret"
            mock_settings.LANGFUSE_BASEURL = "http://langfuse.example.com"

            result = await get_query_detail(mock_db, qid)

        assert result is not None
        assert result["langfuse_trace_url"] == f"http://langfuse.example.com/trace/{trace_id}"

    @pytest.mark.asyncio
    async def test_query_detail_langfuse_url_none_without_trace_id(self, mock_db):
        """Should return langfuse_trace_url=None when no LLM row has a trace_id."""
        from unittest.mock import patch

        qid = uuid.uuid4()
        t1 = datetime(2026, 3, 28, 10, 0, 0, tzinfo=timezone.utc)

        llm_row = MagicMock()
        llm_row.created_at = t1
        llm_row.provider = "groq"
        llm_row.model = "llama-3.3-70b"
        llm_row.latency_ms = 400
        llm_row.cost_usd = Decimal("0.001")
        llm_row.completion_tokens = 80
        llm_row.session_id = uuid.uuid4()
        llm_row.langfuse_trace_id = None  # no trace

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalars.return_value.all.return_value = [llm_row]
            elif call_count == 2:
                result.scalars.return_value.all.return_value = []
            elif call_count == 3:
                result.scalar.return_value = "Tell me about AAPL"
            return result

        mock_db.execute = mock_execute

        with patch("backend.services.observability_queries.settings") as mock_settings:
            mock_settings.LANGFUSE_SECRET_KEY = "sk-test-secret"
            mock_settings.LANGFUSE_BASEURL = "http://langfuse.example.com"

            result = await get_query_detail(mock_db, qid)

        assert result is not None
        assert result["langfuse_trace_url"] is None

    @pytest.mark.asyncio
    async def test_query_detail_langfuse_url_none_without_secret_key(self, mock_db):
        """Should return langfuse_trace_url=None when LANGFUSE_SECRET_KEY is empty."""
        from unittest.mock import patch

        qid = uuid.uuid4()
        trace_id = "trace-xyz-456"
        t1 = datetime(2026, 3, 28, 10, 0, 0, tzinfo=timezone.utc)

        llm_row = MagicMock()
        llm_row.created_at = t1
        llm_row.provider = "groq"
        llm_row.model = "llama-3.3-70b"
        llm_row.latency_ms = 400
        llm_row.cost_usd = Decimal("0.001")
        llm_row.completion_tokens = 80
        llm_row.session_id = uuid.uuid4()
        llm_row.langfuse_trace_id = trace_id

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalars.return_value.all.return_value = [llm_row]
            elif call_count == 2:
                result.scalars.return_value.all.return_value = []
            elif call_count == 3:
                result.scalar.return_value = "Tell me about AAPL"
            return result

        mock_db.execute = mock_execute

        with patch("backend.services.observability_queries.settings") as mock_settings:
            mock_settings.LANGFUSE_SECRET_KEY = ""  # empty = not configured
            mock_settings.LANGFUSE_BASEURL = "http://localhost:3001"

            result = await get_query_detail(mock_db, qid)

        assert result is not None
        assert result["langfuse_trace_url"] is None


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


# ── Helpers for get_query_groups tests ──────────────────────────────────────


def _make_group_row(
    key: str | object = "groq",
    query_count: int = 5,
    total_cost: float = 0.01,
    avg_latency: float = 250.0,
    error_rate: float = 0.1,
) -> MagicMock:
    """Build a mock aggregation row for get_query_groups."""
    row = MagicMock()
    row.key = key
    row.query_count = query_count
    row.total_cost = total_cost
    row.avg_latency = avg_latency
    row.error_rate = error_rate
    return row


def _setup_groups_mock(mock_db, rows: list):
    """Wire mock_db.execute to return the given rows for any single query."""
    result = MagicMock()
    result.all.return_value = rows
    mock_db.execute = AsyncMock(return_value=result)


class TestGetQueryGroupsLLM:
    """Tests for get_query_groups with llm_call_log dimensions."""

    @pytest.mark.asyncio
    async def test_group_by_agent_type(self, mock_db):
        """Should group by agent_type and return correct response shape."""
        rows = [_make_group_row(key="react_v2", query_count=10)]
        _setup_groups_mock(mock_db, rows)

        result = await get_query_groups(mock_db, group_by="agent_type")

        assert result["group_by"] == "agent_type"
        assert result["bucket"] is None
        assert result["total_queries"] == 10
        assert len(result["groups"]) == 1
        assert result["groups"][0]["key"] == "react_v2"
        assert result["groups"][0]["query_count"] == 10

    @pytest.mark.asyncio
    async def test_group_by_model(self, mock_db):
        """Should group by model dimension."""
        rows = [
            _make_group_row(key="llama-3.3-70b", query_count=7),
            _make_group_row(key="claude-3-haiku", query_count=3),
        ]
        _setup_groups_mock(mock_db, rows)

        result = await get_query_groups(mock_db, group_by="model")

        assert result["group_by"] == "model"
        assert result["total_queries"] == 10
        assert len(result["groups"]) == 2

    @pytest.mark.asyncio
    async def test_group_by_status(self, mock_db):
        """Should group by status dimension."""
        rows = [
            _make_group_row(key="completed", query_count=8, error_rate=0.0),
            _make_group_row(key="error", query_count=2, error_rate=1.0),
        ]
        _setup_groups_mock(mock_db, rows)

        result = await get_query_groups(mock_db, group_by="status")

        assert result["group_by"] == "status"
        assert result["total_queries"] == 10

    @pytest.mark.asyncio
    async def test_group_by_provider(self, mock_db):
        """Should group by provider dimension."""
        rows = [_make_group_row(key="groq", query_count=15)]
        _setup_groups_mock(mock_db, rows)

        result = await get_query_groups(mock_db, group_by="provider")

        assert result["group_by"] == "provider"
        assert result["groups"][0]["key"] == "groq"

    @pytest.mark.asyncio
    async def test_group_by_tier(self, mock_db):
        """Should group by tier dimension."""
        rows = [
            _make_group_row(key="planner", query_count=5),
            _make_group_row(key="synthesizer", query_count=5),
        ]
        _setup_groups_mock(mock_db, rows)

        result = await get_query_groups(mock_db, group_by="tier")

        assert result["group_by"] == "tier"
        assert result["total_queries"] == 10

    @pytest.mark.asyncio
    async def test_group_by_date_day_bucket(self, mock_db):
        """Should group by date with day bucket and set bucket in response."""
        dt = datetime(2026, 3, 28, 0, 0, 0, tzinfo=timezone.utc)
        rows = [_make_group_row(key=dt, query_count=12)]
        _setup_groups_mock(mock_db, rows)

        result = await get_query_groups(mock_db, group_by="date", bucket="day")

        assert result["group_by"] == "date"
        assert result["bucket"] == "day"
        assert result["groups"][0]["key"] == dt.isoformat()

    @pytest.mark.asyncio
    async def test_group_by_date_week_bucket(self, mock_db):
        """Should accept week bucket for date grouping."""
        dt = datetime(2026, 3, 23, 0, 0, 0, tzinfo=timezone.utc)
        rows = [_make_group_row(key=dt, query_count=50)]
        _setup_groups_mock(mock_db, rows)

        result = await get_query_groups(mock_db, group_by="date", bucket="week")

        assert result["bucket"] == "week"
        assert result["total_queries"] == 50

    @pytest.mark.asyncio
    async def test_group_by_date_month_bucket(self, mock_db):
        """Should accept month bucket for date grouping."""
        dt = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
        rows = [_make_group_row(key=dt, query_count=200)]
        _setup_groups_mock(mock_db, rows)

        result = await get_query_groups(mock_db, group_by="date", bucket="month")

        assert result["bucket"] == "month"
        assert result["total_queries"] == 200

    @pytest.mark.asyncio
    async def test_date_key_iso_format(self, mock_db):
        """Should serialize date keys as ISO 8601 strings."""
        dt = datetime(2026, 3, 28, 14, 30, 0, tzinfo=timezone.utc)
        rows = [_make_group_row(key=dt, query_count=1)]
        _setup_groups_mock(mock_db, rows)

        result = await get_query_groups(mock_db, group_by="date")

        assert result["groups"][0]["key"] == "2026-03-28T14:30:00+00:00"


class TestGetQueryGroupsToolName:
    """Tests for get_query_groups with tool_name dimension."""

    @pytest.mark.asyncio
    async def test_group_by_tool_name(self, mock_db):
        """Should group by tool_name from tool_execution_log."""
        rows = [
            _make_group_row(key="analyze_stock", query_count=20, total_cost=0),
            _make_group_row(key="web_search", query_count=5, total_cost=0),
        ]
        _setup_groups_mock(mock_db, rows)

        result = await get_query_groups(mock_db, group_by="tool_name")

        assert result["group_by"] == "tool_name"
        assert result["total_queries"] == 25
        assert len(result["groups"]) == 2
        # Tools have zero cost
        assert result["groups"][0]["total_cost_usd"] == 0.0
        assert result["groups"][0]["avg_cost_usd"] == 0.0


class TestGetQueryGroupsUser:
    """Tests for get_query_groups with user dimension."""

    @pytest.mark.asyncio
    async def test_group_by_user_returns_email(self, mock_db):
        """Should group by user and return email as key."""
        rows = [
            _make_group_row(key="alice@example.com", query_count=10, total_cost=0.05),
            _make_group_row(key="bob@example.com", query_count=5, total_cost=0.02),
        ]
        _setup_groups_mock(mock_db, rows)

        result = await get_query_groups(mock_db, group_by="user")

        assert result["group_by"] == "user"
        assert result["groups"][0]["key"] == "alice@example.com"
        assert result["groups"][1]["key"] == "bob@example.com"
        assert result["total_queries"] == 15


class TestGetQueryGroupsIntentCategory:
    """Tests for get_query_groups with intent_category dimension."""

    @pytest.mark.asyncio
    async def test_group_by_intent_category(self, mock_db):
        """Should group by intent_category from eval_results."""
        rows = [
            _make_group_row(key="stock_analysis", query_count=8, total_cost=0.04),
            _make_group_row(key="portfolio_review", query_count=4, total_cost=0.02),
        ]
        _setup_groups_mock(mock_db, rows)

        result = await get_query_groups(mock_db, group_by="intent_category")

        assert result["group_by"] == "intent_category"
        assert result["total_queries"] == 12
        assert result["groups"][0]["key"] == "stock_analysis"

    @pytest.mark.asyncio
    async def test_intent_category_empty_result(self, mock_db):
        """Should return empty groups when no eval data exists."""
        _setup_groups_mock(mock_db, [])

        result = await get_query_groups(mock_db, group_by="intent_category")

        assert result["groups"] == []
        assert result["total_queries"] == 0


class TestGetQueryGroupsFilters:
    """Tests for get_query_groups date filters and user scoping."""

    @pytest.mark.asyncio
    async def test_empty_results_any_dimension(self, mock_db):
        """Should return empty groups for any dimension when no data."""
        _setup_groups_mock(mock_db, [])

        result = await get_query_groups(mock_db, group_by="provider")

        assert result["groups"] == []
        assert result["total_queries"] == 0
        assert result["group_by"] == "provider"

    @pytest.mark.asyncio
    async def test_date_from_to_filter_applied(self, mock_db):
        """Should pass date_from and date_to filters without error."""
        rows = [_make_group_row(key="groq", query_count=3)]
        _setup_groups_mock(mock_db, rows)

        result = await get_query_groups(
            mock_db,
            group_by="provider",
            date_from=datetime(2026, 3, 1, tzinfo=timezone.utc),
            date_to=datetime(2026, 3, 31, tzinfo=timezone.utc),
        )

        assert result["total_queries"] == 3

    @pytest.mark.asyncio
    async def test_user_scoping_applied(self, mock_db):
        """Should accept user_id for scoping without error."""
        rows = [_make_group_row(key="react_v2", query_count=2)]
        _setup_groups_mock(mock_db, rows)

        uid = uuid.uuid4()
        result = await get_query_groups(mock_db, group_by="agent_type", user_id=uid)

        assert result["total_queries"] == 2


class TestGetQueryGroupsResponseShape:
    """Tests for response shape correctness."""

    @pytest.mark.asyncio
    async def test_cost_and_latency_rounding(self, mock_db):
        """Should round cost to 6 decimals and latency to 1 decimal."""
        rows = [
            _make_group_row(
                key="groq",
                query_count=3,
                total_cost=0.0123456789,
                avg_latency=123.456789,
                error_rate=0.12345,
            )
        ]
        _setup_groups_mock(mock_db, rows)

        result = await get_query_groups(mock_db, group_by="provider")
        group = result["groups"][0]

        assert group["total_cost_usd"] == round(0.0123456789, 6)
        assert group["avg_cost_usd"] == round(0.0123456789 / 3, 6)
        assert group["avg_latency_ms"] == round(123.456789, 1)
        assert group["error_rate"] == round(0.12345, 4)
