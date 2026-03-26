# Spec B: Agent Intelligence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 4 new agent tools (portfolio health, market briefing, stock intelligence, recommend stocks), update planner with 12 new few-shot examples + response_type routing, and add 3 synthesizer response format variants.

**Architecture:** Each tool is a standalone `BaseTool` subclass registered in ToolRegistry. Planner outputs `response_type` field to route synthesizer format. Graph state carries `response_type` through nodes. Tools query existing DB tables (no new tables — Spec C adds the missing columns).

**Tech Stack:** yfinance (free), numpy (for correlation), existing SQLAlchemy models, FastAPI, LangGraph StateGraph

**Spec:** `docs/superpowers/specs/2026-03-25-agent-intelligence-design.md`
**Depends on:** Spec C (Data Enrichment) must be implemented first — tools need `beta`, `dividend_yield`, `forward_pe` on Stock model and `news.py`/`intelligence.py` fetch functions.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/tools/portfolio_health.py` | Health score computation + PortfolioHealthTool |
| Create | `backend/tools/market_briefing.py` | Market overview + MarketBriefingTool |
| Create | `backend/tools/stock_intelligence.py` | Wraps intelligence.py for agent + StockIntelligenceTool |
| Create | `backend/tools/recommend_stocks.py` | Multi-signal consensus + RecommendStocksTool |
| Create | `backend/schemas/health.py` | PortfolioHealthResult schema |
| Create | `backend/schemas/market.py` | MarketBriefingResult schema |
| Create | `backend/schemas/recommend.py` | StockCandidate + RecommendationResult schemas |
| Create | `backend/routers/market.py` | GET /market/briefing endpoint |
| Modify | `backend/routers/portfolio.py` | Add GET /portfolio/health endpoint |
| Modify | `backend/tools/build_registry.py` | Register 4 new tools |
| Modify | `backend/agents/prompts/planner.md` | 12 new few-shots + response_type + scope update |
| Modify | `backend/agents/prompts/synthesizer.md` | 3 response format variants |
| Modify | `backend/agents/graph.py` | Add response_type to AgentStateV2 |
| Modify | `backend/agents/planner.py` | Extract response_type from plan output |
| Modify | `backend/agents/synthesizer.py` | Select format based on response_type |
| Modify | `backend/main.py` | Mount market router |
| Create | `tests/unit/tools/test_portfolio_health.py` | Health computation tests |
| Create | `tests/unit/tools/test_market_briefing.py` | Market briefing tests |
| Create | `tests/unit/tools/test_recommend_stocks.py` | Recommendation tests |
| Create | `tests/api/test_portfolio_health.py` | API tests |
| Create | `tests/api/test_market_briefing.py` | API tests |

---

### Task 1: Portfolio Health Tool — Core Computation

**Files:**
- Create: `backend/schemas/health.py`
- Create: `backend/tools/portfolio_health.py`
- Create: `tests/unit/tools/test_portfolio_health.py`

This is the largest task. The health tool computes HHI, weighted metrics, correlation, component scores, and a composite grade.

- [ ] **Step 1: Create health schemas**

```python
# backend/schemas/health.py
"""Response schemas for portfolio health endpoint and tool."""

from __future__ import annotations

from pydantic import BaseModel


class HealthComponent(BaseModel):
    """A single health score component."""
    name: str
    score: float  # 0-10
    weight: float  # 0-1
    detail: str


class PositionHealth(BaseModel):
    """Per-position contribution to portfolio health."""
    ticker: str
    weight_pct: float
    signal_score: float | None
    sector: str | None
    contribution: str  # "strength" or "drag"


class PortfolioHealthResult(BaseModel):
    """Complete portfolio health assessment."""
    health_score: float  # 0-10
    grade: str  # A+, A, B+, B, C+, C, D, F
    components: list[HealthComponent]
    metrics: dict  # hhi, effective_stocks, weighted_beta, weighted_sharpe, etc.
    top_concerns: list[str]
    top_strengths: list[str]
    position_details: list[PositionHealth]
```

- [ ] **Step 2: Write tests for health computation**

```python
# tests/unit/tools/test_portfolio_health.py
"""Tests for portfolio health score computation."""

import pytest


