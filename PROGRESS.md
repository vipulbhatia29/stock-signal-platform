# Progress Log

Track what was built in each Claude Code session.

---

## Session 1 — Project Scaffolding

**Date:** 2026-03-01
**Branch:** `feat/initial-scaffold`
**What was done:**
- [x] Python project initialized with `uv init`, all Phase 1 dependencies added
- [x] `backend/config.py` — Pydantic Settings loading from `backend/.env`
- [x] `backend/database.py` — Async SQLAlchemy engine + session factory
- [x] `backend/main.py` — FastAPI app with CORS, rate limiting (slowapi), health check
- [x] Database models created per `docs/data-architecture.md`:
  - `backend/models/user.py` — User + UserPreference (with UserRole enum)
  - `backend/models/stock.py` — Stock + Watchlist
  - `backend/models/price.py` — StockPrice (TimescaleDB hypertable)
  - `backend/models/signal.py` — SignalSnapshot (TimescaleDB hypertable)
  - `backend/models/recommendation.py` — RecommendationSnapshot (TimescaleDB hypertable)
- [x] Alembic configured for async (env.py reads from Settings)
- [x] Initial migration `001_initial_schema.py` with `create_hypertable()` calls
- [x] Auth system:
  - `backend/dependencies.py` — bcrypt hashing, JWT create/decode, `get_current_user`
  - `backend/routers/auth.py` — POST register, login, refresh
  - `backend/schemas/auth.py` — Pydantic v2 request/response models
- [x] Test foundation:
  - `tests/conftest.py` — testcontainers (real Postgres+TimescaleDB), factory-boy factories (User, UserPreference, Stock), authenticated client fixture
  - `tests/unit/test_health.py` — health check tests
  - `tests/unit/test_dependencies.py` — password hashing + JWT round-trip tests
  - `tests/api/test_auth.py` — register, login, refresh endpoint tests (12 tests)
- [x] All 23 tests pass (`uv run pytest tests/ -v`)
- [x] Docker Compose starts on ports 5433/6380 (to avoid conflicts with other projects)
- [x] `uv run alembic upgrade head` creates all tables + hypertables
- [x] `uv run uvicorn backend.main:app --port 8181` starts server, health check returns OK

**Key decisions:**
- Pinned `bcrypt==4.2.1` (passlib incompatible with bcrypt 5.x)
- Docker ports changed to 5433 (Postgres) and 6380 (Redis) to avoid conflicts
- Test approach: per-test engine + truncate tables (avoids asyncpg event loop issues)

**Next:** Signal engine — `backend/tools/market_data.py`, `backend/tools/signals.py`, `backend/tools/recommendations.py` + stock router endpoints + tests (Phase 1 continued)

---

## Session 2 — Signal Engine + Stock API

**Date:** 2026-03-01
**Branch:** `feat/initial-scaffold`
**What was done:**
- [x] `backend/tools/market_data.py` — yfinance OHLCV fetcher:
  - Async wrapper around yfinance (runs in thread pool to avoid blocking)
  - Batch upsert into TimescaleDB (ON CONFLICT DO NOTHING for idempotency)
  - `ensure_stock_exists()` — auto-creates Stock records from yfinance metadata
  - `get_latest_price()` — fetch most recent adj_close from database
- [x] `backend/tools/signals.py` — Technical signal computation engine:
  - RSI(14) with Wilder's smoothed method → OVERSOLD/NEUTRAL/OVERBOUGHT labels
  - MACD(12,26,9) with EMA-based computation → BULLISH/BEARISH labels
  - SMA 50/200 crossover detection → GOLDEN_CROSS/DEATH_CROSS/ABOVE_200/BELOW_200
  - Bollinger Bands(20,2) → UPPER/MIDDLE/LOWER position
  - Annualized return, volatility, Sharpe ratio calculation
  - Composite score (0-10) combining all indicators (4 × 2.5 points each)
  - `store_signal_snapshot()` — upsert into signal_snapshots hypertable
- [x] `backend/tools/recommendations.py` — Recommendation decision engine:
  - Score ≥8 → BUY, 5-7 → WATCH, <5 → AVOID (Phase 1 rules)
  - Confidence levels (HIGH/MEDIUM/LOW) based on score strength
  - Detailed JSONB reasoning with per-signal interpretations
  - `store_recommendation()` — upsert into recommendation_snapshots
