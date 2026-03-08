# Technical Design Document (TDD)

## Stock Signal Platform

**Version:** 1.0
**Date:** March 2026
**Status:** Draft
**Prerequisite reading:** docs/PRD.md, docs/FSD.md, docs/data-architecture.md

---

## 1. Purpose

This document defines HOW the system is built. It covers component architecture,
API contracts, service layer patterns, integration details, and deployment
topology. The FSD defines WHAT the system does; this document defines HOW it
does it.

---

## 2. System Architecture

### 2.1 High-Level Overview

```
┌──────────────────────────────────────────────────────────────┐
│                        CLIENTS                                │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ Next.js SPA │  │ Telegram Bot │  │ MCP Clients (Ph 6) │  │
│  │ (port 3000) │  │              │  │                    │  │
│  └──────┬──────┘  └──────┬───────┘  └────────┬───────────┘  │
└─────────┼────────────────┼────────────────────┼──────────────┘
          │ HTTP/SSE       │ Webhook            │ MCP/stdio
          ▼                ▼                    ▼
┌──────────────────────────────────────────────────────────────┐
│                     FASTAPI APPLICATION                       │
│                     (port 8181)                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                    Middleware Layer                      │ │
│  │  CORS │ Rate Limit (slowapi) │ JWT Auth │ Request ID   │ │
│  └─────────────────────────────────────────────────────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────┐  │
│  │ /auth    │ │ /stocks  │ │ /portfolio│ │ /chat        │  │
│  │ router   │ │ router   │ │ router    │ │ router (SSE) │  │
│  └────┬─────┘ └────┬─────┘ └─────┬─────┘ └──────┬───────┘  │
│       │            │              │               │          │
│  ┌────▼────────────▼──────────────▼───────────────▼────────┐ │
│  │                   SERVICE LAYER                          │ │
│  │  auth_service │ signal_service │ portfolio_service │ ... │ │
│  └────┬────────────┬──────────────┬───────────────┬────────┘ │
│       │            │              │               │          │
│  ┌────▼────────────▼──────────────▼───────────────▼────────┐ │
│  │                   TOOL LAYER                             │ │
│  │  market_data │ signals │ recommendations │ fundamentals  │ │
│  │  portfolio │ forecasting │ screener │ search             │ │
│  └────┬────────────┬──────────────┬───────────────┬────────┘ │
│       │            │              │               │          │
│  ┌────▼────────────▼──────────────▼───────────────▼────────┐ │
│  │                   AGENT LAYER                            │ │
│  │  AgentRegistry │ ToolRegistry │ Agentic Loop │ Stream   │ │
│  │  GeneralAgent │ StockAgent                              │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────┬───────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ PostgreSQL   │  │ Redis 7      │  │ External     │
│ + TimescaleDB│  │              │  │ APIs         │
│ (port 5432)  │  │ (port 6379)  │  │              │
│              │  │ - Cache      │  │ - yfinance   │
│ - OLTP data  │  │ - Celery     │  │ - FRED       │
│ - Time-series│  │   broker     │  │ - Groq       │
│ - Hypertables│  │ - Rate limit │  │ - Anthropic  │
│              │  │   counters   │  │ - SerpAPI    │
└──────────────┘  └──────────────┘  └──────────────┘
                           │
                  ┌────────▼────────┐
                  │ Celery Worker   │
                  │ + Beat          │
                  │                 │
                  │ - Nightly data  │
                  │ - Signal compute│
                  │ - Recommendations│
                  │ - Forecast train│
                  │ - Alert checks  │
                  │ - Portfolio snap │
                  └─────────────────┘
```

### 2.2 Layer Responsibilities

| Layer | Responsibility | Example |
|-------|---------------|---------|
| **Routers** | HTTP handling, request validation, response serialization | Parse JWT, validate Pydantic schema, call service, return response |
| **Services** | Business logic orchestration, transaction management | Combine signal computation + recommendation generation in one flow |
| **Tools** | Domain logic, external API integration, data access | Compute RSI from price data, call yfinance, query TimescaleDB |
| **Agents** | LLM orchestration, tool selection, response synthesis | Interpret "Analyse AAPL", call signal + fundamental + forecast tools, synthesize |
| **Tasks** | Background job execution, scheduling | Nightly: fetch prices → compute signals → generate recommendations → check alerts |