class TestHealthScoreComponents:
    """Tests for individual score component calculations."""

    def test_hhi_score_well_diversified(self) -> None:
        """HHI < 500 should score 10."""
        from backend.tools.portfolio_health import _score_diversification
        assert _score_diversification(400) == 10.0

    def test_hhi_score_concentrated(self) -> None:
        """HHI > 2500 should score 0."""
        from backend.tools.portfolio_health import _score_diversification
        assert _score_diversification(3000) == 0.0

    def test_hhi_score_moderate(self) -> None:
        """HHI between 500-2500 should score linearly."""
        from backend.tools.portfolio_health import _score_diversification
        score = _score_diversification(1500)
        assert 0 < score < 10

    def test_sharpe_score_excellent(self) -> None:
        """Sharpe > 1.5 should score 10."""
        from backend.tools.portfolio_health import _score_risk
        assert _score_risk(2.0) == 10.0

    def test_sharpe_score_negative(self) -> None:
        """Sharpe < 0 should score 0."""
        from backend.tools.portfolio_health import _score_risk
        assert _score_risk(-0.5) == 0.0

    def test_yield_score_optimal(self) -> None:
        """Yield 2-4% should score 10."""
        from backend.tools.portfolio_health import _score_income
        assert _score_income(0.03) == 10.0

    def test_yield_score_zero(self) -> None:
        """Yield 0% should score 3 (not terrible, just no income)."""
        from backend.tools.portfolio_health import _score_income
        assert _score_income(0.0) == 3.0

    def test_sector_balance_good(self) -> None:
        """Max sector < 25% should score 10."""
        from backend.tools.portfolio_health import _score_sector_balance
        assert _score_sector_balance(20.0) == 10.0

    def test_sector_balance_concentrated(self) -> None:
        """Max sector > 50% should score 0."""
        from backend.tools.portfolio_health import _score_sector_balance
        assert _score_sector_balance(55.0) == 0.0


class TestGradeAssignment:
    """Tests for score-to-grade mapping."""

    def test_grade_a_plus(self) -> None:
        """Score >= 9.5 should be A+."""
        from backend.tools.portfolio_health import _score_to_grade
        assert _score_to_grade(9.7) == "A+"

    def test_grade_b(self) -> None:
        """Score 7.0-7.4 should be B."""
        from backend.tools.portfolio_health import _score_to_grade
        assert _score_to_grade(7.2) == "B"

    def test_grade_f(self) -> None:
        """Score < 3.0 should be F."""
        from backend.tools.portfolio_health import _score_to_grade
        assert _score_to_grade(2.5) == "F"


class TestCompositeHealth:
    """Tests for weighted composite calculation."""

    def test_all_perfect_scores_10(self) -> None:
        """All component scores at 10 should give composite 10."""
        from backend.tools.portfolio_health import _compute_composite
        components = {
            "diversification": 10.0,
            "signal_quality": 10.0,
            "risk": 10.0,
            "income": 10.0,
            "sector_balance": 10.0,
        }
        assert _compute_composite(components) == 10.0

    def test_all_zero_scores_0(self) -> None:
        """All component scores at 0 should give composite 0."""
        from backend.tools.portfolio_health import _compute_composite
        components = {
            "diversification": 0.0,
            "signal_quality": 0.0,
            "risk": 0.0,
            "income": 0.0,
            "sector_balance": 0.0,
        }
        assert _compute_composite(components) == 0.0
```

- [ ] **Step 3: Implement portfolio_health.py**

The tool needs:
- `_score_diversification(hhi)` → 0-10
- `_score_signal_quality(weighted_composite)` → 0-10 (direct pass-through)
- `_score_risk(weighted_sharpe)` → 0-10
- `_score_income(weighted_yield)` → 0-10
- `_score_sector_balance(max_sector_pct)` → 0-10
- `_score_to_grade(score)` → letter grade
- `_compute_composite(components)` → weighted average
- `compute_portfolio_health(portfolio_id, db)` → PortfolioHealthResult (async, queries DB)
- `PortfolioHealthTool(BaseTool)` — wraps compute function for agent

Key implementation details:
- Query `Position` → join `Stock` (sector, beta, dividend_yield) → join latest `SignalSnapshot` (composite_score, sharpe_ratio)
- HHI = sum of squared allocation percentages (from Position weights)
- Correlation: query 90-day `StockPrice` for all position tickers, compute pairwise Pearson correlation using numpy
- Concerns: iterate positions, flag any with signal_score < 5.0 or allocation > 25%, flag sectors > 35%
- Strengths: flag positions with signal_score > 8.0, good diversification (HHI < 1000)

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/tools/test_portfolio_health.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/schemas/health.py backend/tools/portfolio_health.py tests/unit/tools/test_portfolio_health.py
git commit -m "feat(intelligence): portfolio health tool — score computation + 12 tests"
```

