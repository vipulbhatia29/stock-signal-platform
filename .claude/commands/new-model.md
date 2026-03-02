Create a new database model for $ARGUMENTS in the stock signal platform:

1. Read existing models in `backend/models/` to understand the pattern
2. Create `backend/models/$ARGUMENTS.py` using SQLAlchemy 2.0 mapped_column style:
   - Inherit from the shared Base
   - Include created_at and updated_at timestamps
   - Use UUID primary key for user-facing models
   - Add __repr__ for debugging
   - Add proper indexes for common query patterns
   - If this is time-series data, note it should use TimescaleDB hypertable
3. Generate Alembic migration: `uv run alembic revision --autogenerate -m "add $ARGUMENTS table"`
4. Apply migration: `uv run alembic upgrade head`
5. Verify: `uv run alembic current`
6. Create a factory in `tests/conftest.py` or `tests/factories.py` using factory-boy
7. Write basic model tests in `tests/unit/test_model_$ARGUMENTS.py`
8. Run tests: `uv run pytest tests/unit/test_model_$ARGUMENTS.py -v`
9. Update PROGRESS.md with what was built