### 2.3 Key Design Rules

1. **Routers never contain business logic.** They validate, call a service, and return.
2. **Services own transactions.** A service method = one database transaction boundary.
3. **Tools are stateless and independently testable.** Each tool is a pure function
   (data in → result out) that can be called by services, agents, or Celery tasks.
4. **Agents never access the database directly.** They call tools through ToolRegistry.
5. **No circular dependencies.** Direction is always: Router → Service → Tool.
   Agents sit alongside services, calling the same tools.

---

## 3. API Design

### 3.1 Base URL & Versioning

- Base: `/api/v1/`
- Versioning: URL-based. If breaking changes needed, create `/api/v2/` routers.
  Old version stays active for 3 months (migration period).

### 3.2 Authentication Endpoints

```
POST /api/v1/auth/register
  Request:  { email: string, password: string }
  Response: { id: uuid, email: string, created_at: datetime }
  Errors:   409 (email exists), 422 (validation)

POST /api/v1/auth/login
  Request:  { email: string, password: string }
  Response: { access_token: string, refresh_token: string,
              token_type: "bearer", expires_in: int }
  Errors:   401 (bad credentials)

POST /api/v1/auth/refresh
  Request:  { refresh_token: string }
  Response: { access_token: string, refresh_token: string,
              token_type: "bearer", expires_in: int }
  Errors:   401 (invalid/expired refresh token)
```

### 3.3 Stock & Signal Endpoints

```
GET /api/v1/stocks/search?q={query}
  Response: [{ ticker, name, exchange, sector }]
  Auth:     Required

GET /api/v1/stocks/{ticker}/signals
  Response: { ticker, computed_at, rsi: { value, signal },
              macd: { value, histogram, signal }, sma: { sma_50, sma_200,
              signal }, bollinger: { upper, lower, position },
              returns: { annual_return, volatility, sharpe },
              composite_score, is_stale }
  Errors:   404 (ticker not found)

GET /api/v1/stocks/{ticker}/prices?period={1m|3m|6m|1y|5y|10y}
  Response: [{ time, open, high, low, close, volume }]
  Errors:   404 (ticker not found)

GET /api/v1/stocks/{ticker}/signals/history?period={1m|3m|6m|1y}
  Response: [{ computed_at, composite_score, rsi_value, macd_value }]

POST /api/v1/watchlist
  Request:  { ticker: string }
  Response: { id, ticker, added_at }
  Errors:   404 (ticker unknown), 409 (already in watchlist)

DELETE /api/v1/watchlist/{ticker}
  Response: 204

GET /api/v1/watchlist
  Response: [{ ticker, name, sector, latest_price, composite_score,
               signal_summary, last_updated }]
```

### 3.4 Recommendation Endpoints

```
GET /api/v1/recommendations?action={BUY|SELL|HOLD}&confidence={HIGH|MEDIUM|LOW}
  Response: [{ ticker, action, confidence, composite_score,
               suggested_amount_usd, portfolio_weight_pct,
               target_weight_pct, reasoning: { signals, factors },
               generated_at, is_actionable }]

POST /api/v1/recommendations/{id}/acknowledge
  Response: 204
```

### 3.5 Portfolio Endpoints (Phase 3)

```
POST /api/v1/portfolio/transactions
  Request:  { ticker, action: BUY|SELL, quantity, price_per_share,
              fees, transacted_at, notes? }
  Response: { id, ticker, action, quantity, price_per_share, ... }
  Errors:   400 (SELL > holdings), 404 (ticker)

GET /api/v1/portfolio/positions
  Response: [{ ticker, quantity, avg_cost, current_price,
               unrealized_pnl, unrealized_pnl_pct, allocation_pct,
               target_allocation_pct, sector }]

GET /api/v1/portfolio/allocation
  Response: { by_stock: [{ ticker, pct }],
              by_sector: [{ sector, pct }],
              cash_pct, total_value }

GET /api/v1/portfolio/history?period={1m|3m|6m|1y|all}
  Response: [{ date, total_value, day_pnl, total_pnl_pct }]

GET /api/v1/portfolio/dividends?period={1y|all}
  Response: { total_income, trailing_12m_yield,
              payments: [{ ticker, pay_date, amount }] }
```

