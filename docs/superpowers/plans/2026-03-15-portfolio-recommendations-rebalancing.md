# Portfolio-Aware Recommendations + Rebalancing Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the recommendation engine to factor in current portfolio holdings (HOLD/SELL actions) and add a rebalancing endpoint that suggests specific dollar amounts to bring each position to its target allocation.

**Architecture:** Two independent additions — (1) `generate_recommendation()` gains an optional `portfolio_state` param that changes action to HOLD/SELL when appropriate, (2) a new `calculate_position_size()` pure function + `GET /api/v1/portfolio/rebalancing` endpoint + `RebalancingPanel` frontend component. The existing score-threshold logic is unchanged; portfolio context only overrides the action when the stock is held.

**Tech Stack:** Python/FastAPI backend, SQLAlchemy async, Pydantic v2, Next.js/TypeScript/TanStack Query frontend, shadcn/ui, Tailwind CSS.

---

## Chunk 1: Backend — Portfolio-Aware Recommendation Engine

### Task 1: Extend `generate_recommendation()` with portfolio state

**Files:**
- Modify: `backend/tools/recommendations.py`
- Modify: `backend/schemas/stocks.py` (add `suggested_amount` field to `RecommendationResponse`)
- Test: `tests/unit/test_recommendations.py`

#### Background

Currently `generate_recommendation()` only returns BUY / WATCH / AVOID based on score thresholds. We need to add HOLD and SELL actions when the user already holds the stock. The logic (from FSD FR-4.1):

```
score >= 8 AND held AND allocation >= max_position_pct  →  HOLD (HIGH)
score >= 5 AND held                                      →  HOLD (MEDIUM)
score <  5 AND held                                      →  SELL (MEDIUM)
score <  2 AND held                                      →  SELL (HIGH)
all other cases                                          →  existing BUY/WATCH/AVOID logic
```

The `portfolio_state` param is a simple dict: `{"allocation_pct": float | None, "is_held": bool}`. This keeps the function pure and testable without a DB dependency.

- [ ] **Step 1: Write the failing tests first**

Add to `tests/unit/test_recommendations.py`:

```python
from backend.tools.recommendations import generate_recommendation, Action, Confidence
# (PortfolioState is just a TypedDict — import once it exists)

def _make_signal(score: float, ticker: str = "AAPL") -> SignalResult:
    """Helper already exists in the test file — use it."""
    ...  # use existing make_signal helper

# --- Portfolio-aware tests ---

def test_held_strong_signal_at_max_allocation_returns_hold():
    signal = make_signal("AAPL", composite_score=9.0)
    portfolio_state = {"is_held": True, "allocation_pct": 5.5}  # over 5% default
    result = generate_recommendation(signal, current_price=150.0, portfolio_state=portfolio_state)
    assert result.action == Action.HOLD
    assert result.confidence == Confidence.HIGH
    assert "already at target allocation" in result.reasoning["summary"].lower()

def test_held_medium_signal_returns_hold():
    signal = make_signal("AAPL", composite_score=6.0)
    portfolio_state = {"is_held": True, "allocation_pct": 2.0}
    result = generate_recommendation(signal, current_price=150.0, portfolio_state=portfolio_state)
    assert result.action == Action.HOLD
    assert result.confidence == Confidence.MEDIUM

def test_held_weak_signal_returns_sell():
    signal = make_signal("AAPL", composite_score=3.0)
    portfolio_state = {"is_held": True, "allocation_pct": 2.0}
    result = generate_recommendation(signal, current_price=150.0, portfolio_state=portfolio_state)
    assert result.action == Action.SELL
    assert result.confidence == Confidence.MEDIUM

def test_held_very_weak_signal_returns_sell_high_confidence():
    signal = make_signal("AAPL", composite_score=1.5)
    portfolio_state = {"is_held": True, "allocation_pct": 3.0}
    result = generate_recommendation(signal, current_price=150.0, portfolio_state=portfolio_state)
    assert result.action == Action.SELL
    assert result.confidence == Confidence.HIGH

def test_not_held_strong_signal_still_returns_buy():
    signal = make_signal("AAPL", composite_score=8.5)
    portfolio_state = {"is_held": False, "allocation_pct": None}
    result = generate_recommendation(signal, current_price=150.0, portfolio_state=portfolio_state)
    assert result.action == Action.BUY

def test_no_portfolio_state_preserves_existing_logic():
    """Passing None for portfolio_state must not change existing behavior."""
    signal = make_signal("AAPL", composite_score=8.5)
    result = generate_recommendation(signal, current_price=150.0, portfolio_state=None)
    assert result.action == Action.BUY

def test_held_strong_signal_under_max_allocation_returns_buy():
    """Still held but not at cap — should still recommend BUY."""
    signal = make_signal("AAPL", composite_score=8.5)
    portfolio_state = {"is_held": True, "allocation_pct": 2.0}  # under 5% default
    result = generate_recommendation(
        signal, current_price=150.0,
        portfolio_state=portfolio_state,
        max_position_pct=5.0,
    )
    assert result.action == Action.BUY
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/unit/test_recommendations.py -k "portfolio" -v
```

