# LLM Factory & Cascade — Design Spec

**Date**: 2026-03-25
**Phase**: 6A
**Status**: Draft
**Depends on**: None (foundation spec)
**Blocks**: Observability spec, Testing Infrastructure spec

---

## 1. Problem Statement

Our LLM infrastructure has critical gaps that cause user-visible errors, wasted spend, and missed cost optimization:

1. **Single-model Groq** — `GroqProvider` creates one `ChatGroq` with `llama-3.3-70b-versatile`. When it fails (e.g., `groq.APIError: Failed to call a function`), the entire provider is skipped and we fall to paid Anthropic.
2. **Dead tier_config** — `LLMClient` supports `tier_config` for routing planner vs synthesizer to different providers, but `main.py` never populates it. Both tiers get the same flat provider list.
3. **No proactive rate limiting** — We discover Groq rate limits only when we get a 429. No pre-emptive budget tracking.
4. **V1 dead code** — The `AGENT_V2` feature flag and V1 ReAct graph (`graph.py`) add complexity with zero users.
5. **Groq error blindness** — `APIError` (malformed tool calls), `APIStatusError` (500/503), and `APIConnectionError` are not caught by our cascade logic.

### Reference Architecture

Informed by analysis of [aset-platform/ai-agent-ui](https://github.com/aset-platform/ai-agent-ui) (production N-tier Groq/Anthropic cascade) and industry research (RouteLLM, LiteLLM, Portkey patterns). See brainstorm session notes for full comparison.

---

## 2. V1 Deprecation & Cleanup

**Goal**: Remove the `AGENT_V2` feature flag and V1 ReAct graph. V2 (Plan→Execute→Synthesize) becomes the only path.

### Files to modify

| File | Change |
|---|---|
| `backend/config.py:54` | Remove `AGENT_V2: bool = False` from `Settings` |
| `backend/main.py:89-98` | Remove V1 graph compilation (`build_agent_graph` calls for `stock_graph`, `general_graph`) |
| `backend/main.py:114-160` | Remove `if settings.AGENT_V2` conditional — V2 wiring becomes unconditional |
| `backend/routers/chat.py:112` | Remove `use_v2 = settings.AGENT_V2 and ...` branch. Delete V1 `event_generator()`. Keep `_event_generator_v2()` only. |
| `backend/agents/graph.py` | **Delete entirely** (V1 ReAct graph: `AgentState`, `build_agent_graph`, `execute_tool_safely`) |
| `backend/agents/stream.py` | Delete `stream_graph_events()` function (V1-only). **Preserve `StreamEvent` dataclass and `to_ndjson()` method** — used by V2's `_event_generator_v2()`. |
| `backend/agents/graph_v2.py` | Rename to `backend/agents/graph.py`. Update docstring (line 3: remove "Feature-flagged behind AGENT_V2=true. Coexists with V1 ReAct graph"). |
| `tests/unit/agents/test_agent_graph.py` | Delete (tests V1's `build_agent_graph`) |
| `tests/unit/test_agent_graph.py` | Delete (duplicate, also tests V1) |
| `backend/.env.example` | Remove `AGENT_V2=` line |

### Verification

- All tests pass with V2 as the only path
- Chat endpoint works without `AGENT_V2` in env
- CI green

---

## 3. Data-Driven Model Cascade

**Goal**: Replace hardcoded single-model providers with a DB-managed cascade configurable at runtime.

### 3.1 New Table: `llm_model_config`

```sql
CREATE TABLE llm_model_config (
    id              SERIAL PRIMARY KEY,
    provider        VARCHAR(20) NOT NULL,      -- "groq" | "anthropic" | "openai"
    model_name      VARCHAR(100) NOT NULL,     -- "llama-3.3-70b-versatile"
    tier            VARCHAR(20) NOT NULL,      -- "planner" | "synthesizer" | "default"
    priority        INTEGER NOT NULL,          -- 1 = tried first
    is_enabled      BOOLEAN NOT NULL DEFAULT true,
    tpm_limit       INTEGER,                   -- tokens per minute (NULL = unlimited)
    rpm_limit       INTEGER,                   -- requests per minute
    tpd_limit       INTEGER,                   -- tokens per day
    rpd_limit       INTEGER,                   -- requests per day
    cost_per_1k_input  NUMERIC(10,6) DEFAULT 0,
    cost_per_1k_output NUMERIC(10,6) DEFAULT 0,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(provider, model_name, tier)
);
```

**Note**: `updated_at` requires a SQLAlchemy `@event.listens_for(LLMModelConfig, "before_update")` hook or Postgres trigger to auto-update on modification. Without it, `updated_at` will always equal `created_at`.

### 3.2 Seed Data

**Planner tier** (structured JSON output, tool plan generation):

| Priority | Provider | Model | TPM | Notes |
|---|---|---|---|---|
| 1 | groq | llama-3.3-70b-versatile | 12,000 | Best tool-calling, strong JSON |
| 2 | groq | moonshotai/kimi-k2-instruct | 10,000 | Good reasoning for complex plans |
| 3 | groq | meta-llama/llama-4-scout-17b-16e-instruct | 30,000 | Fast, generous TPM fallback |
| 4 | anthropic | claude-sonnet-4-6 | unlimited | Paid safety net |

**Synthesizer tier** (user-facing analysis, no tool calling needed):

| Priority | Provider | Model | TPM | Notes |
|---|---|---|---|---|
| 1 | groq | openai/gpt-oss-120b | 8,000 | Highest quality free model |
| 2 | groq | moonshotai/kimi-k2-instruct | 10,000 | Strong reasoning fallback |
| 3 | anthropic | claude-sonnet-4-6 | unlimited | Quality guarantee |

### 3.3 Config Loader

New module: `backend/agents/model_config.py`

```python
@dataclass(frozen=True)
class ModelConfig:
    """Single model configuration from llm_model_config table."""
    id: int
    provider: str           # "groq" | "anthropic"
    model_name: str         # "llama-3.3-70b-versatile"
    tier: str               # "planner" | "synthesizer"
    priority: int           # 1 = tried first
    is_enabled: bool
    tpm_limit: int | None
    rpm_limit: int | None
    tpd_limit: int | None
    rpd_limit: int | None
    cost_per_1k_input: float
    cost_per_1k_output: float
```

```python
class ModelConfigLoader:
    """Reads llm_model_config from DB, caches in memory."""

    async def load(self) -> dict[str, list[ModelConfig]]:
        """Load enabled models grouped by tier, ordered by priority.
        Returns: {"planner": [ModelConfig, ...], "synthesizer": [...]}
        """

    async def reload(self) -> None:
        """Force re-read from DB. Called by admin endpoint."""
```

- Read on app startup (in `main.py` lifespan)
- Cached in `app.state.model_config`
- Refreshed via `POST /admin/llm-models/reload`
- Falls back to env var `GROQ_MODEL_TIERS` if table is empty (bootstrap safety)

### 3.4 GroqProvider Changes

Current: `GroqProvider.__init__(api_key, model="llama-3.3-70b-versatile")`
New: `GroqProvider.__init__(api_key, models=[ModelConfig, ...], token_budget=TokenBudget)`

The provider internally:
1. Iterates models in priority order
2. Checks `token_budget.can_afford(model_name, estimated_tokens)` for each
3. Attempts the call on the first affordable model
4. On API error → cascades to next model
5. Records cascade event via `ObservabilityCollector` (wired in Spec 2)

### 3.5 Two-Level Cascade Architecture

The cascade operates at two levels. This boundary must be explicit:

**Level 1: GroqProvider (intra-provider model cascade)**
- Iterates its `models` list in priority order
- Checks `token_budget.can_afford()` for each model
- Catches Groq-specific errors (`APIError`, `APIStatusError`, etc.) and tries next model
- When **all internal models are exhausted**, raises `AllModelsExhaustedError` to LLMClient

**Level 2: LLMClient (inter-provider fallback)**
- Iterates providers: `[GroqProvider, AnthropicProvider]`
- Catches `AllModelsExhaustedError` from GroqProvider → marks provider unhealthy → falls to AnthropicProvider
- If all providers fail → raises `AllProvidersFailedError`

**ProviderHealth changes:**
- `ProviderHealth` stays per-provider (not per-model) — it tracks whether the provider as a whole is available
- Per-model health (failures, latency) is tracked by `ObservabilityCollector` (Spec 6B), not by `ProviderHealth`
- `ProviderHealth.mark_exhausted()` BUG FIX: currently sets `exhausted_until = now()` instead of `now() + timedelta(seconds=retry_after)`. Fix in this spec.

### 3.6 LLMClient Tier Wiring

`main.py` lifespan populates `tier_config`:

```python
model_config = await config_loader.load()

# Build provider instances per tier
planner_providers = build_providers(model_config["planner"])
synth_providers = build_providers(model_config["synthesizer"])

llm_client = LLMClient(
    providers=planner_providers,  # default fallback
    tier_config={
        "planner": planner_providers,
        "synthesizer": synth_providers,
    }
)
```

The existing `llm_client.chat(tier="planner")` and `llm_client.chat(tier="synthesizer")` calls in `main.py:140` and `main.py:147` already pass the tier — they'll now route to the correct cascade automatically.

### 3.6 Admin API

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `GET /admin/llm-models` | GET | superuser | List all model configs |
| `PATCH /admin/llm-models/{id}` | PATCH | superuser | Update priority, is_enabled, limits |
| `POST /admin/llm-models/reload` | POST | superuser | Force reload cascade from DB |

### 3.7 User Impact

**Zero.** The cascade is completely invisible. Users ask questions and get answers. Which model responded is logged internally but never exposed to the user. If all Groq models are exhausted, Anthropic handles it silently.

---

## 4. Token Budget

**Goal**: Proactively avoid 429 errors by tracking token/request usage per model with sliding windows.

### 4.1 New Module: `backend/agents/token_budget.py`

```python
class TokenBudget:
    """Async sliding-window rate tracker per model."""

    async def can_afford(self, model: str, estimated_tokens: int) -> bool:
        """Check 4 dimensions (TPM/RPM/TPD/RPD) at 80% threshold."""

    async def record(self, model: str, actual_tokens: int) -> None:
        """Record usage after a successful call."""

    def estimate_tokens(self, messages: list) -> int:
        """Heuristic: len(content) // 4 * 1.2"""

    def load_limits(self, models: list[ModelConfig]) -> None:
        """Populate limits from llm_model_config data."""
```

### 4.2 Sliding Windows

Per-model tracking using `collections.deque` with `asyncio.Lock`:

| Dimension | Window | Source |
|---|---|---|
| TPM (tokens/minute) | 60s | `llm_model_config.tpm_limit` |
| RPM (requests/minute) | 60s | `llm_model_config.rpm_limit` |
| TPD (tokens/day) | 86,400s | `llm_model_config.tpd_limit` |
| RPD (requests/day) | 86,400s | `llm_model_config.rpd_limit` |

### 4.3 Key Design Decisions

- **80% pre-emptive threshold** — `can_afford()` returns False at 80% of limit
- **Limits from DB** — read from `llm_model_config`, refreshed on reload
- **Token estimation before send** — `len(content) // 4 * 1.2` (accurate within ~15% for English). `estimate_tokens()` is intentionally **sync** (not async) — it does no I/O, just arithmetic. Deliberate exception to the "async by default" rule.
- **Actual tokens recorded after response** — uses API response's `usage.prompt_tokens + completion_tokens`
- **In-memory only** — sliding windows don't persist. On restart, budgets reset (conservative, avoids stale data)
- **Async-safe** — uses `asyncio.Lock` (not `threading.Lock` like aset) since our stack is fully async

### 4.4 Integration

`GroqProvider.chat()` calls `budget.can_afford()` before each model attempt. If False, skip to next model. After success, call `budget.record()`.

---

## 5. Groq Error Recovery

**Goal**: Catch Groq-specific errors and cascade to the next model instead of failing the request.

### 5.1 Error Classification

| Error | Current Behavior | New Behavior |
|---|---|---|
| `groq.RateLimitError` (429) | Handled — `ProviderHealth.mark_exhausted()` | No change |
| `groq.APIError` ("Failed to call a function") | **Unhandled — crashes request** | Cascade to next model. Reason: `"tool_call_failure"` |
| `groq.APIStatusError` (500/503) | **Unhandled** | Cascade. Reason: `"server_error"` |
| `groq.APIConnectionError` | Handled by `ConnectionError` catch | Explicit catch for clarity |
| `asyncio.TimeoutError` | Handled | No change |

### 5.2 Implementation

In `GroqProvider.chat()`:

```python
try:
    response = await client.chat.completions.create(...)
except groq.APIError as e:
    if "Failed to call a function" in str(e):
        # Model generated malformed tool call — try next model
        raise ModelCascadeError(model=self._current_model, reason="tool_call_failure")
    raise
except (groq.APIStatusError, groq.APIConnectionError) as e:
    raise ModelCascadeError(model=self._current_model, reason="api_error")
```

`ModelCascadeError` is a new internal exception that `GroqProvider` catches in its cascade loop to try the next model.

---

## 6. Tool Result Truncation

**Goal**: Reduce synthesizer token consumption by truncating tool results before synthesis.

### 6.1 New Setting

`backend/config.py`:
```python
MAX_TOOL_RESULT_CHARS: int = 3000  # per tool result, for synthesizer
```

### 6.2 Where It Happens

In `graph_v2.py` → `synthesize_node()`, before calling `synthesize_fn`:

```python
truncated_results = truncate_tool_results(
    state.get("tool_results", []),
    max_chars=settings.MAX_TOOL_RESULT_CHARS,
)
synthesis = await synthesize_fn(
    tool_results=truncated_results,
    user_context=state.get("user_context", {}),
)
```

### 6.3 Truncation Strategy

- **JSON results**: Keep structure, truncate long arrays to first 5 items, add `"... (N more)"`
- **Text results**: Hard truncate at limit with `"... [truncated, {len} chars total]"` suffix
- **Error results** (`status: "error"`): Never truncated — error messages are short and critical
- **Small results** (< limit): Passed through unchanged

### 6.4 Impact

With 5 tools at 3000 chars each → ~15K chars → ~3,750 tokens for the synthesizer. Well within any Groq model's TPM. Makes cheaper models viable for synthesis.

---

## 7. Migration & Rollout

### 7.1 Alembic Migration

New migration (012):
- Create `llm_model_config` table
- Seed with planner and synthesizer tier data (Section 3.2)
- Include `downgrade()` that drops the table (reversible migration)

**Migration Safety Protocol** (learned from Session 51 data loss incident):

1. **NEVER use `alembic revision --autogenerate`** — it falsely detects ALL existing tables as new and rewrites the entire schema. It also falsely drops TimescaleDB internal indexes (`_compressed_hypertable_*`). Always write migrations manually with only `op.create_table()` / `op.add_column()`.
2. **Verify `alembic heads` before creating** — current head is `d68e82e90c96` (migration 011). Avoid split-head situations.
3. **Check Docker containers before running** — `docker ps | grep 5433` to verify only `ssp-postgres` is running. The `idp-postgres` container also binds to 5433 and caused data loss when both were running (Session 51).
4. **Verify after running** — `SELECT * FROM alembic_version;` should show the new revision. Then verify `SELECT count(*) FROM llm_model_config;` returns the seed data count.
5. **If migration fails** — do NOT re-run blindly. Check `alembic_version` for stale pointer. If tables are missing but version is set: `DELETE FROM alembic_version;` then `uv run alembic upgrade head`.
6. **Startup validation** — `main.py` lifespan already checks critical tables exist via `information_schema`. Add `llm_model_config` to the critical tables list after migration.

### 7.2 Config Changes

| Setting | Old | New |
|---|---|---|
| `AGENT_V2` | `bool = False` | **Removed** |
| `GROQ_MODEL_TIERS` | (new) | `str = ""` — fallback CSV if DB table is empty |
| `MAX_TOOL_RESULT_CHARS` | (new) | `int = 3000` |

### 7.3 Env Var Requirements

User must enable these Groq models in their Groq console:
1. `llama-3.3-70b-versatile`
2. `moonshotai/kimi-k2-instruct`
3. `meta-llama/llama-4-scout-17b-16e-instruct`
4. `openai/gpt-oss-120b`

### 7.4 Rollout Strategy

1. Deploy migration (creates table + seed data)
2. Deploy code changes (V1 removal + cascade + budget + error recovery)
3. Verify via admin endpoints (`/admin/llm-models`, `/admin/tier-health`)
4. Monitor escalation rate (% requests hitting Anthropic) for 48 hours

---

## 8. Files Changed (Summary)

| Action | File |
|---|---|
| **Delete** | `backend/agents/graph.py` (V1) |
| **Delete** | `tests/unit/agents/test_agent_graph.py` (V1 tests) |
| **Delete** | `tests/unit/test_agent_graph.py` (V1 duplicate) |
| **Create** | `backend/agents/token_budget.py` |
| **Create** | `backend/agents/model_config.py` |
| **Create** | `backend/models/llm_config.py` (SQLAlchemy model) |
| **Create** | `backend/schemas/llm_config.py` (Pydantic schemas) |
| **Create** | `backend/routers/admin.py` (admin endpoints) |
| **Create** | `backend/migrations/versions/xxx_012_llm_model_config.py` |
| **Modify** | `backend/config.py` (remove AGENT_V2, add new settings) |
| **Modify** | `backend/main.py` (V2-only wiring, tier_config, model_config loader) |
| **Modify** | `backend/routers/chat.py` (remove V1 path) |
| **Modify** | `backend/agents/providers/groq.py` (multi-model cascade) |
| **Modify** | `backend/agents/llm_client.py` (ProviderHealth per-model) |
| **Modify** | `backend/agents/graph_v2.py` (tool result truncation in synthesize_node) |

---

## 9. Success Criteria

- [ ] V1 graph deleted, `AGENT_V2` flag removed, V2 is the only path
- [ ] `llm_model_config` table created with seed data
- [ ] Groq cascade tries models in priority order within a tier
- [ ] Token budget proactively skips exhausted models (no user-visible 429s)
- [ ] `groq.APIError` ("Failed to call a function") cascades silently
- [ ] Tool results truncated before synthesis (configurable limit)
- [ ] Admin endpoints work: list models, update, reload
- [ ] Existing chat flow works identically from user perspective
- [ ] All unit + API tests pass
- [ ] CI green

---

## 10. Out of Scope

- Observability write path (LLMCallLog, ToolExecutionLog) → Spec 2
- Test suite refactoring and Playwright expansion → Spec 3
- Redis read cache → Future backlog
- Google OAuth → Future backlog
- Subscription tiering (Free/Pro/Premium) → Future backlog
- Portfolio aggregation tool → Future backlog
- ML-based routing (RouteLLM) → Future backlog (need traffic data first)
- LiteLLM adoption → Future backlog (evaluate when scaling to 5+ providers)