- [x] `backend/schemas/stock.py` — Pydantic v2 schemas:
  - StockResponse, StockSearchResponse, PricePointResponse, PricePeriod enum
  - Nested signal schemas: RSIResponse, MACDResponse, SMAResponse, BollingerResponse
  - SignalResponse (full nested structure), RecommendationResponse
  - WatchlistAddRequest, WatchlistItemResponse
- [x] `backend/routers/stocks.py` — REST API endpoints:
  - `GET /api/v1/stocks/search?q=...` — case-insensitive stock search
  - `GET /api/v1/stocks/{ticker}/prices?period=1y` — historical OHLCV data
  - `GET /api/v1/stocks/{ticker}/signals` — latest technical signals (with staleness flag)
  - `GET /api/v1/stocks/watchlist` — user's watchlist (with stock details via JOIN)
  - `POST /api/v1/stocks/watchlist` — add ticker (with 100-ticker limit + duplicate check)
  - `DELETE /api/v1/stocks/watchlist/{ticker}` — remove from watchlist
  - `GET /api/v1/stocks/recommendations` — recent recommendations (24h window, filterable)
- [x] Router mounted in `backend/main.py` at `/api/v1/stocks`
- [x] Test factories added to `tests/conftest.py`:
  - StockPriceFactory, SignalSnapshotFactory, RecommendationSnapshotFactory, WatchlistFactory
- [x] `tests/unit/test_signals.py` — 31 unit tests:
  - RSI: uptrend, downtrend, extreme drop/rally, insufficient data, value range
  - MACD: uptrend bullish, accelerating downtrend bearish, insufficient data
  - SMA: uptrend above 200, downtrend below 200, golden cross detection, insufficient data
  - Bollinger: middle, spike to upper, crash to lower, insufficient data
  - Risk/Return: positive/negative return, volatility, Sharpe positive/negative, insufficient data
  - Composite: max score, min score, mixed mid-range, all-None, within 0-10 range
  - End-to-end: all fields populated, insufficient data, Adj Close preference
- [x] `tests/unit/test_recommendations.py` — 23 unit tests:
  - BUY: score 9+ HIGH confidence, score 8 MEDIUM confidence, boundary tests
  - WATCH: score 7, score 5, MEDIUM/LOW confidence levels
  - AVOID: score 4, score 0 HIGH confidence, score 3 MEDIUM confidence
  - Edge cases: None score, price preserved, ticker preserved, boundary values
  - Reasoning: signal breakdown, returns, score breakdown, RSI interpretation
- [x] `tests/api/test_stocks.py` — 27 API endpoint tests:
  - Search: auth required, by ticker, by name, empty result, missing query
  - Prices: auth required, 404 not found, returns data
  - Signals: auth required, stock not found, no snapshot, full response, stale flag
  - Watchlist: auth, add, unknown ticker, duplicate, get, remove, remove not found, empty
  - Recommendations: auth, empty, returns data, filter by action, filter no match, stale excluded
- [x] All **104 tests pass** (`uv run pytest tests/ -v`)

**Key decisions:**
- All code includes inline educational comments explaining technical analysis concepts
- Signal functions are pure (no DB dependency) for easy unit testing; DB persistence is separate
- MACD test required accelerating downtrend (not constant) because EMA convergence behavior
- Sharpe tests require non-zero noise (smooth series has zero volatility → undefined Sharpe)
- Watchlist endpoints nested under `/api/v1/stocks/watchlist` (not separate router)

**Test count:** 23 (Session 1) → 104 (Session 2) = +81 new tests

**Next:** Seed scripts (`scripts/sync_sp500.py`, `scripts/seed_prices.py`) to populate real stock data, then verify end-to-end: fetch AAPL prices → compute signals → get recommendation via API. After that, Phase 2 (Dashboard UI) or remaining Phase 1 items (Celery tasks for nightly computation).

---

## Session 3 — Seed Scripts + End-to-End Verification + Phase 1 Complete

**Date:** 2026-03-07
**Branch:** `feat/initial-scaffold`
**What was done:**
- [x] `scripts/sync_sp500.py` — S&P 500 universe sync:
  - Scrapes current S&P 500 constituents from Wikipedia via `pandas.read_html()`
  - Upserts into `stocks` table with sector/industry metadata
  - Marks removed stocks as `is_in_universe=False`
  - Supports `--dry-run` flag for preview
  - Handles ticker format conversion (BRK.B → BRK-B for yfinance compatibility)
