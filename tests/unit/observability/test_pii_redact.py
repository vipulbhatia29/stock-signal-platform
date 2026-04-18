"""Tests for PII redaction utility."""

from unittest.mock import patch

from backend.observability.instrumentation.pii_redact import hash_email, redact_message, redact_url


class TestRedactUrl:
    def test_whitelisted_params_pass_through(self) -> None:
        """Whitelisted query params should not be redacted."""
        url = "https://example.com/api?ticker=AAPL&page=1&limit=20"
        result = redact_url(url)
        assert "ticker=AAPL" in result
        assert "page=1" in result
        assert "limit=20" in result

    def test_non_whitelisted_params_redacted(self) -> None:
        """Non-whitelisted query params should be replaced with REDACTED."""
        url = "https://example.com/api?email=user%40example.com&token=secret123"
        result = redact_url(url)
        assert "REDACTED" in result
        assert "secret123" not in result
        assert "user%40example.com" not in result

    def test_no_query_string_unchanged(self) -> None:
        """URLs without query strings should be returned unchanged."""
        url = "https://example.com/api/v1/stocks"
        result = redact_url(url)
        assert result == url

    def test_mixed_params(self) -> None:
        """Mixed safe and unsafe params: safe pass, unsafe redacted."""
        url = "https://example.com/search?q=apple&secret_token=abc&tab=overview"
        result = redact_url(url)
        assert "q=apple" in result
        assert "tab=overview" in result
        assert "REDACTED" in result
        assert "abc" not in result

    def test_redact_disabled_returns_unchanged(self) -> None:
        """When OBS_REDACT_PII is False, URL should be returned unchanged."""
        url = "https://example.com/api?password=secret&page=1"
        with patch("backend.observability.instrumentation.pii_redact.settings") as mock_settings:
            mock_settings.OBS_REDACT_PII = False
            result = redact_url(url)
        assert result == url


class TestRedactMessage:
    def test_email_redacted(self) -> None:
        """Email addresses in messages should be replaced with [EMAIL]."""
        msg = "User user@example.com failed login"
        result = redact_message(msg)
        assert "[EMAIL]" in result
        assert "user@example.com" not in result

    def test_jwt_redacted(self) -> None:
        """JWT tokens in messages should be replaced with [JWT]."""
        jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
            ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        msg = f"Invalid token: {jwt}"
        result = redact_message(msg)
        assert "[JWT]" in result
        assert jwt not in result

    def test_empty_string_unchanged(self) -> None:
        """Empty message should be returned unchanged."""
        result = redact_message("")
        assert result == ""

    def test_redact_disabled_returns_unchanged(self) -> None:
        """When OBS_REDACT_PII is False, message should be returned unchanged."""
        msg = "User user@example.com failed"
        with patch("backend.observability.instrumentation.pii_redact.settings") as mock_settings:
            mock_settings.OBS_REDACT_PII = False
            result = redact_message(msg)
        assert result == msg

    def test_safe_message_unchanged(self) -> None:
        """Messages with no PII should be returned unchanged."""
        msg = "Database connection timeout after 30s"
        result = redact_message(msg)
        assert result == msg


class TestHashEmail:
    def test_consistent_hash(self) -> None:
        """Same email should always produce the same hash."""
        email = "user@example.com"
        assert hash_email(email) == hash_email(email)

    def test_case_insensitive(self) -> None:
        """Email hashing should be case-insensitive."""
        assert hash_email("User@Example.COM") == hash_email("user@example.com")

    def test_returns_64_char_hex(self) -> None:
        """hash_email should return a 64-char hex string (SHA-256)."""
        result = hash_email("test@example.com")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_different_emails_different_hashes(self) -> None:
        """Different emails should produce different hashes."""
        assert hash_email("alice@example.com") != hash_email("bob@example.com")
