# KAN-570: Round-Robin Groq Pool + Per-Request Model Pinning

## Problem

Our `GroqProvider` (backend/agents/providers/groq.py) cascades through models sequentially: llama-70b → qwen3-32b → scout-17b. The first model absorbs ALL traffic until it rate-limits, then cascades. This causes:

1. **Burst exhaustion** — 12K TPM on llama-70b drains in 2-3 heavy requests, then ALL subsequent requests hit cascade latency (+200-500ms per failed attempt)
2. **Mid-conversation model switching** — ReAct loop makes 3-5 `llm_chat()` calls per user request. If llama hits TPM limit between iteration 2 and 3, the model switches to qwen mid-conversation. Different models interpret tool results differently → inconsistent synthesis.
3. **Uneven load** — Groq free tier gives per-model limits. We waste qwen's 10K TPM and scout's 30K TPM while llama is overloaded.

## Solution

Two changes to `GroqProvider`:

### 1. Round-Robin Model Ordering

Instead of always starting with llama-70b, rotate the starting model each request:

```
Request 1: try [llama-70b, qwen3-32b, scout-17b]
Request 2: try [qwen3-32b, scout-17b, llama-70b]
Request 3: try [scout-17b, llama-70b, qwen3-32b]
```

Each model gets primary traffic 1/N of the time. The existing cascade (budget check → API call → on-error-try-next) stays unchanged — we just change the ORDER in which models are tried.

### 2. Per-Request Model Pinning

Within a single user request (ReAct loop = multiple `llm_chat()` calls), pin to the model that succeeded on iteration 1. Subsequent iterations skip round-robin rotation and go directly to the pinned model.

If the pinned model rate-limits mid-conversation, cascade to the next model and pin to THAT one for remaining iterations.

## Architecture

### New: `RoundRobinPool` (in `backend/agents/providers/groq.py` or new file)

```python
class RoundRobinPool:
    """Thread-safe rotating model selector."""

    def __init__(self, models: list[str]) -> None
    def ordered_models(self) -> list[str]  # rotates start position
```

~30 lines. Thread-safe via `threading.Lock`. Counter wraps modulo len(models).

### Modified: `GroqProvider`

- Accept `round_robin: bool = True` in constructor
- `chat()` method uses `pool.ordered_models()` instead of `self._models` directly
- New `pin_model(model: str)` / `reset_pin()` methods

### Modified: `LLMClient`

- New `reset_pin()` method that delegates to the active provider
- Called at the start of each new user request

### Modified: Chat router (`backend/routers/chat.py`)

- `llm_chat` is a lambda closure at line 353: `lambda msgs, tls: llm_client.chat(...)`
- LLMClient is at `request.app.state.llm_client` (set in main.py line 305)
- Call `llm_client.reset_pin()` before entering the react loop (before line 348)

### Note: Model list comes from DB

Models are loaded from `llm_model_config` DB table via `ModelConfigLoader` (main.py lines 174-191), NOT from config.py. The round-robin pool takes whatever models are already configured.

## Config

```python
# backend/config.py
GROQ_ROUND_ROBIN: bool = True  # disable for sequential mode (existing sequential behavior)
```

No model list config needed — models already come from DB via `ModelConfigLoader`.

## Scope

### In scope
- RoundRobinPool class with thread safety
- Integration into GroqProvider.chat()
- Per-request pinning (pin on first success, reset between requests)
- Config toggle
- Unit tests (rotation, thread safety, pinning)

### Out of scope
- Token budget changes (already works)
- Progressive compression (future, if needed)
- Synthesis-specific pool (we don't have a separate synthesis path)
- BYO user keys
- Observability changes (existing `_record_cascade` / `_record_success` cover it)

## Existing Infrastructure (no changes needed)

| Component | Status | Notes |
|-----------|--------|-------|
| `TokenBudget` | ✓ exists | Redis-backed, per-model can_afford/record |
| `ProviderHealth` | ✓ exists | mark_exhausted with TTL recovery |
| `_classify_error` | ✓ exists | Distinguishes rate_limit/auth/timeout |
| `_record_cascade` obs | ✓ exists | Already logs which model cascaded |
| `AllModelsExhaustedError` | ✓ exists | Raised when all fail → LLMClient cascades to Anthropic |

## Acceptance Criteria

- [ ] Round-robin rotates models correctly (unit test: 3 calls cycle through all positions)
- [ ] Thread safety: 50 concurrent calls produce valid rotations
- [ ] Pinning: within a mocked ReAct loop, same model used for all iterations
- [ ] Cascade still works: if pinned model rate-limits, next model is tried and pinned
- [ ] Config: `GROQ_ROUND_ROBIN=false` reverts to sequential mode
- [ ] No regression: existing chat + tool tests pass unchanged
