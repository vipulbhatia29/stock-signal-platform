# Spec B: Agent Intelligence — Design Spec

**Date**: 2026-03-25
**Phase**: 7 (KAN-147)
**Status**: Draft
**Depends on**: Spec C (Data Enrichment — tools need beta, yield, news, intelligence data)
**Blocks**: Spec D (Materialization)

---

## 1. Problem Statement

The agent pipeline has 20 tools but cannot answer the most common passive investor questions: "How healthy is my portfolio?", "What should I buy?", "What happened in the market today?", "Any news on AAPL?". The planner has 13 few-shot examples but no routes for these intents. The synthesizer has one output format (bull/base/bear) that doesn't fit portfolio or market responses.

---

## 2. New Agent Tools (4)

### 2.1 `get_portfolio_health`

**File:** `backend/tools/portfolio_health.py`
**Category:** `portfolio`
**Registered in ToolRegistry:** Yes

Computes a composite health score (0-10) from 5 components:

| Component | Weight | Data Source | Score Logic |
|-----------|--------|-------------|-------------|
| Diversification | 25% | Position weights → HHI | HHI < 500 = 10, > 2500 = 0, linear |
| Signal Quality | 25% | Weighted avg composite_score from SignalSnapshot | Direct (0-10) |
| Risk-Adjusted Returns | 20% | Weighted avg sharpe_ratio from SignalSnapshot | Sharpe > 1.5 = 10, < 0 = 0, linear |
| Income Stability | 15% | Weighted avg dividend_yield from Stock model | Yield 2-4% = 10, 0% = 3, > 8% = 5 |
| Sector Balance | 15% | Max sector weight from Position sector groups | Max < 25% = 10, > 50% = 0, linear |

**Additional computations:**
- `hhi`: sum of squared allocation percentages
- `effective_stocks`: 1 / HHI (how many equal-weight stocks this equals)
- `weighted_beta`: weighted avg of Stock.beta
- `weighted_sharpe`: weighted avg of SignalSnapshot.sharpe_ratio
- `weighted_yield`: weighted avg of Stock.dividend_yield
- `weighted_composite`: weighted avg of SignalSnapshot.composite_score
- `avg_correlation`: mean pairwise Pearson correlation of 90-day price histories (from StockPrice)
- `top_concerns`: list of actionable concerns (e.g., "Technology at 42%", "TSLA signal score 3.8")
- `top_strengths`: list of portfolio strengths
- `position_details`: per-position contribution to health (signal score, weight, sector, drag/lift)

**DB query pattern:**
```python
# All from existing tables — no new data needed (after Spec C adds beta/yield)
positions = await get_positions_with_pnl(portfolio_id, db)
tickers = [p.ticker for p in positions]
stocks = await db.execute(select(Stock).where(Stock.ticker.in_(tickers)))
signals = await db.execute(
    select(SignalSnapshot)
    .where(SignalSnapshot.ticker.in_(tickers))
    .distinct(SignalSnapshot.ticker)
    .order_by(SignalSnapshot.ticker, SignalSnapshot.computed_at.desc())
)
# For correlation: 90-day prices
prices = await db.execute(
    select(StockPrice)
    .where(StockPrice.ticker.in_(tickers), StockPrice.date >= ninety_days_ago)
    .order_by(StockPrice.ticker, StockPrice.date)
)
```

**Return schema:**
```python
class PortfolioHealthResult(BaseModel):
    health_score: float          # 0-10
    grade: str                   # A+, A, B+, B, C+, C, D, F
    components: dict             # diversification, signal_quality, risk, income, sector_balance (each 0-10)
    metrics: dict                # hhi, effective_stocks, weighted_beta, weighted_sharpe, weighted_yield, avg_correlation
    top_concerns: list[str]
    top_strengths: list[str]
    position_details: list[dict] # per-position: ticker, weight, signal_score, sector, contribution
```

### 2.2 `get_market_briefing`

**File:** `backend/tools/market_briefing.py`
**Category:** `data`
**Registered in ToolRegistry:** Yes

Aggregates a "what should I know today?" response:

1. **Index performance:** ^GSPC, ^DJI, ^IXIC, ^VIX via `yf.download()` (1-day change)
2. **Sector ETF performance:** XLK, XLV, XLF, XLE, XLY, XLP, XLI, XLB, XLU, XLRE (1-day change)
3. **Portfolio-relevant news:** yfinance `.news` for top 3 portfolio holdings (by weight)
4. **Upcoming earnings:** yfinance `.calendar` for all portfolio + watchlist tickers (next 14 days)
5. **Top movers in universe:** top 3 gainers + losers from our stocks table (by recent price change)

**Data sources:** All yfinance (free). Cached with VOLATILE TTL (5 min).

**Return schema:**
```python
class MarketBriefingResult(BaseModel):
    indexes: list[dict]          # [{name, ticker, price, change_pct}]
    sector_performance: list[dict]  # [{sector, etf, change_pct}]
    portfolio_news: list[dict]   # [{ticker, title, link, publisher}]
    upcoming_earnings: list[dict] # [{ticker, name, date}]
    top_movers: dict             # {gainers: [...], losers: [...]}
    briefing_date: str
```