- [x] `scripts/seed_prices.py` — Price backfill + signal computation:
  - Fetches OHLCV data via yfinance for specified tickers or full universe
  - Stores prices in TimescaleDB (idempotent upsert)
  - Computes technical signals and stores snapshots
  - Generates recommendations (computed but not persisted — recommendations are user-scoped)
  - Supports `--tickers`, `--universe`, `--period`, `--dry-run` flags
  - Rate-limited (0.5s between tickers) to avoid yfinance throttling
  - Default tickers: AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, JPM, V, UNH
- [x] Added `lxml` dependency for `pandas.read_html()`
- [x] Bug fix: `UserRole` enum in `backend/models/user.py` — SQLAlchemy was sending
  uppercase enum names (`"USER"`) instead of lowercase values (`"user"`) to Postgres.
  Fixed with `values_callable=lambda e: [m.value for m in e]`
- [x] End-to-end verification with real data:
  - AAPL: 501 price rows, composite score 4.0, AVOID (MEDIUM confidence)
  - MSFT: 501 price rows, composite score 4.0, AVOID (MEDIUM confidence)
  - API verified: register (201), login (200), signals (200), prices (200), search (200)
  - Idempotent upsert confirmed (re-run skipped 501 duplicates per ticker)
- [x] `tests/unit/test_sync_sp500.py` — 5 tests:
  - DataFrame structure, whitespace stripping, dot-to-dash conversion, exchange is None, all tickers present
- [x] `tests/unit/test_seed_prices.py` — 5 tests:
  - Successful seed, error handling, signal computation, recommendation generation, default tickers
- [x] All **114 tests pass** (`uv run pytest tests/ -v`)

**Key decisions:**
- Recommendations are NOT persisted by seed script (they require `user_id` FK — generated per-user via API)
- Seed script computes recommendations in-memory for logging/verification only
- `scripts/` is a proper Python package (has `__init__.py`) for `python -m scripts.xxx` usage

**Test count:** 104 (Session 2) → 114 (Session 3) = +10 new tests

**Phase 1 Status:** COMPLETE — all deliverables from project-plan.md Phase 1 are done.

**Next:** Phase 2 — Dashboard + Screener UI (Next.js, login page, stock cards with sentiment badges, screener table with filters, stock detail page with charts). See `project-plan.md` Phase 2 for full deliverable list.

---

## Session 4 — Phase 2 Requirements & Documentation Enhancement

**Date:** 2026-03-07
**Branch:** `feat/initial-scaffold`
**What was done:**
- [x] Created `docs/phase2-requirements.md` — comprehensive Phase 2 requirements spec:
  - 5 backend pre-requisites (httpOnly cookie auth, index membership, on-demand ingestion,
    bulk signals endpoint, signal history endpoint)
  - 7 frontend page specs with wireframe layouts (login, register, dashboard, screener,
    stock detail, nav, auth guard)
  - Acceptance criteria (functional, non-functional, testing)
  - Implementation order (backend first, then frontend)
- [x] Enhanced `CLAUDE.md` with 9 new sections:
  - Session Start protocol, Anti-Patterns tables (Python/TS/Architecture),
    Error Handling & Logging standards, Security section with critical files list,
    Troubleshooting table (consolidated gotchas), Mock & Patch Guidelines,
    Documentation Triggers table, TypeScript/Frontend rules, Dependency management rules
- [x] Fixed `.claude/rules/python-backend.md` — changed "structlog" to `logging.getLogger(__name__)`
  (matches actual codebase; structlog is in deps but never imported)
- [x] Updated `project-plan.md` — Phase 2 now includes backend pre-requisites
  (cookie auth, index model, on-demand ingestion, bulk signals, signal history)
- [x] Updated `docs/FSD.md` — added FR-1.5 (httpOnly cookies), FR-2.4 (index management),
  FR-2.5 (on-demand ingestion), FR-7.5 (bulk signals), FR-7.6 (signal history);
  updated Feature × Phase Matrix; fixed structlog references
- [x] Updated `docs/TDD.md` — rewrote JWT flow for cookie auth (Section 9.1),
  added Sections 3.7-3.10 (index, ingestion, bulk signals, signal history endpoints);
  fixed structlog references
- [x] Updated `docs/data-architecture.md` — added StockIndex + StockIndexMembership tables
  to Section 3.1, updated Phase Mapping (Phase 2 row), updated query patterns and
  data seeding strategy

