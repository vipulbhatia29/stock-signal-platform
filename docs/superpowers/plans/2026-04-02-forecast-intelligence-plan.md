# Forecast Intelligence System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a three-level forecast system (stock → sector → portfolio) with backtesting validation, news sentiment regressors, signal convergence UX, and admin pipeline orchestrator.

**Architecture:** 4 sub-specs shipping serially (A → D → B → C). Single shared migration (024) deployed first. Each spec builds on prior work. Event-driven CacheInvalidator service shared across all specs.

**Tech Stack:** FastAPI, SQLAlchemy async, TimescaleDB, Celery, Prophet, PyPortfolioOpt (Black-Litterman), GPT-4o-mini (sentiment), Finnhub/EDGAR/FRED APIs, React/Next.js, TanStack Query, Recharts, shadcn/ui.

**Spec:** `docs/superpowers/specs/2026-04-02-forecast-intelligence-design.md`

---

## Sprint Overview

| Sprint | Spec | Focus | Sessions | Files (create/modify) | Done When |
|--------|------|-------|----------|----------------------|-----------|
| **1** | Shared | Migration 024 + config + shared models + factories + TypeScript types + router stubs | 1 | 10 create, 5 modify | All 5 tables exist in DB, all models importable, all new TS types defined, all routers mounted (returning 404) |
| **2** | A | BacktestEngine + walk-forward + metrics + DB integration | 1-2 | 4 create, 2 modify | `BacktestEngine._generate_expanding_windows()` produces correct windows, all metric functions pass with known inputs, DB query layer stores/retrieves BacktestRun rows |
| **3** | A | CacheInvalidator + drift upgrade + convergence snapshot | 1-2 | 5 create, 5 modify | CacheInvalidator wired into existing tasks, per-ticker drift threshold works, convergence snapshot populates DB, experimental model excluded from alignment |
| **4** | A | Backtest API + tests + minimal frontend badge | 1-2 | 7 create, 3 modify | All 5 backtest endpoints work, admin auth enforced, accuracy badge visible on stock detail page |
| **5** | D | PipelineRegistry + seed tasks (3 batches) + admin user | 1-2 | 6 create, 9 modify (scripts, 3 batches with tests) | All seed scripts callable as Celery tasks with progress reporting, admin user created from .env, pipeline registry resolves dependencies correctly |
| **6** | D | Pipeline API + admin frontend page | 1-2 | 8 create, 3 modify | Admin can view all task groups, trigger a group, see progress, clear caches from /admin/pipelines |
| **7** | B | NewsProvider interface + Finnhub + EDGAR + Fed + Google | 1-2 | 8 create, 1 modify | All 4 providers parse fixture data correctly, dedup hashing works, rate limiting respected |
| **8** | B | Sentiment scorer + Prophet integration + Celery tasks | 1-2 | 5 create, 3 modify | LLM scoring produces structured JSON, weighted aggregation matches hand-calculated values, Prophet trains with regressors (feature-flagged), news tasks chained correctly |
| **9** | B | Sentiment API + tests | 1-2 | 6 create, 1 modify | All 4 sentiment endpoints work, empty state handled, integration test: mock HTTP → real DB → sentiment_daily populated |
| **10** | C | Portfolio forecast (BL + Monte Carlo + CVaR) + schemas + TS types | 1-2 | 5 create, 1 modify | BL uses excess returns (risk-free subtracted), Monte Carlo produces percentile bands, CVaR at 95% and 99%, portfolio forecast endpoint returns correct shape |
| **11** | C | Convergence service + rationale + API | 1-2 | 5 create, 1 modify | Bulk convergence query (no N+1), divergence hit rate computed correctly, rationale templates work, all convergence endpoints return data |
| **12a** | C | Frontend convergence components (traffic lights, divergence, rationale, accuracy) | 1 | 6 create, 2 modify | Components render with correct design tokens, a11y attributes present, mobile responsive (badge collapse), Jest snapshot tests pass |
| **12b** | C | Frontend portfolio components (BL, Monte Carlo, CVaR, dashboard) + page integration | 1 | 6 create, 4 modify | Portfolio page shows BL forecast + Monte Carlo chart + CVaR, dashboard zone has convergence indicator, MSW handlers work |
| **13** | All | E2E tests + command center integration + full regression | 1 | 3 create, 2 modify | All Playwright E2E pass, command center shows backtest health + sentiment coverage, full test suite green |

### Branching Strategy

One feature branch per spec, all branching from `develop`:
- `feat/KAN-XXX-backtesting` — Sprints 1-4 (Spec A + shared migration)
- `feat/KAN-XXX-admin-pipelines` — Sprints 5-6 (Spec D)
- `feat/KAN-XXX-news-sentiment` — Sprints 7-9 (Spec B)
- `feat/KAN-XXX-convergence-ux` — Sprints 10-13 (Spec C + integration)

Each spec = one PR to develop. Sprint 1 (shared migration) goes into the first branch (backtesting).

### CI Impact

New test files must match existing path filters:
- `tests/unit/services/` → triggered by `backend/**`
- `tests/api/` → triggered by `backend/**`
- `tests/e2e/playwright/` → triggered by `frontend/**` or develop merge
- Add path filter: `backend/services/news/**` → runs news-specific tests

### Migration Safety

Migration 024 is immutable once applied. If Sprint 7-9 development reveals schema changes for news tables, create migration 025. Do NOT amend 024.

---

## Sprint 1: Migration + Config + Shared Models

**Goal:** Create all database tables (shared migration 024) and all new SQLAlchemy models. This unblocks all 4 specs.

### Task 1.1: Add config settings

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/.env`
- Modify: `backend/.env.example`

- [ ] **Step 1:** Read `backend/config.py` to find the Settings class
- [ ] **Step 2:** Add all new config fields to Settings class:

```python
# --- News Sources ---
FINNHUB_API_KEY: str = ""
FRED_API_KEY: str = ""
OPENAI_API_KEY: str = ""
EDGAR_USER_AGENT: str = "StockSignalPlatform admin@example.com"

# --- Sentiment Scoring ---
NEWS_SCORING_MODEL: str = "gpt-4o-mini"
NEWS_SCORING_FALLBACK: str = "groq"
NEWS_INGEST_LOOKBACK_HOURS: int = 6
NEWS_MIN_ARTICLES_FOR_SCORE: int = 1

# --- Backtesting ---
BACKTEST_MIN_TRAIN_DAYS: int = 365
BACKTEST_STEP_DAYS: int = 30
BACKTEST_MIN_WINDOWS: int = 12

# --- Black-Litterman ---
BL_RISK_AVERSION: float = 3.07
BL_MAX_VIEW_CONFIDENCE: float = 0.95

# --- Monte Carlo ---
MONTE_CARLO_SIMULATIONS: int = 10000

# --- Pipeline ---
PIPELINE_FAILURE_MODE: str = "continue"
```

- [ ] **Step 3:** Add corresponding entries to `.env` and `.env.example`
- [ ] **Step 4:** Run `uv run python -c "from backend.config import settings; print(settings.BACKTEST_MIN_TRAIN_DAYS)"` to verify
- [ ] **Step 5:** Commit: `feat: add forecast intelligence config settings`

### Task 1.2: Create BacktestRun model

**Files:**
- Create: `backend/models/backtest.py`
- Test: `tests/unit/models/test_backtest_model.py`

- [ ] **Step 1:** Write test that BacktestRun model can be instantiated:

```python
# tests/unit/models/test_backtest_model.py
import uuid
from datetime import date, datetime, timezone

from backend.models.backtest import BacktestRun


def test_backtest_run_instantiation():
    run = BacktestRun(
        id=uuid.uuid4(),
        ticker="AAPL",
        model_version_id=uuid.uuid4(),
        config_label="baseline",
        train_start=date(2022, 1, 1),
        train_end=date(2023, 12, 31),
        test_start=date(2024, 1, 1),
        test_end=date(2024, 12, 31),
        horizon_days=90,
        num_windows=12,
        mape=0.08,
        mae=15.2,
        rmse=18.5,
        direction_accuracy=0.64,
        ci_containment=0.78,
        market_regime="bull",
        metadata={"ci_bias": "above", "avg_interval_width": 0.15},
    )
    assert run.ticker == "AAPL"
    assert run.mape == 0.08
    assert run.config_label == "baseline"
