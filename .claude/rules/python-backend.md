---
paths:
  - "backend/**/*.py"
---
# Backend Python Rules

- Every function must have type hints and a Google-style docstring
- Use Pydantic v2 BaseModel for request/response schemas (in schemas/ directory)
- Use SQLAlchemy 2.0 mapped_column style, not legacy Column()
- Import order: stdlib, third-party, local (enforced by ruff)
- Use `logging.getLogger(__name__)` for logging, never bare `print()`
- All database queries go through SQLAlchemy async session, never raw SQL
- Raise HTTPException with appropriate status codes, never return error dicts (see Hard Rule #10 for str(e) policy)
- Avoid N+1 queries: never execute DB queries inside a loop — batch with `WHERE ticker IN (...)` or `DISTINCT ON`
- Use `asyncio.gather()` for parallel I/O (external API calls, `asyncio.to_thread` wrappers) — never sequential loops
- Router files should stay under ~500 lines — split into sub-routers when they grow beyond this
