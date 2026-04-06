# Reviewer Persona Mapping

Detect which file categories changed and map to the right reviewers. When multiple categories apply, merge pools and pick the top N (no duplicates), prioritizing the category with the most changed lines.

## Change Type to Persona Mapping

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
| **Tests** | `tests/` (new or significantly modified test files) | 1. Test Engineer (coverage gaps, mock overuse, edge cases, assertion quality) |
| **Spec / Plan docs** | `docs/superpowers/specs/`, `docs/superpowers/plans/` | 1. PM (requirements coverage, acceptance criteria), 2. Staff Architect (feasibility, scope) |
| **Config / Settings** | `backend/config.py`, `.env*`, `pyproject.toml` | 1. DevOps Engineer (env parity), 2. Security Engineer (secret exposure) |

## Persona Count by Depth

| Depth | Persona Count | Selection Rule |
|-------|--------------|----------------|
| **Skip** | 0 | No personas — automated checks only |
| **Quick** | 1-2 | Top priority persona from primary change type + 1 from secondary (if exists) |
| **Full** | 3-5 | Top 2 from primary change type + top 1 from each secondary type (cap at 5) |
