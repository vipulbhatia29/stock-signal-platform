# Phase 4B — AI Chatbot Backend: Intelligence Platform Design

**Date:** 2026-03-17
**Branch:** `feat/KAN-23-cicd-jira` (spec phase — implementation branch TBD)
**Epic:** KAN-1
**Brainstorm:** KAN-17
**Status:** Draft — pending review

---

## 1. Overview

Phase 4B builds a **three-layer financial intelligence platform** that serves as the backend for the AI chatbot and as a reusable MCP server for any client.

### What This Is NOT
- Not a chatbot UI (that's Phase 4C)
- Not a simple LLM wrapper around yfinance
- Not a single-purpose tool

### What This IS
- A **financial intelligence engine** that combines 5 data layers (fundamentals, SEC filings, news/sentiment, macro/geopolitical, alternative signals)
- A **tool registry** with pluggable internal tools and external MCP adapters
- An **MCP server** that exposes enriched analysis tools to any client
- A **streaming chat API** for the Phase 4C frontend
- A **warm data pipeline** for pre-processing high-value data sources

### Design Principles
- **Agent-driven orchestration** — the LLM decides which tools to call based on the user's question
- **Registry pattern** — all tools are discoverable, pluggable, self-describing
- **Graceful degradation** — every tool can fail independently without crashing the response
- **Few-shot prompted** — all agents use example-based prompting for reliable tool selection
- **No new infrastructure** — TimescaleDB + Redis + Celery (all existing)

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CONSUMERS                                │
│  POST /api/v1/chat/stream   │  /mcp (Streamable HTTP)       │
│  (Phase 4C frontend)        │  (Claude Code, Cursor, etc.)  │
└────────────┬────────────────┴──────────────┬────────────────┘
             │                               │
             ▼                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI (port 8181)                        │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐     │
│  │              AGENTIC LOOP                            │     │
│  │  LLMClient → tool calls → Registry → results        │     │
│  │  → append to context → repeat (max 15 iterations)    │     │
│  └───────────────────────┬─────────────────────────────┘     │
│                          │                                    │
│  ┌───────────────────────▼─────────────────────────────┐     │
│  │              TOOL REGISTRY                           │     │
│  │  Internal Tools      │  MCPAdapters                  │     │
│  │  (backend/tools/)    │  (auto-discovered)            │     │
│  └───────────────────────┬─────────────────────────────┘     │
│                          │                                    │
│  ┌───────────────────────▼─────────────────────────────┐     │
│  │              DATA LAYER                              │     │
│  │  Hot: TimescaleDB    Warm: Redis     Cold: APIs      │     │
│  └─────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

### Layer 1 — Consume External MCPs (raw data)

| MCP Server | What it provides | Tier |
|------------|-----------------|------|
| **EdgarTools MCP** | SEC filings: 10-K, 10-Q, 8-K, 13F, Form 4. XBRL native. Used via MCPAdapter for agent access AND as Python library in Celery warm pipeline tasks. | 1 |
| **Alpha Vantage MCP** | News + sentiment scores, quotes, technical indicators | 1 |
| **FRED MCP** (`mcp-fredapi`) | 840K macroeconomic series (GDP, CPI, Fed rate, employment) | 1 |
| **Finnhub MCP** | Analyst ratings, ESG, social sentiment, supply chain, ETF holdings | 1 |
| **GDELT API** (custom tool wrapper) | Geopolitical events, 15-min updates, 300+ event categories | 1 |
| Unusual Whales MCP | Options flow, dark pool, congressional trading | 2 (deferred) |
| Polygon.io MCP | Broader options/market data | 2 (deferred) |

### Layer 2 — Backend Enrichment

**Hot data (TimescaleDB — already exists):**
- Prices, signals, Piotroski, portfolio, recommendations, dividends

**Warm data (Redis cache — new Celery tasks):**

| Data | Cache TTL | Refresh cadence | Source |
|------|-----------|----------------|--------|
| Analyst consensus per ticker | 24h | Daily Celery task | Finnhub |
| Key FRED indicators (Fed rate, CPI, 10Y, unemployment) | 24h | Daily Celery task | FRED MCP |
| Top institutional holders per portfolio stock | 7d | Weekly Celery task | EdgarTools 13F |
| 10-K/10-Q section extracts | 24h | On-demand (first query caches) | EdgarTools |

**Cold data (runtime API calls — no caching):**
- Breaking news + sentiment
- Geopolitical events
- Social sentiment
- Real-time quotes

### Layer 3 — Expose as MCP Server

Our FastAPI backend exposes enriched tools via MCP Streamable HTTP transport at `/mcp`.
Any MCP client (Claude Code, Cursor, future mobile app) can consume these tools.
The chatbot endpoint (`POST /api/v1/chat/stream`) is just one consumer.

---

## 3. Tool Registry + MCPAdapter

### 3.1 Registry Interface

```python
class ToolRegistry:
    def register(tool: BaseTool) -> None
    def register_mcp(adapter: MCPAdapter) -> None
    def discover() -> list[ToolInfo]
    def get(name: str) -> BaseTool
    def execute(name: str, params: dict) -> ToolResult
    def schemas(filter: ToolFilter) -> list[dict]   # JSON schemas for LLM
    def by_category(*categories) -> list[BaseTool]
    def health() -> dict[str, bool]
```

### 3.2 BaseTool

```python
class CachePolicy:
    ttl: timedelta                     # e.g., timedelta(hours=24)
    key_fields: list[str]             # e.g., ["ticker"] — params used in cache key
    backend: Literal["redis"] = "redis"

class BaseTool(ABC):
    name: str                          # "analyze_stock"
    description: str                   # for LLM context
    category: str                      # "analysis"|"data"|"portfolio"|"macro"|"news"|"sec"
    parameters: dict                   # JSON Schema
    cache_policy: CachePolicy | None   # {ttl: "24h", key_fields: ["ticker"]}
    timeout_seconds: float = 10.0      # default for internal tools; 30.0 for proxied MCP tools

    async def execute(params: dict) -> ToolResult
```

Each internal tool is one file in `backend/tools/`. Self-contained, testable.

### 3.3 MCPAdapter

```python
class MCPAdapter:
    name: str              # "edgar_tools"
    transport: str         # "stdio" | "http"
    config: dict           # connection details

    async def connect() -> None
    async def discover_tools() -> list[ProxiedTool]
    async def execute(tool_name: str, params: dict) -> ToolResult
    async def health_check() -> bool
```

Connects to external MCP server, auto-discovers tools, wraps each as `ProxiedTool` (extends `BaseTool`). Caching applied per-tool via `CachePolicy`.

### 3.4 Agent Types = Registry Filters

```python
AGENT_TOOL_FILTERS = {
    "stock": ToolFilter(categories=["analysis", "data", "portfolio", "macro", "news", "sec"]),
    "general": ToolFilter(categories=["data", "news"]),
}
```

### 3.5 Tool Inventory (Phase 4B)

**Internal tools (backend/tools/):**

| Tool | Category | Description | Data sources |
|------|----------|-------------|-------------|
| `analyze_stock` | analysis | Complete stock analysis: technicals + fundamentals + signals + news | DB + Alpha Vantage + Finnhub |
| `get_portfolio_exposure` | portfolio | Sector/geographic exposure + risk analysis | DB |
| `screen_stocks` | analysis | Screener enhanced with macro/analyst overlay | DB + Finnhub |
| `get_recommendations` | portfolio | Recommendations with multi-source context | DB + analyst + macro |
| `compute_signals` | data | Signal computation for a ticker | DB |
| `get_geopolitical_events` | macro | GDELT wrapper — geopolitical events + sector mapping | GDELT API |
| `web_search` | data | General web search for current information | SerpAPI (SERPAPI_API_KEY already in config) |

**Proxied tools (via MCPAdapters):**

| Adapter | Tools exposed |
|---------|--------------|
| `edgar_tools` | `get_10k_section`, `get_13f_holdings`, `get_insider_trades`, `get_8k_events` |
| `alpha_vantage` | `get_news_sentiment`, `get_quotes` |
| `fred` | `get_economic_series` |
| `finnhub` | `get_analyst_ratings`, `get_social_sentiment`, `get_etf_holdings`, `get_esg_scores`, `get_supply_chain` |

---

## 4. LLM Client

### 4.1 Abstraction

```python
class LLMClient:
    providers: list[LLMProvider]   # ordered by preference

    async def chat(
        messages: list[Message],
        tools: list[ToolSchema],
        stream: bool = True,
    ) -> LLMResponse | AsyncIterator[LLMChunk]
```

Normalizes all tool-calling formats. Groq/OpenAI/Local use OpenAI-compatible format. Anthropic has its own format — adapter translates.

### 4.2 Providers

| Provider | Model | Use case | API compatibility |
|----------|-------|----------|------------------|
| **Groq** | Llama 3.3 70B | Primary — fast tool-calling | OpenAI-compatible |
| **Anthropic** | Claude Sonnet 4 | Best reasoning/synthesis | Native SDK, adapter normalizes |
| **OpenAI** | GPT-4o | Reliable tool-calling | OpenAI SDK |
| **Local** | LM Studio | Offline fallback | OpenAI-compatible |

Start with Groq for development. Provider-agnostic interface allows switching with zero code changes.

### 4.3 Fallback Chain

```
Groq → Anthropic → Local → AllProvidersFailedError
```

Aligned with PRD §NFR-3 and FSD §5: Groq (fast/cheap) → Claude (quality) → LM Studio (offline).
OpenAI is available as a provider implementation but NOT in the default fallback chain.
It can be added by configuration if needed — the `LLMClient` accepts an ordered provider list.

Each provider is tried in order. On `APIError` or `Timeout`, log warning and try next. The LLMClient tracks which provider succeeded for logging.

### 4.4 Token Tracking

Every LLM call records:
- `provider`, `model`, `prompt_tokens`, `completion_tokens`
- `latency_ms`, `tool_calls_requested`
- Stored in `LLMCallLog` table (see §7)

---

## 5. Agentic Loop

### 5.1 Core Loop

**Two-phase approach per iteration:**
1. **Tool-calling phase:** call LLM in non-streaming mode (or buffer stream). Detect tool calls from the complete response. Execute tools.
2. **Synthesis phase:** when LLM responds without tool calls, this is the final answer — stream it token-by-token to the client.

This matches how LLM SDKs work in practice: tool_use blocks arrive as part of the response and must be fully received before execution.

```python
async def agentic_loop(
    agent: BaseAgent,
    message: str,
    history: list[Message],
    registry: ToolRegistry,
    llm: LLMClient,
    max_iterations: int = 15,
) -> AsyncIterator[StreamEvent]:

    messages = history + [user_message(message)]
    tools = registry.schemas(agent.tool_filter)

    for i in range(max_iterations):
        response = await llm.chat(messages, tools, stream=True)

        if response.has_tool_calls:
            for tool_call in response.tool_calls:
                yield StreamEvent(type="tool_start", tool=tool_call.name)
                result = await execute_tool_safely(registry, tool_call)
                yield StreamEvent(type="tool_result", tool=tool_call.name, data=result)
                messages.append(tool_message(tool_call, result))
        else:
            async for chunk in response.stream:
                yield StreamEvent(type="token", content=chunk)
            break

    yield StreamEvent(type="done", usage=total_usage)
```

### 5.2 Safe Tool Execution

```python
async def execute_tool_safely(registry, tool_call) -> ToolResult:
    tool = registry.get(tool_call.name)
    try:
        result = await asyncio.wait_for(
            registry.execute(tool_call.name, tool_call.params),
            timeout=tool.timeout_seconds  # 10s internal, 30s proxied MCP
        )
        return ToolResult(status="ok", data=result)
    except ToolNotAvailableError:
        return ToolResult(status="degraded", error="Tool temporarily unavailable")
    except asyncio.TimeoutError:
        return ToolResult(status="timeout", error="Tool took too long")
    except Exception as e:
        logger.error("tool_failed", extra={"tool": tool_call.name, "error": str(e)})
        return ToolResult(status="error", error="Unexpected error")
```

The LLM sees error statuses and adapts its synthesis: "I wasn't able to fetch the latest 10-K filing, but based on the available data..."

### 5.3 Stream Event Types

```json
{ "type": "thinking",     "content": "Analyzing AAPL..." }
{ "type": "tool_start",   "tool": "get_10k_section", "params": {...} }
{ "type": "tool_result",  "tool": "get_10k_section", "status": "ok", "data": {...} }
{ "type": "tool_result",  "tool": "get_news",        "status": "degraded", "error": "..." }
{ "type": "provider_fallback", "from": "groq", "to": "claude" }
{ "type": "context_truncated", "message": "History summarized to fit context" }
{ "type": "token",        "content": "Based on..." }
{ "type": "done",         "usage": { "tokens": 4521, "model": "llama-3.3-70b", "tools_called": 4 } }
```

---

## 6. Agents + Few-Shot Prompting

### 6.1 Agent Types

**StockAgent** — full toolkit, financial analysis expert:
- All tool categories: analysis, data, portfolio, macro, news, sec
- Few-shot examples: "Analyze AAPL", "How exposed am I to Iran?", "What should I buy in Tech?"
- Guardrails: never fabricate numbers, all data from tool calls

**GeneralAgent** — limited toolkit, general Q&A:
- Categories: data, news only
- Few-shot examples: general questions, web search
- No portfolio or SEC access

### 6.2 Prompt Templates

Stored as markdown files, version-controlled:

```
backend/agents/prompts/
  stock_agent.md         # system prompt + 3-4 few-shot examples
  general_agent.md       # system prompt + 2-3 few-shot examples
```

Each prompt includes:
1. Role description
2. Available tools (injected from registry at runtime — NOT hardcoded)
3. 3-4 few-shot examples showing: question → tool calls → synthesis pattern
4. Guardrails and constraints

### 6.3 Few-Shot Example Format

```
### Example 1
User: "Analyze AAPL"
Tools to call:
1. compute_signals(ticker="AAPL")
2. get_news_sentiment(ticker="AAPL")
3. get_analyst_ratings(ticker="AAPL")
4. get_10k_section(ticker="AAPL", section="risk_factors")
Synthesis: Combine technicals, sentiment, analyst view, and key risks
into a structured analysis with clear recommendation.

### Example 2
User: "How exposed is my portfolio to the Iran situation?"
Tools to call:
1. get_geopolitical_events(query="Iran", days=7)
2. get_portfolio_exposure()
3. get_economic_series(series_ids=["DCOILWTICO", "DGS10"])
Synthesis: Map geopolitical events to affected sectors, calculate
portfolio sector overlap, contextualize with oil prices and treasury yields.
```

---

## 7. Database Schema (New Tables)

### 7.1 ChatSession

```sql
CREATE TABLE chat_session (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES "user"(id),
    agent_type VARCHAR(20) NOT NULL,  -- 'stock' | 'general'
    title VARCHAR(255),               -- auto-generated: first 100 chars of user's first message, trimmed to word boundary
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_chat_session_user ON chat_session(user_id, last_active_at DESC);
```

### 7.2 ChatMessage

```sql
CREATE TABLE chat_message (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_session(id),
    role VARCHAR(20) NOT NULL,        -- 'user' | 'assistant' | 'tool'
    content TEXT,
    tool_calls JSONB,                 -- tool calls made in this turn
    model_used VARCHAR(100),
    tokens_used INTEGER,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    latency_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_chat_message_session ON chat_message(session_id, created_at);
```

### 7.3 LLMCallLog (operational)

```sql
CREATE TABLE llm_call_log (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES chat_session(id),
    message_id UUID REFERENCES chat_message(id),
    provider VARCHAR(50) NOT NULL,    -- 'groq' | 'anthropic' | 'openai' | 'local'
    model VARCHAR(100) NOT NULL,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    cost_usd NUMERIC(10,6),           -- estimated cost per call
    latency_ms INTEGER,
    tool_calls_requested JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)      -- composite PK required for TimescaleDB hypertable
);
SELECT create_hypertable('llm_call_log', 'created_at');
```

### 7.4 ToolExecutionLog (operational)

```sql
CREATE TABLE tool_execution_log (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES chat_session(id),
    message_id UUID REFERENCES chat_message(id),
    tool_name VARCHAR(100) NOT NULL,
    params JSONB,
    result_size_bytes INTEGER,
    latency_ms INTEGER,
    cache_hit BOOLEAN DEFAULT FALSE,
    status VARCHAR(20) NOT NULL,      -- 'ok' | 'degraded' | 'timeout' | 'error'
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)      -- composite PK required for TimescaleDB hypertable
);
SELECT create_hypertable('tool_execution_log', 'created_at');
```

**Note:** Composite PK `(id, created_at)` is required because TimescaleDB hypertables need the partitioning column in the primary key. This matches the existing pattern used by `StockPrice` and other hypertables in the codebase.

---

## 8. Session Lifecycle

### 8.1 Create / Resume / Expire

- **New session:** create `ChatSession` with `user_id` + `agent_type`
- **Resume:** load session + last 20 messages as LLM context (sliding window)
- **Context budget:** 16K tokens for the sliding window. Summarization triggers at 12K tokens. Budget is provider-aware — uses the minimum across configured providers (Groq/Claude: 128K+, but we cap at 16K for cost/speed). Token counting via `tiktoken` (OpenAI-compatible) or provider-specific tokenizer.
- **History summary:** when context exceeds 12K tokens, oldest messages summarized by a cheap/fast LLM call: "Previous context: user analyzed AAPL, discussed Iran exposure..."
- **Expiry:** 24h inactivity → `is_active = FALSE`. Messages preserved, session context cleared.

### 8.2 During Streaming

| Event | Behavior |
|-------|----------|
| User sends another message while streaming | Queue in-memory (asyncio.Queue per session) — process after current response. **Note:** per-process queue; does not work across multiple workers. Acceptable for single-process dev; needs Redis-backed queue if multi-worker (Phase 6). |
| User disconnects (closes browser/tab) | Server detects SSE disconnect → cancel remaining tool calls → save partial response |
| User reconnects | Load session → show last complete messages + "response was interrupted" |

### 8.3 Graceful Degradation

| Failure | Response |
|---------|----------|
| LLM provider down | Try next provider in fallback chain. Stream `provider_fallback` event. |
| Single tool fails | Log error, continue with other tools. LLM adapts synthesis: "Couldn't fetch X, but based on available data..." |
| MCP server disconnected | Registry excludes adapter's tools. Stream `degraded` event. |
| Redis cache down | Fall through to cold query (slower). Log warning. |
| DB down | Return 503 — this is fatal. But external tools still queryable. |
| Rate limit hit | Retry with backoff (3 attempts). If exhausted: skip tool, inform user. |
| LLM returns invalid tool call | Validate against schema. Retry once with correction prompt. If still bad: skip tool. |
| Token limit exceeded | Truncate oldest messages, summarize history, retry. Stream `context_truncated` event. |

---

## 9. Logging + Observability

### 9.1 Persistent (DB tables)

- `ChatMessage` — user-facing: tokens, model, cost per turn
- `LLMCallLog` — one row per LLM API call (multiple per user turn)
- `ToolExecutionLog` — one row per tool execution, including cache hits

### 9.2 Structured Python Logging

```python
logger.info("llm_call", extra={
    "provider": "groq", "model": "llama-3.3-70b",
    "prompt_tokens": 3200, "latency_ms": 1200, "tool_calls": 3
})
logger.info("tool_executed", extra={
    "tool": "get_10k_section", "ticker": "AAPL",
    "cache": "miss", "latency_ms": 2400
})
```

JSON-formatted logs, shippable to any aggregator (ELK, CloudWatch) without code changes.

### 9.3 Deferred to LLMOps Phase

- LLM Gateway (LiteLLM or custom)
- Observability dashboard (token usage, cost, latency)
- Prompt versioning
- A/B testing between providers
- Auto-routing based on query complexity

---

## 10. MCP Server (Layer 3)

**Phase note:** MCP server exposure was originally planned for Phase 6 (FSD Feature Matrix, TDD §12). It is pulled forward to Phase 4B because:
1. The Tool Registry (core of Phase 4B) is the exact same abstraction the MCP server exposes — building both simultaneously is cheaper than retrofitting.
2. Mounting MCP on FastAPI is ~50 lines of code on top of the registry — minimal incremental effort.
3. It makes the platform immediately usable from Claude Code and Cursor, enabling the developer to be their own first customer during Phase 4B development.
4. FSD and TDD will be updated to reflect this phase change (KAN-29 catch-up or dedicated PR).

### 10.1 Transport

**Streamable HTTP** — mounted on FastAPI at `/mcp`.

Single endpoint supports both request-response and SSE streaming. Authenticated via JWT (same auth as REST API).

### 10.2 Exposed Tools

The MCP server mirrors the Tool Registry. Whatever is registered is available to MCP clients. This means Claude Code, Cursor, or any MCP client can call:

- `analyze_stock`, `screen_stocks`, `get_portfolio_exposure`
- `get_10k_section`, `get_insider_trades`, `get_analyst_ratings`
- `get_news_sentiment`, `get_geopolitical_events`, `get_economic_series`

### 10.3 Implementation

Using [FastMCP](https://github.com/jlowin/fastmcp) or equivalent library to mount MCP protocol on FastAPI. Tools registered in the Tool Registry are automatically exposed via MCP.

---

## 11. Warm Data Pipeline

New Celery tasks added to existing beat schedule:

| Task | Cadence | What it does | Source |
|------|---------|-------------|--------|
| `sync_analyst_consensus` | Daily 6am ET | Fetch consensus ratings for all watched tickers | Finnhub |
| `sync_fred_indicators` | Daily 7am ET | Fetch key macro series (Fed rate, CPI, 10Y, unemployment, oil) | FRED MCP |
| `sync_institutional_holders` | Weekly Sunday 2am ET | Fetch top 13F holders for portfolio stocks | EdgarTools |
| `cache_10k_section` | On-demand | Extract and cache 10-K sections on first query (TTL 24h) | EdgarTools |

All cached in Redis with appropriate TTLs. Celery tasks use `asyncio.run()` bridge (existing pattern).

---

## 12. File Structure

```
backend/
  agents/
    __init__.py
    base.py                  # BaseAgent ABC
    stock_agent.py           # StockAgent
    general_agent.py         # GeneralAgent
    loop.py                  # agentic tool-calling loop
    stream.py                # NDJSON/SSE streaming + event types
    llm_client.py            # LLMClient + provider implementations
    prompts/
      stock_agent.md         # few-shot system prompt
      general_agent.md       # few-shot system prompt
  tools/
    __init__.py
    registry.py              # ToolRegistry
    base.py                  # BaseTool, ProxiedTool, MCPAdapter, CachePolicy, ToolResult
    analyze_stock.py         # internal tool
    portfolio_exposure.py    # internal tool
    screen_stocks.py         # internal tool
    recommendations.py       # internal tool (enhanced)
    compute_signals.py       # internal tool (wraps existing)
    geopolitical.py          # GDELT wrapper
    adapters/
      __init__.py
      edgar.py               # MCPAdapter for EdgarTools
      alpha_vantage.py       # MCPAdapter for Alpha Vantage
      fred.py                # MCPAdapter for FRED
      finnhub.py             # MCPAdapter for Finnhub
  mcp_server/
    __init__.py
    server.py                # FastMCP server mounted at /mcp
    auth.py                  # JWT auth for MCP connections
  models/
    chat.py                  # ChatSession, ChatMessage
    logs.py                  # LLMCallLog, ToolExecutionLog
  routers/
    chat.py                  # POST /api/v1/chat/stream
  tasks/
    warm_data.py             # Celery tasks: analyst, FRED, institutional
```

---

## 13. API Contract

### 13.1 Chat Endpoint

```
POST /api/v1/chat/stream
Authorization: Bearer <jwt>
Content-Type: application/json

Request:
{
  "message": "Analyze AAPL given the Iran situation",
  "session_id": "uuid" | null,       // null = new session
  "agent_type": "stock" | "general"  // required for new session; ignored when resuming (agent bound at creation)
}

Response: text/event-stream (NDJSON)
  { "type": "thinking", "content": "Analyzing AAPL..." }
  { "type": "tool_start", "tool": "compute_signals", "params": {"ticker": "AAPL"} }
  { "type": "tool_result", "tool": "compute_signals", "status": "ok" }
  ...
  { "type": "token", "content": "Based on..." }
  { "type": "done", "session_id": "uuid", "usage": {...} }
```

### 13.2 Session Management

```
GET /api/v1/chat/sessions
  → list of user's chat sessions

GET /api/v1/chat/sessions/{id}/messages
  → messages for a session

DELETE /api/v1/chat/sessions/{id}
  → soft-delete (mark inactive)
```

---

## 14. Dependencies (New Packages)

```
# LLM providers
groq                    # Groq SDK (OpenAI-compatible)
anthropic               # Anthropic SDK
openai                  # OpenAI SDK (also used for LM Studio)

# MCP
fastmcp                 # MCP server framework for FastAPI
mcp                     # MCP client SDK (for consuming external MCPs)

# External data
edgartools              # SEC EDGAR Python library
gdeltdoc                # GDELT DOC API client

# Already have: httpx, redis, celery, sqlalchemy, pydantic
```

API keys needed in `.env`:
```
GROQ_API_KEY=...           # already in Settings
ANTHROPIC_API_KEY=...      # already in Settings
OPENAI_API_KEY=...         # already in Settings
ALPHA_VANTAGE_API_KEY=...  # NEW
FINNHUB_API_KEY=...        # NEW
FRED_API_KEY=...           # already in Settings (free, requires registration)
# EdgarTools: free, no key needed (uses SEC EDGAR public API)
# GDELT: free, no key needed
```

---

## 15. Testing Strategy

### 15.1 Unit Tests (mock LLM)

- Mock `LLMClient` to return predefined tool calls
- Test: registry discovers tools, executes them, handles errors
- Test: agentic loop orchestrates correctly with mock responses
- Test: streaming events emitted in correct order
- Test: cache hit/miss logic in ProxiedTool
- Test: graceful degradation (tool timeout, MCP disconnect)

### 15.2 Integration Tests (contract tests with real LLM)

- Use real Groq API with cheap/fast model
- Define contracts: "analyze stock" should call at least `compute_signals` + one news tool
- Assert tool call patterns, not exact outputs
- Run manually or in separate CI job (not blocking PR gate)

### 15.3 Test Expectations Per Component

| Component | Tests |
|-----------|-------|
| ToolRegistry | register, discover, execute, schemas, by_category, health |
| MCPAdapter | connect, discover_tools, execute, health_check, reconnect |
| BaseTool | execute, cache hit/miss, timeout handling |
| LLMClient | chat, stream, fallback chain, token tracking |
| Agentic loop | full loop with mock LLM, tool errors, max iterations |
| Chat endpoint | auth (401), happy path (200 + stream), invalid agent_type (422) |
| Session management | create, resume, expire, history truncation |
| Warm data tasks | Celery task execution, Redis cache population |

---

## 16. Success Criteria

- [ ] Tool Registry with discover/register/execute working
- [ ] 4 MCPAdapters connected (EdgarTools, Alpha Vantage, FRED, Finnhub)
- [ ] GDELT custom tool wrapper working
- [ ] 6 internal tools registered and functional
- [ ] LLMClient with Groq provider working (fallback chain optional for v1)
- [ ] Agentic loop with streaming events
- [ ] Few-shot prompted Stock and General agents
- [ ] Chat endpoint: POST /api/v1/chat/stream returns NDJSON stream
- [ ] Session create/resume/expire working
- [ ] MCP server at /mcp exposing all registered tools
- [ ] Warm data pipeline: daily analyst + FRED tasks, weekly 13F
- [ ] LLMCallLog + ToolExecutionLog tables populated
- [ ] Graceful degradation: tool failure doesn't crash response
- [ ] All existing 267 backend + 20 frontend tests still pass
- [ ] New unit tests for all Phase 4B components

---

## 17. Out of Scope

- Frontend ChatPanel wiring (Phase 4C)
- Unusual Whales / options flow integration (Tier 2, Phase 5)
- Polygon.io integration (Tier 2, Phase 5)
- LLM Gateway / LiteLLM (LLMOps phase)
- Observability dashboards (LLMOps phase)
- Prompt versioning / A/B testing (LLMOps phase)
- Multi-device session sync (Phase 6)
- Offline mode (Phase 6)
- FinGPT / fine-tuned models (research phase)
