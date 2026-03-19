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

### 4.4 Retry + Fallback Strategy

Each provider implements a retry policy before falling through to the next:

```python
class RetryPolicy:
    max_retries: int = 3
    base_delay: float = 1.0          # seconds
    max_delay: float = 10.0          # cap for exponential backoff
    backoff_factor: float = 2.0      # delay = base * (factor ^ attempt)
```

**Failure classification — determines retry vs. switch:**

| Failure | Action | Rationale |
|---------|--------|-----------|
| HTTP 500/503 (server error) | Retry with exponential backoff (1s, 2s, 4s), then switch | Transient — likely recovers |
| HTTP 429 + `Retry-After` ≤ 5s | Wait the specified time, retry | Short wait is acceptable |
| HTTP 429 + `Retry-After` > 5s | **Switch immediately** | User is waiting — can't afford long waits |
| HTTP 429 + "quota exceeded" | **Switch immediately + mark provider as exhausted** | Retrying is pointless until quota resets |
| Timeout (30s no response) | **Switch immediately** | Provider is unresponsive |
| HTTP 400 context_length_exceeded | **Do NOT switch** — truncate history, retry same provider | Input problem, not provider problem |
| Malformed response / parse error | Retry once, then switch | Could be transient |
| Connection refused / DNS failure | **Switch immediately** | Provider is down |

**Provider health tracking:**

```python
class ProviderHealth:
    provider: str
    is_exhausted: bool = False        # quota exceeded — skip until reset
    exhausted_until: datetime | None  # when to try again (from Retry-After or midnight)
    consecutive_failures: int = 0
    last_failure: datetime | None
```

The `LLMClient` checks provider health before attempting a call. Exhausted providers are skipped entirely (no retry, no backoff) until their reset time. This avoids wasting time on providers that will definitely reject the request.

**Backoff implementation:**

```python
async def call_with_retry(provider, messages, tools) -> LLMResponse:
    for attempt in range(policy.max_retries):
        try:
            return await asyncio.wait_for(
                provider.chat(messages, tools),
                timeout=30.0
            )
        except RateLimitError as e:
            if e.is_quota_exhausted:
                provider.health.mark_exhausted(e.retry_after)
                raise  # fall through to next provider
            if e.retry_after and e.retry_after <= 5:
                await asyncio.sleep(e.retry_after)
                continue
            raise  # fall through to next provider
        except (ServerError, ConnectionError):
            delay = min(policy.base_delay * (policy.backoff_factor ** attempt), policy.max_delay)
            logger.warning("llm_retry", extra={"provider": provider.name, "attempt": attempt, "delay": delay})
            await asyncio.sleep(delay)
        except asyncio.TimeoutError:
            raise  # fall through immediately
    raise MaxRetriesExceeded(provider.name)
```

The LLMClient tracks which provider succeeded for logging and streams a `provider_fallback` event to the client when switching.

### 4.4 Token Tracking

Every LLM call records:
- `provider`, `model`, `prompt_tokens`, `completion_tokens`
- `latency_ms`, `tool_calls_requested`
- Stored in `LLMCallLog` table (see §7)

---

## 5. Agentic Loop (LangGraph)

### 5.1 Why LangGraph

The agentic loop is built on **LangGraph** (`langgraph` v1.0+) rather than a custom Python loop. This decision is driven by Phase 5-6 requirements that would otherwise require a rewrite:

| Capability | Phase 4B (now) | Phase 5-6 (future) |
|------------|---------------|---------------------|
| **Checkpointing** | Disconnect recovery (§8.2) | Long-running multi-step analyses |
| **Conditional branching** | Tool-call vs. synthesis decision | Retrain triggers, macro regime routing |
| **Parallel tool execution** | Fan-out for independent tools | Multi-source data gathering |
| **Human-in-the-loop** | Not needed yet | Stop-loss confirmation, trade approval |
| **Multi-agent** | Single agent per session | StockAgent + MacroAgent collaboration |

LangGraph's `StateGraph` is a thin abstraction over our existing pattern — the Phase 4B graph has just 2 nodes (`call_model` → `execute_tools` → loop). But it gives us the above capabilities without refactoring the orchestration layer later.

