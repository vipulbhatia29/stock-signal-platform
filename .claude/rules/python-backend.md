---
paths:
  - "backend/**/*.py"
---
# Backend Python Rules

- Use async def for all FastAPI endpoints and database operations
- Every function must have type hints and a Google-style docstring
- Use Pydantic v2 BaseModel for request/response schemas (in schemas/ directory)
- Use SQLAlchemy 2.0 mapped_column style, not legacy Column()
- Import order: stdlib, third-party, local (enforced by ruff)
- Use structlog for logging, never print()
- All database queries go through SQLAlchemy async session, never raw SQL
- Raise HTTPException with appropriate status codes, never return error dicts
