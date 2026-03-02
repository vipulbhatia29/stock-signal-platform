---
paths:
  - "tests/**/*.py"
---
# Testing Rules

- Every test function MUST have a docstring explaining what it tests
- Test naming: test_{what}_{condition}_{expected} (e.g., test_rsi_below_30_returns_oversold)
- Use factory-boy factories for test data, never raw dictionaries
- Integration tests MUST use testcontainers (real Postgres/Redis), never SQLite
- Use freezegun for any time-dependent tests (stock signals depend on dates)
- Use pytest.mark.asyncio for async tests
- Use pytest.mark.slow for tests that take >5 seconds
- Run the specific test file after writing: `uv run pytest {file} -v`
- Fix ALL failures before reporting the task as done
- Fixtures go in conftest.py at the appropriate level (tests/ or tests/unit/ etc.)