### 5.2 Graph Architecture

```
                    ┌──────────────┐
                    │    START     │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
              ┌────►│  call_model  │◄────┐
              │     └──────┬───────┘     │
              │            │             │
              │     ┌──────▼───────┐     │
              │     │  has_tools?  │     │
              │     └──┬───────┬───┘     │
              │   yes  │       │  no     │
              │ ┌──────▼─────┐ │         │
              │ │exec_tools  │ │         │
              │ └──────┬─────┘ │         │
              │        │       │         │
              └────────┘ ┌─────▼───────┐ │
                         │  synthesize │ │
                         └─────┬───────┘ │
                               │         │
                        ┌──────▼───────┐ │
                        │     END      │ │
                        └──────────────┘ │
              (max_iterations reached)───┘
```

### 5.3 State Definition

```python
from typing import Annotated, TypedDict
from langgraph.graph.message import AnyMessage, add_messages


class AgentState(TypedDict):
    """State managed by the LangGraph agent graph."""
    messages: Annotated[list[AnyMessage], add_messages]
    agent_type: str                    # "stock" | "general"
    iteration: int                     # current iteration count
    tool_results: list[dict]           # accumulated tool results for streaming
    usage: dict                        # token usage tracking
```

### 5.4 Core Graph

```python
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver


def build_agent_graph(
    agent: BaseAgent,
    registry: ToolRegistry,
    llm_client: LLMClient,
    max_iterations: int = 15,
) -> StateGraph:
    """Build the LangGraph StateGraph for an agent."""

    # Bind tools to the LLM via LangChain-compatible wrapper
    tools = registry.get_langchain_tools(agent.tool_filter)

    async def call_model(state: AgentState) -> dict:
        """Call the LLM with current messages + tool schemas."""
        response = await llm_client.chat(
            messages=state["messages"],
            tools=registry.schemas(agent.tool_filter),
        )
        return {
            "messages": [response.to_langchain_message()],
            "iteration": state["iteration"] + 1,
            "usage": response.usage_dict(),
        }

    async def execute_tools(state: AgentState) -> dict:
        """Execute all tool calls from the last LLM response."""
        last_message = state["messages"][-1]
        results = []
        for tool_call in last_message.tool_calls:
            result = await execute_tool_safely(
                registry, tool_call["name"], tool_call["args"]
            )
            results.append({
                "tool": tool_call["name"],
                "status": result.status,
                "data": result.data,
                "error": result.error,
            })
        # ToolNode handles message formatting; we track results for streaming
        return {"tool_results": results}

    def should_continue(state: AgentState) -> str:
        """Route: if LLM returned tool calls and under max iterations, execute them."""
        last_message = state["messages"][-1]
        if state["iteration"] >= max_iterations:
            return "end"
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "execute_tools"
        return "end"

    # Build the graph
    tool_node = ToolNode(tools)
    graph = StateGraph(AgentState)
    graph.add_node("call_model", call_model)
    graph.add_node("execute_tools", tool_node)

    graph.add_edge(START, "call_model")
    graph.add_conditional_edges("call_model", should_continue, {
        "execute_tools": "execute_tools",
        "end": END,
    })
    graph.add_edge("execute_tools", "call_model")

    # Compile with checkpointer for session persistence
    checkpointer = MemorySaver()  # Phase 6: swap for PostgresSaver or RedisSaver
    return graph.compile(checkpointer=checkpointer)
```

### 5.5 Safe Tool Execution

```python
async def execute_tool_safely(registry, tool_name: str, params: dict) -> ToolResult:
    try:
        return await asyncio.wait_for(
            registry.execute(tool_name, params),
            timeout=registry.get(tool_name).timeout_seconds
        )
    except KeyError:
        return ToolResult(status="error", error=f"Tool '{tool_name}' not found")
    except asyncio.TimeoutError:
        return ToolResult(status="timeout", error="Tool took too long")
    except Exception as e:
        logger.error("tool_failed", extra={"tool": tool_name, "error": str(e)})
        return ToolResult(status="error", error=str(e))
```

The LLM sees error statuses and adapts its synthesis: "I wasn't able to fetch the latest 10-K filing, but based on the available data..."

