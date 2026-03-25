# Architecture Gaps — Future Backlog

**Date**: 2026-03-25
**Status**: Backlog — not specced for implementation
**Source**: Brainstorm session comparing SSP vs aset-platform + industry research

---

## Purpose

Documents architecture gaps identified during the Phase 6 brainstorm that are **not addressed in the active specs** (6A/6B/6C). Each item has enough context for future refinement without re-doing the analysis.

---

## Backlog Items

### B1: Redis Read Cache for API Responses

**Priority**: MEDIUM
**Effort**: ~1 sprint

**Gap**: aset has `CacheService` backed by Redis with TTL tiers (60s volatile, 300s stable, 30s admin). Dashboard endpoints check Redis first, fall through to DB on miss. Write-through invalidation on data changes.

**Our state**: Redis running (Celery broker + refresh token blocklist) but no API response caching. Every dashboard load hits Postgres.

**What to build**:
- `CacheService` class with `get()`, `set()`, `invalidate()` methods
- TTL tiers: volatile (watchlist, scores), stable (charts, fundamentals), admin (metrics)
- Decorator or middleware for cacheable endpoints
- Invalidation on ingest/signal computation

**Reference**: `aset-platform/backend/cache.py`

---

### B2: Cache Warmup on Startup

**Priority**: LOW
**Effort**: Bundle with B1

**Gap**: aset pre-warms shared cache keys (ticker registry, audit log) on startup. Per-ticker chart data warmed in background thread.

**What to build**: Warm top-N portfolio tickers and dashboard aggregates on startup. Background thread for non-blocking warmup.

**Reference**: `aset-platform/backend/cache_warmup.py`

---

### B3: Chat Audit Trail

**Priority**: LOW-MEDIUM
**Effort**: ~2-3 stories

**Gap**: aset persists complete chat session transcripts to their data layer (session_id, user, messages, agents used, timestamps). Queryable for debugging and compliance.

**Our state**: `ChatMessage` and `ChatSession` models exist. Messages are persisted during chat. But no audit-specific query endpoints or retention policies.

**What to build**:
- `GET /admin/audit/sessions` — list sessions with filtering (user, date range, agent type)
- `GET /admin/audit/sessions/{id}/messages` — full transcript
- Retention policy for old sessions

**Reference**: `aset-platform/backend/audit_routes.py`

---

### B4: Centralized Input Validation Module

**Priority**: LOW
**Effort**: ~1 story

**Gap**: aset has `validation.py` with reusable validators for tickers (`^[A-Za-z0-9^.\-]{1,15}$`), search queries (max 500 chars), batch sizes (max 50). Consistent error messages.

**Our state**: Validation is inline in routers and tools. Inconsistent patterns and error messages.

**What to build**:
- `backend/validation.py` with `validate_ticker()`, `validate_search_query()`, `validate_ticker_batch()`
- Apply at tool boundaries and router inputs
- Consistent error response format

**Reference**: `aset-platform/backend/validation.py`

---

### B5: Portfolio Aggregation Tool

**Priority**: MEDIUM
**Effort**: ~1 sprint

**Gap**: For "analyze my portfolio" with 100+ stocks, the agent shouldn't call tools 100 times. Need a backend aggregation tool that returns a pre-computed portfolio summary.

**What to build**:
- `PortfolioAnalysisTool` — reads pre-computed signals, fundamentals, forecasts from DB
- Computes: weighted composite score, sector allocation, top/bottom by score, risk metrics, drift alerts
- Returns one structured result (~2K tokens) instead of N individual tool calls
- Planner routes "analyze my portfolio" to this single tool

**Design notes from brainstorm**: This is a backend aggregation problem, not an LLM context problem. The heavy lifting happens in SQL/Python, not in the agent loop.

---

### B6: Google OAuth (SSO)

**Priority**: MEDIUM
**Effort**: ~1 sprint

**Gap**: aset has Google + Facebook OAuth via PKCE flow. We only have email/password JWT auth.

**What to build**:
- Google OAuth 2.0 with PKCE (authorization code flow)
- `GET /auth/oauth/authorize?provider=google` → redirect to Google consent
- `POST /auth/oauth/callback` → exchange code for tokens, create/link user
- `CachedJWKSClient` for Google ID token verification with TTL-based key rotation
- Frontend: "Sign in with Google" button on login page
- State token management (in-memory or Redis) for CSRF protection

**Not needed**: Facebook SSO (US market, not critical)

**Reference**: `aset-platform/auth/oauth_service.py`, `auth/endpoints/oauth_routes.py`

---

### B7: Subscription Tiering (Free/Pro/Premium)

**Priority**: LOW (after Google OAuth)
**Effort**: ~2 sprints
**Depends on**: B6 (Google OAuth)

**Gap**: aset has designed (draft) a 3-tier subscription system with Razorpay (India) + Stripe (international).

**What to build** (adapted for US):
- User model: `subscription_tier`, `subscription_status`, `subscription_start/end`, `stripe_customer_id`
- JWT claims: `subscription_tier`, `usage_remaining`
- Stripe integration: checkout sessions, webhook handlers, subscription lifecycle
- `SubscriptionGuard` dependency: check tier + quota before tool execution
- Quota enforcement: analyses/month, chats/day, forecast horizons per tier
- `llm_model_config` gets a `user_tier` filter column — route free users to cheap models, premium to quality models

**Reference**: `aset-platform/claudedocs/design_subscription_system_2026-03-15.md`

---

### B8: ML-Based Routing (RouteLLM)

**Priority**: LOW (need traffic data first)
**Effort**: Research + 1 sprint

**Gap**: Industry research shows ML-based routing (RouteLLM, Martian) achieves 2x cost reduction by classifying query complexity and routing to the cheapest capable model.

**Prerequisites**: Enough traffic data to train/fine-tune a classifier. Our `llm_call_log` table (from Phase 6B) will collect this data over time.

**When to revisit**: After 10K+ logged requests with quality signals (user feedback, confidence scores).

---

### B9: LiteLLM Adoption

**Priority**: LOW (evaluate when scaling to 5+ providers)
**Effort**: ~1 sprint to integrate

**Gap**: LiteLLM (17k+ GitHub stars) provides unified API across 100+ LLM providers with built-in fallbacks, retries, rate limits, and cost tracking. Our hand-rolled `LLMClient` works for 2-3 providers but would struggle at scale.

**When to revisit**: When we add providers beyond Groq + Anthropic (e.g., OpenAI, Google, Mistral, Cohere).

---

### B10: Anthropic Batch API for Nightly Pipeline

**Priority**: LOW-MEDIUM
**Effort**: ~2-3 stories

**Gap**: Anthropic's batch API offers 50% cost reduction for non-real-time workloads. Our Celery nightly pipeline (signal computation, forecasts) could use this.

**What to build**:
- Batch API client for Celery tasks that call Anthropic
- Submit batch → poll for results → process
- Only for nightly jobs, not real-time chat

---

## Priority Summary

| Priority | Items |
|---|---|
| **Do next** (after Phase 6) | B5 (Portfolio Aggregation), B1+B2 (Redis Cache) |
| **Medium term** | B6 (Google OAuth), B3 (Audit Trail), B10 (Batch API) |
| **When needed** | B4 (Validation), B7 (Subscriptions), B8 (ML Routing), B9 (LiteLLM) |
