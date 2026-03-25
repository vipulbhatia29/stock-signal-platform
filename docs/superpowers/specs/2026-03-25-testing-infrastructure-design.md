# Testing Infrastructure — Design Spec

**Date**: 2026-03-25
**Phase**: 6C
**Status**: Draft
**Depends on**: LLM Factory & Cascade (6A), Agent Observability (6B)

---

## 1. Problem Statement

The LLM Factory changes (Phase 6A + 6B) touch the entire agent pipeline — providers, client, graph, executor, synthesizer, admin routes. We need:

1. **New tests** for TokenBudget, GroqProvider cascade, ObservabilityCollector, admin endpoints
2. **Test cleanup** — remove V1-related tests, deduplicate (we already found one duplicate today)
3. **E2E expansion** — 7 Playwright tests is not enough to catch UI regressions from backend changes
4. **Test organization** — consistent directory structure for maintainability

Reference: aset-platform has a mature Playwright setup with Page Object Model (POM), auth fixtures, mock backend responses, screenshot/trace artifacts, and CI integration with 30+ E2E tests.

### Current Test Suite Inventory

| Directory | Files | Tests (approx) | Purpose |
|---|---|---|---|
| `tests/unit/` | 70 files | ~735 | Tools, models, schemas, agents (mocked) |
| `tests/api/` | 20 files | ~180 | FastAPI endpoints (testcontainers) |
| `tests/integration/` | 3 files | ~24 | MCP stdio subprocess |
| `tests/e2e/` | 1 file + eval | ~7 | Basic Playwright smoke |
| `frontend/src/__tests__/` | 23 files | ~107 | Jest component tests |
| **Total** | ~117 files | **~1,053** | |

---

## 2. New Tests for Phase 6A/6B Components

### 2.1 Token Budget (`tests/unit/agents/test_token_budget.py`)

| Test | What it verifies |
|---|---|
| `test_estimate_tokens_basic` | `len // 4 * 1.2` heuristic |
| `test_can_afford_under_threshold` | Returns True when usage < 80% |
| `test_can_afford_at_threshold` | Returns False at 80% TPM |
| `test_can_afford_rpm_limit` | RPM dimension checked |
| `test_can_afford_tpd_limit` | Daily token limit checked |
| `test_can_afford_rpd_limit` | Daily request limit checked |
| `test_record_updates_sliding_window` | Usage recorded, visible in next check |
| `test_sliding_window_expiry` | Old entries expire after window period |
| `test_unknown_model_allowed` | Models not in config are allowed (no limits) |
| `test_load_limits_from_config` | Limits populated from ModelConfig list |
| `test_concurrent_access` | Multiple async tasks don't corrupt state |

**Count: ~11 tests**

### 2.2 Groq Provider Cascade (`tests/unit/providers/test_groq_provider.py`)

| Test | What it verifies |
|---|---|
| `test_first_model_succeeds` | First model in cascade handles the call |
| `test_cascade_on_budget_exhausted` | Budget full → silently tries next model |
| `test_cascade_on_api_error` | `groq.APIError` → next model |
| `test_cascade_on_tool_call_failure` | "Failed to call a function" → next model |
| `test_cascade_on_status_error` | 500/503 → next model |
| `test_cascade_on_connection_error` | Network failure → next model |
| `test_all_models_exhausted_raises` | All Groq models fail → raises (LLMClient falls to Anthropic) |
| `test_records_cascade_event` | ObservabilityCollector.record_cascade called |
| `test_records_successful_request` | ObservabilityCollector.record_request called |
| `test_budget_record_after_success` | TokenBudget.record called with actual tokens |

**Count: ~10 tests**

### 2.3 LLM Client Tier Routing (`tests/unit/agents/test_llm_client_tiers.py`)