```

- [ ] **Step 2:** Run test — expect FAIL (module not found)

```bash
uv run pytest tests/unit/models/test_backtest_model.py -v
```

- [ ] **Step 3:** Create `backend/models/backtest.py`:

```python
"""Backtest run results for Prophet model validation."""

import uuid as _uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, Float, Integer, String, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin


class BacktestRun(TimestampMixin, Base):
    """Walk-forward backtest result for a single ticker+horizon+config."""

    __tablename__ = "backtest_runs"

    id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    ticker: Mapped[str] = mapped_column(
        String(10), ForeignKey("stocks.ticker"), nullable=False
    )
    model_version_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_versions.id"), nullable=False
    )
    config_label: Mapped[str] = mapped_column(String(30), nullable=False)
    train_start: Mapped[date] = mapped_column(Date, nullable=False)
    train_end: Mapped[date] = mapped_column(Date, nullable=False)
    test_start: Mapped[date] = mapped_column(Date, nullable=False)
    test_end: Mapped[date] = mapped_column(Date, nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    num_windows: Mapped[int] = mapped_column(Integer, nullable=False)
    mape: Mapped[float] = mapped_column(Float, nullable=False)
    mae: Mapped[float] = mapped_column(Float, nullable=False)
    rmse: Mapped[float] = mapped_column(Float, nullable=False)
    direction_accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    ci_containment: Mapped[float] = mapped_column(Float, nullable=False)
    market_regime: Mapped[str | None] = mapped_column(String(20), nullable=True)
    metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index(
            "ix_backtest_runs_ticker_horizon",
            "ticker",
            "horizon_days",
            "created_at",
            postgresql_using="btree",
        ),
    )
```

- [ ] **Step 4:** Run test — expect PASS
- [ ] **Step 5:** Commit: `feat: add BacktestRun model`

### Task 1.3: Create SignalConvergenceDaily model

**Files:**
- Create: `backend/models/convergence.py`
- Test: `tests/unit/models/test_convergence_model.py`

- [ ] **Step 1:** Write test:

```python
# tests/unit/models/test_convergence_model.py
from datetime import date

from backend.models.convergence import SignalConvergenceDaily


def test_convergence_daily_instantiation():
    row = SignalConvergenceDaily(
        date=date(2026, 4, 1),
        ticker="AAPL",
        rsi_direction="bullish",
        macd_direction="bullish",
        sma_direction="bullish",
        piotroski_direction="bullish",
        forecast_direction="neutral",
        news_sentiment=None,
        signals_aligned=4,
        convergence_label="strong_bull",
        composite_score=8.5,
    )
    assert row.signals_aligned == 4
    assert row.convergence_label == "strong_bull"
    assert row.news_sentiment is None  # nullable until Spec B
```

- [ ] **Step 2:** Run test — expect FAIL
- [ ] **Step 3:** Create `backend/models/convergence.py`:

```python
"""Daily signal convergence snapshot — tracks alignment of all indicators."""

from datetime import date

from sqlalchemy import Date, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin


class SignalConvergenceDaily(TimestampMixin, Base):
    """Pre-computed daily convergence state per ticker.

    Powers historical pattern analysis: "when this divergence pattern
    happened before, the forecast was right X% of the time."
    """

    __tablename__ = "signal_convergence_daily"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), primary_key=True)
    rsi_direction: Mapped[str] = mapped_column(String(10), nullable=False)
    macd_direction: Mapped[str] = mapped_column(String(10), nullable=False)
    sma_direction: Mapped[str] = mapped_column(String(10), nullable=False)
    piotroski_direction: Mapped[str] = mapped_column(String(10), nullable=False)
    forecast_direction: Mapped[str] = mapped_column(String(10), nullable=False)
    news_sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)
    signals_aligned: Mapped[int] = mapped_column(Integer, nullable=False)
    convergence_label: Mapped[str] = mapped_column(String(20), nullable=False)
    composite_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_return_90d: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_return_180d: Mapped[float | None] = mapped_column(Float, nullable=True)
```

- [ ] **Step 4:** Run test — expect PASS
- [ ] **Step 5:** Commit: `feat: add SignalConvergenceDaily model`

### Task 1.4: Create News models

**Files:**
- Create: `backend/models/news.py`
- Test: `tests/unit/models/test_news_model.py`

- [ ] **Step 1:** Write test:

```python
# tests/unit/models/test_news_model.py
import uuid
from datetime import date, datetime, timezone

from backend.models.news import NewsArticle, NewsSentimentDaily


def test_news_article_instantiation():
    article = NewsArticle(
        id=uuid.uuid4(),
        published_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
        ticker="AAPL",
        headline="Apple beats Q2 earnings estimates",
        summary="Revenue up 12% YoY...",
        source="finnhub",
        source_url="https://example.com/article",
        event_type="earnings",
        dedupe_hash="abc123def456",
    )
    assert article.source == "finnhub"
    assert article.scored_at is None


def test_sentiment_daily_instantiation():
    sentiment = NewsSentimentDaily(
        date=date(2026, 4, 1),
        ticker="AAPL",
        stock_sentiment=0.7,
        sector_sentiment=0.3,
        macro_sentiment=-0.2,
        article_count=5,
        confidence=0.85,
        dominant_event_type="earnings",
        quality_flag="ok",
    )
    assert sentiment.stock_sentiment == 0.7
    assert sentiment.quality_flag == "ok"


def test_sentiment_macro_ticker():
    """Macro sentiment uses special ticker '__MACRO__'."""
    macro = NewsSentimentDaily(
        date=date(2026, 4, 1),
        ticker="__MACRO__",
        stock_sentiment=0.0,
        sector_sentiment=0.0,
        macro_sentiment=-0.5,
        article_count=3,
        confidence=0.9,
    )
    assert macro.ticker == "__MACRO__"
```

- [ ] **Step 2:** Run test — expect FAIL
- [ ] **Step 3:** Create `backend/models/news.py`:

```python
"""News articles and sentiment aggregation models."""

import uuid as _uuid
from datetime import date, datetime

from sqlalchemy import Date, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin


class NewsArticle(TimestampMixin, Base):
    """Ingested news article metadata. No full article text stored."""

    __tablename__ = "news_articles"

    id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True), default=_uuid.uuid4
    )
    published_at: Mapped[datetime] = mapped_column(
        primary_key=True
    )  # hypertable time column — composite PK with id
    ticker: Mapped[str | None] = mapped_column(String(10), nullable=True)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    dedupe_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    scored_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Composite PK: (published_at, id) — required for TimescaleDB hypertable
    __table_args__ = (
        {"extend_existing": True},
    )


class NewsSentimentDaily(TimestampMixin, Base):
    """Aggregated daily sentiment per ticker. '__MACRO__' for macro-level."""

    __tablename__ = "news_sentiment_daily"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), primary_key=True)
    stock_sentiment: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sector_sentiment: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    macro_sentiment: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    article_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    dominant_event_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    rationale_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_flag: Mapped[str] = mapped_column(
        String(10), nullable=False, default="ok"
    )  # 'ok', 'suspect', 'invalidated'
```

- [ ] **Step 4:** Run test — expect PASS
- [ ] **Step 5:** Commit: `feat: add NewsArticle and NewsSentimentDaily models`

### Task 1.5: Create AdminAuditLog model

**Files:**
- Create: `backend/models/audit.py`
- Test: `tests/unit/models/test_audit_model.py`

- [ ] **Step 1:** Write test:

```python
# tests/unit/models/test_audit_model.py
import uuid

from backend.models.audit import AdminAuditLog


def test_audit_log_instantiation():
    log = AdminAuditLog(
        user_id=uuid.uuid4(),
        action="cache_clear_all",
        target="convergence:*",
        metadata={"keys_deleted": 42},
    )
    assert log.action == "cache_clear_all"
