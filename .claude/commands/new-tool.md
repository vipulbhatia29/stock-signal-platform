Create a new agent tool called $ARGUMENTS for the stock signal platform:

1. Read existing tools in `backend/tools/` to understand the pattern (especially `registry.py`)
2. Create `backend/tools/$ARGUMENTS.py` with:
   - A @tool decorated function (LangChain style) with type hints and Google docstring
   - Pydantic v2 input/output models if the tool has complex inputs
   - Proper error handling that returns useful error messages to the agent
   - Async implementation if it involves I/O (database, network)
3. Register the new tool in `backend/tools/registry.py`
4. Create `tests/unit/test_$ARGUMENTS.py` with at least 3 tests:
   - Happy path with valid input
   - Edge case (empty data, missing fields, etc.)
   - Error handling (invalid ticker, network failure, etc.)
5. Run the tests: `uv run pytest tests/unit/test_$ARGUMENTS.py -v`
6. Fix any failures before reporting done
7. Update PROGRESS.md with what was built
