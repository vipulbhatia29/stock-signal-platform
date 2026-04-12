# Reference Tables (moved from CLAUDE.md to save context budget)

These were in CLAUDE.md but consumed ~80 lines on every interaction. Now loaded only when relevant.

## Services (local dev)

| Service | Command | Port |
|---|---|---|
| Backend | `uv run uvicorn backend.main:app --reload --port 8181` | 8181 |
| Frontend | `cd frontend && npm run dev` | 3000 |
| Postgres | `docker compose up -d postgres` | **5433** |
| Redis | `docker compose up -d redis` | **6380** |
| Celery worker | `uv run celery -A backend.tasks worker --loglevel=info` | — |
| Langfuse | `docker compose up -d langfuse-db langfuse-server` | **3001** |
| Langfuse DB | (auto with langfuse-server) | **5434** |
| Docs | `uv run mkdocs serve` | 8000 |

## Git Branching

```
main        ← production-ready, protected (ci-merge/build required)
develop     ← integration branch, protected (ci-pr/backend-test + frontend-test)
feat/KAN-*  ← Story branches → PR to develop
hotfix/KAN-* ← emergency fixes → PR to main + back-merge to develop
```

- **ALWAYS branch from `develop`**, never from `main`
- PR title: `[KAN-X] Summary`
- Never commit directly to main or develop
- Never skip hooks (`--no-verify`)
- `uv.lock` is committed — run `uv sync` after pulling

## Testing Conventions

- **Tier architecture** — T0-T5. Full spec: `docs/superpowers/specs/2026-04-01-test-suite-overhaul.md`
- **xdist for unit tests ONLY** — `pytest-xdist -n auto` on `tests/unit/`. API/integration tests run sequentially.
- **E2E against production build** — Playwright runs against `next build && next start`, never `next dev`.
- **Coverage at sprint end** — no hooks, no mid-edit checks. Before the PR, report coverage delta.
- **Semgrep custom rules** — `.semgrep/stock-signal-rules.yml`. Test rules in `tests/semgrep/`.
- **Hypothesis** — `max_examples=20` in CI, `200` in nightly.
- **Every bug fix gets a regression test** — `@pytest.mark.regression`.

## Sprint Documents

Specs: `docs/superpowers/specs/`. Plans: `docs/superpowers/plans/`. Archive: `docs/superpowers/archive/` (never read).
