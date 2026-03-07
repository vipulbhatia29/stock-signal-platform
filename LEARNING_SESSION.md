# Learning Sessions

Track what was learned about codebase architecture and software development principles.

---

## Session 1 — Understanding the Foundation (2026-03-07)

**Goal:** Walk through every file built in Sessions 1-2, understand what it does, why it exists, and what software principles it teaches.

**Status:** Completed Sessions 1 and 2 codebase walkthrough. Tests not yet reviewed.

---

### What We Covered

#### 1. config.py — Configuration Management
- **Principle:** Separate configuration from code (12-Factor App)
- **Concepts learned:**
  - `BaseSettings` (Pydantic) loads values from `.env` files and environment variables
  - Class inheritance — `Settings(BaseSettings)` gets all parent abilities
  - Type-annotated class variables with defaults (`DATABASE_URL: str = "..."`)
  - `@property` decorator — a method that looks like a variable, used to transform data (string → list) while hiding complexity from the caller

#### 2. database.py — Database Connection
- **Principle:** Separation of Concerns — connection logic in one place
- **Concepts learned:**
  - **Engine** — the low-level connection to PostgreSQL (the "phone line")
  - **Connection pooling** — keep connections pre-opened for performance (`pool_size=5`)
  - **Session** — a higher-level "conversation" with the database
  - **Session factory** — a template that creates new sessions on demand
  - **`async`/`await`** — lets Python handle many requests concurrently without blocking
  - **`yield`** — pauses a function, hands out a value, then cleans up after
  - **Dependency injection** — `Depends(get_async_session)` gives endpoints a ready-to-use session

#### 3. Models — Database Table Definitions (ORM Pattern)
- **Principle:** ORM maps Python classes to database tables — write Python, SQLAlchemy writes SQL
- **Mental model:** Class = table, attribute = column, instance = row, relationship = JOIN

##### base.py — Reusable Building Blocks
- `Base` — root parent for all models, SQLAlchemy discovers tables through it
- `TimestampMixin` — adds `created_at`/`updated_at` to any model (DRY principle)
- `UUIDPrimaryKeyMixin` — UUID primary keys (not guessable like sequential integers)
- **Mixin** — a class that adds specific features to other classes

##### models/user.py — Entity Model with Relationships
- **Multiple inheritance** — `User(UUIDPrimaryKeyMixin, TimestampMixin, Base)` gets 3 columns for free
- **Column constraints** — `unique=True`, `nullable=False`, `index=True` (database-enforced rules)
- **Enum** — `UserRole(str, enum.Enum)` restricts values to ADMIN/USER
- **Relationships:**
  - One-to-One: User ↔ UserPreference (`uselist=False`)
  - One-to-Many: User ↔ Watchlist items (`list[]`)
  - `back_populates` — bidirectional link (both sides stay in sync)
  - `cascade="all, delete-orphan"` — delete children when parent is deleted

##### models/stock.py — Many-to-Many via Join Table
- **Watchlist** as a join table with two foreign keys (user_id, ticker)
- **Many-to-Many:** one user watches many stocks, one stock watched by many users
- **One-directional relationships** — only define if your code actually uses the link
- **`TYPE_CHECKING`** — solves circular imports (import only during type checking, not runtime)
- **ForeignKey string format** — `"tablename.columnname"` references database tables, not Python classes

##### models/price.py — Time-Series Data
- **Hypertable** — TimescaleDB partitions data by time for fast range queries
- **Composite primary key** — `(time, ticker)` uniquely identifies each row
- **No UUID, no timestamps** — time-series rows use `time` as identity, are append-only
- **`Numeric(12, 4)`** vs `Float` — exact precision for financial data
- **`adj_close`** — adjusted close accounts for stock splits and dividends

##### models/signal.py & recommendation.py — Computed Results
- **Three-layer data pipeline:** Prices (raw) → Signals (analysis) → Recommendations (decisions)
- **Nullable signals** — each indicator computed independently; partial results stored
- **JSONB columns** — flexible JSON storage for data whose structure may evolve
- **User-specific recommendations** — signals are universal, recommendations are per-user
- **Operational flags** — `is_actionable`, `acknowledged` for UX features
- **`price_at_recommendation`** — snapshot price for later accuracy evaluation

#### 4. dependencies.py — Authentication & Security
- **Password hashing** — one-way transformation (bcrypt), never store plain text
  - `hash_password()` at registration, `verify_password()` at login
- **JWT tokens** — signed strings proving identity, sent with every request
  - Three parts: header, payload, signature (signed with secret key)
  - Access token (60 min) for API calls, refresh token (7 days) to get new access tokens
  - `decode_token()` verifies signature + expiry + type
- **Dependency injection chaining** — `oauth2_scheme → get_async_session → get_current_user`
  - Endpoints just write `Depends(get_current_user)` and get a `User` object

#### 5. schemas/auth.py — API Contract (Boundary Validation)
- **Models vs Schemas** — Models talk to the database, Schemas talk to the frontend
- **Security gate** — schemas filter out internal fields (e.g., `hashed_password` never exposed)
- **Pydantic** — "here's what the data should look like" → it makes sure it does
  - Automatic validation: `EmailStr`, `Field(min_length=8)`
  - Type coercion: receives string "25", converts to int 25
  - `model_config = {"from_attributes": True}` — read directly from SQLAlchemy objects
