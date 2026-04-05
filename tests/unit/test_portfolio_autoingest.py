"""Unit tests for portfolio transaction ticker format validation (KAN-404).

Tests the regex-based ticker format guard added to the create_transaction
endpoint. Full API flow with DB is covered by existing API tests.
"""

from __future__ import annotations

import re

import pytest

TICKER_REGEX = re.compile(r"^[A-Z]{1,5}$")


def is_valid_ticker(ticker: str) -> bool:
    """Return True if ticker matches the accepted format."""
    return bool(TICKER_REGEX.match(ticker))


# ---------------------------------------------------------------------------
# Valid tickers — should pass the format check
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ticker",
    [
        "AAPL",
        "F",
        "BRK",
        "TSLA",
        "GOOGL",
    ],
)
def test_valid_ticker_format(ticker: str) -> None:
    """Tickers of 1-5 uppercase ASCII letters should pass validation."""
    assert is_valid_ticker(ticker), f"Expected '{ticker}' to be valid"


# ---------------------------------------------------------------------------
# Invalid tickers — should be rejected by the format check
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ticker",
    [
        "INVALID123",  # contains digits
        "",  # empty string
        "TOOLONG",  # 7 characters — exceeds 5-letter cap
        "aapl",  # lowercase
        "AA PL",  # contains a space
        "AA.B",  # contains a dot (e.g., BRK.B uses a different representation)
        "123",  # digits only
        "ABCDEF",  # 6 letters — one too many
    ],
)
def test_invalid_ticker_format(ticker: str) -> None:
    """Tickers that don't match 1-5 uppercase letters should fail validation."""
    assert not is_valid_ticker(ticker), f"Expected '{ticker}' to be invalid"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_single_letter_ticker() -> None:
    """Single-letter tickers like 'F' (Ford) are valid."""
    assert is_valid_ticker("F")


def test_five_letter_ticker() -> None:
    """Five-letter tickers like 'GOOGL' are at the boundary and valid."""
    assert is_valid_ticker("GOOGL")


def test_six_letter_ticker_rejected() -> None:
    """Six-letter tickers exceed the 5-letter cap and must be rejected."""
    assert not is_valid_ticker("ABCDEF")


def test_lowercase_rejected() -> None:
    """Lowercase input should fail; callers must normalize to upper before matching."""
    assert not is_valid_ticker("aapl")
    assert not is_valid_ticker("Aapl")