### 2.3 `get_stock_intelligence`

**File:** `backend/tools/stock_intelligence.py`
**Category:** `data`
**Registered in ToolRegistry:** Yes

Wraps the `GET /stocks/{ticker}/intelligence` endpoint from Spec C. Provides the agent with structured access to:
- Recent analyst upgrades/downgrades
- Insider buy/sell activity
- Next earnings date
- EPS revisions
- Recent news headlines

This tool essentially calls the Spec C endpoints and formats for LLM consumption.

### 2.4 `recommend_stocks`

**File:** `backend/tools/recommend_stocks.py`
**Category:** `portfolio`
**Registered in ToolRegistry:** Yes

Multi-signal consensus stock picker. Decomposes "which stocks should I pick?" into 4 parallel signal sources:

**Signal sources:**

1. **Portfolio gap:** Identify underweight sectors from health tool, find BUY-rated stocks in those sectors, compute correlation with existing holdings
2. **Signal engine:** All stocks with composite_score ≥ 8 (from DB)
3. **Fundamentals:** Rank by value + quality (low forward_pe, high ROE, Piotroski ≥ 7, positive revenue_growth)
4. **Momentum:** Sort by recent composite_score improvement or positive earnings surprise

**Merge logic:**
```python
# UNION ALL → DISTINCT by ticker
# Consensus count: how many sources agree (1-4)
# Weighted score: signal (30%) + portfolio_fit (25%) + fundamentals (25%) + momentum (20%)
# Rank by weighted score, return top 5-10 with per-source rationale
```

**Return schema:**
```python
class StockCandidate(BaseModel):
    ticker: str
    name: str
    sector: str
    consensus_count: int         # 1-4
    recommendation_score: float  # 0-10
    sources: list[str]           # ["portfolio_gap", "signals", "fundamentals", "momentum"]
    rationale: list[str]         # human-readable reasons per source
    signal_score: float | None
    forward_pe: float | None
    dividend_yield: float | None
    portfolio_correlation: float | None  # avg correlation with existing holdings

class RecommendationResult(BaseModel):
    candidates: list[StockCandidate]
    portfolio_context: dict      # current sectors, underweight sectors, health_score
```

---

## 3. New API Endpoint

### 3.1 `GET /api/v1/portfolio/health`

**Router:** `backend/routers/portfolio.py`
**Auth:** Required
**Cache:** `user:{uid}:portfolio:health` with VOLATILE TTL (5 min)

Returns `PortfolioHealthResult` for the authenticated user's portfolio. Also backs the dashboard StatTile.

### 3.2 `GET /api/v1/market/briefing`

**Router:** `backend/routers/market.py` (new file)
**Auth:** Required
**Cache:** `app:market:briefing` with VOLATILE TTL (5 min)