### 3.6 Chat Endpoint (Phase 4)

```
POST /api/v1/chat/stream
  Request:  { message: string, session_id?: uuid, agent_type: "general"|"stock" }
  Response: SSE stream of NDJSON events:
    { type: "token", content: "..." }
    { type: "tool_start", tool: "signals", input: {...} }
    { type: "tool_result", tool: "signals", output: {...} }
    { type: "done", session_id: uuid, tokens_used: int }
```

### 3.7 Index Endpoints (Phase 2)

```
GET /api/v1/indexes
  Response: [{ id, name, description, stock_count, last_synced_at }]
  Auth:     Required

GET /api/v1/indexes/{index_id}/stocks
  Response: [{ ticker, name, sector, latest_price, composite_score,
               signal_summary, last_updated }]
  Auth:     Required
```

### 3.8 Data Ingestion Endpoint (Phase 2)

```
POST /api/v1/stocks/{ticker}/ingest
  Response: { ticker, name, sector, prices_fetched, signals_computed,
              composite_score }
  Auth:     Required
  Rate:     5 requests/minute (expensive: yfinance + signal computation)
  Behavior: If ticker has no data → full 10Y fetch
            If ticker has data → delta fetch from last_fetched_at
            Always recomputes signals after fetch
  Errors:   404 (invalid ticker on yfinance), 429 (rate limit)
```

### 3.9 Bulk Signals Endpoint (Phase 2)

```
GET /api/v1/stocks/signals/bulk?index_id={uuid}
                               &rsi={OVERSOLD|NEUTRAL|OVERBOUGHT}
                               &macd={BULLISH|BEARISH}
                               &sector={Technology|Healthcare|...}
                               &score_min={0-10}&score_max={0-10}
                               &sort_by={composite_score|sharpe|annual_return}
                               &sort_order={asc|desc}
                               &limit={50}&offset={0}
  Response: { total, items: [{ ticker, name, sector, rsi_value, rsi_signal,
               macd_signal, sma_signal, bollinger_signal, annual_return,
               volatility, sharpe, composite_score, computed_at, is_stale }] }
  Auth:     Required
  Query:    DISTINCT ON (ticker) ORDER BY computed_at DESC
  Perf:     <3 seconds for 500 stocks
```

### 3.10 Signal History Endpoint (Phase 2)

```
GET /api/v1/stocks/{ticker}/signals/history?days={90}&limit={100}
  Response: [{ computed_at, composite_score, rsi_value, rsi_signal,
               macd_value, macd_signal, sma_signal, bollinger_signal }]
  Auth:     Required
  Default:  90 days, max 365 days
```

---

## 4. Service Layer Design

### 4.1 Service Pattern

Every service follows:

```python
class SignalService:
    def __init__(self, db: AsyncSession, redis: Redis):
        self.db = db
        self.redis = redis

    async def get_latest_signals(self, ticker: str) -> SignalResponse:
        """Get latest signals, compute if stale."""
        # 1. Check cache
        cached = await self.redis.get(f"signals:{ticker}")
        if cached:
            return SignalResponse.model_validate_json(cached)

        # 2. Query database
        snapshot = await self._get_latest_snapshot(ticker)
        if snapshot and not snapshot.is_stale:
            response = SignalResponse.from_orm(snapshot)
            await self.redis.set(f"signals:{ticker}", response.model_dump_json(), ex=3600)
            return response

        # 3. Compute fresh if stale or missing
        prices = await market_data_tool.fetch_prices(ticker)
        signals = signal_tool.compute_all(prices)
        await self._store_snapshot(ticker, signals)

        response = SignalResponse.from_signals(signals)
        await self.redis.set(f"signals:{ticker}", response.model_dump_json(), ex=3600)
        return response
```

### 4.2 Dependency Injection

FastAPI `Depends()` chain:

```python
# database.py
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session

# dependencies.py
async def get_redis() -> Redis:
    return Redis.from_url(settings.REDIS_URL)

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_async_session)
) -> User:
    # decode JWT, query user, return
    ...

async def get_signal_service(
    db: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis)
) -> SignalService:
    return SignalService(db, redis)
```

### 4.3 Caching Strategy

| Data | Cache Key | TTL | Invalidation |
|------|-----------|-----|-------------|
| Latest signals | `signals:{ticker}` | 1 hour | On new signal computation |
| Latest price | `price:{ticker}` | 5 minutes | On price fetch |
| Screener results | `screener:{hash_of_filters}` | 30 minutes | On nightly batch |
| Portfolio positions | `positions:{portfolio_id}` | 0 (no cache) | N/A (always fresh) |
| Recommendations | `recs:{user_id}:{date}` | Until next computation | On daily batch |

---

## 5. Agent Architecture

### 5.1 Agent Registry

```python
class AgentRegistry:
    agents: dict[str, BaseAgent] = {
        "general": GeneralAgent,
        "stock": StockAgent,
    }

    def get(self, agent_type: str) -> BaseAgent:
        return self.agents[agent_type](tool_registry=self.tool_registry)
```

### 5.2 Tool Registry

```python
class ToolRegistry:
    """Central registry of all tools available to agents."""
    tools: dict[str, Callable] = {
        "fetch_stock_data": market_data.fetch_prices,
        "compute_signals": signals.compute_all,
        "get_recommendations": recommendations.get_current,
        "get_fundamentals": fundamentals.get_fundamentals,
        "get_portfolio": portfolio.get_positions,
        "screen_stocks": screener.screen,
        "run_forecast": forecasting.forecast,
        "web_search": search.web_search,
    }
```

### 5.3 Agentic Loop

```python
async def agentic_loop(agent: BaseAgent, message: str, max_iterations: int = 15):
    messages = [{"role": "user", "content": message}]

    for i in range(max_iterations):
        # Call LLM (Groq for tool-calling, Claude for synthesis)
        response = await llm_client.chat(messages, tools=agent.tools)

        if response.has_tool_calls:
            for tool_call in response.tool_calls:
                yield {"type": "tool_start", "tool": tool_call.name}
                result = await tool_registry.execute(tool_call)
                yield {"type": "tool_result", "tool": tool_call.name, "output": result}
                messages.append(tool_call_message(tool_call, result))
        else:
            # No more tool calls — this is the final synthesis
            yield {"type": "token", "content": response.content}
            break
```

### 5.4 LLM Client with Fallback

```python
class LLMClient:
    providers = [
        GroqProvider(model="llama-3.3-70b-versatile"),  # Fast, cheap, tool-calling
        AnthropicProvider(model="claude-sonnet-4-20250514"),   # Synthesis quality
        LMStudioProvider(base_url="http://localhost:1234/v1"), # Offline fallback
    ]

    async def chat(self, messages, tools=None):
        for provider in self.providers:
            try:
                return await provider.chat(messages, tools)
            except (APIError, Timeout) as e:
                logger.warning(f"{provider.name} failed: {e}, trying next")
                continue
        raise AllProvidersFailedError()
```

---

## 6. Background Job Design

### 6.1 Celery Configuration

