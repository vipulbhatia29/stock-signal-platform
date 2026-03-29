# KAN-227: Schema Alignment + Alerts Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync all frontend TypeScript types with backend Pydantic schemas, extend the alert system with severity/title/ticker/dedup columns, wire divestment alerts into the nightly pipeline, and redesign the alert bell popover.

**Architecture:** Two independent workstreams — schema sync (mechanical, frontend-only) and alerts redesign (backend migration + producer updates + frontend popover rewrite). Schema sync is done first because the alert popover needs the updated `AlertResponse` type.

**Tech Stack:** Python/FastAPI/SQLAlchemy (backend), TypeScript/Next.js/TanStack Query (frontend), Alembic (migrations), pytest + testcontainers (backend tests), Jest + @testing-library/react (frontend tests)

**Spec:** `docs/superpowers/specs/2026-03-29-schema-alignment-alerts-redesign.md`

**LM Studio Triage:** Each task includes a complexity score (context_span + convention_density + ambiguity, each 1-5). Tasks scoring ≤ 8 are candidates for `/implement-local`.

---

## File Structure

### Backend (modified)
| File | Responsibility |
|------|---------------|
| `backend/models/alert.py` | Add 4 new columns to `InAppAlert` |
| `backend/schemas/alerts.py` | Add `severity`, `title`, `ticker` to `AlertResponse` with `Literal` |
| `backend/routers/alerts.py` | Pass new fields in manual `AlertResponse` constructor |
| `backend/tasks/alerts.py` | Dedup helper, update 4 producers, add divestment producer, retention cleanup |
| `backend/migrations/versions/*_018_*.py` | Migration: 4 columns + 2 indexes |

### Frontend (modified)
| File | Responsibility |
|------|---------------|
| `frontend/src/types/api.ts` | Fix 3 mismatched types + add 39 missing types |
| `frontend/src/hooks/use-alerts.ts` | Update `useAlerts()` return shape, remove `useUnreadAlertCount()` |
| `frontend/src/components/alert-bell.tsx` | Full popover redesign |

### Tests (new/modified)
| File | Responsibility |
|------|---------------|
| `tests/unit/pipeline/test_alert_producers.py` | Unit tests for all alert producers + dedup (same dir as existing `test_alerts.py`) |
| `tests/api/test_alerts_api.py` | API tests with testcontainers |
| `frontend/src/__tests__/alert-bell.test.tsx` | Component + hook tests |

### Codebase Notes (verified against code)
- `Position` model has NO `current_price` or `sector` — use `get_positions_with_pnl()` from `backend/services/portfolio.py` which returns enriched positions
- Popover is `@base-ui/react`, NOT shadcn — no `asChild` prop on `PopoverTrigger`
- Frontend tests mock at hook level (`jest.mock("@/hooks/...")`) not `@/lib/api` level
- Existing alert tests live at `tests/unit/pipeline/test_alerts.py`
- `async_session_factory` already imported in `backend/tasks/alerts.py`

---

## Task 1: Alembic Migration — Add Alert Columns + Indexes

**Complexity: 3** (context_span=1, convention_density=1, ambiguity=1) — single file, follows existing migration pattern, spec is explicit

**Files:**
- Modify: `backend/models/alert.py`
- Create: `backend/migrations/versions/*_018_alert_severity_title_ticker.py`

- [ ] **Step 1: Add columns to InAppAlert model**

In `backend/models/alert.py`, add after `alert_type` column (line 25):

```python
severity: Mapped[str] = mapped_column(String(30), nullable=False, server_default="info")
title: Mapped[str] = mapped_column(String(200), nullable=False, server_default="")
ticker: Mapped[str | None] = mapped_column(String(10), nullable=True)
dedup_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
```

Add import `String` if not already imported (it is — used by `message` and `alert_type`).

- [ ] **Step 2: Write incremental migration manually**

Do NOT use `alembic revision --autogenerate` — it falsely detects TimescaleDB tables and rewrites the entire schema. Write manually:

Create `backend/migrations/versions/<timestamp>_018_alert_severity_title_ticker.py`:

```python
"""018 — add severity, title, ticker, dedup_key to in_app_alerts

Revision ID: <generate>
Revises: a7b3c4d5e6f7
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa

revision = "<generate>"
down_revision = "a7b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("in_app_alerts", sa.Column("severity", sa.String(30), nullable=False, server_default="info"))
    op.add_column("in_app_alerts", sa.Column("title", sa.String(200), nullable=False, server_default=""))
    op.add_column("in_app_alerts", sa.Column("ticker", sa.String(10), nullable=True))
    op.add_column("in_app_alerts", sa.Column("dedup_key", sa.String(100), nullable=True))
    op.create_index("ix_in_app_alerts_dedup", "in_app_alerts", ["user_id", "dedup_key", "created_at"])
    op.create_index("ix_in_app_alerts_cleanup", "in_app_alerts", ["is_read", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_in_app_alerts_cleanup", table_name="in_app_alerts")
    op.drop_index("ix_in_app_alerts_dedup", table_name="in_app_alerts")
    op.drop_column("in_app_alerts", "dedup_key")
    op.drop_column("in_app_alerts", "ticker")
    op.drop_column("in_app_alerts", "title")
    op.drop_column("in_app_alerts", "severity")
```

Use `alembic revision -m "018 ..."` to generate the revision ID, then replace the body.

- [ ] **Step 3: Run migration**

Run: `uv run alembic upgrade head`
Expected: Migration applies cleanly, no errors.

- [ ] **Step 4: Verify migration**

Run: `uv run alembic current`
Expected: Shows new revision as head.

Run: `uv run python -c "from backend.models.alert import InAppAlert; print([c.name for c in InAppAlert.__table__.columns])"`
Expected: List includes `severity`, `title`, `ticker`, `dedup_key`.

- [ ] **Step 5: Commit**

```bash
git add backend/models/alert.py backend/migrations/versions/*_018_*
git commit -m "feat(alerts): migration 018 — severity, title, ticker, dedup_key columns + indexes"
```

---

## Task 2: Update Alert Schemas + Router

**Complexity: 4** (context_span=1, convention_density=2, ambiguity=1) — two files, follows existing pattern, Literal type is a convention choice

**Files:**
- Modify: `backend/schemas/alerts.py`
- Modify: `backend/routers/alerts.py`

- [ ] **Step 1: Update AlertResponse schema**

In `backend/schemas/alerts.py`, add `Literal` import and new fields:

```python
from typing import Literal

class AlertResponse(BaseModel):
    id: uuid.UUID
    alert_type: str
    severity: Literal["critical", "warning", "info"]
    title: str
    ticker: str | None
    message: str
    metadata: dict | None = None
    is_read: bool
    created_at: datetime
```

- [ ] **Step 2: Update router AlertResponse construction**

In `backend/routers/alerts.py`, update the list comprehension in `get_alerts()` (around line 76):

