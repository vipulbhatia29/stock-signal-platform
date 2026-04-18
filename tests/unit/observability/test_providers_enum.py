"""Unit tests for ExternalProvider and ErrorReason enums.

Validates membership, value correctness, and string-enum behaviour so that
schema changes to the provider list are caught immediately.
"""

from __future__ import annotations

import pytest

from backend.observability.instrumentation.providers import ErrorReason, ExternalProvider


def test_external_provider_enum_covers_10_providers() -> None:
    """ExternalProvider must enumerate exactly the 10 known external services."""
    names = {p.value for p in ExternalProvider}
    assert names == {
        "yfinance",
        "finnhub",
        "edgar",
        "fred",
        "google_news",
        "openai",
        "anthropic",
        "groq",
        "resend",
        "google_oauth",
    }


def test_error_reason_enum_has_expected_values() -> None:
    """ErrorReason must enumerate exactly 8 failure classifications."""
    assert len(ErrorReason) == 8
    assert ErrorReason.RATE_LIMIT_429.value == "rate_limit_429"


def test_external_provider_is_str_enum() -> None:
    """ExternalProvider values must be plain strings for JSON / DB serialisation."""
    assert isinstance(ExternalProvider.OPENAI.value, str)
    assert ExternalProvider.OPENAI == "openai"


def test_error_reason_is_str_enum() -> None:
    """ErrorReason values must be plain strings for JSON / DB serialisation."""
    assert isinstance(ErrorReason.TIMEOUT.value, str)
    assert ErrorReason.TIMEOUT == "timeout"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("yfinance", ExternalProvider.YFINANCE),
        ("anthropic", ExternalProvider.ANTHROPIC),
        ("google_oauth", ExternalProvider.GOOGLE_OAUTH),
    ],
)
def test_external_provider_round_trip(value: str, expected: ExternalProvider) -> None:
    """ExternalProvider must reconstruct from its string value (DB round-trip)."""
    assert ExternalProvider(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("rate_limit_429", ErrorReason.RATE_LIMIT_429),
        ("circuit_open", ErrorReason.CIRCUIT_OPEN),
        ("auth_failure", ErrorReason.AUTH_FAILURE),
    ],
)
def test_error_reason_round_trip(value: str, expected: ErrorReason) -> None:
    """ErrorReason must reconstruct from its string value (DB round-trip)."""
    assert ErrorReason(value) == expected
