"""Tests for auth dependencies: password hashing, JWT tokens."""

import uuid

import pytest
from freezegun import freeze_time

from backend.dependencies import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    """Tests for bcrypt password hashing."""

    def test_hash_and_verify(self) -> None:
        """Hashed password should verify correctly."""
        password = "TestPassword1"
        hashed = hash_password(password)
        assert verify_password(password, hashed)

    def test_wrong_password_fails(self) -> None:
        """Wrong password should not verify."""
        hashed = hash_password("CorrectPass1")
        assert not verify_password("WrongPass1", hashed)

    def test_hash_is_unique(self) -> None:
        """Same password should produce different hashes (salt)."""
        h1 = hash_password("SamePass1")
        h2 = hash_password("SamePass1")
        assert h1 != h2


class TestJWTTokens:
    """Tests for JWT creation and decoding."""

    def test_create_and_decode_access_token(self) -> None:
        """Access token round-trips correctly."""
        user_id = uuid.uuid4()
        token = create_access_token(user_id)
        decoded_id = decode_token(token, expected_type="access")
        assert decoded_id == user_id

    def test_create_and_decode_refresh_token(self) -> None:
        """Refresh token round-trips correctly."""
        user_id = uuid.uuid4()
        token = create_refresh_token(user_id)
        decoded_id = decode_token(token, expected_type="refresh")
        assert decoded_id == user_id

    def test_access_token_rejected_as_refresh(self) -> None:
        """Access token should not decode as refresh type."""
        from fastapi import HTTPException

        user_id = uuid.uuid4()
        token = create_access_token(user_id)
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token, expected_type="refresh")
        assert exc_info.value.status_code == 401

    def test_refresh_token_rejected_as_access(self) -> None:
        """Refresh token should not decode as access type."""
        from fastapi import HTTPException

        user_id = uuid.uuid4()
        token = create_refresh_token(user_id)
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token, expected_type="access")
        assert exc_info.value.status_code == 401

    def test_invalid_token_raises(self) -> None:
        """Garbage token should raise 401."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            decode_token("not.a.valid.token", expected_type="access")
        assert exc_info.value.status_code == 401

    @freeze_time("2026-03-01 12:00:00")
    def test_expired_access_token(self) -> None:
        """Expired access token should raise 401."""
        from fastapi import HTTPException

        user_id = uuid.uuid4()
        token = create_access_token(user_id)

        # Jump forward past expiry
        with freeze_time("2026-03-02 12:00:00"):
            with pytest.raises(HTTPException) as exc_info:
                decode_token(token, expected_type="access")
            assert exc_info.value.status_code == 401