### 5.6 LangGraph ↔ StreamEvent Bridge

The LangGraph graph runs internally with LangChain message types. The chat router converts graph events to our `StreamEvent` NDJSON format for the frontend:

```python
async def stream_graph_events(graph, input_state, config) -> AsyncIterator[StreamEvent]:
    """Bridge LangGraph astream_events to our NDJSON StreamEvent format."""
    yield StreamEvent(type="thinking", content="Analyzing your question...")

    async for event in graph.astream_events(input_state, config, version="v2"):
        if event["event"] == "on_chat_model_start":
            pass  # model invocation started
        elif event["event"] == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield StreamEvent(type="token", content=chunk.content)
        elif event["event"] == "on_tool_start":
            yield StreamEvent(type="tool_start", tool=event["name"], params=event["data"].get("input"))
        elif event["event"] == "on_tool_end":
            yield StreamEvent(type="tool_result", tool=event["name"], status="ok", data=event["data"].get("output"))

    yield StreamEvent(type="done", usage={})
```

### 5.7 Future Phase Extensions

The LangGraph architecture enables these Phase 5-6 features with minimal changes:

| Feature | How LangGraph Enables It |
|---------|-------------------------|
| **Parallel tool execution** | Replace sequential `execute_tools` with `Send()` API for fan-out |
| **Human-in-the-loop** | Add `interrupt()` before trade execution nodes |
| **Multi-agent** | Add `supervisor` node that routes to sub-graphs (StockAgent, MacroAgent) |
| **Persistent checkpointing** | Swap `MemorySaver` for `PostgresSaver` (already have TimescaleDB) |
| **Conditional workflows** | Add new conditional edges (e.g., if macro risk > threshold → deep analysis) |

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

- **New session:** create `ChatSession` with `user_id` + `agent_type`. LangGraph `thread_id` = `ChatSession.id` (UUID).
- **Resume:** LangGraph's `MemorySaver` checkpointer stores graph state per `thread_id`. Resuming a session = invoking the compiled graph with the same `{"configurable": {"thread_id": session_id}}`. No manual message loading needed — the checkpointer restores full conversation state including tool call history.
- **Context budget:** 16K tokens for the sliding window. Summarization triggers at 12K tokens. Budget is provider-aware — uses the minimum across configured providers (Groq/Claude: 128K+, but we cap at 16K for cost/speed). Token counting via `tiktoken` (OpenAI-compatible) or provider-specific tokenizer.
- **History summary:** when context exceeds 12K tokens, oldest messages summarized by a cheap/fast LLM call: "Previous context: user analyzed AAPL, discussed Iran exposure..."
- **Expiry:** 24h inactivity → `is_active = FALSE`. Messages preserved in DB. LangGraph checkpoint can be cleared.
- **Checkpointer upgrade path:** Phase 4B uses `MemorySaver` (in-memory, sufficient for single-process dev). Phase 6 swaps to `PostgresSaver` or `RedisSaver` for multi-worker persistence with zero code changes to the graph.

### 8.2 During Streaming

| Event | Behavior |
|-------|----------|
| User sends another message while streaming | Queue in-memory (asyncio.Queue per session) — process after current response. **Note:** per-process queue; does not work across multiple workers. Acceptable for single-process dev; needs Redis-backed queue if multi-worker (Phase 6). |
| User disconnects (closes browser/tab) | LangGraph checkpointer saves graph state at each node boundary. Server detects SSE disconnect → cancel remaining tool calls. On reconnect, graph can resume from last checkpoint rather than replaying from scratch. |
| User reconnects | Load session → LangGraph restores from checkpoint → show last complete messages + "response was interrupted" |

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
    graph.py                 # LangGraph StateGraph builder + AgentState
    stream.py                # StreamEvent types + LangGraph→NDJSON bridge
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
# Agent orchestration
langgraph               # LangGraph — StateGraph, checkpointing, streaming
langchain-core          # LangChain core — message types, tool abstractions

# LLM providers (LangChain-compatible wrappers)
langchain-groq          # Groq provider for LangChain
langchain-anthropic     # Anthropic provider for LangChain
langchain-openai        # OpenAI provider for LangChain (also LM Studio)

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
