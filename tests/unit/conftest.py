"""Unit test fixtures — CI-only db_url override + DB-fixture guardrail.

Locally, tests use testcontainers (root conftest.py) so the dev DB is never touched.
In CI, we override db_url to read DATABASE_URL set by the GitHub Actions workflow.

IMPORTANT: No load_dotenv() here — that was the original KAN-58 bug.
"""

import os

import pytest

# Only override db_url when running in CI — otherwise the root conftest's
# testcontainers fixture provides an ephemeral database automatically.
if os.environ.get("CI"):

    @pytest.fixture(scope="session")
    def db_url() -> str:
        """Use CI service container database instead of testcontainers."""
        url = os.environ.get("DATABASE_URL")
        if not url:
            pytest.fail(
                "CI=true but DATABASE_URL not set. "
                "Configure CI_DATABASE_URL in GitHub Actions secrets."
            )
        return url


# ---------------------------------------------------------------------------
# Guardrail: ban DB-hitting fixtures from tests/unit/
# ---------------------------------------------------------------------------
# The root conftest.py provides `client` and `authenticated_client` fixtures
# that hit a real database via httpx + the FastAPI app. Under pytest-xdist
# (tests/unit/ runs with -n auto), multiple workers share one DB, and the
# per-test TRUNCATE teardown in the `client` fixture races with sibling
# workers still running tests — causing flaky data loss or, historically,
# "relation does not exist" errors when combined with the DROP teardown.
#
# Tests that need an HTTP client backed by a real DB are integration tests
# and belong in tests/api/ (which runs sequentially, no xdist).
#
# These overrides fail loudly at fixture setup time with an actionable
# message so regressions can't sneak in.


@pytest.fixture
def client():
    """Guardrail — DB-hitting client fixture is banned under tests/unit/."""
    pytest.fail(
        "The `client` fixture hits the real database and races with "
        "sibling xdist workers under tests/unit/. Move this test to "
        "tests/api/ where tests run sequentially."
    )


@pytest.fixture
def authenticated_client():
    """Guardrail — DB-hitting authenticated_client fixture is banned under tests/unit/."""
    pytest.fail(
        "The `authenticated_client` fixture hits the real database and "
        "races with sibling xdist workers under tests/unit/. Move this "
        "test to tests/api/ where tests run sequentially."
    )


@pytest.fixture
def db_session():
    """Guardrail — DB-hitting db_session is banned under tests/unit/.

    tests/unit/ runs with pytest-xdist -n auto. Multiple workers share
    one Postgres instance; per-test TRUNCATE teardown races with sibling
    workers still running tests. Tests that need a real DB belong in
    tests/api/ (sequential).
    """
    pytest.fail(
        "The `db_session` fixture hits the real database and races with "
        "sibling xdist workers under tests/unit/. Move this test to "
        "tests/api/ where tests run sequentially."
    )


# ---------------------------------------------------------------------------
# Singleton cleanup — resets task_tracer module singletons after every test
# so stale references don't bleed across tests that patch them.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_observability_singletons():
    """Reset task_tracer singletons after each test.

    Prevents stale LangfuseService / ObservabilityCollector references from
    leaking between tests that patch these singletons. The guard added in
    Fix 9 (trace_task raises RuntimeError when not initialised) makes this
    cleanup critical — without it, a test that sets the singleton and then
    crashes before teardown would leave it set for the next test.
    """
    yield
    from backend.services.observability import task_tracer

    task_tracer.set_langfuse_service(None)
    task_tracer.set_observability_collector(None)