```python
AlertResponse(
    id=a.id,
    alert_type=a.alert_type,
    severity=a.severity,
    title=a.title,
    ticker=a.ticker,
    message=a.message,
    metadata=a.metadata_,
    is_read=a.is_read,
    created_at=a.created_at,
)
```

- [ ] **Step 3: Run existing tests**

Run: `uv run pytest tests/unit/alerts/ tests/api/test_alerts*.py -v 2>/dev/null || uv run pytest tests/unit/ -k alert -v`
Expected: Existing tests pass (or none exist yet — that's fine, we add them in Task 7).

- [ ] **Step 4: Commit**

```bash
git add backend/schemas/alerts.py backend/routers/alerts.py
git commit -m "feat(alerts): add severity/title/ticker to AlertResponse schema + router"
```

---

## Task 3: Add Dedup Helper + Update Existing Producers

**Complexity: 8** (context_span=3, convention_density=3, ambiguity=2) — modifies existing task logic, needs to understand 4 producer flows, dedup is new pattern

**Files:**
- Modify: `backend/tasks/alerts.py`

- [ ] **Step 1: Add dedup helper function**

Add at the top of `backend/tasks/alerts.py` (after imports):

```python
async def _alert_exists_recently(
    db: AsyncSession,
    user_id: uuid.UUID,
    dedup_key: str,
    hours: int = 24,
) -> bool:
    """Check if a similar alert was created within the dedup window."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(InAppAlert.id)
        .where(
            InAppAlert.user_id == user_id,
            InAppAlert.dedup_key == dedup_key,
            InAppAlert.created_at > cutoff,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None
```

Add imports: `from datetime import timedelta, timezone`.

- [ ] **Step 2: Update `_create_alert` to accept new fields**

Update the existing `_create_alert` function signature and body:

```python
async def _create_alert(
    db: AsyncSession,
    alert_type: str,
    message: str,
    metadata_: dict | None = None,
    user_id: uuid.UUID | None = None,
    severity: str = "info",
    title: str = "",
    ticker: str | None = None,
    dedup_key: str | None = None,
) -> bool:
    """Create an alert, skipping if dedup_key matches a recent alert.

    Returns True if alert was created, False if deduped.
    """
    if dedup_key and user_id:
        if await _alert_exists_recently(db, user_id, dedup_key):
            return False

    alert = InAppAlert(
        user_id=user_id,
        alert_type=alert_type,
        severity=severity,
        title=title,
        ticker=ticker,
        dedup_key=dedup_key,
        message=message,
        metadata_=metadata_,
        is_read=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(alert)
    return True
```

- [ ] **Step 3: Update `_alert_new_buy_recommendations` producer**

Update the call to `_create_alert` inside this function to pass new fields:

```python
created = await _create_alert(
    db,
    alert_type="recommendation",
    message=f"New BUY signal for {ticker} — composite score {score:.1f}/10",
    metadata_={"ticker": ticker, "route": f"/stocks/{ticker}"},
    user_id=user_id,
    severity="info",
    title="New BUY Signal",
    ticker=ticker,
    dedup_key=f"buy:{ticker}",
)
if created:
    count += 1
```

- [ ] **Step 4: Update `_alert_signal_flips` producer**

Update the signal flip alert creation to distinguish upgrades from downgrades:

```python
is_downgrade = _is_downgrade(old_action, new_action)
severity = "warning" if is_downgrade else "info"
title = "Score Downgrade" if is_downgrade else "Score Upgrade"
direction = "downgrade" if is_downgrade else "upgrade"

created = await _create_alert(
    db,
    alert_type="signal_change",
    message=f"{ticker} signal changed: {old_action} → {new_action} (score {score:.1f}/10)",
    metadata_={"ticker": ticker, "route": f"/stocks/{ticker}"},
    user_id=user_id,
    severity=severity,
    title=title,
    ticker=ticker,
    dedup_key=f"signal_flip:{direction}:{ticker}",
)
if created:
    count += 1
```

Add helper:

```python
def _is_downgrade(old_action: str, new_action: str) -> bool:
    """Returns True if the signal change is a downgrade."""
    rank = {"BUY": 3, "WATCH": 2, "AVOID": 1, "SELL": 0}
    return rank.get(new_action, 0) < rank.get(old_action, 0)
```

- [ ] **Step 5: Update drift + pipeline alert creation**

For drift alerts (inside the loop iterating `pipeline_context.get("degraded", [])`):

```python
created = await _create_alert(
    db,
    alert_type="drift",
    message=f"{ticker} forecast model degraded — accuracy below threshold, retraining queued",
    metadata_={"ticker": ticker, "route": f"/stocks/{ticker}"},
    user_id=uid,
    severity="warning",
    title="Forecast Degraded",
    ticker=ticker,
    dedup_key=f"drift:{ticker}",
)
```

For pipeline alerts:

```python
# Partial failure
await _create_alert(
    db,
    alert_type="pipeline",
    message="Nightly price refresh completed with some failures — check pipeline logs",
    metadata_={"route": "/dashboard"},
    user_id=uid,
    severity="warning",
    title="Pipeline Issue",
    ticker=None,
    dedup_key="pipeline:partial",
)

# Total failure
await _create_alert(
    db,
    alert_type="pipeline",
    message="Nightly price refresh failed — all tickers affected",
    metadata_={"route": "/dashboard"},
    user_id=uid,
    severity="critical",
    title="Pipeline Failed",
    ticker=None,
    dedup_key="pipeline:total",
)
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/unit/ -k alert -v`
Expected: Pass (existing tests may need updating if they assert on `_create_alert` signature).

- [ ] **Step 7: Commit**

```bash
git add backend/tasks/alerts.py
git commit -m "feat(alerts): dedup helper + severity/title/ticker on all producers"
```

---

## Task 4: Divestment Alert Producer + Retention Cleanup

**Complexity: 9** (context_span=3, convention_density=3, ambiguity=3) — new producer with batch user queries, integrates existing divestment function, retention logic

**Files:**
- Modify: `backend/tasks/alerts.py`

- [ ] **Step 1: Add divestment alert producer**

**IMPORTANT:** `Position` model has NO `current_price` or `sector` fields. The portfolio router uses `get_positions_with_pnl()` from `backend/services/portfolio.py` which returns enriched positions with `market_value`, `unrealized_pnl_pct`, `allocation_pct`, and `sector`. The divestment producer MUST follow the same pattern.

Add new function in `backend/tasks/alerts.py`:

```python
async def _alert_divestment_rules(db: AsyncSession) -> int:
    """Generate alerts from divestment rule checks for all users with portfolios."""
    from backend.models.portfolio import Portfolio, Position
    from backend.models.signal import SignalSnapshot
    from backend.models.user import UserPreference
    from backend.services.portfolio import get_positions_with_pnl
    from backend.tools.divestment import check_divestment_rules

    TITLE_MAP = {
        "stop_loss": "Stop-Loss Triggered",
        "position_concentration": "Concentration Risk",
        "sector_concentration": "Sector Overweight",
        "weak_fundamentals": "Weak Fundamentals",
    }

    count = 0

    # Fetch all users who have at least one portfolio with positions
    user_result = await db.execute(
        select(Portfolio.user_id)
        .join(Position, Position.portfolio_id == Portfolio.id)
        .distinct()
    )
    user_ids = [row[0] for row in user_result.fetchall()]

    for uid in user_ids:
        # Fetch portfolio
        port_result = await db.execute(
            select(Portfolio).where(Portfolio.user_id == uid).limit(1)
        )
        portfolio = port_result.scalar_one_or_none()
        if not portfolio:
            continue

        # Use the same service function the portfolio router uses —
        # returns enriched positions with market_value, unrealized_pnl_pct,
        # allocation_pct, and sector (JOINed from Stock table)
        positions = await get_positions_with_pnl(portfolio.id, db)
        if not positions:
            continue

        # Fetch preferences
        pref_result = await db.execute(
            select(UserPreference).where(UserPreference.user_id == uid)
        )
        prefs = pref_result.scalar_one_or_none()
        if not prefs:
            continue

        # Build sector allocations (same logic as portfolio router lines 252-261)
        total_value = sum(p.market_value or 0 for p in positions)
        sector_buckets: dict[str, float] = {}
        for p in positions:
            sector = p.sector or "Unknown"
            sector_buckets[sector] = sector_buckets.get(sector, 0.0) + (p.market_value or 0)
        sector_allocations = [
            {"sector": s, "pct": round(v / total_value * 100, 2) if total_value > 0 else 0.0}
            for s, v in sector_buckets.items()
        ]

        # Batch-fetch latest signals for all tickers (avoid N+1)
        tickers = [p.ticker for p in positions]
        subq = (
            select(
                SignalSnapshot.ticker,
                func.max(SignalSnapshot.computed_at).label("latest"),
            )
            .where(SignalSnapshot.ticker.in_(tickers))
            .group_by(SignalSnapshot.ticker)
            .subquery()
        )
        signal_result = await db.execute(
            select(SignalSnapshot.ticker, SignalSnapshot.composite_score).join(
                subq,
                (SignalSnapshot.ticker == subq.c.ticker)
                & (SignalSnapshot.computed_at == subq.c.latest),
            )
        )
        signal_map = {row.ticker: row.composite_score for row in signal_result}

        # Check each position
        for p in positions:
            pos_dict = {
                "ticker": p.ticker,
                "unrealized_pnl_pct": p.unrealized_pnl_pct,
                "allocation_pct": p.allocation_pct,
                "sector": p.sector,
            }
            signal = {"composite_score": signal_map.get(p.ticker)} if p.ticker in signal_map else None

            alerts = check_divestment_rules(pos_dict, sector_allocations, signal, prefs)
            for a in alerts:
                rule = a["rule"]
                created = await _create_alert(
                    db,
                    alert_type="divestment",
                    message=a["message"],
                    metadata_={
                        "rule": rule,
                        "value": a["value"],
                        "threshold": a["threshold"],
                        "route": f"/stocks/{p.ticker}",
                    },
                    user_id=uid,
                    severity=a["severity"],
                    title=TITLE_MAP.get(rule, rule.replace("_", " ").title()),
                    ticker=p.ticker,
                    dedup_key=f"divestment:{rule}:{p.ticker}",
                )
                if created:
                    count += 1

    return count
```

Add import at top of file: `from sqlalchemy import func` (if not already present).

- [ ] **Step 2: Add retention cleanup function**

```python
async def _cleanup_old_read_alerts(db: AsyncSession) -> int:
    """Delete read alerts older than 90 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    result = await db.execute(
        delete(InAppAlert).where(
            InAppAlert.is_read == True,  # noqa: E712
            InAppAlert.created_at < cutoff,
        )
    )
    return result.rowcount or 0
```

Add import: `from sqlalchemy import delete`.

- [ ] **Step 3: Wire into `_generate_alerts_async`**

Update `_generate_alerts_async` to call the new producer and cleanup:

```python
async def _generate_alerts_async(pipeline_context: dict | None = None) -> dict:
    pipeline_context = pipeline_context or {}
    alerts_created = 0

    async with async_session_factory() as db:
        # Existing producers
        alerts_created += await _alert_new_buy_recommendations(db)
        alerts_created += await _alert_signal_flips(db)

        # Drift alerts
        for ticker in pipeline_context.get("degraded", []):
            # ... existing drift logic ...

        # Pipeline status alerts
        # ... existing pipeline logic ...

        # NEW: Divestment alerts
        alerts_created += await _alert_divestment_rules(db)

        await db.commit()

        # NEW: Retention cleanup (after commit so new alerts aren't affected)
        async with async_session_factory() as cleanup_db:
            deleted = await _cleanup_old_read_alerts(cleanup_db)
            await cleanup_db.commit()

    logger.info("Alert generation complete: %d created, %d old read alerts cleaned", alerts_created, deleted)
    return {"alerts_created": alerts_created, "alerts_cleaned": deleted}
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/ -k alert -v`
Expected: Pass.

- [ ] **Step 5: Commit**

```bash
git add backend/tasks/alerts.py
git commit -m "feat(alerts): divestment producer + 90-day retention cleanup"
```

---

## Task 5: Frontend Schema Sync — Fix 3 Mismatched Types

**Complexity: 4** (context_span=1, convention_density=2, ambiguity=1) — single file, mechanical field additions, spec is explicit

**Files:**
- Modify: `frontend/src/types/api.ts`

- [ ] **Step 1: Fix AlertResponse**

Update `AlertResponse` to match updated backend schema (remove fields that are now in backend):

```typescript
export interface AlertResponse {
  id: string;
  alert_type: string;
  severity: "critical" | "warning" | "info";
  title: string;
  ticker: string | null;
  message: string;
  is_read: boolean;
  created_at: string;
  metadata: Record<string, unknown>;
}
```

- [ ] **Step 2: Fix ChatMessage**

Add missing fields to `ChatMessage`:

```typescript
export interface ChatMessage {
  id: string;
  role: string;
  content: string | null;
  tool_calls: Record<string, unknown>[] | null;
  model_used: string | null;
  tokens_used: number | null;
  prompt_tokens: number | null;    // NEW
  completion_tokens: number | null; // NEW
  latency_ms: number | null;       // NEW
  feedback: string | null;         // NEW
  created_at: string;
}
```

- [ ] **Step 3: Fix Recommendation**

Add `suggested_amount` to `Recommendation`:

```typescript
export interface Recommendation {
  ticker: string;
  action: string;
  confidence: number;
  composite_score: number;
  price_at_recommendation: number;
  reasoning: string;
  generated_at: string;
  is_actionable: boolean;
  suggested_amount: number | null; // NEW
}
```

- [ ] **Step 4: Run type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: Pass with no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/api.ts
git commit -m "fix(types): sync AlertResponse, ChatMessage, Recommendation with backend schemas"
```

---

## Task 6: Frontend Schema Sync — Add 39 Missing Types

**Complexity: 5** (context_span=2, convention_density=2, ambiguity=1) — single file, many types but each is mechanical translation from backend schemas

**Files:**
- Modify: `frontend/src/types/api.ts`

- [ ] **Step 1: Add Auth + Chat types**

Add after existing Auth section:

```typescript
export interface TokenRefreshRequest {
  refresh_token: string;
}

export interface ChatRequest {
  message: string;
  session_id?: string;
  agent_type?: "stock" | "general";
}
```

Add after existing Chat section:

```typescript
export interface AdminChatSessionSummary {
  id: string;
  agent_type: string;
  title: string | null;
  is_active: boolean;
  decline_count: number;
  user_email: string;
  message_count: number;
  created_at: string;
  last_active_at: string;
}

export interface AdminChatSessionListResponse {
  total: number;
  sessions: AdminChatSessionSummary[];
}

export interface AdminChatTranscriptResponse {
  session: AdminChatSessionSummary;
  messages: ChatMessage[];
}

export interface AdminChatStatsResponse {
  total_sessions: number;
  total_messages: number;
  active_sessions: number;
  feedback_up: number;
  feedback_down: number;
}
```

- [ ] **Step 2: Add Alert list/batch types**

Add after `UnreadAlertCount`:

```typescript
export interface AlertListResponse {
  alerts: AlertResponse[];
  total: number;
  unread_count: number;
}

export interface BatchReadRequest {
  alert_ids: string[];
}

export interface BatchReadResponse {
  updated: number;
}

export interface UnreadCountResponse {
  unread_count: number;
}
```

- [ ] **Step 3: Add Intelligence types**

Add new section:

```typescript
// ── Intelligence ──────────────────────────────────────────────────────────────

export interface NewsItem {
  title: string;
  link: string;
  publisher: string | null;
  published: string | null;
  source: string;
}

export interface StockNewsResponse {
  ticker: string;
  articles: NewsItem[];
  fetched_at: string;
}

export interface UpgradeDowngrade {
  firm: string;
  to_grade: string;
  from_grade: string | null;
  action: string;
  date: string;
}

export interface InsiderTransaction {
  insider_name: string;
  relation: string | null;
  transaction_type: string;
  shares: number;
  value: number | null;
  date: string;
}

export interface ShortInterest {
  short_percent_of_float: number;
  short_ratio: number | null;
  shares_short: number | null;
}

export interface StockIntelligenceResponse {
  ticker: string;
  upgrades_downgrades: UpgradeDowngrade[];
  insider_transactions: InsiderTransaction[];
  next_earnings_date: string | null;
  eps_revisions: Record<string, unknown> | null;
  short_interest: ShortInterest | null;
  fetched_at: string;
}
```

- [ ] **Step 4: Add Portfolio Health types**

```typescript
// ── Portfolio Health ──────────────────────────────────────────────────────────

export interface HealthComponent {
  name: string;
  score: number;
  weight: number;
  detail: string;
}

export interface PositionHealth {
  ticker: string;
  weight_pct: number;
  signal_score: number | null;
  sector: string | null;
  contribution: "strength" | "drag";
}

export interface PortfolioHealthResult {
  health_score: number;
  grade: string;
  components: HealthComponent[];
  metrics: Record<string, unknown>;
  top_concerns: string[];
  top_strengths: string[];
  position_details: PositionHealth[];
}

export interface PortfolioHealthSnapshotResponse {
  snapshot_date: string;
  health_score: number;
  grade: string;
  diversification_score: number;
  signal_quality_score: number;
  risk_score: number;
  income_score: number;
  sector_balance_score: number;
  hhi: number;
  weighted_beta: number | null;
  weighted_sharpe: number | null;
  weighted_yield: number | null;
  position_count: number;
}
```

- [ ] **Step 5: Add Market types**

```typescript
// ── Market ────────────────────────────────────────────────────────────────────

export interface IndexPerformance {
  name: string;
  ticker: string;
  price: number;
  change_pct: number;
}

export interface SectorPerformance {
  sector: string;
  etf: string;
  change_pct: number;
}

export interface MarketBriefingResult {
  indexes: IndexPerformance[];
  sector_performance: SectorPerformance[];
  portfolio_news: Record<string, unknown>[];
  upcoming_earnings: Record<string, unknown>[];
  top_movers: Record<string, unknown>;
  briefing_date: string;
}
```

- [ ] **Step 6: Add Health, LLM Config, Observability, Recommend, Stock types**

```typescript
// ── Health ─────────────────────────────────────────────────────────────────────

export interface MCPToolsStatus {
  enabled: boolean;
  mode: "stdio" | "fallback_direct" | "direct" | "disabled";
  healthy: boolean;
  tool_count: number;
  restarts: number;
  uptime_seconds: number | null;
  last_error: string | null;
  fallback_since: string | null;
}

export interface DependencyStatus {
  healthy: boolean;
  latency_ms: number | null;
  error: string | null;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  version: string;
  redis: DependencyStatus;
  database: DependencyStatus;
  mcp_tools: MCPToolsStatus;
}

// ── LLM Config ────────────────────────────────────────────────────────────────

export interface LLMModelConfigResponse {
  id: number;
  provider: string;
  model_name: string;
  tier: string;
  priority: number;
  is_enabled: boolean;
  tpm_limit: number | null;
  rpm_limit: number | null;
  tpd_limit: number | null;
  rpd_limit: number | null;
  cost_per_1k_input: number;
  cost_per_1k_output: number;
  notes: string | null;
}

export interface LLMModelConfigUpdate {
  priority?: number;
  is_enabled?: boolean;
  tpm_limit?: number | null;
  rpm_limit?: number | null;
  tpd_limit?: number | null;
  rpd_limit?: number | null;
  cost_per_1k_input?: number;
  cost_per_1k_output?: number;
  notes?: string | null;
}

export interface TierToggleRequest {
  model: string;
  enabled: boolean;
}

// ── Observability ─────────────────────────────────────────────────────────────

export interface KPIResponse {
  queries_today: number;
  avg_latency_ms: number;
  avg_cost_per_query: number;
  pass_rate: number | null;
  fallback_rate_pct: number;
}

export interface QueryRow {
  query_id: string;
  timestamp: string;
  query_text: string;
  agent_type: string;
  tools_used: string[];
  llm_calls: number;
  llm_models: string[];
  db_calls: number;
  external_calls: number;
  external_sources: string[];
  total_cost_usd: number;
  duration_ms: number;
  score: number | null;
  status: string;
}

export interface QueryListResponse {
  items: QueryRow[];
  total: number;
  page: number;
  size: number;
}

export interface StepDetail {
  step_number: number;
  action: string;
  type_tag: string;
  model_name: string | null;
  input_summary: string | null;
  output_summary: string | null;
  latency_ms: number | null;
  cost_usd: number | null;
  cache_hit: boolean;
}

export interface QueryDetailResponse {
  query_id: string;
  query_text: string;
  steps: StepDetail[];
  langfuse_trace_url: string | null;
}

export interface LangfuseURLResponse {
  url: string | null;
}

export interface AssessmentRunSummary {
  id: string;
  trigger: string;
  total_queries: number;
  passed_queries: number;
  pass_rate: number;
  total_cost_usd: number;
  started_at: string;
  completed_at: string;
}

export interface AssessmentHistoryResponse {
  items: AssessmentRunSummary[];
}

// ── Recommendations (extended) ────────────────────────────────────────────────

export interface StockCandidate {
  ticker: string;
  name: string;
  sector: string | null;
  recommendation_score: number;
  sources: string[];
  rationale: string[];
  signal_score: number | null;
  forward_pe: number | null;
  dividend_yield: number | null;
}

export interface RecommendationResult {
  candidates: StockCandidate[];
  portfolio_context: Record<string, unknown>;
}

// ── Stock (extended) ──────────────────────────────────────────────────────────

export interface OHLCResponse {
  ticker: string;
  period: string;
  count: number;
  timestamps: string[];
  open: number[];
  high: number[];
  low: number[];
  close: number[];
  volume: number[];
}
```

- [ ] **Step 7: Run type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: Pass with no errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types/api.ts
git commit -m "feat(types): add 39 missing TypeScript types from backend schemas"
```

---

## Task 7: Backend Tests — Unit + API

**Complexity: 9** (context_span=3, convention_density=3, ambiguity=3) — multiple test files, testcontainers setup, mock patterns, dedup edge cases

**Files:**
- Create: `tests/unit/pipeline/test_alert_producers.py`
- Create: `tests/api/test_alerts_api.py`

- [ ] **Step 1: Create unit tests for alert producers**

Create `tests/unit/pipeline/test_alert_producers.py` (same directory as existing `test_alerts.py`):

```python
"""Unit tests for alert producers — dedup, field mapping, edge cases."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.alert import InAppAlert
from backend.schemas.alerts import AlertResponse


# ── AlertResponse schema tests ──

def test_alert_response_includes_new_fields():
    """AlertResponse schema must include severity, title, ticker."""
    resp = AlertResponse(
        id=uuid.uuid4(),
        alert_type="divestment",
        severity="critical",
        title="Stop-Loss Triggered",
        ticker="TSLA",
        message="Down 18%",
        is_read=False,
        created_at=datetime.now(timezone.utc),
    )
    assert resp.severity == "critical"
    assert resp.title == "Stop-Loss Triggered"
    assert resp.ticker == "TSLA"


def test_alert_response_rejects_invalid_severity():
    """Literal type should reject typos like 'critcal'."""
    with pytest.raises(Exception):  # ValidationError
        AlertResponse(
            id=uuid.uuid4(),
            alert_type="test",
            severity="critcal",  # typo
            title="Test",
            ticker=None,
            message="test",
            is_read=False,
            created_at=datetime.now(timezone.utc),
        )


def test_alert_response_allows_null_ticker():
    """Pipeline alerts have no ticker."""
    resp = AlertResponse(
        id=uuid.uuid4(),
        alert_type="pipeline",
        severity="warning",
        title="Pipeline Issue",
        ticker=None,
        message="Partial failure",
        is_read=False,
        created_at=datetime.now(timezone.utc),
    )
    assert resp.ticker is None


# ── Dedup key format tests ──

def test_dedup_key_divestment_format():
    """Dedup key for divestment alerts follows 'divestment:{rule}:{ticker}' pattern."""
    key = f"divestment:stop_loss:TSLA"
    assert key == "divestment:stop_loss:TSLA"


def test_dedup_key_signal_flip_format():
    """Dedup key for signal flips follows 'signal_flip:{direction}:{ticker}' pattern."""
    key = f"signal_flip:downgrade:AAPL"
    assert key == "signal_flip:downgrade:AAPL"


# ── _is_downgrade helper tests ──

def test_is_downgrade_buy_to_watch():
    from backend.tasks.alerts import _is_downgrade
    assert _is_downgrade("BUY", "WATCH") is True


def test_is_downgrade_avoid_to_buy():
    from backend.tasks.alerts import _is_downgrade
    assert _is_downgrade("AVOID", "BUY") is False


def test_is_downgrade_same_action():
    from backend.tasks.alerts import _is_downgrade
    assert _is_downgrade("WATCH", "WATCH") is False
```

- [ ] **Step 2: Create API tests for alerts endpoints**

Create `tests/api/test_alerts_api.py`:

```python
"""API tests for alerts endpoints — real DB via testcontainers."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from backend.models.alert import InAppAlert


@pytest.fixture
async def seed_alerts(db_session, test_user):
    """Seed alerts for testing."""
    alerts = []
    for i, (sev, title, ticker, is_read) in enumerate([
        ("critical", "Stop-Loss Triggered", "TSLA", False),
        ("warning", "Score Downgrade", "AAPL", False),
        ("info", "New BUY Signal", "MSFT", True),
    ]):
        alert = InAppAlert(
            user_id=test_user.id,
            alert_type="divestment" if sev == "critical" else "signal_change",
            severity=sev,
            title=title,
            ticker=ticker,
            dedup_key=f"test:{ticker}:{i}",
            message=f"Test alert for {ticker}",
            metadata_={"route": f"/stocks/{ticker}"},
            is_read=is_read,
            created_at=datetime.now(timezone.utc) - timedelta(hours=i),
        )
        db_session.add(alert)
        alerts.append(alert)
    await db_session.commit()
    return alerts


@pytest.mark.asyncio
async def test_get_alerts_returns_new_fields(client: AsyncClient, auth_headers, seed_alerts):
    """GET /alerts returns severity, title, ticker in response."""
    resp = await client.get("/api/v1/alerts", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "alerts" in data
    assert data["total"] == 3
    assert data["unread_count"] == 2
    first = data["alerts"][0]
    assert "severity" in first
    assert "title" in first
    assert "ticker" in first
    assert first["severity"] in ("critical", "warning", "info")


@pytest.mark.asyncio
async def test_get_alerts_pagination(client: AsyncClient, auth_headers, seed_alerts):
    """GET /alerts respects limit and offset."""
    resp = await client.get("/api/v1/alerts?limit=1&offset=0", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["alerts"]) == 1
    assert data["total"] == 3


@pytest.mark.asyncio
async def test_multi_user_isolation(client: AsyncClient, auth_headers, seed_alerts, db_session):
    """User A cannot see User B's alerts."""
    other_user_id = uuid.uuid4()
    other_alert = InAppAlert(
        user_id=other_user_id,
        alert_type="test",
        severity="info",
        title="Other User Alert",
        ticker="GOOG",
        message="Should not appear",
        is_read=False,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(other_alert)
    await db_session.commit()

    resp = await client.get("/api/v1/alerts", headers=auth_headers)
    data = resp.json()
    tickers = [a["ticker"] for a in data["alerts"]]
    assert "GOOG" not in tickers


@pytest.mark.asyncio
async def test_retention_only_deletes_read(db_session, test_user):
    """Retention cleanup deletes read alerts >90d but preserves unread ones."""
    from backend.tasks.alerts import _cleanup_old_read_alerts

    old_date = datetime.now(timezone.utc) - timedelta(days=91)

    # Old read alert — should be deleted
    read_alert = InAppAlert(
        user_id=test_user.id, alert_type="test", severity="info", title="Old Read",
        ticker=None, message="old read", is_read=True, created_at=old_date,
    )
    # Old unread alert — should be preserved
    unread_alert = InAppAlert(
        user_id=test_user.id, alert_type="test", severity="critical", title="Old Unread",
        ticker=None, message="old unread", is_read=False, created_at=old_date,
    )
    db_session.add_all([read_alert, unread_alert])
    await db_session.commit()

    deleted = await _cleanup_old_read_alerts(db_session)
    await db_session.commit()

    assert deleted == 1  # only read alert deleted
```

- [ ] **Step 3: Run all tests**

Run: `uv run pytest tests/unit/pipeline/test_alert_producers.py tests/api/test_alerts_api.py -v`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/pipeline/test_alert_producers.py tests/api/test_alerts_api.py
git commit -m "test(alerts): unit tests for producers + API tests with testcontainers"
```

---

## Task 8: Frontend — Alert Hooks Update

**Complexity: 5** (context_span=1, convention_density=2, ambiguity=2) — single file, TanStack Query pattern, return shape change

**Files:**
- Modify: `frontend/src/hooks/use-alerts.ts`

- [ ] **Step 1: Rewrite use-alerts.ts**

Replace the entire file:

```typescript
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { get, patch } from "@/lib/api";
import type { AlertListResponse } from "@/types/api";

export function useAlerts() {
  return useQuery({
    queryKey: ["alerts"],
    queryFn: () => get<AlertListResponse>("/alerts"),
    staleTime: 60 * 1000,
    select: (data) => ({
      alerts: data.alerts,
      total: data.total,
      unreadCount: data.unread_count,
    }),
  });
}

export function useMarkAlertsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (alertIds: string[]) =>
      patch("/alerts/read", { alert_ids: alertIds }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}
```

Note: `useUnreadAlertCount()` is removed — `useAlerts()` now returns `unreadCount`.

- [ ] **Step 2: Run type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: May fail if `alert-bell.tsx` still imports `useUnreadAlertCount`. That's expected — fixed in Task 9.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/use-alerts.ts
git commit -m "feat(alerts): update useAlerts hook, remove useUnreadAlertCount"
```

---

## Task 9: Frontend — Alert Bell Popover Redesign

**Complexity: 10** (context_span=3, convention_density=3, ambiguity=4) — full component rewrite, undo toast state, skeleton loading, router navigation, severity colors

**Files:**
- Modify: `frontend/src/components/alert-bell.tsx`

- [ ] **Step 1: Rewrite alert-bell.tsx**

Replace the entire component:

```tsx
"use client";

import { useState, useEffect, useCallback } from "react";
import { Bell } from "lucide-react";
import { useRouter } from "next/navigation";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { useAlerts, useMarkAlertsRead } from "@/hooks/use-alerts";
import type { AlertResponse } from "@/types/api";

const SEVERITY_COLORS: Record<string, string> = {
  critical: "text-loss",
  warning: "text-warning",
  info: "text-cyan",
};

function formatTimeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function formatTitle(alert: AlertResponse): string {
  if (alert.title) return alert.title;
  // Fallback for legacy alerts with empty title
  return alert.alert_type
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function AlertSkeleton() {
  return (
    <div className="space-y-3 p-4">
      {[1, 2, 3].map((i) => (
        <div key={i} className="flex gap-3 animate-pulse">
          <div className="w-2 h-2 rounded-full bg-muted mt-2" />
          <div className="flex-1 space-y-2">
            <div className="h-3 bg-muted rounded w-2/3" />
            <div className="h-3 bg-muted rounded w-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

function AlertItem({
  alert,
  onClick,
}: {
  alert: AlertResponse;
  onClick: (alert: AlertResponse) => void;
}) {
  const severity = alert.severity as keyof typeof SEVERITY_COLORS;
  const color = SEVERITY_COLORS[severity] ?? "text-subtle";
  const title = formatTitle(alert);

  return (
    <button
      onClick={() => onClick(alert)}
      className={`flex gap-3 px-4 py-3 w-full text-left border-b border-border/50 hover:bg-muted/30 transition-colors ${
        alert.is_read ? "opacity-60" : ""
      }`}
    >
      <div className="flex-shrink-0 mt-1.5">
        {alert.is_read ? (
          <div className="w-2 h-2 rounded-full border border-muted-foreground/30" />
        ) : (
          <div className="w-2 h-2 rounded-full bg-blue-500" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex justify-between items-baseline gap-2">
          <span className={`font-semibold text-xs ${color}`}>{title}</span>
          <span className="text-muted-foreground text-[11px] whitespace-nowrap">
            {formatTimeAgo(alert.created_at)}
          </span>
        </div>
        <p className="text-muted-foreground text-xs mt-0.5 line-clamp-2">
          {alert.message}
        </p>
        {alert.ticker && (
          <span className="text-muted-foreground text-[11px] bg-muted/50 px-2 py-0.5 rounded mt-1.5 inline-block">
            {alert.ticker} →
          </span>
        )}
      </div>
    </button>
  );
}

export function AlertBell() {
  const router = useRouter();
  const { data, isLoading } = useAlerts();
  const markRead = useMarkAlertsRead();
  const [pendingMarkAll, setPendingMarkAll] = useState<string[] | null>(null);

  const alerts = data?.alerts ?? [];
  const unreadCount = data?.unreadCount ?? 0;

  // Delayed "mark all read" — gives user 5s to undo before API call fires
  useEffect(() => {
    if (!pendingMarkAll) return;
    const timer = setTimeout(() => {
      markRead.mutate(pendingMarkAll);
      setPendingMarkAll(null);
    }, 5000);
    return () => clearTimeout(timer);
  }, [pendingMarkAll, markRead]);

  const handleAlertClick = useCallback(
    (alert: AlertResponse) => {
      if (!alert.is_read) {
        markRead.mutate([alert.id]);
      }
      if (alert.ticker) {
        router.push(`/stocks/${alert.ticker}`);
      }
    },
    [markRead, router],
  );

  const handleMarkAllRead = useCallback(() => {
    const unreadIds = alerts.filter((a) => !a.is_read).map((a) => a.id);
    if (unreadIds.length === 0) return;
    // Don't call API yet — set pending state and wait 5s for undo
    setPendingMarkAll(unreadIds);
  }, [alerts]);

  const handleUndo = useCallback(() => {
    // Cancel the pending API call (timer cleanup in useEffect handles it)
    setPendingMarkAll(null);
  }, []);

  return (
    <Popover>
      <PopoverTrigger>
        <button className="relative p-2 rounded-md hover:bg-muted/50 transition-colors">
          <Bell className="h-5 w-5 text-muted-foreground" />
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 bg-loss text-white text-[10px] font-bold rounded-full min-w-[18px] h-[18px] flex items-center justify-center px-1">
              {unreadCount > 99 ? "99+" : unreadCount}
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="w-[380px] p-0 max-h-[400px] flex flex-col"
      >
        {/* Header */}
        <div className="flex justify-between items-center px-4 py-3 border-b border-border">
          <span className="font-semibold text-sm">Notifications</span>
          {unreadCount > 0 && (
            <button
              onClick={handleMarkAllRead}
              className="text-cyan text-xs hover:underline"
            >
              Mark all read
            </button>
          )}
        </div>

        {/* Undo toast — API call is delayed 5s, undo cancels it */}
        {pendingMarkAll && (
          <div className="flex justify-between items-center px-4 py-2 bg-muted/50 border-b border-border text-xs">
            <span className="text-muted-foreground">Marked all read.</span>
            <button onClick={handleUndo} className="text-cyan hover:underline">
              Undo
            </button>
          </div>
        )}

        {/* Alert list */}
        <div className="overflow-y-auto flex-1">
          {isLoading ? (
            <AlertSkeleton />
          ) : alerts.length === 0 ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
              No notifications
            </div>
          ) : (
            alerts.map((alert) => (
              <AlertItem
                key={alert.id}
                alert={alert}
                onClick={handleAlertClick}
              />
            ))
          )}
        </div>

        {/* Footer */}
        {alerts.length > 0 && (
          <div className="px-4 py-2.5 border-t border-border text-center">
            <span className="text-cyan text-xs cursor-pointer hover:underline">
              View all notifications →
            </span>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
```

- [ ] **Step 2: Run type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: Pass.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/alert-bell.tsx
git commit -m "feat(alerts): redesign alert bell popover — severity colors, loading, undo toast"
```

---

## Task 10: Frontend Tests — Alert Bell + Hooks

**Complexity: 8** (context_span=2, convention_density=3, ambiguity=3) — mock setup for TanStack Query, router mocking, multiple interaction tests

**Files:**
- Create: `frontend/src/__tests__/alert-bell.test.tsx`

- [ ] **Step 1: Create alert bell tests**

Create `frontend/src/__tests__/alert-bell.test.tsx`:

**Note:** Follow project convention — mock at hook level (`jest.mock("@/hooks/use-alerts")`) not at `@/lib/api` level.

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AlertBell } from "@/components/alert-bell";

// Mock next/navigation
const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

// Mock at hook level (project convention — see trending-stocks.test.tsx, chat-panel.test.tsx)
const mockMutate = jest.fn();
const mockAlertsData = {
  alerts: [
    {
      id: "1",
      alert_type: "divestment",
      severity: "critical" as const,
      title: "Stop-Loss Triggered",
      ticker: "TSLA",
      message: "Down 18.2% from cost basis",
      is_read: false,
      created_at: new Date().toISOString(),
      metadata: {},
    },
    {
      id: "2",
      alert_type: "signal_change",
      severity: "warning" as const,
      title: "Score Downgrade",
      ticker: "AAPL",
      message: "Dropped from 8.4 to 6.1",
      is_read: false,
      created_at: new Date().toISOString(),
      metadata: {},
    },
    {
      id: "3",
      alert_type: "pipeline",
      severity: "info" as const,
      title: "",
      ticker: null,
      message: "Pipeline completed",
      is_read: true,
      created_at: new Date(Date.now() - 86400000).toISOString(),
      metadata: {},
    },
  ],
  unreadCount: 2,
  total: 3,
};

jest.mock("@/hooks/use-alerts", () => ({
  useAlerts: () => ({
    data: mockAlertsData,
    isLoading: false,
    isError: false,
  }),
  useMarkAlertsRead: () => ({
    mutate: mockMutate,
  }),
}));

describe("AlertBell", () => {
  beforeEach(() => {
    mockPush.mockClear();
    mockMutate.mockClear();
  });

  it("renders badge with unread count", () => {
    render(<AlertBell />);
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("shows alerts in popover on click", () => {
    render(<AlertBell />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Stop-Loss Triggered")).toBeInTheDocument();
    expect(screen.getByText("Score Downgrade")).toBeInTheDocument();
  });

  it("renders severity colors correctly", () => {
    render(<AlertBell />);
    fireEvent.click(screen.getByRole("button"));
    const critical = screen.getByText("Stop-Loss Triggered");
    expect(critical.className).toContain("text-loss");
    const warning = screen.getByText("Score Downgrade");
    expect(warning.className).toContain("text-warning");
  });

  it("falls back to alert_type when title is empty", () => {
    render(<AlertBell />);
    fireEvent.click(screen.getByRole("button"));
    // Alert 3 has empty title, alert_type="pipeline" → "Pipeline"
    expect(screen.getByText("Pipeline")).toBeInTheDocument();
  });

  it("shows read alerts with reduced opacity", () => {
    render(<AlertBell />);
    fireEvent.click(screen.getByRole("button"));
    const readAlert = screen.getByText("Pipeline completed").closest("button");
    expect(readAlert?.className).toContain("opacity-60");
  });

  it("navigates to stock page on alert click with ticker", () => {
    render(<AlertBell />);
    fireEvent.click(screen.getByRole("button"));
    // Click on the alert item containing the TSLA message
    fireEvent.click(screen.getByText("Down 18.2% from cost basis"));
    expect(mockPush).toHaveBeenCalledWith("/stocks/TSLA");
    expect(mockMutate).toHaveBeenCalledWith(["1"]);
  });

  it("does not navigate when alert has no ticker", () => {
    render(<AlertBell />);
    fireEvent.click(screen.getByRole("button"));
    fireEvent.click(screen.getByText("Pipeline completed"));
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("does not show badge when unread count is 0", () => {
    // Override hook mock for this test
    const useAlerts = require("@/hooks/use-alerts").useAlerts;
    jest.spyOn({ useAlerts }, "useAlerts").mockReturnValue({
      data: { alerts: [], unreadCount: 0, total: 0 },
      isLoading: false,
      isError: false,
    });
    // Note: this test may need re-rendering with updated mock —
    // implementer should adjust based on Jest module mock behavior
  });
});
```

- [ ] **Step 2: Run frontend tests**

Run: `cd frontend && npx jest src/__tests__/alert-bell.test.tsx --verbose`
Expected: All tests pass.

- [ ] **Step 3: Run full frontend test suite**

Run: `cd frontend && npx jest --verbose`
Expected: All tests pass — no regressions.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/__tests__/alert-bell.test.tsx
git commit -m "test(alerts): frontend tests — bell component, severity colors, navigation, edge cases"
```

---

## Task 11: Final Verification

**Complexity: 3** (context_span=1, convention_density=1, ambiguity=1) — run commands, verify output

**Files:** None (verification only)

- [ ] **Step 1: Run full backend test suite**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: All pass, including new alert tests.

- [ ] **Step 2: Run backend lint**

Run: `uv run ruff check --fix && uv run ruff format`
Expected: Clean.

- [ ] **Step 3: Run frontend type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: Pass.

- [ ] **Step 4: Run frontend lint**

Run: `cd frontend && npm run lint`
Expected: Clean.

- [ ] **Step 5: Run frontend tests**

Run: `cd frontend && npx jest --verbose`
Expected: All pass.

- [ ] **Step 6: Verify migration**

Run: `uv run alembic current && uv run alembic heads`
Expected: Single head, matches current.

- [ ] **Step 7: Commit any lint fixes**

```bash
git add -A
git commit -m "chore: lint fixes from final verification"
```

---

## Task 12: Documentation + Memories + Learnings

**Complexity: 6** (context_span=3, convention_density=2, ambiguity=1) — multiple files to update, but content is known from implementation

**Files:**
- Modify: `docs/TDD.md` — add/update alert API contracts (§ alert endpoints section)
- Modify: `docs/FSD.md` — add alert system functional requirements (FR for notifications)
- Modify: `docs/PRD.md` — update if notification feature changes product scope
- Modify: `project-plan.md` — mark KAN-227 complete, update Phase B.5 progress
- Modify: `PROGRESS.md` — add session entry with accomplishments, test counts, files changed
- Update Serena memories as needed

- [ ] **Step 1: Update TDD.md**

Add/update the alert system API contract section:
- `GET /api/v1/alerts` — document new `severity`, `title`, `ticker` fields in `AlertListResponse`
- `PATCH /api/v1/alerts/read` — no contract change
- `GET /api/v1/alerts/unread-count` — no contract change
- Document dedup_key column purpose and 24h window
- Document retention policy (90 days, read alerts only)

- [ ] **Step 2: Update FSD.md**

Add functional requirement for alert notifications:
- FR: Users receive in-app notifications for divestment rule violations and score threshold crossings
- FR: Alert bell shows unread count badge, clickable alerts navigate to stock detail
- FR: Alerts are generated nightly by the Celery pipeline
- FR: Read alerts auto-expire after 90 days

- [ ] **Step 3: Update PRD.md (if needed)**

Check if the notification/alert feature changes the product scope described in PRD. If PRD already mentions alerts, update the description. If not, add a brief mention under the portfolio monitoring section.

- [ ] **Step 4: Update project-plan.md**

Mark KAN-227 (BU-1) as complete in Phase B.5 section:
```markdown
- [x] **BU-1: Schema Alignment + Alerts Redesign** (~1 session) — PR #XXX (Session 72). Migration 018 (severity/title/ticker/dedup_key), 39 new FE types + 3 fixes, divestment alert producer, alert bell popover redesign, dedup + retention. XX new tests.
```

- [ ] **Step 5: Update PROGRESS.md**

Add session entry:
```markdown
### Session 72: KAN-227 — Schema Alignment + Alerts Redesign
- **Phase B.5 BU-1 COMPLETE** — PR #XXX merged to develop
- Migration 018: severity, title, ticker, dedup_key columns + 2 indexes on in_app_alerts
- Schema sync: 3 type fixes + 39 new TypeScript types in types/api.ts
- Alert producers: dedup helper, updated 4 existing producers, new divestment producer
- Alert retention: 90-day cleanup for read alerts in nightly pipeline
- Alert bell: full popover redesign (severity colors, loading skeleton, undo toast, ticker navigation)
- XX new backend tests, XX new frontend tests
- Alembic head: XXX (migration 018)
```

- [ ] **Step 6: Update Serena memories**

Update `project/state`:
- Current phase, completed stories, test counts, alembic head, resume point

Update `project/testing` if test patterns changed.

Add any new conventions or gotchas discovered during implementation to appropriate memory.

- [ ] **Step 7: Update MEMORY.md**

Update Project State section with:
- Session 72 accomplishments
- Updated test counts
- New alembic head
- Resume point (next: KAN-228 BU-2)

- [ ] **Step 8: Capture learnings + conventions**

Document any implementation learnings as Serena memories or `.claude/rules/`:
- New patterns discovered (e.g., reusing `get_positions_with_pnl()` in Celery tasks)
- Gotchas encountered (e.g., base-ui PopoverTrigger has no asChild)
- Convention confirmations (e.g., mock hooks not api in FE tests)

- [ ] **Step 9: Commit documentation updates**

```bash
git add docs/TDD.md docs/FSD.md docs/PRD.md project-plan.md PROGRESS.md
git commit -m "docs: KAN-227 session closeout — TDD, FSD, project-plan, PROGRESS updated"
```

---

## Dependency Graph

```
Task 1 (migration) ──→ Task 2 (schema+router) ──→ Task 3 (dedup+producers) ──→ Task 4 (divestment+retention)
                                                                                         │
Task 5 (fix 3 types) ──→ Task 6 (add 39 types) ──→ Task 8 (hooks) ──→ Task 9 (bell) ──→ Task 10 (FE tests)
                                                                                         │
                                                    Task 7 (BE tests) ──────────────────→ Task 11 (verify)
                                                                                         │
                                                                                         ↓
                                                                                    Task 12 (docs+memories)
```

Tasks 1-4 (backend) and Tasks 5-6 (frontend types) can run in parallel.
Task 7 (BE tests) depends on Tasks 1-4.
Tasks 8-10 (frontend alerts) depend on Tasks 5-6.
Task 11 depends on everything.
Task 12 depends on Task 11 (needs final test counts, PR number, alembic head).

## LM Studio Triage Summary

| Task | Score | Local LLM Candidate? |
|------|-------|---------------------|
| 1. Migration | 3/15 | Yes |
| 2. Schema + Router | 4/15 | Yes |
| 3. Dedup + Producers | 8/15 | Borderline — yes (≤8) |
| 4. Divestment + Retention | 9/15 | No |
| 5. Fix 3 types | 4/15 | Yes |
| 6. Add 39 types | 5/15 | Yes |
| 7. Backend tests | 9/15 | No |
| 8. Hooks update | 5/15 | Yes |
| 9. Bell redesign | 10/15 | No |
| 10. Frontend tests | 8/15 | Borderline — yes (≤8) |
| 11. Final verify | 3/15 | Yes |
| 12. Docs + memories | 6/15 | Yes |