| Test | What it verifies |
|---|---|
| `test_tier_planner_uses_planner_providers` | `tier="planner"` routes to planner cascade |
| `test_tier_synthesizer_uses_synth_providers` | `tier="synthesizer"` routes to synth cascade |
| `test_no_tier_uses_default_providers` | No tier → default provider list |
| `test_tier_not_in_config_uses_default` | Unknown tier → falls back to default |
| `test_provider_failover_across_providers` | Groq fails entirely → Anthropic handles |
| `test_all_providers_failed_error` | All fail → `AllProvidersFailedError` |

**Count: ~6 tests**

### 2.4 Observability Collector (`tests/unit/agents/test_observability.py`)

| Test | What it verifies |
|---|---|
| `test_record_request_increments_count` | Per-model counter |
| `test_record_request_tracks_rpm` | Sliding window RPM |
| `test_record_cascade_increments_count` | Cascade counter |
| `test_cascade_log_bounded` | Deque maxlen=1000 |
| `test_tier_health_healthy` | 0 failures → "healthy" |
| `test_tier_health_degraded` | 1-3 failures → "degraded" |
| `test_tier_health_down` | 4+ failures → "down" |
| `test_tier_health_disabled` | Manual disable → "disabled" |
| `test_latency_stats_avg_p95` | Avg and p95 computation |
| `test_get_stats_returns_all_metrics` | Full stats dict |

**Count: ~10 tests**

### 2.5 Model Config & Admin (`tests/api/test_admin_llm.py`)

| Test | What it verifies |
|---|---|
| `test_list_models_returns_seed_data` | GET /admin/llm-models |
| `test_update_model_priority` | PATCH changes priority |
| `test_disable_model` | PATCH is_enabled=false |
| `test_reload_models` | POST /admin/llm-models/reload |
| `test_llm_metrics_endpoint` | GET /admin/llm-metrics |
| `test_tier_health_endpoint` | GET /admin/tier-health |
| `test_tier_toggle_endpoint` | POST /admin/tier-toggle |
| `test_llm_usage_endpoint` | GET /admin/llm-usage |
| `test_admin_requires_superuser` | 403 for non-superuser |

**Count: ~9 tests**

### 2.6 Tool Result Truncation (`tests/unit/agents/test_truncation.py`)

| Test | What it verifies |
|---|---|
| `test_small_result_unchanged` | Below limit → passthrough |
| `test_text_result_truncated` | Above limit → truncated with suffix |
| `test_json_array_truncated` | Long arrays → first 5 items |
| `test_error_result_never_truncated` | status="error" → full content |

**Count: ~4 tests**

### 2.7 Integration: Full Cascade Flow (`tests/integration/test_cascade_e2e.py`)

| Test | What it verifies |
|---|---|
| `test_plan_execute_synthesize_with_cascade` | Full V2 flow with mocked Groq models |
| `test_cascade_fallback_to_anthropic` | All Groq fail → Anthropic handles |
| `test_budget_exhaustion_triggers_cascade` | Budget full → next model |
| `test_observability_records_cascade` | Full flow writes to llm_call_log |
| `test_tool_results_truncated_for_synthesizer` | Synthesizer gets truncated results |

**Count: ~5 tests**

**Total new tests: ~55-65**

---

## 3. Test Suite Cleanup

### 3.1 V1 Test Removal

| File | Action | Reason |
|---|---|---|
| `tests/unit/agents/test_agent_graph.py` | **Delete** | Tests V1 `build_agent_graph` |
| `tests/unit/test_agent_graph.py` | **Delete** | Duplicate of above |
| Any test importing `AGENT_V2` | **Update** | Remove flag references |
| Any test importing `backend.agents.graph` (V1) | **Update** | Point to `graph_v2` |

### 3.2 Deduplication

Scan for duplicate test files (like the `test_internal_tools.py` we found today). Run:
```bash
# Find files with identical names across test directories
find tests -name "*.py" | xargs -I{} basename {} | sort | uniq -d
```

### 3.3 Test Reorganization

Move any misplaced test files into the correct subdirectory:

```
tests/unit/
├── agents/           # Agent pipeline: planner, executor, synthesizer, entity registry
│   ├── test_token_budget.py      # NEW
│   ├── test_observability.py     # NEW
│   └── ... (existing)
├── providers/        # NEW directory — LLM provider tests
│   ├── test_groq_provider.py     # NEW (cascade, error handling)
│   └── test_llm_client.py       # MOVED from agents/ (+ new tier routing tests)
├── tools/            # Existing — no changes
├── models/           # Existing — no changes
├── schemas/          # Existing — no changes
└── adversarial/      # Existing — no changes
```

---

## 4. Playwright E2E Expansion

### 4.1 Setup: Page Object Model

Adopt aset's POM pattern for maintainability.

**New directory structure:**

```
tests/e2e/
├── playwright.config.ts
├── fixtures/
│   └── auth.fixture.ts           # JWT token from storageState
├── pages/
│   ├── base.page.ts              # Abstract: goto(), loc(), tid(), waitForLoaderGone()
│   ├── login.page.ts             # Login form interactions
│   ├── dashboard.page.ts         # Dashboard tiles, refresh, navigation
│   ├── stock-detail.page.ts      # Stock detail sections
│   ├── chat.page.ts              # Chat panel: send, receive, tool steps
│   └── screener.page.ts          # Screener table
├── setup/
│   └── auth.setup.ts             # Login once → save storageState
├── tests/
│   ├── auth/
│   │   ├── login.spec.ts         # Login flow, validation
│   │   └── logout.spec.ts        # Logout, token cleared
│   ├── dashboard/
│   │   ├── home.spec.ts          # Tiles render, scores display, refresh works
│   │   └── navigation.spec.ts    # Sidebar routes, transitions
│   ├── chat/
│   │   ├── chat.spec.ts          # Send message, response streams, tool steps visible
│   │   └── chat-error.spec.ts    # Backend error → graceful message (not "internal error")
│   ├── stocks/
│   │   ├── detail.spec.ts        # Signal cards, chart, fundamentals, forecast, dividends
│   │   └── screener.spec.ts      # Table loads, sort, filter
│   └── errors/
│       └── network-error.spec.ts # Backend down → error state
└── utils/
    ├── api.helper.ts             # Seed data via API
    ├── auth.helper.ts            # Read cached JWT token
    └── selectors.ts              # Shared data-testid constants
```

### 4.2 Playwright Config

```typescript
// Key settings (adapted from aset)
export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  retries: process.env.CI ? 2 : 1,
  workers: 3,
  use: {
    headless: true,
    screenshot: "only-on-failure",
    trace: "on-first-retry",
    video: "retain-on-failure",
    baseURL: "http://localhost:3000",
  },
  projects: [
    { name: "setup", testMatch: /.*\.setup\.ts/, testDir: "./setup" },
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], storageState: ".auth/user.json" },
      dependencies: ["setup"],
    },
  ],
  // webServer starts services for local dev only.
  // CI starts services in a separate step and sets reuseExistingServer: true via env.
  webServer: [
    { command: "uv run uvicorn backend.main:app --port 8181", url: "http://localhost:8181/api/v1/health", timeout: 60_000, reuseExistingServer: !process.env.CI },
    { command: "cd frontend && npm run dev", url: "http://localhost:3000", timeout: 60_000, reuseExistingServer: !process.env.CI },
  ],
});
```

### 4.3 Key Patterns from aset

- **Auth setup project** runs first, logs in, saves `storageState` to `.auth/user.json`. All tests reuse it — no login per test.
- **Mock backend responses** via `page.route("**/chat/stream", ...)` — E2E tests don't depend on real LLM calls. Tests verify UI behavior, not LLM quality.
- **`data-testid` attributes** on key UI elements — tests use `page.getByTestId()` not fragile CSS selectors.
- **Serial mode for chat tests** — `test.describe.configure({ mode: "serial" })` because chat state carries between tests.

### 4.4 E2E Test Coverage