---

### Task 2: Market Briefing Tool

**Files:**
- Create: `backend/schemas/market.py`
- Create: `backend/tools/market_briefing.py`
- Create: `tests/unit/tools/test_market_briefing.py`

- [ ] **Step 1: Create market schemas**

```python
# backend/schemas/market.py
"""Response schemas for market briefing endpoint and tool."""

from __future__ import annotations

from pydantic import BaseModel


class IndexPerformance(BaseModel):
    """Market index daily performance."""
    name: str
    ticker: str
    price: float
    change_pct: float


class SectorPerformance(BaseModel):
    """Sector ETF daily performance."""
    sector: str
    etf: str
    change_pct: float


class MarketBriefingResult(BaseModel):
    """Complete market briefing response."""
    indexes: list[IndexPerformance]
    sector_performance: list[SectorPerformance]
    portfolio_news: list[dict]
    upcoming_earnings: list[dict]
    top_movers: dict  # {gainers: [...], losers: [...]}
    briefing_date: str
```

- [ ] **Step 2: Write tests**

```python
# tests/unit/tools/test_market_briefing.py
"""Tests for market briefing tool."""

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest


class TestFetchIndexPerformance:
    """Tests for index data fetching."""

    def test_returns_index_data(self) -> None:
        """Should return formatted index performance."""
        from backend.tools.market_briefing import _fetch_index_performance

        mock_data = pd.DataFrame({"Close": [5000.0, 5050.0]}, index=pd.date_range("2026-03-24", periods=2))
        with patch("backend.tools.market_briefing.yf.download", return_value=mock_data):
            result = _fetch_index_performance("^GSPC", "S&P 500")
        assert result["name"] == "S&P 500"
        assert result["change_pct"] == pytest.approx(1.0, abs=0.1)

    def test_empty_data_returns_none(self) -> None:
        """Empty yfinance data should return None."""
        from backend.tools.market_briefing import _fetch_index_performance

        with patch("backend.tools.market_briefing.yf.download", return_value=pd.DataFrame()):
            result = _fetch_index_performance("^GSPC", "S&P 500")
        assert result is None


class TestFetchSectorPerformance:
    """Tests for sector ETF data."""

    def test_returns_sector_list(self) -> None:
        """Should return list of sector performances."""
        from backend.tools.market_briefing import _fetch_sector_etf_performance

        mock_data = pd.DataFrame(
            {"Close": [[100.0, 101.0], [50.0, 49.5]]},
            columns=pd.MultiIndex.from_tuples([("Close", "XLK"), ("Close", "XLV")]),
            index=pd.date_range("2026-03-24", periods=2),
        )
        # This test may need adjustment based on actual yf.download multi-ticker format
        # The key assertion is that the function returns a list of dicts
        pass  # Implementation-dependent — test after implementing
```

- [ ] **Step 3: Implement market_briefing.py**

The tool fetches:
1. Index performance: `yf.download(["^GSPC", "^DJI", "^IXIC", "^VIX"], period="2d")` → compute 1-day change
2. Sector ETFs: `yf.download(["XLK", "XLV", "XLF", "XLE", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE"], period="2d")`
3. Portfolio news: for top 3 holdings by weight, call `fetch_yfinance_news()` from `backend/tools/news.py`
4. Upcoming earnings: for all portfolio + watchlist tickers, call `fetch_next_earnings_date()` from `backend/tools/intelligence.py`
5. Top movers: query `StockPrice` for latest 2 days, compute % change, sort

All yfinance calls run in thread pool via `asyncio.to_thread()`.

- [ ] **Step 4: Run tests + commit**

```bash
uv run pytest tests/unit/tools/test_market_briefing.py -v
git add backend/schemas/market.py backend/tools/market_briefing.py tests/unit/tools/test_market_briefing.py
git commit -m "feat(intelligence): market briefing tool — indexes, sectors, news, earnings"
```

---

### Task 3: Stock Intelligence + Recommend Stocks Tools

