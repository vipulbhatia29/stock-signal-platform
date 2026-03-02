Create a new API endpoint for $ARGUMENTS in the stock signal platform:

1. Read existing routers in `backend/routers/` to understand the pattern
2. Create or update the appropriate router file in `backend/routers/`
3. Create Pydantic v2 request/response schemas in `backend/schemas/`
4. Add the router to `backend/main.py` if it's a new file
5. Create `tests/api/test_$ARGUMENTS.py` with tests for:
   - Unauthenticated request → 401
   - Happy path with valid authenticated request → 200
   - Invalid input → 422
   - Not found (where applicable) → 404
6. Run the tests: `uv run pytest tests/api/test_$ARGUMENTS.py -v`
7. Fix any failures before reporting done
8. Update PROGRESS.md with what was built
