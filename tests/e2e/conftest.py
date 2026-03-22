"""E2E test fixtures — real user, portfolio, LLM key gating."""
import os

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip e2e tests if no LLM API key is available."""
    if not os.environ.get("GROQ_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
        skip_marker = pytest.mark.skip(reason="No LLM API key — skipping e2e tests")
        for item in items:
            item.add_marker(skip_marker)
