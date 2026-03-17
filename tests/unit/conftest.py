"""Unit test fixtures — overrides root conftest db_url for CI compatibility."""

import os

import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture(scope="session")
def db_url() -> str:
    """Read DATABASE_URL from environment (CI service container or local .env).

    Overrides root conftest db_url which depends on testcontainers.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.fail(
            "DATABASE_URL not set. Set it in .env for local dev "
            "or as a CI secret for GitHub Actions."
        )
    return url