**Key decisions:**
- httpOnly cookies over localStorage (security — XSS protection)
- Stock indexes as separate table with membership (not boolean flags) — supports
  multi-index membership (AAPL in S&P 500 + NASDAQ-100 + Dow 30)
- On-demand ingestion with delta fetch (not full re-fetch for existing tickers)
- Server-side pagination for screener (not client-side — 500 stocks too large)
- stdlib `logging` over structlog for now (structlog migration deferred to production)
- Dark/light theme toggle; mobile layouts deferred

**Test count:** 114 (unchanged — no code changes, only documentation)

**Next:** Begin Phase 2 implementation. Start with backend pre-requisites (cookie auth →
index model + migration → ingestion endpoint → bulk signals → signal history), then
scaffold Next.js frontend and build pages. See `docs/phase2-requirements.md` Section 6
for full implementation order.

---

## Session 5 — Phase 2 Backend Pre-Requisites

**Date:** 2026-03-07
**Branch:** `feat/initial-scaffold`
**What was done:**
- [x] httpOnly cookie authentication (dual-mode: Authorization header + cookie):
  - `backend/dependencies.py` — `_extract_token()` checks header first, then cookie
  - `backend/routers/auth.py` — login/refresh set cookies via `_set_auth_cookies()`
  - `POST /logout` endpoint added — clears auth cookies
  - `backend/config.py` — added `COOKIE_SECURE` setting
- [x] `backend/models/index.py` — StockIndex + StockIndexMembership models:
  - StockIndex: name, slug (indexed), description
  - StockIndexMembership: ticker FK + index_id FK with unique constraint
- [x] `backend/routers/indexes.py` — Index API endpoints:
  - `GET /indexes` — list all indexes with stock counts (LEFT JOIN + COUNT)
  - `GET /indexes/{slug}/stocks` — paginated stocks with latest price + signal via window functions
- [x] `backend/schemas/index.py` — IndexResponse, IndexStockItem, IndexStocksResponse
- [x] `backend/routers/stocks.py` — 3 new endpoints:
  - `POST /{ticker}/ingest` — on-demand ingestion with ticker validation
  - `GET /signals/bulk` — screener with filters (index, RSI, MACD, sector, score range), sorting, pagination
  - `GET /{ticker}/signals/history` — chronological signal snapshots with days + limit params
- [x] `backend/schemas/stock.py` — added IngestResponse, BulkSignalItem, BulkSignalsResponse, SignalHistoryItem
- [x] `backend/tools/market_data.py` — delta fetch functions:
  - `fetch_prices_delta()` — queries MAX(time), fetches from that date forward
  - `update_last_fetched_at()` — updates Stock.last_fetched_at after fetch
  - `_download_ticker_range()` — yfinance download with start date
- [x] `scripts/sync_indexes.py` — seed S&P 500, NASDAQ-100, Dow 30 index memberships from Wikipedia
- [x] Indexes router mounted in `backend/main.py` at `/api/v1/indexes`
- [x] Test factories: StockIndexFactory, StockIndexMembershipFactory added to conftest.py
- [x] `tests/api/test_auth.py` — expanded from 12 to 20 tests (cookie auth, logout)
- [x] `tests/api/test_indexes.py` — 8 tests for index endpoints
- [x] `tests/api/test_ingest.py` — 4 tests for ingestion endpoint
- [x] `tests/api/test_bulk_signals.py` — 7 tests for screener endpoint
- [x] `tests/api/test_signal_history.py` — 6 tests for signal history
- [x] All **147 tests pass** (`uv run pytest tests/ -v`)

**Key decisions:**
- Dual-mode auth preserves backward compatibility (header takes precedence over cookie)
- Window functions (row_number OVER PARTITION BY) for efficient "latest per ticker" queries
- Lazy imports in ingest endpoint to avoid circular dependency between routers and tools
- Ticker validation via regex pattern `^[A-Za-z0-9.\-]{1,10}$`

**Test count:** 114 (Session 4) → 147 (Session 5) = +33 new tests

**Pending:**
- Alembic migration `002_stock_indexes.py` for new tables (needs Docker running)

**Next:** Phase 2 frontend — Next.js project setup, login/register pages, dashboard,
screener, stock detail page. See `docs/workflow_phase2.md` Tasks 2.1-2.7.
