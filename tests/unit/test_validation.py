"""Tests for backend.validation — centralized input validation types."""

import pytest

from backend.validation import (
    TICKER_RE,
    ConfidenceLevel,
    MacdState,
    RsiState,
    SignalAction,
)


class TestTickerRegex:
    """TICKER_RE should accept valid stock tickers and reject invalid ones."""

    @pytest.mark.parametrize(
        "ticker",
        ["AAPL", "MSFT", "BRK.B", "BRK-B", "A", "T", "GOOG", "SPY", "QQQ", "VTI"],
    )
    def test_valid_tickers(self, ticker: str) -> None:
        assert TICKER_RE.match(ticker), f"Expected '{ticker}' to be valid"

    @pytest.mark.parametrize(
        "ticker",
        [
            "",  # empty
            "AVERYLONGTICKER",  # >10 chars
            "AAPL MSFT",  # space
            "$AAPL",  # dollar sign
            "AA@PL",  # at sign
            "AA PL",  # space in middle
            "AAPL!",  # exclamation
        ],
    )
    def test_invalid_tickers(self, ticker: str) -> None:
        assert not TICKER_RE.match(ticker), f"Expected '{ticker}' to be invalid"

    def test_caret_allowed(self) -> None:
        """Caret is allowed for index symbols like ^GSPC."""
        assert TICKER_RE.match("^GSPC")


class TestSignalEnums:
    """Signal enum values must match what the database stores."""

    def test_rsi_states(self) -> None:
        assert set(RsiState) == {RsiState.OVERSOLD, RsiState.NEUTRAL, RsiState.OVERBOUGHT}
        assert RsiState.OVERSOLD.value == "OVERSOLD"

    def test_macd_states(self) -> None:
        assert set(MacdState) == {MacdState.BULLISH, MacdState.BEARISH, MacdState.NEUTRAL}
        assert MacdState.BULLISH.value == "BULLISH"

    def test_signal_actions(self) -> None:
        expected = {"BUY", "WATCH", "AVOID", "HOLD", "SELL"}
        assert {a.value for a in SignalAction} == expected

    def test_confidence_levels(self) -> None:
        expected = {"HIGH", "MEDIUM", "LOW"}
        assert {c.value for c in ConfidenceLevel} == expected

    def test_enums_are_string_subclass(self) -> None:
        """Enums extending (str, Enum) compare equal to their string values."""
        assert RsiState.OVERSOLD == "OVERSOLD"
        assert MacdState.BULLISH == "BULLISH"
        assert SignalAction.BUY == "BUY"
