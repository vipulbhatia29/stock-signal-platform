"""Unit test fixtures — CI-only db_url override.

Locally, tests use testcontainers (root conftest.py) so the dev DB is never touched.
In CI, we override db_url to read CI_DATABASE_URL from GitHub Actions secrets.
"""

import os

import pytest

# Only override db_url when running in CI — otherwise the root conftest's
# testcontainers fixture provides an ephemeral database automatically.
if os.environ.get("CI"):

    @pytest.fixture(scope="session")
    def db_url() -> str:
        """Use CI service container database instead of testcontainers."""
        url = os.environ.get("CI_DATABASE_URL")
        if not url:
            pytest.fail(
                "CI=true but CI_DATABASE_URL not set. Configure it in GitHub Actions secrets."
            )
        return url