```

- [ ] **Step 2:** Run test — expect FAIL
- [ ] **Step 3:** Create `backend/models/audit.py`:

```python
"""Admin audit logging for pipeline and cache operations."""

import uuid as _uuid

from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin


class AdminAuditLog(TimestampMixin, Base):
    """Tracks admin actions: pipeline triggers, cache clears, etc."""

    __tablename__ = "admin_audit_log"

    id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    user_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    target: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

- [ ] **Step 4:** Run test — expect PASS
- [ ] **Step 5:** Commit: `feat: add AdminAuditLog model`

### Task 1.6: Register models in __init__.py

**Files:**
- Modify: `backend/models/__init__.py`

- [ ] **Step 1:** Read `backend/models/__init__.py` to see existing imports
- [ ] **Step 2:** Add new model imports:

```python
from backend.models.backtest import BacktestRun  # noqa: F401
from backend.models.convergence import SignalConvergenceDaily  # noqa: F401
from backend.models.news import NewsArticle, NewsSentimentDaily  # noqa: F401
from backend.models.audit import AdminAuditLog  # noqa: F401
```

- [ ] **Step 3:** Verify all models importable:

```bash
uv run python -c "from backend.models import BacktestRun, SignalConvergenceDaily, NewsArticle, NewsSentimentDaily, AdminAuditLog; print('OK')"
```

- [ ] **Step 4:** Commit: `feat: register forecast intelligence models`

### Task 1.7: Create Alembic migration 024

**Files:**
- Create: `backend/migrations/versions/024_forecast_intelligence.py`

- [ ] **Step 1:** Generate migration scaffold:

```bash
uv run alembic revision --autogenerate -m "024 forecast intelligence tables"
```

- [ ] **Step 2:** Edit the generated migration to add TimescaleDB hypertable creation and indexes. The autogenerated migration will create the tables but NOT the hypertables or custom indexes. Manually add after each `create_table`:

```python
# After signal_convergence_daily table creation:
op.execute("SELECT create_hypertable('signal_convergence_daily', 'date')")
op.execute("""
    CREATE INDEX ix_convergence_label
    ON signal_convergence_daily(convergence_label, forecast_direction)
""")

# After news_articles table creation:
op.execute("SELECT create_hypertable('news_articles', 'published_at')")
op.execute("""
    CREATE INDEX ix_news_ticker
    ON news_articles(ticker, published_at DESC)
""")

# After news_sentiment_daily table creation:
op.execute("SELECT create_hypertable('news_sentiment_daily', 'date')")

# After admin_audit_log table creation:
op.execute("""
    CREATE INDEX ix_audit_user
    ON admin_audit_log(user_id, created_at DESC)
""")
```

- [ ] **Step 3:** Verify `down_revision` matches current head (`5c9a05c38ee1`) by reading the file
- [ ] **Step 4:** Review autogenerated migration — remove any false TimescaleDB index drops (known gotcha)
- [ ] **Step 5:** Apply migration:

```bash
uv run alembic upgrade head
```

- [ ] **Step 6:** Verify tables exist:

```bash
uv run python -c "
import asyncio
from backend.database import async_session_factory
from sqlalchemy import text
async def check():
    async with async_session_factory() as db:
        result = await db.execute(text(\"SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN ('backtest_runs','signal_convergence_daily','news_articles','news_sentiment_daily','admin_audit_log')\"))
        tables = [r[0] for r in result]
        print(f'Found tables: {tables}')
        assert len(tables) == 5, f'Expected 5, got {len(tables)}'
asyncio.run(check())
"
```

- [ ] **Step 7:** Commit: `feat: migration 024 — forecast intelligence tables`

### Task 1.8: Create factory-boy factories for new models

**Files:**
- Create: `tests/factories/forecast_intelligence.py`

- [ ] **Step 1:** Create factories for all new models:

```python
# tests/factories/forecast_intelligence.py
"""Factory-boy factories for forecast intelligence models."""

import uuid
from datetime import date, datetime, timezone

import factory

from backend.models.backtest import BacktestRun
from backend.models.convergence import SignalConvergenceDaily
from backend.models.news import NewsArticle, NewsSentimentDaily
from backend.models.audit import AdminAuditLog


class BacktestRunFactory(factory.Factory):
    class Meta:
        model = BacktestRun

    id = factory.LazyFunction(uuid.uuid4)
    ticker = "AAPL"
    model_version_id = factory.LazyFunction(uuid.uuid4)
    config_label = "baseline"
    train_start = date(2022, 1, 1)
    train_end = date(2023, 12, 31)
    test_start = date(2024, 1, 1)
    test_end = date(2024, 12, 31)
    horizon_days = 90
    num_windows = 12
    mape = 0.08
    mae = 15.2
    rmse = 18.5
    direction_accuracy = 0.64
    ci_containment = 0.78
    market_regime = "bull"


class SignalConvergenceDailyFactory(factory.Factory):
    class Meta:
        model = SignalConvergenceDaily

    date = date(2026, 4, 1)
    ticker = "AAPL"
    rsi_direction = "bullish"
    macd_direction = "bullish"
    sma_direction = "bullish"
    piotroski_direction = "neutral"
    forecast_direction = "bullish"
    signals_aligned = 4
    convergence_label = "strong_bull"
    composite_score = 8.5


class NewsSentimentDailyFactory(factory.Factory):
    class Meta:
        model = NewsSentimentDaily

    date = date(2026, 4, 1)
    ticker = "AAPL"
    stock_sentiment = 0.5
    sector_sentiment = 0.2
    macro_sentiment = -0.1
    article_count = 5
    confidence = 0.8
    quality_flag = "ok"
```

- [ ] **Step 2:** Verify imports work
- [ ] **Step 3:** Commit: `feat: factory-boy factories for forecast intelligence models`

### Task 1.9: Mount all new routers as stubs + add TypeScript types