```python
# tasks/__init__.py
app = Celery("stock_signal_platform")
app.config_from_object({
    "broker_url": settings.REDIS_URL,
    "result_backend": settings.REDIS_URL,
    "task_serializer": "json",
    "result_serializer": "json",
    "accept_content": ["json"],
    "timezone": "America/New_York",  # Market timezone
    "beat_schedule": {
        "nightly-refresh": {
            "task": "tasks.refresh_data.refresh_all",
            "schedule": crontab(hour=18, minute=0),  # 6 PM ET (after market close)
        },
        "nightly-signals": {
            "task": "tasks.compute_signals.compute_all",
            "schedule": crontab(hour=18, minute=30),
        },
        "nightly-recommendations": {
            "task": "tasks.generate_recommendations.generate_all",
            "schedule": crontab(hour=19, minute=0),
        },
        "nightly-portfolio-snapshot": {
            "task": "tasks.snapshot_portfolio.snapshot_all",
            "schedule": crontab(hour=19, minute=15),
        },
        "nightly-alerts": {
            "task": "tasks.check_alerts.check_all",
            "schedule": crontab(hour=19, minute=30),
        },
        "nightly-evaluate-forecasts": {
            "task": "tasks.evaluate_forecasts.evaluate",
            "schedule": crontab(hour=20, minute=0),
        },
        "nightly-evaluate-recommendations": {
            "task": "tasks.evaluate_recommendations.evaluate",
            "schedule": crontab(hour=20, minute=15),
        },
        "weekly-forecasts": {
            "task": "tasks.run_forecasts.train_and_forecast",
            "schedule": crontab(hour=21, minute=0, day_of_week=6),  # Saturday
        },
        "morning-briefing": {
            "task": "tasks.notifications.morning_briefing",
            "schedule": crontab(hour=7, minute=0),  # 7 AM ET
        },
    },
})
```

### 6.2 Task Error Handling

```python
@app.task(bind=True, max_retries=3, default_retry_delay=60)
def refresh_ticker(self, ticker: str):
    task_log = TaskLog(task_name="refresh_ticker", ticker=ticker, status="STARTED")
    try:
        data = yfinance.download(ticker, period="5d")
        store_prices(ticker, data)
        task_log.status = "SUCCESS"
    except Exception as e:
        task_log.status = "RETRY" if self.request.retries < 3 else "FAILED"
        task_log.error_message = str(e)
        task_log.retry_count = self.request.retries
        if self.request.retries < 3:
            raise self.retry(exc=e)
    finally:
        save_task_log(task_log)
```

---

## 7. Frontend Architecture

### 7.1 Directory Structure

```
frontend/
├── app/
│   ├── layout.tsx              # Root layout with providers
│   ├── page.tsx                # Redirect to /dashboard
│   ├── login/page.tsx
│   ├── dashboard/page.tsx      # Watchlist + recommendations
│   ├── screener/page.tsx
│   ├── portfolio/page.tsx
│   ├── stocks/[ticker]/page.tsx
│   └── chat/page.tsx
├── components/
│   ├── ui/                     # shadcn/ui primitives
│   ├── StockCard.tsx
│   ├── SignalBadge.tsx
│   ├── RecommendationPanel.tsx
│   ├── PortfolioChart.tsx
│   ├── AllocationPie.tsx
│   ├── ScreenerTable.tsx
│   ├── ChatMessage.tsx
│   └── ChatInput.tsx
├── hooks/
│   ├── useAuth.ts
│   ├── useWatchlist.ts
│   ├── useSignals.ts
│   ├── useRecommendations.ts
│   ├── usePortfolio.ts
│   └── useChat.ts
├── lib/
│   ├── api.ts                  # Centralized fetch + JWT handling
│   ├── auth.ts                 # Token storage + refresh logic
│   └── types.ts                # Shared TypeScript types
└── providers/
    ├── AuthProvider.tsx
    └── QueryProvider.tsx
```

### 7.2 State Management

- **Server state:** TanStack Query (React Query) for all API data
- **Client state:** React useState/useReducer (minimal — most state is server-derived)
- **Auth state:** React Context via AuthProvider
- **No Redux, no Zustand** — complexity not justified for this scale

### 7.3 Data Fetching Pattern

```typescript
// hooks/useRecommendations.ts
export function useRecommendations(filters?: RecommendationFilters) {
  return useQuery({
    queryKey: ['recommendations', filters],
    queryFn: () => api.get('/recommendations', { params: filters }),
    staleTime: 5 * 60 * 1000,      // 5 min
    refetchInterval: 5 * 60 * 1000,  // auto-refresh
  });
}
```

---

## 8. Integration Patterns

### 8.1 yfinance Integration

