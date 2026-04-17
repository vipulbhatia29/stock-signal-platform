"""Tests for bootstrap.build_client_from_settings() target selection."""

import pytest

from backend.observability.bootstrap import build_client_from_settings
from backend.observability.targets.internal_http import InternalHTTPTarget


@pytest.mark.parametrize(
    "url,secret",
    [
        (None, None),
        (None, "s3cret"),
        ("http://localhost:8181", None),
    ],
    ids=["both-none", "url-missing", "secret-missing"],
)
def test_bootstrap_internal_http_requires_url_and_secret(monkeypatch, url, secret):
    """internal_http raises RuntimeError when URL or secret is missing."""
    monkeypatch.setattr("backend.config.settings.OBS_TARGET_TYPE", "internal_http")
    monkeypatch.setattr("backend.config.settings.OBS_TARGET_URL", url)
    monkeypatch.setattr("backend.config.settings.OBS_INGEST_SECRET", secret)
    with pytest.raises(RuntimeError, match="OBS_TARGET_URL"):
        build_client_from_settings()


def test_bootstrap_internal_http_happy_path(monkeypatch, tmp_path):
    """internal_http with valid URL+secret creates InternalHTTPTarget."""
    monkeypatch.setattr("backend.config.settings.OBS_TARGET_TYPE", "internal_http")
    monkeypatch.setattr("backend.config.settings.OBS_TARGET_URL", "http://localhost:8181")
    monkeypatch.setattr("backend.config.settings.OBS_INGEST_SECRET", "s3cret")
    monkeypatch.setattr("backend.config.settings.OBS_SPOOL_ENABLED", False)
    monkeypatch.setattr("backend.config.settings.OBS_SPOOL_DIR", str(tmp_path))
    client = build_client_from_settings()
    assert isinstance(client._target, InternalHTTPTarget)