| Test File | Tests | What it covers |
|---|---|---|
| `login.spec.ts` | 3 | Login form, validation, redirect to dashboard |
| `logout.spec.ts` | 2 | Logout button, token cleared, redirect to login |
| `home.spec.ts` | 4 | Dashboard loads, tiles render, scores displayed, refresh works |
| `navigation.spec.ts` | 3 | Sidebar links, route transitions, active state |
| `chat.spec.ts` | 5 | Send message, response appears, tool steps visible, multi-turn, agent selector |
| `chat-error.spec.ts` | 2 | Backend error → graceful message, not raw error |
| `detail.spec.ts` | 3 | Stock detail sections render (signals, chart, fundamentals) |
| `screener.spec.ts` | 3 | Table loads, column sort, click navigates to detail |
| `network-error.spec.ts` | 2 | Backend unreachable → appropriate error state |

**Total: ~27 new E2E tests** (up from 7)

---

## 5. CI Integration

### 5.1 Updated Workflow: `.github/workflows/ci-pr.yml`

Add E2E job that runs on `develop` PRs (not every push — too slow):

```yaml
e2e:
  runs-on: ubuntu-latest
  timeout-minutes: 15
  needs: [backend-test, frontend-test]  # only if unit tests pass
  steps:
    - uses: actions/checkout@v6
    - uses: actions/setup-node@v6
    - name: Install Playwright
      run: cd tests/e2e && npm ci && npx playwright install --with-deps chromium
    - name: Cache Playwright browsers
      uses: actions/cache@v4
      with:
        path: ~/.cache/ms-playwright
        key: pw-${{ runner.os }}-${{ hashFiles('tests/e2e/package-lock.json') }}
    - name: Start services
      run: |
        # Start backend + frontend, wait for health checks
    - name: Run E2E tests
      run: cd tests/e2e && npx playwright test
    - name: Upload report
      if: always()
      uses: actions/upload-artifact@v4
      with:
        name: playwright-report
        path: tests/e2e/playwright-report
        retention-days: 14
    - name: Upload traces on failure
      if: failure()
      uses: actions/upload-artifact@v4
      with:
        name: playwright-traces
        path: tests/e2e/test-results
        retention-days: 7
```

### 5.2 Frontend Component Tests

Add `data-testid` attributes to key components as needed for E2E selectors. This is done during E2E test authoring, not as a separate task.

---

## 6. Implementation Sequencing

| Story | Scope | Depends on | Effort |
|---|---|---|---|
| **S1** | Unit tests: TokenBudget, GroqProvider cascade, LLMClient tiers | Phase 6A code | ~2h |
| **S2** | Unit tests: ObservabilityCollector, admin endpoints | Phase 6B code | ~2h |
| **S3** | Test cleanup: delete V1 tests, deduplicate, reorganize directories | Phase 6A (V1 removal) | ~1h |
| **S4** | Integration test: full cascade with mocked providers | S1 + S2 | ~2h |
| **S5** | Playwright POM setup: config, base page, auth fixture, helpers | Independent | ~3h |
| **S6** | E2E tests: all spec files (auth, dashboard, chat, stocks, errors) | S5 | ~4h |
| **S7** | CI workflow: E2E job, artifact upload, caching | S6 | ~1h |

**Total: ~15h across 7 stories**

---

## 7. Success Criteria

- [ ] 55+ new unit/integration tests for Phase 6A/6B components
- [ ] All V1-related tests deleted or updated
- [ ] No duplicate test files
- [ ] Test directories reorganized (providers/ subdirectory)
- [ ] Playwright POM structure with auth fixtures
- [ ] 25+ E2E tests covering auth, dashboard, chat, stocks, errors
- [ ] E2E tests mock backend responses (no real LLM dependency)
- [ ] CI runs E2E on develop PRs with artifact upload
- [ ] Total test count: ~1,100+ (from ~1,053)

---

## 8. Out of Scope

- Performance/load testing → future
- Visual regression testing (screenshot comparison) → future
- Mobile viewport E2E tests → future
- E2E tests for admin panel → future (admin UI not built yet)
