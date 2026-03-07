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
