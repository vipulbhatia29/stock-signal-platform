---
description: Intelligent review routing — score changes, auto-select depth and personas, present recommendation to PM
---

# Review Configuration

When `superpowers:requesting-code-review` is invoked, score the changes and recommend the appropriate review depth. Always present the score and recommendation — PM decides whether to skip, adjust, or proceed.

## Step 1: Score the Change

| Dimension | 1 (Low) | 3 (Medium) | 5 (High) |
|-----------|---------|------------|----------|
| **lines_changed** | < 30 lines | 30–150 lines | 150+ lines |
| **risk_surface** | Internal/logging/comments | Existing behavior change | New API contract, auth flow, DB schema, or data model |
| **cross_module** | 1–2 files in same module | 3–5 files across 2 modules | 6+ files or 3+ modules or new infrastructure |

**Total = lines_changed + risk_surface + cross_module** (range 3–15)

## Step 2: Route by Score

| Score | Depth | What Happens |
|-------|-------|-------------|
| **3–6** | **Skip** | No formal review. Lint + tests + Semgrep are sufficient. Present: "Review score X/15 — recommend skip. Lint/tests/Semgrep all green. Commit? (or force review)" |
| **7–10** | **Quick** | 1–2 personas, inline in conversation (no agent dispatch). Opus reads the diff and reviews from those perspectives. Present: "Review score X/15 — quick review with [Persona A, Persona B]. Proceed?" |
| **11–15** | **Full** | Full agent-dispatched review, 1 round, personas auto-selected per Step 3. Present: "Review score X/15 — full 5-persona review. Adjust personas or add a round?" |

## Step 3: Select Personas by Change Type

Detect which file categories changed and map to the right reviewers. When multiple categories apply, merge pools and pick the top N (no duplicates), prioritizing the category with the most changed lines.

### Change Type → Persona Mapping

| Change Type | Detection Pattern | Personas (ordered by priority) |
|-------------|------------------|-------------------------------|
| **API / Routers** | `backend/routers/`, `backend/observability/routers/` | 1. Staff Full-Stack Engineer (does frontend integration break?), 2. API Designer (contract consistency), 3. Security Engineer (auth guards, IDOR) |
| **Backend Services** | `backend/services/`, `backend/agents/`, `backend/tools/` | 1. Staff Backend Architect (design patterns, error handling), 2. Performance Engineer (N+1, caching, async) |
| **Models / Migrations** | `backend/models/`, `alembic/versions/` | 1. Staff Data Engineer (schema design, indexes, constraints), 2. Middleware Engineer (ORM mapping, migration safety, rollback) |
| **Auth / Security** | `backend/auth/`, `backend/dependencies.py`, JWT/OAuth files | 1. Security Engineer (OWASP, token handling), 2. Cryptography Expert (key management, timing attacks) |
| **Frontend Components** | `frontend/src/components/`, `frontend/src/app/` | 1. UX Engineer (usability, responsiveness), 2. Accessibility Expert (WCAG, keyboard nav), 3. Frontend Architect (state, performance) |
| **Frontend API / Hooks** | `frontend/src/lib/`, `frontend/src/hooks/` | 1. Staff Full-Stack Engineer (API contract alignment), 2. Frontend Architect (error handling, caching) |
| **Schemas / Types** | `backend/schemas/`, `frontend/src/types/` | 1. API Designer (contract stability, backwards compat), 2. Staff Full-Stack Engineer (serialization, validation) |
| **CI / Infra / Docker** | `.github/workflows/`, `docker-compose*`, `Dockerfile*` | 1. DevOps Engineer (pipeline correctness), 2. Security Engineer (secret handling, image hardening) |
| **Celery / Tasks** | `backend/tasks/` | 1. Staff Backend Architect (idempotency, retry, ordering), 2. Reliability Engineer (failure modes, monitoring) |
| **Spec / Plan docs** | `docs/superpowers/specs/`, `docs/superpowers/plans/` | 1. PM (requirements coverage, acceptance criteria), 2. Staff Architect (feasibility, scope) |
| **Config / Settings** | `backend/config.py`, `.env*`, `pyproject.toml` | 1. DevOps Engineer (env parity), 2. Security Engineer (secret exposure) |

### Persona Count by Depth

| Depth | Persona Count | Selection Rule |
|-------|--------------|----------------|
| **Skip** | 0 | No personas — automated checks only |
| **Quick** | 1–2 | Top priority persona from primary change type + 1 from secondary (if exists) |
| **Full** | 3–5 | Top 2 from primary change type + top 1 from each secondary type (cap at 5) |

## Step 4: Present the Recommendation

Always show this to the PM before proceeding:

```
Review score: X/15 (lines: X, risk: X, cross-module: X)
Change types: [API, Backend Services, ...]
Recommendation: [Skip / Quick / Full]
Personas: [list, or "none — automated checks sufficient"]
[Proceed? / Commit? / Adjust?]
```

## Round Control

- Default: **1 round** always
- Second round: only if first round found **Critical-severity** issues AND PM approves
- Never run 3+ rounds

## Override Rules

- PM can always force a higher depth ("force review" on a skip, "full review" on a quick)
- PM can always force a lower depth ("skip review" on a full) — but Opus should flag if risk_surface ≥ 4
- Phase-end review (via `/phase-closeout`) always runs Full regardless of score — it includes additional dimensions from `phase-end-review.md`

## Examples

| Scenario | Lines | Risk | Cross | Score | Depth | Personas |
|----------|:-----:|:----:|:-----:|:-----:|-------|----------|
| Fix `str(e)` in one file | 1 | 1 | 1 | **3** | Skip | — |
| Scope analytics to user-only | 1 | 3 | 1 | **5** | Skip | — |
| Split health endpoint + add auth | 3 | 3 | 1 | **7** | Quick | Security Engineer |
| New API router + service + tests | 3 | 5 | 3 | **11** | Full | API Designer, Backend Architect, Security Engineer |
| Auth overhaul (OAuth + email verify) | 5 | 5 | 5 | **15** | Full | Security, Crypto, Full-Stack, PM, QA |
| Spec document review | 1 | 3 | 1 | **5** | Skip as code review, but PM review of spec content separately |