Expected: ImportError or NameError (portfolio_state param doesn't exist yet).

- [ ] **Step 3: Implement the upgrade in `backend/tools/recommendations.py`**

Add a `PortfolioState` TypedDict at the top (after existing imports):

```python
from typing import TypedDict

class PortfolioState(TypedDict, total=False):
    """Minimal portfolio context passed to the recommendation engine."""
    is_held: bool
    allocation_pct: float | None
```

Add `Action.HOLD` and `Action.SELL` to the `Action` class:

```python
class Action:
    BUY = "BUY"
    WATCH = "WATCH"
    AVOID = "AVOID"
    HOLD = "HOLD"
    SELL = "SELL"
```

Update `generate_recommendation()` signature:

```python
def generate_recommendation(
    signal: SignalResult,
    current_price: float,
    portfolio_state: PortfolioState | None = None,
    max_position_pct: float = 5.0,
) -> RecommendationResult:
```

Insert portfolio override block BEFORE the existing score-threshold block:

```python
# ── Portfolio-aware overrides ────────────────────────────────────
# When the user already holds this stock, context changes the action.
# HOLD means "keep it, don't buy more"; SELL means "signals are weak, exit".
if portfolio_state and portfolio_state.get("is_held"):
    alloc = portfolio_state.get("allocation_pct") or 0.0

    if score >= BUY_THRESHOLD and alloc >= max_position_pct:
        reasoning["summary"] = (
            f"Strong signals (score {score}/10) but already at target allocation "
            f"({alloc:.1f}% ≥ {max_position_pct:.1f}%). Hold current position."
        )
        return RecommendationResult(
            ticker=signal.ticker,
            action=Action.HOLD,
            confidence=Confidence.HIGH,
            composite_score=score,
            current_price=current_price,
            reasoning=reasoning,
            is_actionable=True,
        )

    if score >= WATCH_THRESHOLD:
        reasoning["summary"] = (
            f"Moderate signals (score {score}/10). You hold this stock — hold your position."
        )
        return RecommendationResult(
            ticker=signal.ticker,
            action=Action.HOLD,
            confidence=Confidence.MEDIUM,
            composite_score=score,
            current_price=current_price,
            reasoning=reasoning,
            is_actionable=False,
        )

    # score < WATCH_THRESHOLD while held → SELL
    confidence = Confidence.HIGH if score < 2.0 else Confidence.MEDIUM
    reasoning["summary"] = (
        f"Weak signals (score {score}/10) and you hold this stock. "
        "Consider exiting the position."
    )
    return RecommendationResult(
        ticker=signal.ticker,
        action=Action.SELL,
        confidence=confidence,
        composite_score=score,
        current_price=current_price,
        reasoning=reasoning,
        is_actionable=True,
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_recommendations.py -v
```

Expected: all pass (both old and new tests).

- [ ] **Step 5: Add `suggested_amount` to `RecommendationResult` dataclass and `RecommendationResponse` schema**

In `backend/tools/recommendations.py`, add to `RecommendationResult`:

```python
suggested_amount: float | None = None  # dollar amount to invest (BUY only)
```

In `backend/schemas/stocks.py`, add to `RecommendationResponse`:

```python
suggested_amount: float | None = None
```

- [ ] **Step 6: Commit**

```bash
git add backend/tools/recommendations.py backend/schemas/stocks.py tests/unit/test_recommendations.py
git commit -m "feat: portfolio-aware recommendations — HOLD/SELL actions with portfolio context"
```

---

### Task 2: `calculate_position_size()` pure function

**Files:**
- Modify: `backend/tools/recommendations.py`
- Test: `tests/unit/test_recommendations.py`

#### Background

FSD FR-4.2 defines position sizing as:

```
target_pct = min(max_position_pct, 100 / num_target_positions)
gap_pct    = target_pct - current_allocation_pct
suggested  = min(gap_pct * total_value / 100, available_cash)
→ 0 if sector is at cap
→ 0 if suggested < $100
```

`available_cash = total_value - sum(market_values)` — computed by the caller, passed in.

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_recommendations.py`:

```python
from backend.tools.recommendations import calculate_position_size

def test_position_size_basic():
    """Normal case: stock not held, plenty of cash, under sector cap."""
    amount = calculate_position_size(
        ticker="AAPL",
        current_allocation_pct=0.0,
        total_value=100_000.0,
        available_cash=20_000.0,
        num_target_positions=20,
        max_position_pct=5.0,
        sector_allocation_pct=10.0,
        max_sector_pct=30.0,
    )
    # target = min(5%, 100/20=5%) = 5% → gap = 5% → 5% * 100k = 5000
    assert amount == 5000.0

def test_position_size_already_at_target():
    """Already at target allocation → 0."""
    amount = calculate_position_size(
        ticker="AAPL",
        current_allocation_pct=5.0,
        total_value=100_000.0,
        available_cash=10_000.0,
        num_target_positions=20,
        max_position_pct=5.0,
        sector_allocation_pct=10.0,
        max_sector_pct=30.0,
    )
    assert amount == 0.0

def test_position_size_sector_at_cap():
    """Sector already full → 0 regardless of gap."""
    amount = calculate_position_size(
        ticker="AAPL",
        current_allocation_pct=0.0,
        total_value=100_000.0,
        available_cash=20_000.0,
        num_target_positions=20,
        max_position_pct=5.0,
        sector_allocation_pct=30.0,  # at cap
        max_sector_pct=30.0,
    )
    assert amount == 0.0

def test_position_size_capped_by_cash():
    """Suggested amount exceeds available cash → capped."""
    amount = calculate_position_size(
        ticker="AAPL",
        current_allocation_pct=0.0,
        total_value=100_000.0,
        available_cash=1_000.0,  # only $1k available
        num_target_positions=20,
        max_position_pct=5.0,
        sector_allocation_pct=5.0,
        max_sector_pct=30.0,
    )
    assert amount == 1000.0

def test_position_size_below_minimum():
    """Suggested < $100 → 0 (too small to be worth trading)."""
    amount = calculate_position_size(
        ticker="AAPL",
        current_allocation_pct=4.9,
        total_value=100_000.0,
        available_cash=5_000.0,
        num_target_positions=20,
        max_position_pct=5.0,
        sector_allocation_pct=5.0,
        max_sector_pct=30.0,
    )
    # gap = 0.1% → 0.001 * 100k = $100 — exactly at boundary, should pass
    assert amount == 100.0

def test_position_size_rounds_to_cents():
    """Result is rounded to 2 decimal places."""
    amount = calculate_position_size(
        ticker="AAPL",
        current_allocation_pct=0.0,
        total_value=33_333.0,
        available_cash=50_000.0,
        num_target_positions=20,
        max_position_pct=5.0,
        sector_allocation_pct=5.0,
        max_sector_pct=30.0,
    )
    assert amount == round(amount, 2)
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/unit/test_recommendations.py -k "position_size" -v
```

Expected: ImportError (function doesn't exist yet).

- [ ] **Step 3: Implement `calculate_position_size()`**

Add to `backend/tools/recommendations.py` (after `generate_recommendation`):

```python
MIN_TRADE_SIZE = 100.0  # minimum dollar amount worth recommending


def calculate_position_size(
    ticker: str,
    current_allocation_pct: float,
    total_value: float,
    available_cash: float,
    num_target_positions: int,
    max_position_pct: float,
    sector_allocation_pct: float,
    max_sector_pct: float,
) -> float:
    """Calculate how many dollars to invest in a BUY recommendation.

    Uses equal-weight targeting capped by max_position_pct and sector cap.
    Returns 0 if the sector is full, the position is already at target,
    or the suggested amount is below the minimum trade size ($100).

    Args:
        ticker: Stock ticker (used for logging only).
        current_allocation_pct: Current position size as % of portfolio.
        total_value: Total portfolio market value in dollars.
        available_cash: Cash available (total_value - sum of position values).
        num_target_positions: Number of positions to target for equal weighting.
        max_position_pct: Maximum single-position size (from UserPreference).
        sector_allocation_pct: Current sector allocation as % of portfolio.
        max_sector_pct: Maximum sector concentration (from UserPreference).

    Returns:
        Suggested dollar amount to invest, rounded to 2 decimal places.
        Returns 0.0 if the position should not be added to.
    """
    # Sector cap check — if sector is full, don't add more exposure
    if sector_allocation_pct >= max_sector_pct:
        logger.debug("Skipping %s: sector at cap (%.1f%% >= %.1f%%)",
                     ticker, sector_allocation_pct, max_sector_pct)
        return 0.0

    # Equal-weight target, capped by max_position_pct
    equal_weight_pct = 100.0 / max(num_target_positions, 1)
    target_pct = min(max_position_pct, equal_weight_pct)

    # How much more room do we have?
    gap_pct = target_pct - current_allocation_pct
    if gap_pct <= 0:
        return 0.0

    # Dollar amount needed to fill the gap, limited by available cash
    suggested = min(gap_pct / 100.0 * total_value, available_cash)

    if suggested < MIN_TRADE_SIZE:
        return 0.0

    return round(suggested, 2)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_recommendations.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/tools/recommendations.py tests/unit/test_recommendations.py
git commit -m "feat: calculate_position_size() — equal-weight targeting with sector cap"
```

---

## Chunk 2: Backend — Rebalancing Endpoint

### Task 3: Rebalancing schemas + endpoint

**Files:**
- Modify: `backend/schemas/portfolio.py` (add `RebalancingSuggestion`, `RebalancingResponse`)
- Modify: `backend/routers/portfolio.py` (add `GET /api/v1/portfolio/rebalancing`)
- Test: `tests/api/test_portfolio.py`

#### Background

The rebalancing endpoint fetches the user's portfolio, computes available cash (`total_value - invested`), and runs `calculate_position_size()` for every held position. It returns a list of suggestions (one per position) with `action`, `suggested_amount`, and a short `reason`.

Positions that are at target allocation get `suggested_amount=0` and `action="HOLD"`. Positions over target could in principle get a `SELL` suggestion, but for simplicity in Phase 3.5, we only suggest adding to under-weight positions. SELL from the divestment engine covers the rest.

- [ ] **Step 1: Write failing API test**

Add to `tests/api/test_portfolio.py`:

```python
async def test_rebalancing_requires_auth(client):
    response = await client.get("/api/v1/portfolio/rebalancing")
    assert response.status_code == 401

async def test_rebalancing_empty_portfolio(auth_client):
    response = await auth_client.get("/api/v1/portfolio/rebalancing")
    assert response.status_code == 200
    data = response.json()
    assert data["suggestions"] == []
    assert data["total_value"] == 0.0
    assert data["available_cash"] == 0.0

async def test_rebalancing_with_positions(auth_client, db_session, test_user):
    # Set up: create a stock + position via the transactions endpoint
    # (reuse existing helpers from test_portfolio.py)
    # Then call rebalancing and verify structure
    response = await auth_client.get("/api/v1/portfolio/rebalancing")
    assert response.status_code == 200
    data = response.json()
    assert "suggestions" in data
    assert "total_value" in data
    assert "available_cash" in data
    assert "num_positions" in data
    for s in data["suggestions"]:
        assert "ticker" in s
        assert "action" in s
        assert "current_allocation_pct" in s
        assert "target_allocation_pct" in s
        assert "suggested_amount" in s
        assert "reason" in s
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/api/test_portfolio.py -k "rebalanc" -v
```

Expected: 404 (endpoint doesn't exist yet).

- [ ] **Step 3: Add schemas to `backend/schemas/portfolio.py`**

```python
class RebalancingSuggestion(BaseModel):
    """Single rebalancing suggestion for one position."""

    ticker: str
    action: str                      # "BUY_MORE" | "HOLD" | "AT_CAP"
    current_allocation_pct: float | None
    target_allocation_pct: float
    suggested_amount: float          # 0.0 means no action needed
    reason: str


class RebalancingResponse(BaseModel):
    """Full rebalancing output for the portfolio."""

    total_value: float
    available_cash: float
    num_positions: int
    suggestions: list[RebalancingSuggestion]
```

- [ ] **Step 4: Add endpoint to `backend/routers/portfolio.py`**

```python
@router.get("/rebalancing", response_model=RebalancingResponse)
async def get_rebalancing(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> RebalancingResponse:
    """Compute rebalancing suggestions for all open positions.

    For each held position, calculates how much the user would need to invest
    to bring it to its equal-weight target (capped by max_position_pct and
    max_sector_pct from UserPreference).

    Available cash is computed as total_value - sum(market_values) — i.e.,
    what is not currently invested.
    """
    portfolio = await _get_or_create_portfolio(current_user.id, db)
    pref = await _get_or_create_preference(current_user.id, db)

    positions = await get_positions_with_pnl(portfolio.id, db)

    if not positions:
        return RebalancingResponse(
            total_value=0.0,
            available_cash=0.0,
            num_positions=0,
            suggestions=[],
        )

    # Compute portfolio totals
    total_invested = sum(p.market_value or 0.0 for p in positions)
    # Available cash = whatever's not invested (Phase 3.5: no explicit cash account)
    # We use total_value = total_invested here (no cash balance tracked yet).
    # available_cash reflects how much more could theoretically be deployed if
    # the user has external funds — for now we set it to 0 as a conservative default
    # since we don't track cash. The suggested_amount is still computed correctly
    # against total_invested.
    total_value = total_invested
    available_cash = 0.0  # no cash account in Phase 3.5

    num_positions = len(positions)

    # Build sector allocation map for sector cap checks
    sector_totals: dict[str, float] = {}
    for p in positions:
        if p.sector and p.market_value:
            sector_totals[p.sector] = sector_totals.get(p.sector, 0.0) + p.market_value
    sector_pct_map: dict[str, float] = {
        sector: (val / total_value * 100) if total_value > 0 else 0.0
        for sector, val in sector_totals.items()
    }

    suggestions = []
    for pos in positions:
        alloc = pos.allocation_pct or 0.0
        sector_alloc = sector_pct_map.get(pos.sector or "", 0.0)

        amount = calculate_position_size(
            ticker=pos.ticker,
            current_allocation_pct=alloc,
            total_value=total_value,
            available_cash=available_cash,
            num_target_positions=num_positions,
            max_position_pct=pref.max_position_pct,
            sector_allocation_pct=sector_alloc,
            max_sector_pct=pref.max_sector_pct,
        )

        equal_weight_pct = 100.0 / max(num_positions, 1)
        target_pct = min(pref.max_position_pct, equal_weight_pct)

        if sector_alloc >= pref.max_sector_pct:
            action = "AT_CAP"
            reason = f"Sector {pos.sector or 'Unknown'} is at the {pref.max_sector_pct:.0f}% cap"
        elif amount > 0:
            action = "BUY_MORE"
            reason = (
                f"Under-weight ({alloc:.1f}% vs {target_pct:.1f}% target). "
                f"Add ${amount:,.2f} to reach target."
            )
        else:
            action = "HOLD"
            reason = f"At or above target allocation ({alloc:.1f}% ≥ {target_pct:.1f}%)"

        suggestions.append(
            RebalancingSuggestion(
                ticker=pos.ticker,
                action=action,
                current_allocation_pct=alloc,
                target_allocation_pct=round(target_pct, 2),
                suggested_amount=amount,
                reason=reason,
            )
        )

    # Sort: BUY_MORE first (highest gap), then HOLD, then AT_CAP
    action_order = {"BUY_MORE": 0, "HOLD": 1, "AT_CAP": 2}
    suggestions.sort(key=lambda s: (action_order.get(s.action, 9), -s.suggested_amount))

    return RebalancingResponse(
        total_value=total_value,
        available_cash=available_cash,
        num_positions=num_positions,
        suggestions=suggestions,
    )
```

**Note:** Import `calculate_position_size` from `backend.tools.recommendations` at the top of `portfolio.py`.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/api/test_portfolio.py -v
```

Expected: all pass including new rebalancing tests.

- [ ] **Step 6: Lint**

```bash
uv run ruff check backend/ --fix && uv run ruff format backend/
```

Expected: zero errors.

- [ ] **Step 7: Commit**

```bash
git add backend/schemas/portfolio.py backend/routers/portfolio.py tests/api/test_portfolio.py
git commit -m "feat: GET /api/v1/portfolio/rebalancing — position sizing suggestions"
```

---

### Task 4: Wire `suggested_amount` into the ingest/recommendation pipeline

**Files:**
- Modify: `backend/routers/stocks.py` (`ingest_ticker` handler — pass portfolio state when available)

#### Background

The `ingest_ticker` endpoint currently calls `generate_recommendation()` without portfolio context. We need to optionally pass the user's portfolio state so stored recommendations get HOLD/SELL actions when appropriate.

This is best-effort: if the user has no portfolio, we skip portfolio context (existing behavior). The positions are already fetched in a later step in the ingest flow if needed — here we add a lightweight check.

- [ ] **Step 1: Read the ingest endpoint**

```bash
# Check ingest_ticker in backend/routers/stocks.py around line 400
```

- [ ] **Step 2: Modify `ingest_ticker` to pass portfolio state**

In `ingest_ticker`, after computing the signal, before calling `generate_recommendation`, add:

```python
# ── Optional portfolio context ────────────────────────────────────────
# If the user has this stock in their portfolio, pass allocation context
# so the recommendation engine can return HOLD/SELL instead of BUY.
portfolio_state = None
try:
    from backend.routers.portfolio import _get_or_create_portfolio
    from backend.tools.portfolio import get_positions_with_pnl
    portfolio = await _get_or_create_portfolio(current_user.id, db)
    positions = await get_positions_with_pnl(portfolio.id, db)
    pos_map = {p.ticker: p for p in positions}
    if ticker in pos_map:
        p = pos_map[ticker]
        portfolio_state = {
            "is_held": True,
            "allocation_pct": p.allocation_pct or 0.0,
        }
    pref_result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == current_user.id)
    )
    pref = pref_result.scalar_one_or_none()
    max_position_pct = pref.max_position_pct if pref else 5.0
except Exception:
    logger.warning("Could not load portfolio context for %s — using basic recommendation", ticker)
    portfolio_state = None
    max_position_pct = 5.0

rec = generate_recommendation(
    signal_result,
    current_price=float(latest_price),
    portfolio_state=portfolio_state,
    max_position_pct=max_position_pct,
)
```

- [ ] **Step 3: Run all unit + API tests**

```bash
uv run pytest tests/unit/ tests/api/ -v
```

Expected: all 250+ tests pass (no regressions).

- [ ] **Step 4: Commit**

```bash
git add backend/routers/stocks.py
git commit -m "feat: wire portfolio context into ingest recommendation engine"
```

---

## Chunk 3: Frontend — Rebalancing Panel

### Task 5: TypeScript types + data hook

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/hooks/use-stocks.ts`

- [ ] **Step 1: Add types to `frontend/src/types/api.ts`**

```typescript
export interface RebalancingSuggestion {
  ticker: string;
  action: "BUY_MORE" | "HOLD" | "AT_CAP";
  current_allocation_pct: number | null;
  target_allocation_pct: number;
  suggested_amount: number;
  reason: string;
}

export interface RebalancingResponse {
  total_value: number;
  available_cash: number;
  num_positions: number;
  suggestions: RebalancingSuggestion[];
}
```

- [ ] **Step 2: Add hook to `frontend/src/hooks/use-stocks.ts`**

Near the other portfolio hooks (at the bottom of the file):

```typescript
export function useRebalancing() {
  return useQuery<RebalancingResponse>({
    queryKey: ["portfolio", "rebalancing"],
    queryFn: () => get<RebalancingResponse>("/api/v1/portfolio/rebalancing"),
    staleTime: 5 * 60 * 1000, // 5 min — positions don't change that fast
  });
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: zero type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/hooks/use-stocks.ts
git commit -m "feat: RebalancingResponse types + useRebalancing hook"
```

---

### Task 6: `RebalancingPanel` component

**Files:**
- Create: `frontend/src/components/rebalancing-panel.tsx`
- Modify: `frontend/src/app/(authenticated)/portfolio/portfolio-client.tsx`

#### Design

A collapsible section below the positions table (above the allocation pie) showing a compact table:

| Ticker | Current % | Target % | Action | Suggested |
|--------|-----------|----------|--------|-----------|
| AAPL   | 2.1%      | 5.0%     | BUY MORE | $2,900 |
| MSFT   | 5.1%      | 5.0%     | HOLD   | — |

- BUY_MORE rows: green `suggested_amount` + a subtle green left border
- HOLD rows: muted
- AT_CAP rows: amber badge

Hidden when portfolio is empty or all suggestions are HOLD.

- [ ] **Step 1: Create `frontend/src/components/rebalancing-panel.tsx`**

```tsx
"use client";

import { RebalancingSuggestion } from "@/types/api";
import { SectionHeading } from "@/components/section-heading";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface Props {
  suggestions: RebalancingSuggestion[];
  totalValue: number;
}

const ACTION_LABEL: Record<RebalancingSuggestion["action"], string> = {
  BUY_MORE: "Buy more",
  HOLD: "Hold",
  AT_CAP: "At cap",
};

const ACTION_VARIANT: Record<
  RebalancingSuggestion["action"],
  "default" | "secondary" | "outline"
> = {
  BUY_MORE: "default",
  HOLD: "secondary",
  AT_CAP: "outline",
};

export function RebalancingPanel({ suggestions, totalValue }: Props) {
  const actionable = suggestions.filter((s) => s.action === "BUY_MORE");

  if (suggestions.length === 0) return null;

  return (
    <div className="mt-6">
      <SectionHeading
        title="Rebalancing"
        subtitle={
          actionable.length > 0
            ? `${actionable.length} position${actionable.length > 1 ? "s" : ""} under target allocation`
            : "All positions at target allocation"
        }
      />
      <div className="rounded-lg border border-border overflow-hidden mt-3">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="text-left px-4 py-2 font-medium text-muted-foreground">Ticker</th>
              <th className="text-right px-4 py-2 font-medium text-muted-foreground">Current</th>
              <th className="text-right px-4 py-2 font-medium text-muted-foreground">Target</th>
              <th className="text-center px-4 py-2 font-medium text-muted-foreground">Action</th>
              <th className="text-right px-4 py-2 font-medium text-muted-foreground">Suggested</th>
            </tr>
          </thead>
          <tbody>
            {suggestions.map((s) => (
              <tr
                key={s.ticker}
                className={cn(
                  "border-b border-border last:border-0 transition-colors hover:bg-muted/20",
                  s.action === "BUY_MORE" && "border-l-2 border-l-[var(--color-gain)]"
                )}
              >
                <td className="px-4 py-2.5 font-mono font-medium">{s.ticker}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">
                  {s.current_allocation_pct != null
                    ? `${s.current_allocation_pct.toFixed(1)}%`
                    : "—"}
                </td>
                <td className="px-4 py-2.5 text-right tabular-nums text-muted-foreground">
                  {s.target_allocation_pct.toFixed(1)}%
                </td>
                <td className="px-4 py-2.5 text-center">
                  <Badge variant={ACTION_VARIANT[s.action]}>
                    {ACTION_LABEL[s.action]}
                  </Badge>
                </td>
                <td
                  className={cn(
                    "px-4 py-2.5 text-right tabular-nums font-medium",
                    s.action === "BUY_MORE" && "text-[var(--color-gain)]"
                  )}
                >
                  {s.suggested_amount > 0
                    ? `$${s.suggested_amount.toLocaleString("en-US", {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}`
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground mt-2">
        Targets based on equal-weight across {suggestions.length} positions, capped by your
        concentration limits.
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Wire into `portfolio-client.tsx`**

At the top, add the import:

```typescript
import { RebalancingPanel } from "@/components/rebalancing-panel";
import { useRebalancing } from "@/hooks/use-stocks";
```

Inside `PortfolioClient`, add the hook:

```typescript
const { data: rebalancing } = useRebalancing();
```

After the existing positions/allocation section (look for the `<div className="grid ... lg:grid-cols-5">` that holds positions + pie), add the panel below it:

```tsx
{rebalancing && rebalancing.suggestions.length > 0 && (
  <RebalancingPanel
    suggestions={rebalancing.suggestions}
    totalValue={rebalancing.total_value}
  />
)}
```

- [ ] **Step 3: TypeScript + lint check**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

Expected: zero errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/rebalancing-panel.tsx frontend/src/app/(authenticated)/portfolio/portfolio-client.tsx
git commit -m "feat: RebalancingPanel — per-position rebalancing suggestions on portfolio page"
```

---

## Chunk 4: Housekeeping + Verification

### Task 7: Archive completed sprint docs + full test run

**Files:**
- Move: `docs/superpowers/specs/2026-03-14-divestment-rules-engine-design.md` → `docs/superpowers/archive/`
- Move: `docs/superpowers/plans/divestment-rules-implementation.md` → `docs/superpowers/archive/`

- [ ] **Step 1: Archive divestment docs**

```bash
mv docs/superpowers/specs/2026-03-14-divestment-rules-engine-design.md docs/superpowers/archive/
mv docs/superpowers/plans/divestment-rules-implementation.md docs/superpowers/archive/
```

- [ ] **Step 2: Full test suite**

```bash
uv run pytest tests/unit/ tests/api/ -v --tb=short
```

Expected: all tests pass (250+ baseline + new tests from this plan).

- [ ] **Step 3: Frontend build**

```bash
cd frontend && npm run build
```

Expected: zero errors, zero type errors.

- [ ] **Step 4: Lint both**

```bash
uv run ruff check backend/ tests/ --fix && uv run ruff format backend/ tests/
cd frontend && npm run lint
```

Expected: zero errors.

- [ ] **Step 5: Update docs + PROGRESS.md + Serena memories**

Update:
- `PROGRESS.md` — add session entry for this work
- `project-plan.md` — mark items 10 and 11 ✅
- `docs/FSD.md` — verify FR-4.1 and FR-4.2 are marked complete
- Serena `project_overview` memory — update current state, test count, next items
- Auto-memory `MEMORY.md` — update resume point

- [ ] **Step 6: Final commit**

```bash
git add docs/ PROGRESS.md project-plan.md
git commit -m "docs: session 25 — portfolio-aware recommendations + rebalancing complete"
```