**Files:**
- Create: `backend/tools/stock_intelligence.py`
- Create: `backend/schemas/recommend.py`
- Create: `backend/tools/recommend_stocks.py`
- Create: `tests/unit/tools/test_recommend_stocks.py`

- [ ] **Step 1: Implement stock_intelligence.py**

Thin wrapper around `intelligence.py` functions (from Spec C) formatted as a BaseTool:

```python
# backend/tools/stock_intelligence.py
class StockIntelligenceTool(BaseTool):
    name = "get_stock_intelligence"
    description = "Get recent analyst upgrades/downgrades, insider transactions, upcoming earnings, and EPS revisions for a stock."
    category = "data"
    # execute() calls fetch_upgrades_downgrades, fetch_insider_transactions, etc.
```

- [ ] **Step 2: Create recommend schemas**

```python
# backend/schemas/recommend.py
class StockCandidate(BaseModel):
    ticker: str
    name: str
    sector: str
    consensus_count: int
    recommendation_score: float
    sources: list[str]
    rationale: list[str]
    signal_score: float | None
    forward_pe: float | None
    dividend_yield: float | None
    portfolio_correlation: float | None

class RecommendationResult(BaseModel):
    candidates: list[StockCandidate]
    portfolio_context: dict
```

- [ ] **Step 3: Write recommend_stocks tests**

```python
# tests/unit/tools/test_recommend_stocks.py
"""Tests for multi-signal recommendation engine."""

import pytest


class TestConsensusScoring:
    """Tests for multi-source consensus scoring."""

    def test_four_source_consensus_scores_highest(self) -> None:
        """Candidate appearing in all 4 sources should score highest."""
        from backend.tools.recommend_stocks import _compute_recommendation_score
        score = _compute_recommendation_score(
            signal_score=8.5, fundamental_score=8.0,
            momentum_score=7.5, portfolio_fit_score=9.0,
        )
        assert score > 8.0

    def test_single_source_scores_lower(self) -> None:
        """Candidate from only one source should score lower."""
        from backend.tools.recommend_stocks import _compute_recommendation_score
        score = _compute_recommendation_score(
            signal_score=8.5, fundamental_score=0.0,
            momentum_score=0.0, portfolio_fit_score=0.0,
        )
        assert score < 5.0

    def test_weights_sum_to_one(self) -> None:
        """Recommendation weights should sum to 1.0."""
        from backend.tools.recommend_stocks import RECOMMENDATION_WEIGHTS
        assert abs(sum(RECOMMENDATION_WEIGHTS.values()) - 1.0) < 0.01
```

- [ ] **Step 4: Implement recommend_stocks.py**

The tool:
1. Gets portfolio health (calls `compute_portfolio_health` internally)
2. Identifies underweight sectors
3. Queries BUY-rated stocks (`composite_score >= 8`)
4. Ranks by fundamentals (low forward_pe, high ROE, Piotroski >= 7)
5. Computes portfolio correlation for top candidates
6. Merges sources, deduplicates, computes consensus score
7. Returns top 5-10 with per-source rationale

- [ ] **Step 5: Run tests + commit**

```bash
uv run pytest tests/unit/tools/test_recommend_stocks.py -v
git add backend/tools/stock_intelligence.py backend/schemas/recommend.py backend/tools/recommend_stocks.py tests/unit/tools/test_recommend_stocks.py
git commit -m "feat(intelligence): stock intelligence + recommend_stocks tools"
```

---

### Task 4: API Endpoints

**Files:**
- Create: `backend/routers/market.py`
- Modify: `backend/routers/portfolio.py`
- Modify: `backend/main.py`
- Create: `tests/api/test_portfolio_health.py`
- Create: `tests/api/test_market_briefing.py`

- [ ] **Step 1: Create market router**

```python
# backend/routers/market.py
"""Market overview router — briefing, sector performance."""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, Request
from backend.dependencies import get_current_user
from backend.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/market", tags=["market"])

@router.get("/briefing")
async def get_market_briefing(
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    """Get today's market briefing — indexes, sectors, portfolio news, earnings."""
    # Cache check, call MarketBriefingTool, return result
    ...
```

- [ ] **Step 2: Add portfolio health endpoint**

In `backend/routers/portfolio.py`, add:

```python
@router.get("/health", response_model=PortfolioHealthResult)
async def get_portfolio_health(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> PortfolioHealthResult:
    """Get portfolio health score with component breakdown."""
    # Cache check, call compute_portfolio_health, return result
    ...
```