```python
# tools/market_data.py
async def fetch_prices(ticker: str, period: str = "10y") -> pd.DataFrame:
    """Fetch OHLCV data from yfinance, store to TimescaleDB."""
    # yfinance is synchronous — run in thread pool
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(
        None, lambda: yf.download(ticker, period=period, auto_adjust=False)
    )
    if data.empty:
        raise TickerNotFoundError(f"No data for {ticker}")

    # Upsert to StockPrice (ON CONFLICT DO NOTHING for idempotency)
    await bulk_upsert_prices(ticker, data)
    return data
```

**Rate limit handling:** yfinance is unofficial and rate-limited. We enforce:
- 2-second delay between tickers in batch operations
- Exponential backoff on HTTP 429 responses
- Maximum 5 concurrent yfinance requests

### 8.2 FRED API Integration (Phase 5)

```python
# tools/macro.py
FRED_SERIES = {
    "yield_curve_10y2y": "T10Y2Y",
    "vix": "VIXCLS",
    "unemployment_claims": "ICSA",
    "fed_funds_rate": "FEDFUNDS",
}

async def fetch_macro_indicators() -> dict:
    for name, series_id in FRED_SERIES.items():
        data = fred_client.get_series(series_id, limit=1)
        store_macro_snapshot(name, data)
```

### 8.3 Telegram Integration (Phase 5)

```python
# services/notification.py
async def send_telegram(user_id: uuid, message: str):
    prefs = await get_user_preferences(user_id)
    if not prefs.notify_telegram:
        return
    if is_quiet_hours(prefs):
        await schedule_for_after_quiet_hours(user_id, message)
        return
    await telegram_bot.send_message(chat_id=prefs.telegram_chat_id, text=message)
```

---

## 9. Security Design

### 9.1 JWT Token Flow (httpOnly Cookies)

```
1. Client sends POST /auth/login with credentials
2. Server validates and sets httpOnly cookies in response:
   Set-Cookie: access_token=<jwt>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=3600
   Set-Cookie: refresh_token=<jwt>; HttpOnly; Secure; SameSite=Lax; Path=/api/v1/auth; Max-Age=604800
3. Browser automatically includes cookies on all same-origin requests
4. Server reads token from cookie (or Authorization header — dual-mode)
5. When access_token expires → 401 response
6. Frontend middleware automatically calls POST /auth/refresh
7. Server reads refresh_token from cookie, validates, sets new cookie pair
8. POST /auth/logout clears cookies (Set-Cookie with Max-Age=0)
9. If refresh_token expired → redirect to /login
```

**Dual-mode auth dependency**: `get_current_user` checks `Authorization: Bearer`
header first (for API clients, scripts). If absent, reads `access_token` cookie.
This allows both browser (cookie) and programmatic (header) access.

### 9.2 Rate Limiting Design

```python
# main.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, storage_uri=settings.REDIS_URL)

# Apply per-endpoint limits
@router.get("/stocks/{ticker}/signals")
@limiter.limit("60/minute")
async def get_signals(ticker: str, request: Request): ...

@router.post("/chat/stream")
@limiter.limit("10/minute")  # Expensive: LLM calls
async def chat_stream(request: Request): ...
```

---

## 10. Deployment Architecture (Phase 6)

### 10.1 Local Development

```
Docker Compose:
  postgres (timescale/timescaledb:latest-pg16) → port 5432
  redis (redis:7-alpine) → port 6379

Native (not containerized):
  FastAPI (uvicorn --reload) → port 8181
  Next.js (npm run dev) → port 3000
  Celery worker + beat
```

### 10.2 Production (Azure)

```
Azure Container Apps:
  api (FastAPI) → 2 replicas, min 0 max 4
  worker (Celery) → 1 replica
  beat (Celery Beat) → 1 replica (singleton)
  frontend (Next.js static export or Node) → 1 replica

Azure Database for PostgreSQL Flexible Server:
  + TimescaleDB extension enabled
  Burstable B2s (2 vCPU, 4 GB) — scale up if needed

Azure Cache for Redis:
  Basic C0 (250 MB) — sufficient for cache + Celery broker

Azure Blob Storage:
  ML model artifacts (data/models/ equivalent)

Azure Container Registry:
  Docker images for all services

GitHub Actions:
  PR → lint + test
  Merge to main → build + push images → deploy to staging
  Tag → deploy to production
```

