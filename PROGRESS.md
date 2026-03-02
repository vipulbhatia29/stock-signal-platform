# Progress Log

Track what was built in each Claude Code session.

---

## Session 1 — Project Scaffolding

**Date:** TBD
**Branch:** `feat/initial-scaffold`
**What was done:**
- [ ] Project directory structure created
- [ ] uv initialized with core dependencies
- [ ] Docker Compose with Postgres+TimescaleDB and Redis
- [ ] SQLAlchemy async engine + Alembic setup
- [ ] Base models (User, Stock, StockPrice)
- [ ] FastAPI app skeleton with health check
- [ ] pytest conftest with fixtures
- [ ] Verify: `docker compose up -d` → `uv run pytest` → all green

**Next:** Signal engine (Phase 1 continued)
