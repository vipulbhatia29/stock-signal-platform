"""API test fixtures — CI-only db_url override.

Locally, tests use testcontainers (root conftest.py) so the dev DB is never touched.
In CI, we override db_url to read DATABASE_URL set by the GitHub Actions workflow.

IMPORTANT: No load_dotenv() here — that was the original KAN-58 bug.
The old conftest loaded .env which contained the dev DATABASE_URL, causing
drop_all to destroy dev tables on teardown.
"""

import os

import pytest

import backend.services.http_client as _http_mod
import backend.services.redis_pool as _redis_mod


@pytest.fixture(autouse=True)
async def _reset_shared_clients():
    """Reset shared clients between API tests to avoid stale event-loop references.

    Both httpx and Redis create connections bound to the current event loop.
    If not closed before the loop teardown, asyncio raises 'Event loop is closed'
    during the transport's call_connection_lost callback.
    """
    yield
    if _http_mod._client is not None:
        await _http_mod._client.aclose()
        _http_mod._client = None
    if _redis_mod._pool is not None:
        await _redis_mod._pool.aclose()
        _redis_mod._pool = None


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