- [ ] **Step 3: Mount market router in main.py**

```python
from backend.routers import market
app.include_router(market.router, prefix="/api/v1")
```

- [ ] **Step 4: Write API tests**

Auth + happy path tests for both endpoints.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/market.py backend/routers/portfolio.py backend/main.py tests/api/
git commit -m "feat(intelligence): portfolio health + market briefing API endpoints"
```

---

### Task 5: Register Tools in ToolRegistry

**Files:**
- Modify: `backend/tools/build_registry.py`

- [ ] **Step 1: Register 4 new tools**

```python
from backend.tools.portfolio_health import PortfolioHealthTool
from backend.tools.market_briefing import MarketBriefingTool
from backend.tools.stock_intelligence import StockIntelligenceTool
from backend.tools.recommend_stocks import RecommendStocksTool

registry.register(PortfolioHealthTool())
registry.register(MarketBriefingTool())
registry.register(StockIntelligenceTool())
registry.register(RecommendStocksTool())
```

- [ ] **Step 2: Run registry tests + commit**

```bash
uv run pytest tests/unit/tools/test_tool_registry.py -v
git add backend/tools/build_registry.py
git commit -m "feat(intelligence): register 4 new tools — 24 total"
```

---

### Task 6: Planner Prompt Updates

**Files:**
- Modify: `backend/agents/prompts/planner.md`
- Modify: `backend/agents/planner.py`
- Modify: `backend/agents/graph.py`

- [ ] **Step 1: Update planner scope + add response_type**

In `planner.md`:
- Add portfolio health, market intelligence, stock news to scope section
- Add `response_type` field to output format JSON
- Add 12 new few-shot examples (all listed in Spec B §4.2)

- [ ] **Step 2: Extract response_type in planner.py**

In `parse_plan_response()`, extract `response_type` from the parsed JSON (default to `"stock_analysis"` for backward compatibility).

- [ ] **Step 3: Add response_type to AgentStateV2**

In `backend/agents/graph.py`:
```python
class AgentStateV2(TypedDict):
    # ... existing fields ...
    response_type: str
```

In `plan_node`, set `response_type` from plan output.

- [ ] **Step 4: Run planner tests + commit**

```bash
uv run pytest tests/unit/agents/test_planner.py -v
git add backend/agents/prompts/planner.md backend/agents/planner.py backend/agents/graph.py
git commit -m "feat(intelligence): planner — 12 new few-shots + response_type routing"
```

---

### Task 7: Synthesizer Response Format Variants

**Files:**
- Modify: `backend/agents/prompts/synthesizer.md`
- Modify: `backend/agents/synthesizer.py`

- [ ] **Step 1: Add 3 response format templates to synthesizer.md**

Add portfolio_health, market_briefing, and recommendation format templates as described in Spec B §5.1.

- [ ] **Step 2: Update synthesizer.py to select format**

Read `response_type` from graph state (passed from planner). Inject the appropriate format section into the synthesizer prompt before calling LLM.

- [ ] **Step 3: Run synthesizer tests + commit**

```bash
uv run pytest tests/unit/agents/test_synthesizer.py -v
git add backend/agents/prompts/synthesizer.md backend/agents/synthesizer.py
git commit -m "feat(intelligence): synthesizer — 3 response format variants based on response_type"
```

---

### Task 8: Final Verification

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest tests/unit/ tests/api/ -q --tb=short
uv run ruff check backend/ tests/
```

- [ ] **Step 2: Verify tool count**

```python
# Should show 24 tools
from backend.tools.build_registry import build_registry
r = build_registry()
print(len(r.discover()))  # 24
```

- [ ] **Step 3: Commit any remaining fixes**

---

## Execution Summary

| Task | Description | New Tests | Files |
|------|-------------|-----------|-------|
| 1 | Portfolio health tool + schemas | 12 | 3 |
| 2 | Market briefing tool + schemas | 3 | 3 |
| 3 | Stock intelligence + recommend tools | 3 | 4 |
| 4 | API endpoints (health + briefing) | 4 | 5 |
| 5 | Register tools in registry | 0 | 1 |
| 6 | Planner prompt + response_type | 0 | 3 |
| 7 | Synthesizer format variants | 0 | 2 |
| 8 | Final verification | 0 | 0 |
| **Total** | | **~22** | **21** |