### 10.3 Monitoring & Observability

```python
# Structured logging throughout
import logging

logger = logging.getLogger(__name__)

@router.get("/stocks/{ticker}/signals")
async def get_signals(ticker: str, request: Request):
    logger.info("signal_request", ticker=ticker, user_id=request.state.user_id)
    ...
    logger.info("signal_response", ticker=ticker, composite_score=result.composite_score,
                duration_ms=elapsed)
```

- **Logs:** stdlib `logging` → stdout → Azure Monitor (production); structlog migration for later
- **Metrics:** OpenTelemetry instrumentation on FastAPI + Celery
- **Traces:** Correlation ID on every request (X-Request-ID header)
- **Alerts:** Azure Monitor alerts on error rate > 5%, P95 latency > 5s
- **Job health:** TaskLog table queried by dashboard widget

---

## 11. Testing Architecture

### 11.1 Test Pyramid

```
        ╱╲
       ╱E2E╲           Playwright: 3-5 critical user journeys
      ╱──────╲          (login → dashboard → screener → detail)
     ╱  API   ╲         httpx AsyncClient: every endpoint
    ╱──────────╲        (auth, happy path, errors)
   ╱Integration ╲       testcontainers: full pipeline
  ╱──────────────╲      (price fetch → signal compute → store)
 ╱    Unit Tests   ╲     Pure functions: signal math, scoring,
╱════════════════════╲   position sizing, FIFO cost basis
```

### 11.2 Test Infrastructure

```python
# tests/conftest.py

@pytest.fixture(scope="session")
def postgres_container():
    """Real Postgres + TimescaleDB via testcontainers."""
    with PostgresContainer("timescale/timescaledb:latest-pg16") as pg:
        yield pg

@pytest.fixture
async def db_session(postgres_container):
    """Fresh async session per test with automatic rollback."""
    engine = create_async_engine(postgres_container.get_connection_url())
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine) as session:
        yield session
        await session.rollback()

@pytest.fixture
def stock_factory(db_session):
    """Factory-boy factory for Stock model."""
    class StockFactory(factory.alchemy.SQLAlchemyModelFactory):
        class Meta:
            model = Stock
            sqlalchemy_session = db_session
        ticker = factory.Sequence(lambda n: f"TEST{n}")
        name = factory.Faker("company")
        sector = "Technology"
    return StockFactory
```

### 11.3 Coverage Requirements

- Minimum: 80% line coverage enforced by pytest-cov
- Critical paths requiring 100%: signal computation, composite scoring,
  recommendation decision rules, FIFO cost basis, position sizing
- Integration tests for: price fetch → signal compute → recommendation store pipeline
- Agent tests (weekly, uses real LLM): verify tool selection and response quality

---

## 12. MCP Server Design (Phase 6)

### 12.1 MCP Server Mapping

Each tool group becomes an MCP server:

| MCP Server | Tools Exposed |
|-----------|---------------|
| market-data | fetch_prices, get_latest_price, search_stocks |
| signal-engine | compute_signals, get_latest_signals, get_composite_score |
| portfolio | get_positions, get_allocation, log_transaction, get_dividends |
| screener | screen_stocks, get_universe |
| recommendations | get_recommendations, acknowledge |

### 12.2 Transport

- stdio for local MCP clients (Claude Desktop, Claude Code)
- SSE for remote MCP clients
- Same business logic — MCP is just a transport wrapper

```python
# mcp_servers/signal_engine.py
from mcp.server import Server

server = Server("signal-engine")

@server.tool()
async def compute_signals(ticker: str) -> dict:
    """Compute all technical signals for a stock."""
    return await signal_tool.compute_all(ticker)
```

---

## 13. Document Cross-References

| Question | Document |
|----------|----------|
| What are we building and why? | docs/PRD.md |
| What does each feature do in detail? | docs/FSD.md (this doc's sibling) |
| How is the system architected? | docs/TDD.md (this doc) |
| What's the database schema? | docs/data-architecture.md |
| What tech stack and conventions? | CLAUDE.md |
| What's the build order? | project-plan.md |
| What has been built so far? | PROGRESS.md |