- **Naming convention:** `{Action}Request` (data in) and `{Action}Response` (data out)

#### 6. routers/auth.py — HTTP Endpoints
- **`@router.post("/register")`** — decorator maps HTTP method + URL to a function
  - FastAPI reads function signature to auto-parse body and inject dependencies
  - `response_model` filters output through a schema (security gate)
- **`flush()` vs `commit()`** — flush sends to DB (reversible), commit finalizes (permanent)
- **Transactions** — all-or-nothing: if step 4 fails, step 3 is rolled back
- **Security:** "Invalid email or password" (same message for both — don't reveal which emails exist)

#### 7. main.py — Application Entry Point
- **`app = FastAPI(...)`** — the central object everything attaches to
- **Rate limiting** (slowapi + Redis) — prevents abuse (60 requests/minute per IP)
- **CORS middleware** — allows frontend (port 3000) to call API (port 8181)
  - Middleware = code that runs on every request, like a security checkpoint
- **Health check** — `/health` returns `{"status": "ok"}` for monitoring
- **Router mounting** — `app.include_router(auth.router, prefix="/api/v1/auth")`
  - Prefix prepended to all routes: `/register` becomes `/api/v1/auth/register`
- **API versioning** — `/api/v1/` allows future `/api/v2/` without breaking existing clients

#### 8. tools/market_data.py — Data Pipeline
- **Pipeline:** Yahoo Finance API → pandas DataFrame → PostgreSQL
- **`asyncio.to_thread()`** — runs blocking (sync) code in a background thread so async server stays responsive
- **`_` prefix** — private function convention (internal use only)
- **Upsert** (`ON CONFLICT DO NOTHING`) — idempotent writes, safe to run multiple times
- **Chunking** — batch large inserts (500 rows at a time) to avoid timeouts
- **"Get or create" pattern** — `ensure_stock_exists()` checks first, creates if needed

#### 9. tools/signals.py — Technical Analysis Engine
- **`@dataclass`** — simple container for passing data around (no DB, no API, just holds values)
- **Pure functions** — input → output, no side effects (no DB, no API calls)
  - Huge benefit: easy to test with fake data, no infrastructure needed
- **Orchestrator pattern** — `compute_signals()` coordinates, helper functions do the work
- **Composite score** — 4 indicators × 2.5 points each = 0-10 scale
- **`on_conflict_do_update`** — overwrite existing signals (unlike prices which use `do_nothing`)

#### 10. tools/recommendations.py — Decision Engine
- **Pipeline pattern** — one tool's output feeds into the next tool's input
- **Conservative defaults** — when in doubt, AVOID with LOW confidence
- **Reasoning as JSONB** — store WHY a decision was made, not just WHAT
- **Interpretation helpers** — turn technical labels into plain English

#### 11. schemas/stock.py — Nested Response Schemas
- **Nested schemas** — group related fields into sub-objects for clean JSON
- **Two schemas for same data** — `StockResponse` (full) vs `StockSearchResponse` (minimal)
  - Send only what the consumer needs
- **`PricePeriod` enum** — restricts inputs to valid values, auto-rejects invalid ones
- **`is_stale` flag** — UX detail for frontend to warn about old data

#### 12. routers/stocks.py — Stock API Endpoints
- **Path vs Query parameters** — path identifies a resource, query filters/modifies
- **Flat DB → Nested response** — router translates between database shape and API shape
- **SQL JOIN** — combine two tables in one query (Watchlist + Stock)
- **DRY helper** — `_require_stock()` extracted because 3 endpoints need the same check
- **REST conventions** — 200 OK, 201 Created, 204 No Content, 404 Not Found, 409 Conflict
- **Dynamic query building** — add `.where()` clauses conditionally based on user filters

---

### Key Software Principles Learned

| Principle | Where We Saw It |
|-----------|----------------|
| Separation of Concerns | Each file has one job (config, DB, auth, signals, etc.) |
| Configuration Management | Settings in `.env`, not hardcoded in code |
| ORM (Object-Relational Mapping) | Python classes map to database tables |
| Dependency Injection | `Depends()` provides sessions, auth, etc. automatically |
| Boundary Validation | Pydantic schemas validate at system edges |
| DRY (Don't Repeat Yourself) | Mixins, helper functions, shared dependencies |
| Pure Functions | Signal computations — easy to test, no side effects |
| Idempotent Operations | Upserts — safe to run multiple times |
| Pipeline Pattern | Prices → Signals → Recommendations |
| Conservative Defaults | Fail safely with financial decisions |

### 4-Layer Architecture Pattern

Every feature follows:
```
Model → Tool/Service → Schema → Router
(DB table)  (business logic)  (API shape)  (HTTP endpoint)
```

---

### Next Learning Session

- [ ] Review test files to understand how everything is verified:
  - `tests/conftest.py` — shared fixtures, factories, test database setup
  - `tests/unit/test_signals.py` — 31 tests for signal computations
  - `tests/unit/test_recommendations.py` — 23 tests for decision engine
  - `tests/api/test_stocks.py` — 27 API endpoint tests
- [ ] Understand testing principles: fixtures, factories, mocking, test categories
- [ ] After that: ready to follow along with new development (seed scripts, Phase 2 dashboard)