Returns `MarketBriefingResult`. App-wide cache since market data is the same for all users (portfolio-relevant news section uses requesting user's portfolio).

---

## 4. Planner Prompt Updates

### 4.1 Updated Scope

Add to "You ONLY handle queries about" in `planner.md`:

```
- **Portfolio health:** diversification, concentration, health score, recommendations, rebalancing
- **Market intelligence:** market overview, trending sectors, earnings calendar, analyst upgrades/downgrades
- **Stock news & intelligence:** recent news, insider activity, EPS revisions, analyst rating changes
```

### 4.2 New Few-Shot Examples (~12)

```
"How healthy is my portfolio?"
→ portfolio: [get_portfolio_health]

"Am I diversified enough?"
→ portfolio: [get_portfolio_health]

"What's dragging down my portfolio?"
→ portfolio: [get_portfolio_health]

"What should I buy?" / "Which stocks should I pick?"
→ portfolio: [get_portfolio_health, recommend_stocks]

"How can I improve my portfolio?"
→ portfolio: [get_portfolio_health, recommend_stocks]

"Should I sell TSLA?"
→ portfolio: [get_portfolio_health, risk_narrative(TSLA), get_stock_intelligence(TSLA)]

"What happened in the market today?"
→ market_overview: [get_market_briefing]

"Any news on AAPL?"
→ stock_analysis: [get_stock_intelligence(AAPL)]

"Any earnings coming up for my stocks?"
→ portfolio: [get_market_briefing]

"Did any analysts upgrade AAPL?"
→ stock_analysis: [get_stock_intelligence(AAPL)]

"Are insiders buying TSLA?"
→ stock_analysis: [get_stock_intelligence(TSLA)]

"What's the best stock to buy right now?"
→ portfolio: [get_portfolio_health, recommend_stocks]
  (redirected from previous decline to data-driven recommendation)
```

### 4.3 Response Type Field

Add `response_type` to planner output format:

```json
{
  "intent": "portfolio",
  "response_type": "portfolio_health" | "stock_analysis" | "market_briefing" | "recommendation" | "simple",
  "reasoning": "...",
  "steps": [...]
}
```

Default: `"stock_analysis"` (backward compatible). The synthesizer uses this to select output format.

---

## 5. Synthesizer Prompt Updates

### 5.1 Response Format Variants

Add conditional formats based on `response_type`:

**`portfolio_health` format:**
```json
{
  "summary": "Your portfolio scores 7.2/10 (B+)...",
  "health_score": 7.2,
  "grade": "B+",
  "key_findings": ["Technology overweight at 35%", "Strong signal quality 8.1"],
  "action_items": ["Consider reducing tech exposure", "Review TSLA (AVOID signal)"],
  "evidence": [...],
  "gaps": []
}
```

**`market_briefing` format:**
```json
{
  "summary": "Markets mixed today. S&P 500 +0.3%, NASDAQ -0.1%...",
  "highlights": ["S&P 500 near all-time high", "Energy sector leading (+1.8%)"],
  "portfolio_impact": "Your holdings are mostly neutral. AAPL earnings in 3 days.",
  "upcoming_events": ["AAPL earnings Mar 28", "FOMC meeting Apr 2"],
  "evidence": [...],
  "gaps": []
}
```

**`recommendation` format:**
```json
{
  "summary": "Based on your portfolio gaps and market signals, here are top picks...",
  "candidates": [...],
  "portfolio_context": "Your portfolio is Technology-heavy (42%). Recommendations focus on Healthcare and Consumer Staples.",
  "evidence": [...],
  "gaps": []
}
```

**`stock_analysis` format:** Unchanged (existing bull/base/bear scenarios).

### 5.2 Synthesizer Selection Logic

In `backend/agents/synthesizer.py`, before calling the LLM, select the appropriate prompt section based on `response_type` from planner output. Pass `response_type` through the graph state.

---

## 6. Graph State Update

Add `response_type` to `AgentStateV2` in `backend/agents/graph.py`:

```python
class AgentStateV2(TypedDict):
    # ... existing fields ...
    response_type: str  # "stock_analysis" | "portfolio_health" | "market_briefing" | "recommendation" | "simple"
```

Set by `plan_node` from planner output. Read by `synthesize_node` to select prompt format.

---

## 7. Tool Registration

In `backend/tools/build_registry.py`, register the 4 new tools:

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

Total tools: 24 (was 20).

---

## 8. Files Changed

| Action | File | Change |
|--------|------|--------|
| **Create** | `backend/tools/portfolio_health.py` | Health score computation + PortfolioHealthTool |
| **Create** | `backend/tools/market_briefing.py` | Market overview + MarketBriefingTool |
| **Create** | `backend/tools/stock_intelligence.py` | News/upgrades/insider wrapper + StockIntelligenceTool |
| **Create** | `backend/tools/recommend_stocks.py` | Multi-signal consensus + RecommendStocksTool |
| **Create** | `backend/routers/market.py` | Market briefing endpoint |
| **Create** | `backend/schemas/health.py` | PortfolioHealthResult + components schemas |
| **Create** | `backend/schemas/market.py` | MarketBriefingResult schema |
| **Create** | `backend/schemas/recommend.py` | StockCandidate + RecommendationResult schemas |
| **Modify** | `backend/routers/portfolio.py` | Add GET /portfolio/health endpoint |
| **Modify** | `backend/tools/build_registry.py` | Register 4 new tools |
| **Modify** | `backend/agents/prompts/planner.md` | Updated scope + 12 new few-shots + response_type |
| **Modify** | `backend/agents/prompts/synthesizer.md` | 3 new response format templates |
| **Modify** | `backend/agents/graph.py` | Add response_type to AgentStateV2 + pass through nodes |
| **Modify** | `backend/agents/synthesizer.py` | Read response_type, select prompt format |
| **Modify** | `backend/agents/planner.py` | Extract response_type from plan |
| **Modify** | `backend/main.py` | Mount market router |
| **Create** | `tests/unit/tools/test_portfolio_health.py` | Health score computation tests |
| **Create** | `tests/unit/tools/test_market_briefing.py` | Market briefing tests |
| **Create** | `tests/unit/tools/test_recommend_stocks.py` | Recommendation engine tests |
| **Create** | `tests/api/test_portfolio_health.py` | API endpoint tests |
| **Create** | `tests/api/test_market_briefing.py` | API endpoint tests |

---

## 9. Success Criteria

- [ ] "How healthy is my portfolio?" → health score with component breakdown
- [ ] "What should I buy?" → multi-signal candidates with rationale
- [ ] "What happened in the market today?" → index/sector/news/earnings briefing
- [ ] "Any news on AAPL?" → structured news + upgrades + insider activity
- [ ] "Am I diversified?" → HHI + correlation + sector balance analysis
- [ ] "What's dragging me down?" → per-position contribution ranking
- [ ] Planner correctly routes all 12 new question types
- [ ] Synthesizer produces appropriate format for each response type
- [ ] 24 total agent tools (was 20)
- [ ] All existing tests pass

---

## 10. Out of Scope

- Portfolio optimizer (mean-variance optimization) → too complex, future
- Real-time price streaming → WebSocket, future
- Sentiment scoring on news → could use Alpha Vantage later
- Target allocation tracking → needs user to define targets first
- Tax-loss harvesting suggestions → regulatory complexity