**Files:**
- Modify: `backend/main.py` (mount all 4 routers — they'll 404 until services exist)
- Modify: `frontend/src/types/api.ts` (add all new TypeScript types)
- Modify: `frontend/src/lib/api.ts` (add API client stubs)

This prevents merge conflicts from modifying these files across 4 specs.

- [ ] **Step 1:** Create empty router files with placeholder endpoints:

```python
# backend/routers/backtesting.py
from fastapi import APIRouter
router = APIRouter(prefix="/backtests", tags=["backtesting"])

# backend/routers/sentiment.py
from fastapi import APIRouter
router = APIRouter(prefix="/sentiment", tags=["sentiment"])

# backend/routers/convergence.py
from fastapi import APIRouter
router = APIRouter(prefix="/convergence", tags=["convergence"])

# backend/routers/admin_pipelines.py
from fastapi import APIRouter
router = APIRouter(prefix="/admin/pipelines", tags=["admin-pipelines"])
```

- [ ] **Step 2:** Mount in `backend/main.py`:

```python
from backend.routers.backtesting import router as backtesting_router
from backend.routers.sentiment import router as sentiment_router
from backend.routers.convergence import router as convergence_router
from backend.routers.admin_pipelines import router as admin_pipelines_router

app.include_router(backtesting_router, prefix="/api/v1")
app.include_router(sentiment_router, prefix="/api/v1")
app.include_router(convergence_router, prefix="/api/v1")
app.include_router(admin_pipelines_router, prefix="/api/v1")
```

- [ ] **Step 3:** Add TypeScript types to `frontend/src/types/api.ts`:

```typescript
// Forecast Intelligence types
export interface BacktestResult {
  id: string;
  ticker: string;
  config_label: string;
  horizon_days: number;
  mape: number;
  mae: number;
  rmse: number;
  direction_accuracy: number;
  ci_containment: number;
  market_regime: string | null;
  created_at: string;
}

export interface SignalLight {
  name: string;
  direction: 'bullish' | 'bearish' | 'neutral';
  value: number | null;
}

export interface StockConvergence {
  ticker: string;
  lights: SignalLight[];
  aligned_count: number;
  total_signals: number;
  convergence_label: string;
  divergence: { pattern: string; hit_rate: number; sample_count: number } | null;
  model_status: string;
}

export interface NewsSentiment {
  date: string;
  ticker: string;
  stock_sentiment: number;
  sector_sentiment: number;
  macro_sentiment: number;
  article_count: number;
  confidence: number;
  dominant_event_type: string | null;
}

export interface BLForecastResult {
  portfolio_expected_return: number;
  per_position_returns: Record<string, number>;
  view_contributions: Record<string, number>;
  confidence_level: string;
}

export interface MonteCarloResult {
  horizon_days: number;
  bands: { day: number; p5: number; p25: number; median: number; p75: number; p95: number }[];
}

export interface CVaRResult {
  var_pct_95: number;
  cvar_pct_95: number;
  var_pct_99: number;
  cvar_pct_99: number;
  horizon_days: number;
}

export interface PipelineTask {
  name: string;
  display_name: string;
  group: string;
  order: number;
  status: 'not_run' | 'queued' | 'running' | 'success' | 'failed';
  schedule: string | null;
  estimated_duration: string;
  is_seed: boolean;
  idempotent: boolean;
}

export interface PipelineGroup {
  name: string;
  tasks: PipelineTask[];
  is_running: boolean;
}
```

- [ ] **Step 4:** Commit: `feat: mount router stubs + TypeScript types for forecast intelligence`

### Task 1.10: Run existing test suite to confirm no regressions

- [ ] **Step 1:** Run unit tests:

```bash
uv run pytest tests/unit/ -q --tb=short -x
```

Expected: all existing tests pass (no regressions from new models/migration).

- [ ] **Step 2:** Run lint:

```bash
uv run ruff check backend/ tests/ && uv run ruff format --check backend/ tests/
```

- [ ] **Step 3:** Commit if any fixes needed

---

## Sprint 2: BacktestEngine + Walk-Forward (Spec A)

**Goal:** Core backtesting engine with walk-forward validation and metric computation.

### Task 2.1: Create Pydantic schemas for backtesting

**Files:**
- Create: `backend/schemas/backtesting.py`

- [ ] **Step 1:** Create schemas:

```python
# backend/schemas/backtesting.py
"""Pydantic schemas for backtest API."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class BacktestRunResponse(BaseModel):
    """Single backtest run result."""

    id: UUID
    ticker: str
    config_label: str
    horizon_days: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    num_windows: int
    mape: float
    mae: float
    rmse: float
    direction_accuracy: float
    ci_containment: float
    market_regime: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class BacktestSummaryItem(BaseModel):
    """Per-ticker backtest summary (latest run per horizon)."""

    ticker: str
    horizon_days: int
    mape: float
    direction_accuracy: float
    ci_containment: float
    market_regime: str | None = None
    config_label: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BacktestSummaryResponse(BaseModel):
    """All tickers sorted by accuracy."""

    items: list[BacktestSummaryItem]
    total: int


class BacktestTriggerRequest(BaseModel):
    """Request to trigger a backtest run."""

    ticker: str | None = Field(None, description="Specific ticker, or None for all")
    horizon_days: int = Field(90, description="Forecast horizon to backtest")


class BacktestTriggerResponse(BaseModel):
    """Response after triggering a backtest."""

    task_id: str
    status: str = "queued"


class CalibrateTriggerRequest(BaseModel):
    """Request to trigger seasonality calibration."""

    ticker: str | None = Field(None, description="Specific ticker, or None for all")


class CalibrateTriggerResponse(BaseModel):
    """Response after triggering calibration."""

    task_id: str
    status: str = "queued"
```

- [ ] **Step 2:** Verify imports: `uv run python -c "from backend.schemas.backtesting import BacktestRunResponse; print('OK')"`
- [ ] **Step 3:** Commit: `feat: add backtest Pydantic schemas`

### Task 2.2: Implement BacktestEngine — walk-forward logic

**Files:**
- Create: `backend/services/backtesting.py`
- Create: `tests/unit/services/test_backtest_engine.py`

- [ ] **Step 1:** Write failing tests for expanding window generation:

```python
# tests/unit/services/test_backtest_engine.py
"""Tests for BacktestEngine walk-forward validation."""

from datetime import date

import pytest

from backend.services.backtesting import BacktestEngine


class TestExpandingWindows:
    """Test walk-forward expanding window generation."""

    def test_generates_correct_number_of_windows(self):
        engine = BacktestEngine()
        windows = engine._generate_expanding_windows(
            data_start=date(2022, 1, 1),
            data_end=date(2024, 12, 31),
            min_train_days=365,
            step_days=30,
            horizon_days=90,
        )
        # 3 years of data, 1 year min training, 30-day steps
        # First test point: 2023-01-01 + 90 = 2023-04-01
        # Last possible test point: 2024-12-31 - 90 = 2024-10-02
        # Windows from 2023-01 to 2024-10, stepping 30 days = ~21 windows
        assert len(windows) >= 12  # min_windows config
        assert len(windows) <= 25  # sanity upper bound

    def test_training_set_grows_each_window(self):
        engine = BacktestEngine()
        windows = engine._generate_expanding_windows(
            data_start=date(2022, 1, 1),
            data_end=date(2024, 12, 31),
            min_train_days=365,
            step_days=30,
            horizon_days=90,
        )
        for i in range(1, len(windows)):
            prev_train_end = windows[i - 1]["train_end"]
            curr_train_end = windows[i]["train_end"]
            assert curr_train_end > prev_train_end, (
                f"Window {i} train_end ({curr_train_end}) must be after "
                f"window {i-1} train_end ({prev_train_end})"
            )

    def test_no_overlap_between_train_and_test(self):
        engine = BacktestEngine()
        windows = engine._generate_expanding_windows(
            data_start=date(2022, 1, 1),
            data_end=date(2024, 12, 31),
            min_train_days=365,
            step_days=30,
            horizon_days=90,
        )
        for i, w in enumerate(windows):
            assert w["test_date"] > w["train_end"], (
                f"Window {i}: test_date ({w['test_date']}) must be after "
                f"train_end ({w['train_end']})"
            )

    def test_all_windows_share_same_train_start(self):
        """Expanding window: train_start is always the data start."""
        engine = BacktestEngine()
        windows = engine._generate_expanding_windows(
            data_start=date(2022, 1, 1),
            data_end=date(2024, 12, 31),
            min_train_days=365,
            step_days=30,
            horizon_days=90,
        )
        for w in windows:
            assert w["train_start"] == date(2022, 1, 1)


class TestMetricComputation:
    """Test MAPE, MAE, RMSE, direction accuracy, CI containment."""

    def test_mape_computation(self):
        engine = BacktestEngine()
        actuals = [100.0, 110.0, 90.0, 105.0]
        predicted = [102.0, 108.0, 95.0, 100.0]
        mape = engine._compute_mape(actuals, predicted)
        # |100-102|/100 + |110-108|/110 + |90-95|/90 + |105-100|/105
        # = 0.02 + 0.0182 + 0.0556 + 0.0476 = 0.1414 / 4 = 0.0353
        assert abs(mape - 0.0353) < 0.001

    def test_direction_accuracy(self):
        engine = BacktestEngine()
        # Price went from base to actual; forecast predicted direction
        base_prices = [100.0, 100.0, 100.0, 100.0]
        actuals = [110.0, 90.0, 105.0, 95.0]  # up, down, up, down
        predicted = [108.0, 95.0, 98.0, 92.0]  # up, down, down, down
        # Directions: correct, correct, WRONG, correct = 3/4 = 0.75
        acc = engine._compute_direction_accuracy(base_prices, actuals, predicted)
        assert acc == 0.75

    def test_ci_containment(self):
        engine = BacktestEngine()
        actuals = [100.0, 110.0, 90.0, 105.0]
        lowers = [95.0, 105.0, 85.0, 100.0]
        uppers = [108.0, 115.0, 95.0, 110.0]
        # 100 in [95,108]? Yes. 110 in [105,115]? Yes.
        # 90 in [85,95]? Yes. 105 in [100,110]? Yes. = 4/4 = 1.0
        containment = engine._compute_ci_containment(actuals, lowers, uppers)
        assert containment == 1.0

    def test_ci_containment_partial(self):
        engine = BacktestEngine()
        actuals = [100.0, 120.0]  # second is outside
        lowers = [95.0, 105.0]
        uppers = [108.0, 115.0]  # 120 > 115, outside
        containment = engine._compute_ci_containment(actuals, lowers, uppers)
        assert containment == 0.5
```

- [ ] **Step 2:** Run tests — expect FAIL:

```bash
uv run pytest tests/unit/services/test_backtest_engine.py -v
```

- [ ] **Step 3:** Create `backend/services/backtesting.py` with the engine:

```python
"""Walk-forward backtesting engine for Prophet model validation."""

import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta

logger = logging.getLogger(__name__)


@dataclass
class WindowSpec:
    """Single walk-forward window definition."""

    train_start: date
    train_end: date
    test_date: date  # the date we're predicting for


@dataclass
class BacktestMetrics:
    """Computed metrics from a backtest run."""

    mape: float
    mae: float
    rmse: float
    direction_accuracy: float
    ci_containment: float
    ci_bias: str  # "above", "below", "balanced"
    avg_interval_width: float
    num_windows: int
    per_window_results: list[dict] = field(default_factory=list)


class BacktestEngine:
    """Walk-forward validation for Prophet models.

    Uses expanding window: training set grows with each step.
    Test point is always one step ahead of training data.
    No overlap between any test period and training data.
    """

    def _generate_expanding_windows(
        self,
        data_start: date,
        data_end: date,
        min_train_days: int = 365,
        step_days: int = 30,
        horizon_days: int = 90,
    ) -> list[dict]:
        """Generate expanding window specifications.

        Args:
            data_start: First available data point.
            data_end: Last available data point.
            min_train_days: Minimum training period.
            step_days: Days to advance between windows.
            horizon_days: Forecast horizon.

        Returns:
            List of window dicts with train_start, train_end, test_date.
        """
        windows = []
        first_train_end = data_start + timedelta(days=min_train_days)
        current_train_end = first_train_end

        while True:
            test_date = current_train_end + timedelta(days=horizon_days)
            if test_date > data_end:
                break

            windows.append({
                "train_start": data_start,
                "train_end": current_train_end,
                "test_date": test_date,
            })
            current_train_end += timedelta(days=step_days)

        return windows

    def _compute_mape(
        self, actuals: list[float], predicted: list[float]
    ) -> float:
        """Mean Absolute Percentage Error."""
        if not actuals:
            return 0.0
        errors = []
        for a, p in zip(actuals, predicted):
            if a != 0:
                errors.append(abs(a - p) / abs(a))
        return sum(errors) / len(errors) if errors else 0.0

    def _compute_mae(
        self, actuals: list[float], predicted: list[float]
    ) -> float:
        """Mean Absolute Error."""
        if not actuals:
            return 0.0
        return sum(abs(a - p) for a, p in zip(actuals, predicted)) / len(actuals)

    def _compute_rmse(
        self, actuals: list[float], predicted: list[float]
    ) -> float:
        """Root Mean Squared Error."""
        if not actuals:
            return 0.0
        mse = sum((a - p) ** 2 for a, p in zip(actuals, predicted)) / len(actuals)
        return math.sqrt(mse)

    def _compute_direction_accuracy(
        self,
        base_prices: list[float],
        actuals: list[float],
        predicted: list[float],
    ) -> float:
        """Percentage of correct up/down predictions."""
        if not actuals:
            return 0.0
        correct = 0
        for base, actual, pred in zip(base_prices, actuals, predicted):
            actual_up = actual > base
            pred_up = pred > base
            if actual_up == pred_up:
                correct += 1
        return correct / len(actuals)

    def _compute_ci_containment(
        self,
        actuals: list[float],
        lowers: list[float],
        uppers: list[float],
    ) -> float:
        """Percentage of actuals within predicted confidence interval."""
        if not actuals:
            return 0.0
        contained = sum(
            1 for a, lo, hi in zip(actuals, lowers, uppers) if lo <= a <= hi
        )
        return contained / len(actuals)

    def _compute_ci_bias(
        self,
        actuals: list[float],
        predicted: list[float],
    ) -> str:
        """Whether actuals are systematically above/below predictions."""
        if not actuals:
            return "balanced"
        above = sum(1 for a, p in zip(actuals, predicted) if a > p)
        ratio = above / len(actuals)
        if ratio > 0.6:
            return "above"
        elif ratio < 0.4:
            return "below"
        return "balanced"
```

- [ ] **Step 4:** Run tests — expect PASS:

```bash
uv run pytest tests/unit/services/test_backtest_engine.py -v
```

- [ ] **Step 5:** Commit: `feat: BacktestEngine with walk-forward and metric computation`

---

## Sprint 3: Drift Upgrade + Seasonality + Convergence Snapshot (Spec A)

**Goal:** Upgrade drift detection with per-ticker baselines, add seasonality calibration, and create the convergence snapshot task.

### Task 3.1: CacheInvalidator service

**Files:**
- Create: `backend/services/cache_invalidator.py`
- Create: `tests/unit/services/test_cache_invalidator.py`

- [ ] **Step 1:** Write failing tests:

```python
# tests/unit/services/test_cache_invalidator.py
"""Tests for event-driven CacheInvalidator."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.services.cache_invalidator import CacheInvalidator


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.delete = AsyncMock(return_value=1)
    redis.scan = AsyncMock(return_value=(0, []))
    return redis


@pytest.fixture
def invalidator(mock_redis):
    return CacheInvalidator(redis=mock_redis)


@pytest.mark.asyncio
async def test_on_signals_updated_clears_convergence(invalidator, mock_redis):
    await invalidator.on_signals_updated(["AAPL", "MSFT"])
    # Should clear convergence and rationale for both tickers
    calls = [str(c) for c in mock_redis.delete.call_args_list]
    assert any("app:convergence:AAPL" in c for c in calls)
    assert any("app:convergence:MSFT" in c for c in calls)
    assert any("app:convergence:rationale:AAPL" in c for c in calls)


@pytest.mark.asyncio
async def test_on_signals_updated_does_not_clear_unrelated(invalidator, mock_redis):
    """Negative test: invalidating AAPL should NOT touch MSFT cache."""
    await invalidator.on_signals_updated(["AAPL"])
    calls = [str(c) for c in mock_redis.delete.call_args_list]
    assert not any("MSFT" in c for c in calls)


@pytest.mark.asyncio
async def test_on_prices_updated_does_not_clear_bl_cache(invalidator, mock_redis):
    """BL/MC/CVaR caches rely on TTL, not explicit invalidation on price update."""
    await invalidator.on_prices_updated(["AAPL"])
    calls = [str(c) for c in mock_redis.delete.call_args_list]
    assert not any("bl-forecast" in c for c in calls)
    assert not any("monte-carlo" in c for c in calls)
    assert not any("cvar" in c for c in calls)


@pytest.mark.asyncio
async def test_on_portfolio_changed_clears_user_caches(invalidator, mock_redis):
    user_id = "user-123"
    await invalidator.on_portfolio_changed(user_id)
    calls = [str(c) for c in mock_redis.delete.call_args_list]
    assert any(f"bl-forecast:{user_id}" in c for c in calls)
    assert any(f"monte-carlo:{user_id}" in c for c in calls)
    assert any(f"cvar:{user_id}" in c for c in calls)
```

- [ ] **Step 2:** Run tests — expect FAIL
- [ ] **Step 3:** Create `backend/services/cache_invalidator.py`:

```python
"""Event-driven cache invalidation. Trigger-agnostic — same logic whether
called from nightly pipeline, admin dashboard, or user action."""

import logging

logger = logging.getLogger(__name__)


class CacheInvalidator:
    """Single source of truth for cache invalidation rules.

    Injected as FastAPI dependency for request lifecycle.
    Imported directly in Celery tasks.
    """

    def __init__(self, redis):
        self._redis = redis

    async def on_prices_updated(self, tickers: list[str]) -> None:
        """Price data changed. Clear convergence + forecast caches.

        Does NOT clear BL/MC/CVaR — those have 1hr TTL (natural expiry).
        """
        for t in tickers:
            await self._redis.delete(
                f"app:convergence:{t}",
                f"app:convergence:rationale:{t}",
                f"app:forecast:{t}",
            )
        logger.info("Cache invalidated for %d tickers (prices)", len(tickers))

    async def on_signals_updated(self, tickers: list[str]) -> None:
        """Signal snapshots recomputed."""
        for t in tickers:
            await self._redis.delete(
                f"app:convergence:{t}",
                f"app:convergence:rationale:{t}",
            )

    async def on_stock_ingested(self, ticker: str) -> None:
        """Brand new stock added. Nothing to invalidate — warm proactively."""
        logger.info("New stock ingested: %s — cache warming deferred", ticker)

    async def on_forecast_updated(self, tickers: list[str]) -> None:
        """Forecasts regenerated."""
        for t in tickers:
            await self._redis.delete(
                f"app:forecast:{t}",
                f"app:convergence:{t}",
                f"app:convergence:rationale:{t}",
            )
        # Sector caches — clear all (can't efficiently map ticker→sector here)
        await self._clear_pattern("app:sector-forecast:*")

    async def on_backtest_completed(self, tickers: list[str]) -> None:
        """Backtest results updated."""
        for t in tickers:
            await self._redis.delete(f"app:backtest:{t}")

    async def on_sentiment_scored(self, tickers: list[str]) -> None:
        """New sentiment scores available."""
        for t in tickers:
            await self._redis.delete(
                f"app:sentiment:{t}",
                f"app:convergence:{t}",
                f"app:convergence:rationale:{t}",
            )

    async def on_portfolio_changed(self, user_id: str) -> None:
        """User added/removed positions."""
        await self._redis.delete(
            f"app:bl-forecast:{user_id}",
            f"app:monte-carlo:{user_id}",
            f"app:cvar:{user_id}",
        )

    async def _clear_pattern(self, pattern: str) -> int:
        """Clear keys matching pattern using SCAN (never KEYS)."""
        deleted = 0
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
            if keys:
                await self._redis.delete(*keys)
                deleted += len(keys)
            if cursor == 0:
                break
        return deleted
```

- [ ] **Step 4:** Run tests — expect PASS
- [ ] **Step 5:** Commit: `feat: CacheInvalidator service — event-driven, trigger-agnostic`

### Task 3.2: Convergence snapshot Celery task

**Files:**
- Create: `backend/tasks/convergence.py`
- Create: `tests/unit/tasks/test_convergence_task.py`
- Modify: `backend/tasks/market_data.py` (add to nightly Phase 3)

- [ ] **Step 1:** Write test for direction classification helpers:

```python
# tests/unit/tasks/test_convergence_task.py
"""Tests for convergence snapshot computation."""

import pytest

from backend.tasks.convergence import (
    _classify_rsi,
    _classify_macd,
    _classify_sma,
    _classify_piotroski,
    _classify_forecast,
    _compute_convergence_label,
)


class TestDirectionClassification:
    def test_rsi_bullish(self):
        assert _classify_rsi(35.0) == "bullish"

    def test_rsi_bearish(self):
        assert _classify_rsi(75.0) == "bearish"

    def test_rsi_neutral(self):
        assert _classify_rsi(55.0) == "neutral"

    def test_rsi_none(self):
        assert _classify_rsi(None) == "neutral"

    def test_macd_bullish(self):
        assert _classify_macd(0.5, 0.3) == "bullish"  # positive and rising

    def test_macd_bearish(self):
        assert _classify_macd(-0.5, -0.3) == "bearish"  # negative and falling

    def test_sma_bullish(self):
        assert _classify_sma(current_price=210.0, sma_200=200.0) == "bullish"

    def test_sma_neutral_within_2pct(self):
        assert _classify_sma(current_price=201.0, sma_200=200.0) == "neutral"

    def test_piotroski_bullish(self):
        assert _classify_piotroski(7) == "bullish"

    def test_piotroski_bearish(self):
        assert _classify_piotroski(2) == "bearish"

    def test_forecast_bullish(self):
        assert _classify_forecast(0.05) == "bullish"  # +5% > +3%

    def test_forecast_neutral(self):
        assert _classify_forecast(0.01) == "neutral"  # +1% within ±3%


class TestConvergenceLabels:
    def test_strong_bull(self):
        directions = ["bullish", "bullish", "bullish", "bullish", "neutral"]
        assert _compute_convergence_label(directions) == "strong_bull"

    def test_weak_bull(self):
        directions = ["bullish", "bullish", "bullish", "bearish", "neutral"]
        assert _compute_convergence_label(directions) == "weak_bull"

    def test_mixed(self):
        directions = ["bullish", "bullish", "bearish", "bearish", "neutral"]
        assert _compute_convergence_label(directions) == "mixed"

    def test_strong_bear(self):
        directions = ["bearish", "bearish", "bearish", "bearish", "neutral"]
        assert _compute_convergence_label(directions) == "strong_bear"
```

- [ ] **Step 2:** Run tests — expect FAIL
- [ ] **Step 3:** Create `backend/tasks/convergence.py`:

```python
"""Celery task for computing daily signal convergence snapshots."""

import asyncio
import logging
from datetime import date

from backend.tasks import celery_app

logger = logging.getLogger(__name__)


def _classify_rsi(rsi: float | None) -> str:
    if rsi is None:
        return "neutral"
    if rsi < 40:
        return "bullish"
    if rsi > 70:
        return "bearish"
    return "neutral"


def _classify_macd(histogram: float | None, prev_histogram: float | None) -> str:
    if histogram is None:
        return "neutral"
    if histogram > 0 and (prev_histogram is None or histogram > prev_histogram):
        return "bullish"
    if histogram < 0 and (prev_histogram is None or histogram < prev_histogram):
        return "bearish"
    return "neutral"


def _classify_sma(current_price: float | None, sma_200: float | None) -> str:
    if current_price is None or sma_200 is None or sma_200 == 0:
        return "neutral"
    pct_diff = (current_price - sma_200) / sma_200
    if pct_diff > 0.02:
        return "bullish"
    if pct_diff < -0.02:
        return "bearish"
    return "neutral"


def _classify_piotroski(score: int | None) -> str:
    if score is None:
        return "neutral"
    if score >= 6:
        return "bullish"
    if score <= 3:
        return "bearish"
    return "neutral"


def _classify_forecast(predicted_return: float | None) -> str:
    if predicted_return is None:
        return "neutral"
    if predicted_return > 0.03:
        return "bullish"
    if predicted_return < -0.03:
        return "bearish"
    return "neutral"


def _compute_convergence_label(directions: list[str]) -> str:
    """Compute convergence label from signal directions.

    Revised thresholds (per domain review):
    - Strong Bull: 4+ bullish, 0 bearish
    - Weak Bull: 3+ bullish, <=1 bearish
    - Strong Bear: 4+ bearish, 0 bullish
    - Weak Bear: 3+ bearish, <=1 bullish
    - Mixed: everything else
    """
    bullish = directions.count("bullish")
    bearish = directions.count("bearish")

    if bullish >= 4 and bearish == 0:
        return "strong_bull"
    if bullish >= 3 and bearish <= 1:
        return "weak_bull"
    if bearish >= 4 and bullish == 0:
        return "strong_bear"
    if bearish >= 3 and bullish <= 1:
        return "weak_bear"
    return "mixed"


@celery_app.task
def compute_convergence_snapshot_task():
    """Nightly task: compute convergence state for all tracked tickers.

    Also backfills actual_return_90d/180d for rows from 90/180 days ago.
    """
    return asyncio.run(_compute_convergence_snapshot_async())


async def _compute_convergence_snapshot_async() -> dict:
    """Compute and store daily convergence snapshot."""
    from backend.database import async_session_factory
    from backend.models.convergence import SignalConvergenceDaily
    from backend.models.signal import SignalSnapshot

    # Implementation: query latest signals, classify directions,
    # compute labels, store rows, backfill actual returns.
    # Full implementation in Sprint 3 when we wire to DB.
    logger.info("Convergence snapshot task — implementation pending full wiring")
    return {"status": "ok", "computed": 0}
```

- [ ] **Step 4:** Run tests — expect PASS
- [ ] **Step 5:** Commit: `feat: convergence snapshot task with direction classification`

### Task 3.3: Upgrade drift detection

**Files:**
- Modify: `backend/tasks/evaluation.py`
- Create: `tests/unit/tasks/test_drift_upgrade.py`

_(Full implementation with per-ticker baselines, validate-before-promote, experimental demotion/self-healing)_

- [ ] **Step 1:** Write tests for per-ticker threshold and validate-before-promote logic
- [ ] **Step 2:** Run tests — expect FAIL
- [ ] **Step 3:** Modify `_check_drift_async()` in evaluation.py to use calibrated baselines
- [ ] **Step 4:** Add `retrain_and_validate()` function
- [ ] **Step 5:** Run tests — expect PASS
- [ ] **Step 6:** Run existing evaluation tests to confirm no regressions
- [ ] **Step 7:** Commit: `feat: per-ticker calibrated drift detection with validate-before-promote`

---

## Sprint 4: Backtest API + Tests (Spec A Complete)

### Task 4.1: Backtest router

**Files:**
- Create: `backend/routers/backtesting.py`
- Modify: `backend/main.py` (mount router)

_(Endpoints: GET /backtests/{ticker}, GET /backtests/summary, POST /backtests/run, POST /backtests/calibrate, GET /backtests/{ticker}/history)_

### Task 4.2: Backtest Celery tasks

**Files:**
- Modify: `backend/tasks/forecasting.py`

_(Add run_backtest_task, calibrate_seasonality_task)_

### Task 4.3: API tests

**Files:**
- Create: `tests/api/test_backtest_endpoints.py`

_(Auth tests, happy path, pagination, empty state)_

### Task 4.4: Integration test (slow)

**Files:**
- Create: `tests/integration/test_backtest_slow.py`

_(Real Prophet, AAPL fixture data, 252 points, 3 windows, sanity assertions)_

### Task 4.5: Cache invalidation integration test

**Files:**
- Create: `tests/integration/test_cache_invalidation.py`

---

## Sprint 5: PipelineRegistry + Seed Tasks (Spec D Start)

### Task 5.1: PipelineRegistry service

**Files:**
- Create: `backend/services/pipeline_registry.py`
- Create: `tests/unit/services/test_pipeline_registry.py`

Includes:
- `TaskDefinition` dataclass with all fields from spec (name, display_name, group, order, depends_on, is_seed, schedule, estimated_duration, idempotent, incremental)
- `run_group()` with Celery chord/chain dispatch
- Pipeline run tracking via Redis: `pipeline:run:{run_id}` → JSON with `{group, status, started_at, child_task_ids, completed, failed, total}`
- Failure modes: stop_on_failure, continue, threshold:N
- Concurrent run protection: check for active run before dispatch

### Task 5.2: Seed task wrappers

**Files:**
- Create: `backend/tasks/seed_tasks.py`
- Modify: 9 scripts (expose async functions)

### Task 5.3: Pipeline registry config

**Files:**
- Create: `backend/services/pipeline_registry_config.py`

### Task 5.4: Admin user seed

_(Create admin user from .env on first run)_

---

## Sprint 6: Pipeline API + Frontend (Spec D Complete)

### Task 6.1: Admin pipeline router

**Files:**
- Create: `backend/routers/admin_pipelines.py`
- Create: `backend/schemas/admin_pipeline.py`

Includes:
- Pipeline group run tracking via Redis (`{run_id, group, status, child_task_ids, completed, failed, total}`)
- Sentiment quality_flag admin endpoint: `POST /api/v1/admin/sentiment/invalidate?date_from=...&date_to=...`
- Cache clear with whitelist validation and admin audit logging
- Concurrent run protection (409 Conflict)

### Task 6.2: Pipeline Control frontend page

**Files:**
- Create: `frontend/src/app/(authenticated)/admin/pipelines/page.tsx`
- Create: `frontend/src/components/admin/pipeline-group-card.tsx`
- Create: `frontend/src/components/admin/pipeline-task-row.tsx`
- Create: `frontend/src/components/admin/pipeline-run-history.tsx`
- Create: `frontend/src/components/admin/cache-controls.tsx`
- Create: `frontend/src/hooks/use-admin-pipelines.ts`

### Task 6.3: API + E2E tests

**Files:**
- Create: `tests/api/test_admin_pipeline_endpoints.py`
- Create: `tests/e2e/playwright/tests/admin-pipelines.spec.ts`

---

## Sprint 7: NewsProvider Interface + Implementations (Spec B Start)

### Task 7.1: NewsProvider ABC + RawArticle

**Files:**
- Create: `backend/services/news/__init__.py`
- Create: `backend/services/news/base.py`

### Task 7.2: Finnhub provider

**Files:**
- Create: `backend/services/news/finnhub_provider.py`
- Create: `tests/fixtures/news/finnhub_aapl.json`

### Task 7.3: EDGAR 8-K provider

**Files:**
- Create: `backend/services/news/edgar_provider.py`
- Create: `tests/fixtures/news/edgar_8k_sample.json`

### Task 7.4: Fed RSS + FRED provider

**Files:**
- Create: `backend/services/news/fed_provider.py`
- Create: `tests/fixtures/news/fed_rss_sample.xml`

### Task 7.5: Google News fallback provider

**Files:**
- Create: `backend/services/news/google_provider.py`

### Task 7.6: Provider unit tests

**Files:**
- Create: `tests/unit/services/test_news_providers.py`

---

## Sprint 8: Sentiment Scorer + Prophet Integration (Spec B)

### Task 8.1: OpenAI provider for LLM Factory

**Files:**
- Create: `backend/services/llm/openai_provider.py`

### Task 8.2: Sentiment scorer

**Files:**
- Create: `backend/services/news/sentiment_scorer.py`
- Create: `tests/unit/services/test_sentiment_scorer.py`

_(Prompt construction, batch scoring, weighted aggregation with decay, edge cases)_

### Task 8.3: News ingestion orchestrator

**Files:**
- Create: `backend/services/news/ingestion.py`

### Task 8.4: Prophet regressor integration

**Files:**
- Modify: `backend/tools/forecasting.py`

_(Add sentiment regressors to train_prophet_model, fetch sentiment data)_

### Task 8.5: News Celery tasks

**Files:**
- Create: `backend/tasks/news_sentiment.py`
- Modify: `backend/tasks/__init__.py` (beat schedule)

---

## Sprint 9: Sentiment API + Tests (Spec B Complete)

### Task 9.1: Sentiment router + schemas

**Files:**
- Create: `backend/routers/sentiment.py`
- Create: `backend/schemas/sentiment.py`
- Modify: `backend/main.py`

### Task 9.2: Sentiment unit tests

**Files:**
- Create: `tests/unit/tasks/test_news_sentiment_tasks.py`

### Task 9.3: Sentiment API tests

**Files:**
- Create: `tests/api/test_sentiment_endpoints.py`

### Task 9.4: News pipeline integration test

**Files:**
- Create: `tests/integration/test_news_pipeline.py`

---

## Sprint 10: Portfolio Forecast — BL + Monte Carlo + CVaR (Spec C Start)

### Task 10.1: PortfolioForecastService

**Files:**
- Create: `backend/services/portfolio_forecast.py`
- Create: `tests/unit/services/test_portfolio_forecast.py`

_(BL with excess returns, Monte Carlo with proper annualization, CVaR at 95%+99%)_

### Task 10.2: Portfolio forecast schemas

**Files:**
- Create: `backend/schemas/portfolio_forecast.py`

### Task 10.3: Portfolio forecast endpoints

**Files:**
- Modify: `backend/routers/portfolio.py`

### Task 10.4: Portfolio forecast API tests

**Files:**
- Create: `tests/api/test_portfolio_forecast_endpoints.py`

---

## Sprint 11: Convergence Service + Rationale + API (Spec C)

### Task 11.1: SignalConvergenceService (full, with news)

**Files:**
- Create: `backend/services/signal_convergence.py`
- Create: `tests/unit/services/test_signal_convergence.py`

_(Direction classification, convergence labels, divergence detection, bulk queries, hit rate computation)_

### Task 11.2: RationaleGenerator

**Files:**
- Create: `backend/services/rationale.py`
- Create: `tests/unit/services/test_rationale_generator.py`

### Task 11.3: Convergence router + schemas

**Files:**
- Create: `backend/routers/convergence.py`
- Create: `backend/schemas/convergence.py`
- Modify: `backend/main.py`

Endpoints include:
- `GET /api/v1/convergence/{ticker}` — traffic lights + rationale
- `GET /api/v1/convergence/portfolio/{id}` — portfolio convergence summary
- `GET /api/v1/convergence/{ticker}/history` — convergence over time
- `GET /api/v1/sectors/{sector}/convergence` — sector convergence (equal-weight aggregation)

### Task 11.4: Convergence API tests

**Files:**
- Create: `tests/api/test_convergence_endpoints.py`

---

## Sprint 12: Frontend Convergence + Portfolio Components (Spec C)

### Task 12.1: Traffic light components

**Files:**
- Create: `frontend/src/components/convergence/traffic-light-row.tsx`
- Create: `frontend/src/components/convergence/divergence-alert.tsx`
- Create: `frontend/src/components/convergence/rationale-section.tsx`
- Create: `frontend/src/components/convergence/accuracy-badge.tsx`

### Task 12.2: Portfolio forecast components

**Files:**
- Create: `frontend/src/components/portfolio/bl-forecast-card.tsx`
- Create: `frontend/src/components/portfolio/monte-carlo-chart.tsx`
- Create: `frontend/src/components/portfolio/cvar-card.tsx`
- Create: `frontend/src/components/portfolio/convergence-summary.tsx`

### Task 12.3: Hooks + API client + types

**Files:**
- Create: `frontend/src/hooks/use-convergence.ts`
- Create: `frontend/src/hooks/use-sentiment.ts`
- Create: `frontend/src/hooks/use-bl-forecast.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/types/api.ts`

### Task 12.4: Page integrations

**Files:**
- Modify: `frontend/src/components/forecast-card.tsx` (accuracy badge)
- Modify: `frontend/src/app/(authenticated)/portfolio/portfolio-client.tsx`
- Modify: `frontend/src/app/(authenticated)/dashboard/_components/portfolio-zone.tsx` (convergence indicator + BL return)
- Modify: `frontend/src/mocks/handlers.ts` (MSW handlers)

Note: Dashboard portfolio zone gets a compact convergence indicator + BL expected return number. Click-through to portfolio page for full detail.

---

## Sprint 13: E2E Tests + Final Integration + Expert Review (All Specs)

### Task 13.1: E2E Playwright tests

**Files:**
- Create: `tests/e2e/playwright/tests/convergence.spec.ts`
- Create: `tests/e2e/playwright/tests/portfolio-forecast.spec.ts`

### Task 13.2: Command center integration

**Files:**
- Modify: `backend/observability/routers/command_center.py`

_(Add backtest health, sentiment coverage metrics)_

### Task 13.3: Full regression test run

```bash
uv run pytest tests/unit/ -q --tb=short -x
uv run pytest tests/api/ -q --tb=short
uv run ruff check backend/ tests/ && uv run ruff format --check backend/ tests/
cd frontend && npm run lint && npm run build
```

### Task 13.4: Coverage report

```bash
uv run pytest --cov=backend --cov-report=term-missing -q
```

---

## Plan Review Findings (6 Personas)

**Review conducted against spec to verify complete coverage and implementation correctness.**

### Critical Fixes Applied

| # | Persona | Finding | Fix Applied |
|---|---------|---------|-------------|
| P1 | PM | No user-visible deliverable until Sprint 12 | Added accuracy badge to stock detail in Sprint 4 |
| P2 | PM | Sprint 12 too large (17 files) | Split into 12a (convergence) + 12b (portfolio) |
| U1 | UI/UX | No component-level testing before integration | Jest snapshot tests per component before page integration |
| F1 | Full-Stack | Response schema defined in Sprint 10, consumed in Sprint 12 — gap | TypeScript types defined in Sprint 1 (contract-first) |
| F2 | Full-Stack | `main.py` modified 4 times across specs (merge conflicts) | All routers mounted as stubs in Sprint 1 |
| B1 | Backend | BacktestEngine has no DB integration test in Sprint 2 | Added DB integration test with factory-boy fixtures |
| T1 | DevOps | Migration 024 schema change risk | Immutability note added, reference spec rule |
| T2 | DevOps | 9 seed scripts refactored in one task (async bug risk) | Split into 3 batches with tests between |
| S1 | Spec Audit | Experimental model not excluded from convergence alignment | Added model status check in convergence snapshot task |
| S2 | Spec Audit | Sentiment decay formula not explicitly tested | Test with hand-calculated expected values required |

### Important Fixes Applied

| # | Persona | Finding | Fix Applied |
|---|---------|---------|-------------|
| P3 | PM | No acceptance criteria per sprint | "Done When" column added to sprint overview |
| U2 | UI/UX | No accessibility testing | a11y requirements added to Sprint 12 components |
| U3 | UI/UX | Monte Carlo chart sizing in jsdom | Noted as Playwright-only test (Sprint 13) |
| F3 | Full-Stack | api.ts and types modified in 5 sprints | All TS types and API stubs defined in Sprint 1 |
| B2 | Backend | CacheInvalidator created but not wired into existing tasks | Wiring task added to Sprint 3 (modify existing tasks) |
| B3 | Backend | Prophet regressor breaks if Spec B not complete | Feature flag: skip sentiment if NEWS_SCORING_MODEL empty |
| B4 | Backend | No factory-boy factories for new models | Factories added in Sprint 1 Task 1.8 |
| T3 | DevOps | No branching strategy | One branch per spec, all from develop |
| T4 | DevOps | No CI impact assessment | Path filter notes added |
| S3 | Spec Audit | BL excess return subtraction not explicitly tested | Explicit test required in Sprint 10 |
| S4 | Spec Audit | Threshold failure mode not tested | Test case defined for Sprint 5 |

## Expert Review Checklist

After all sprints complete, run this review:

### Full-Stack Engineer
- [ ] All N+1 queries resolved (bulk convergence, batch sentiment)
- [ ] TanStack Query keys namespaced correctly
- [ ] Monte Carlo chart renders with correct data shape
- [ ] Mobile responsive: traffic lights collapse on < 640px
- [ ] All new hooks follow existing patterns

### Middleware / Integration Engineer
- [ ] CacheInvalidator injected at all data-write sites
- [ ] All Celery task return values are JSON-serializable
- [ ] News scoring chained after ingest (not separate schedule)
- [ ] OpenAI provider registered in LLM Factory
- [ ] All seed tasks use `bind=True`
- [ ] Pipeline run tracking in Redis works correctly

### QA / Test Engineer
- [ ] Divergence hit rate query test passes
- [ ] Sentiment weighted aggregation formula test passes
- [ ] BL excess return subtraction test passes
- [ ] Cache invalidation negative test (no over-invalidation) passes
- [ ] Slow integration test validates pipeline end-to-end
- [ ] MSW handlers added for all new endpoints
- [ ] All tests follow tier architecture (T1-T4)

### Stock Domain Expert
- [ ] RSI thresholds documented and consistent
- [ ] Convergence labels use revised thresholds (4+ for strong)
- [ ] BL risk_aversion = 3.07 (retail-appropriate)
- [ ] CI containment target ~80% documented
- [ ] Sector sentiment is sector-specific (not global macro)
- [ ] Excess returns calculated correctly (subtract risk-free)

### Staff Architect
- [ ] Migration 024 applied and immutable
- [ ] actual_return backfill working in convergence task
- [ ] Pipeline group run tracking in Redis
- [ ] Sentiment quality_flag column functional
- [ ] CacheInvalidator consistent across all trigger sources
- [ ] No circular imports across new service modules
