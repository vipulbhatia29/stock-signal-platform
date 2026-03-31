"""Tests for PII sanitization utility."""

from __future__ import annotations

from backend.utils.sanitize import sanitize_summary


class TestSanitizeSummary:
    """Tests for sanitize_summary()."""

    def test_redacts_user_id_key(self) -> None:
        """Should redact user_id values."""
        data = {"user_id": "550e8400-e29b-41d4-a716-446655440000", "ticker": "AAPL"}
        result = sanitize_summary(data)
        assert "[REDACTED]" in result
        assert "AAPL" in result
        assert "550e8400" not in result

    def test_redacts_email_key(self) -> None:
        """Should redact email field values."""
        result = sanitize_summary({"email": "user@example.com", "query": "analyze TSLA"})
        assert "[REDACTED]" in result
        assert "analyze TSLA" in result

    def test_redacts_password_key(self) -> None:
        """Should redact password values."""
        result = sanitize_summary({"password": "secret123", "action": "login"})
        assert "[REDACTED]" in result
        assert "secret123" not in result

    def test_redacts_nested_pii(self) -> None:
        """Should redact PII keys at all nesting levels."""
        result = sanitize_summary({"params": {"user_id": "abc-123", "ticker": "MSFT"}})
        assert "[REDACTED]" in result
        assert "MSFT" in result
        assert "abc-123" not in result

    def test_redacts_email_in_string_values(self) -> None:
        """Should redact email addresses found in string values."""
        result = sanitize_summary({"note": "Contact john@acme.com for details"})
        assert "[EMAIL]" in result
        assert "john@acme.com" not in result

    def test_preserves_financial_data(self) -> None:
        """Should preserve tickers, prices, dates — operational signal."""
        result = sanitize_summary({"ticker": "AAPL", "price": 185.50, "date": "2026-03-28"})
        assert "AAPL" in result
        assert "185.5" in result

    def test_truncates_to_max_length(self) -> None:
        """Should truncate output to max_length characters."""
        long_data = {"data": "x" * 500}
        result = sanitize_summary(long_data, max_length=100)
        assert len(result) <= 100

    def test_handles_none_input(self) -> None:
        """Should handle None input gracefully."""
        result = sanitize_summary(None)
        assert isinstance(result, str)
        assert len(result) <= 300

    def test_handles_plain_string(self) -> None:
        """Should handle plain non-JSON string input."""
        result = sanitize_summary("hello world")
        assert "hello world" in result

    def test_handles_non_serializable(self) -> None:
        """Should handle non-JSON-serializable input."""
        result = sanitize_summary(object())
        assert isinstance(result, str)
        assert len(result) <= 300

    def test_redacts_api_key(self) -> None:
        """Should redact api_key values."""
        result = sanitize_summary({"api_key": "sk-1234567890", "model": "gpt-4"})
        assert "[REDACTED]" in result
        assert "sk-1234567890" not in result

    def test_redacts_authorization_key(self) -> None:
        """Should redact authorization header values."""
        result = sanitize_summary({"authorization": "Bearer xyz", "status": "ok"})
        assert "[REDACTED]" in result

    def test_redacts_secret_key(self) -> None:
        """Should redact secret values."""
        result = sanitize_summary({"secret": "my-secret", "tool": "search"})
        assert "[REDACTED]" in result

    def test_redacts_token_key(self) -> None:
        """Should redact token values."""
        result = sanitize_summary({"token": "eyJhbGciOiJIUzI1NiJ9", "action": "auth"})
        assert "[REDACTED]" in result
        assert "eyJ" not in result
