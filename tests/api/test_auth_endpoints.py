"""Auth API endpoint tests — register, login, logout, refresh, and token behaviour.

This test suite covers the authentication router endpoints defined in
backend/routers/auth.py.  Each class maps to one endpoint, and each test
method covers a distinct scenario (happy-path, validation, auth-required).

NOTE: The current auth.py only implements the four core endpoints
(register / login / logout / refresh).  Tests for extended endpoints
(verify-email, forgot-password, OAuth, admin) are marked xfail so they
are tracked but do not block CI until the features land.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import settings
from backend.dependencies import hash_password
from backend.models.user import User, UserPreference, UserRole

# ---------------------------------------------------------------------------
# Module-level test credential constants (not real credentials — CI only)
# ---------------------------------------------------------------------------
_TP = "ValidPass1"  # noqa: S105


async def _register(client: AsyncClient, email: str, pw: str) -> dict:
    """Register a user and return the response JSON."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": pw},
    )
    return resp.json()


async def _login(client: AsyncClient, email: str, pw: str) -> dict:
    """Login and return the response JSON."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": pw},
    )
    return resp.json()


async def _register_and_login(client: AsyncClient, email: str, pw: str) -> dict:
    """Register then login; return the login response JSON (token pair)."""
    await _register(client, email, pw)
    return await _login(client, email, pw)


# ===========================================================================
# POST /api/v1/auth/register
# ===========================================================================


class TestRegisterEndpoint:
    """Tests for POST /api/v1/auth/register."""

    async def test_register_success_returns_201(self, client: AsyncClient) -> None:
        """Valid registration returns 201 with user data."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "new@example.com", "password": _TP},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "new@example.com"
        assert "id" in data
        assert "password" not in data
        assert "hashed_password" not in data

    async def test_register_success_creates_user_with_uuid(self, client: AsyncClient) -> None:
        """Registered user receives a valid UUID id field."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "uuid@example.com", "password": _TP},
        )
        assert resp.status_code == 201
        uuid.UUID(resp.json()["id"])  # raises if not valid UUID

    async def test_register_duplicate_email_returns_409(self, client: AsyncClient) -> None:
        """Registering the same email twice returns 409 Conflict."""
        payload = {"email": "dupe@example.com", "password": _TP}
        await client.post("/api/v1/auth/register", json=payload)
        resp = await client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 409

    async def test_register_duplicate_email_detail_mentions_registered(
        self, client: AsyncClient
    ) -> None:
        """409 detail message mentions that the email is already registered."""
        payload = {"email": "dupe2@example.com", "password": _TP}
        await client.post("/api/v1/auth/register", json=payload)
        resp = await client.post("/api/v1/auth/register", json=payload)
        detail = resp.json()["detail"].lower()
        assert "already" in detail or "registered" in detail

    async def test_register_weak_password_no_uppercase_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Password without uppercase letter returns 422."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "weak@example.com", "password": "nouppercase1"},
        )
        assert resp.status_code == 422

    async def test_register_weak_password_no_digit_returns_422(self, client: AsyncClient) -> None:
        """Password without a digit returns 422."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "weak2@example.com", "password": "NoDigitsHere"},
        )
        assert resp.status_code == 422

    async def test_register_password_too_short_returns_422(self, client: AsyncClient) -> None:
        """Password shorter than 8 characters returns 422."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "short@example.com", "password": "Ab1"},
        )
        assert resp.status_code == 422

    async def test_register_missing_email_returns_422(self, client: AsyncClient) -> None:
        """Missing email field returns 422."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"password": _TP},
        )
        assert resp.status_code == 422

    async def test_register_missing_password_returns_422(self, client: AsyncClient) -> None:
        """Missing password field returns 422."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "nopass@example.com"},
        )
        assert resp.status_code == 422

    async def test_register_invalid_email_format_returns_422(self, client: AsyncClient) -> None:
        """Non-email string in email field returns 422."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": _TP},
        )
        assert resp.status_code == 422


# ===========================================================================
# POST /api/v1/auth/login
# ===========================================================================


class TestLoginEndpoint:
    """Tests for POST /api/v1/auth/login."""

    async def test_login_success_returns_token_pair(self, client: AsyncClient) -> None:
        """Valid credentials return access_token and refresh_token."""
        await _register(client, "login@example.com", _TP)
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "login@example.com", "password": _TP},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data.get("token_type") == "bearer"

    async def test_login_sets_httponly_cookies(self, client: AsyncClient) -> None:
        """Login response sets httpOnly cookies for browser-based auth."""
        await _register(client, "cookies@example.com", _TP)
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "cookies@example.com", "password": _TP},
        )
        assert resp.status_code == 200
        headers = resp.headers.get_list("set-cookie")
        assert any("access_token" in h for h in headers)
        assert any("httponly" in h.lower() for h in headers)

    async def test_login_wrong_password_returns_401(self, client: AsyncClient) -> None:
        """Wrong password returns 401 Unauthorized."""
        await _register(client, "wrongpass@example.com", _TP)
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "wrongpass@example.com", "password": "WrongPass9"},
        )
        assert resp.status_code == 401

    async def test_login_nonexistent_user_returns_401(self, client: AsyncClient) -> None:
        """Unknown email returns 401 (no user enumeration)."""
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@example.com", "password": _TP},
        )
        assert resp.status_code == 401

    async def test_login_inactive_user_returns_401(self, client: AsyncClient, db_url: str) -> None:
        """Disabled (is_active=False) user cannot log in."""
        engine = create_async_engine(db_url, echo=False)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        email = "inactive@example.com"
        async with session_factory() as session:
            user = User(
                email=email,
                hashed_password=hash_password(_TP),
                is_active=False,
            )
            session.add(user)
            await session.flush()  # populate user.id before FK reference
            pref = UserPreference(user_id=user.id)
            session.add(pref)
            await session.commit()
        await engine.dispose()

        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": _TP},
        )
        assert resp.status_code == 401

    async def test_login_missing_password_returns_422(self, client: AsyncClient) -> None:
        """Missing password field in login request returns 422."""
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "partial@example.com"},
        )
        assert resp.status_code == 422

    async def test_login_no_user_enumeration(self, client: AsyncClient) -> None:
        """Wrong password and unknown user return the same 401 (no enumeration)."""
        await _register(client, "existing@example.com", _TP)

        resp_known = await client.post(
            "/api/v1/auth/login",
            json={"email": "existing@example.com", "password": "WrongPass9"},
        )
        resp_unknown = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "WrongPass9"},
        )
        assert resp_known.status_code == resp_unknown.status_code == 401


# ===========================================================================
# POST /api/v1/auth/logout
# ===========================================================================


class TestLogoutEndpoint:
    """Tests for POST /api/v1/auth/logout."""

    async def test_logout_returns_204(self, client: AsyncClient) -> None:
        """Logout returns 204 No Content."""
        resp = await client.post("/api/v1/auth/logout")
        assert resp.status_code == 204

    async def test_logout_clears_auth_cookies(self, client: AsyncClient) -> None:
        """Logout response deletes the auth cookies."""
        resp = await client.post("/api/v1/auth/logout")
        assert resp.status_code == 204
        set_cookie_headers = resp.headers.get_list("set-cookie")
        cookie_names = [h.split("=")[0] for h in set_cookie_headers]
        assert "access_token" in cookie_names
        assert "refresh_token" in cookie_names

    async def test_logout_without_auth_succeeds(self, client: AsyncClient) -> None:
        """Logout is idempotent — works even when not logged in."""
        resp = await client.post("/api/v1/auth/logout")
        assert resp.status_code == 204

    async def test_logout_twice_succeeds(self, client: AsyncClient) -> None:
        """Calling logout twice does not error."""
        await _register(client, "double_logout@example.com", _TP)
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "double_logout@example.com", "password": _TP},
        )
        assert login_resp.status_code == 200

        assert (await client.post("/api/v1/auth/logout")).status_code == 204
        assert (await client.post("/api/v1/auth/logout")).status_code == 204


# ===========================================================================
# POST /api/v1/auth/refresh
# ===========================================================================


class TestRefreshEndpoint:
    """Tests for POST /api/v1/auth/refresh."""

    async def test_refresh_with_valid_token_returns_new_pair(self, client: AsyncClient) -> None:
        """Valid refresh token returns a new access+refresh pair."""
        tokens = await _register_and_login(client, "refresh@example.com", _TP)
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_refresh_updates_cookies(self, client: AsyncClient) -> None:
        """Refresh endpoint updates auth cookies."""
        tokens = await _register_and_login(client, "refresh_cookie@example.com", _TP)
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert resp.status_code == 200
        headers = resp.headers.get_list("set-cookie")
        assert any("access_token" in h for h in headers)

    async def test_refresh_with_access_token_returns_401(self, client: AsyncClient) -> None:
        """Using an access token where a refresh token is expected returns 401."""
        tokens = await _register_and_login(client, "refresh_wrong@example.com", _TP)
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["access_token"]},  # wrong type
        )
        assert resp.status_code == 401

    async def test_refresh_with_garbage_token_returns_401(self, client: AsyncClient) -> None:
        """Random string in refresh_token field returns 401."""
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "this.is.garbage"},
        )
        assert resp.status_code == 401

    async def test_refresh_with_tampered_token_returns_401(self, client: AsyncClient) -> None:
        """JWT with modified payload (bad signature) returns 401."""
        tokens = await _register_and_login(client, "tamper@example.com", _TP)
        tampered = tokens["refresh_token"] + "X"
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tampered},
        )
        assert resp.status_code == 401

    async def test_refresh_expired_token_returns_401(self, client: AsyncClient) -> None:
        """Expired refresh token returns 401."""
        past = datetime.now(timezone.utc) - timedelta(days=1)
        expired_token = jwt.encode(
            {"sub": str(uuid.uuid4()), "exp": past, "type": "refresh"},
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": expired_token},
        )
        assert resp.status_code == 401

    async def test_refresh_missing_field_returns_422(self, client: AsyncClient) -> None:
        """Missing refresh_token field returns 422."""
        resp = await client.post("/api/v1/auth/refresh", json={})
        assert resp.status_code == 422


# ===========================================================================
# GET /api/v1/auth/me  (xfail — not yet implemented)
# ===========================================================================


class TestMeEndpoint:
    """Tests for GET /api/v1/auth/me (extended auth endpoints)."""

    @pytest.mark.xfail(reason="GET /me not yet implemented in auth router", strict=False)
    async def test_me_returns_current_user(self, client: AsyncClient) -> None:
        """Authenticated GET /me returns current user profile."""
        tokens = await _register_and_login(client, "me@example.com", _TP)
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "me@example.com"

    @pytest.mark.xfail(reason="GET /me not yet implemented in auth router", strict=False)
    async def test_me_without_auth_returns_401(self, client: AsyncClient) -> None:
        """GET /me without a token returns 401."""
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401


# ===========================================================================
# Extended endpoints (xfail until features land)
# ===========================================================================


class TestVerifyEmailEndpoint:
    """Tests for POST /api/v1/auth/verify-email."""

    @pytest.mark.xfail(reason="verify-email endpoint not yet implemented", strict=False)
    async def test_valid_token_verifies_email(self, client: AsyncClient) -> None:
        """Valid verification token marks the user as verified."""
        resp = await client.post(
            "/api/v1/auth/verify-email",
            json={"token": "valid-verification-token"},
        )
        assert resp.status_code == 200

    @pytest.mark.xfail(reason="verify-email endpoint not yet implemented", strict=False)
    async def test_expired_token_returns_400(self, client: AsyncClient) -> None:
        """Expired verification token returns 400."""
        resp = await client.post(
            "/api/v1/auth/verify-email",
            json={"token": "expired-token"},
        )
        assert resp.status_code == 400

    @pytest.mark.xfail(reason="verify-email endpoint not yet implemented", strict=False)
    async def test_already_verified_is_idempotent(self, client: AsyncClient) -> None:
        """Already-verified user returns 200 or 409 (idempotent)."""
        resp = await client.post(
            "/api/v1/auth/verify-email",
            json={"token": "valid-already-verified"},
        )
        assert resp.status_code in (200, 409)


class TestForgotPasswordEndpoint:
    """Tests for POST /api/v1/auth/forgot-password."""

    @pytest.mark.xfail(reason="forgot-password endpoint not yet implemented", strict=False)
    async def test_known_email_returns_200(self, client: AsyncClient) -> None:
        """Known email triggers reset and returns 200 (no enumeration)."""
        await _register(client, "forgot@example.com", _TP)
        resp = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "forgot@example.com"},
        )
        assert resp.status_code == 200

    @pytest.mark.xfail(reason="forgot-password endpoint not yet implemented", strict=False)
    async def test_unknown_email_also_returns_200(self, client: AsyncClient) -> None:
        """Unknown email also returns 200 to prevent user enumeration."""
        resp = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "nobody@example.com"},
        )
        assert resp.status_code == 200


class TestChangePasswordEndpoint:
    """Tests for POST /api/v1/auth/change-password."""

    @pytest.mark.xfail(reason="change-password endpoint not yet implemented", strict=False)
    async def test_change_password_success(self, client: AsyncClient) -> None:
        """Valid current password allows changing to a new password."""
        tokens = await _register_and_login(client, "changepw@example.com", _TP)
        resp = await client.post(
            "/api/v1/auth/change-password",
            json={"old_password": _TP, "new_password": "NewPass2"},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 200

    @pytest.mark.xfail(reason="change-password endpoint not yet implemented", strict=False)
    async def test_change_password_wrong_old_returns_401(self, client: AsyncClient) -> None:
        """Wrong current password returns 401."""
        tokens = await _register_and_login(client, "changepw2@example.com", _TP)
        resp = await client.post(
            "/api/v1/auth/change-password",
            json={"old_password": "WrongOld9", "new_password": "NewPass2"},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 401


class TestGoogleOAuthEndpoints:
    """Tests for Google OAuth endpoints."""

    @pytest.mark.xfail(reason="Google OAuth not yet implemented", strict=False)
    async def test_google_authorize_returns_redirect_url(self, client: AsyncClient) -> None:
        """GET /google/authorize returns a redirect URL with state parameter."""
        resp = await client.get("/api/v1/auth/google/authorize")
        assert resp.status_code in (200, 302)

    @pytest.mark.xfail(reason="Google OAuth not yet implemented", strict=False)
    async def test_google_unlink_success(self, client: AsyncClient) -> None:
        """Authenticated POST /google/unlink succeeds (or 400 if no password set)."""
        tokens = await _register_and_login(client, "unlink@example.com", _TP)
        resp = await client.post(
            "/api/v1/auth/google/unlink",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code in (200, 400)

    @pytest.mark.xfail(reason="Google OAuth not yet implemented", strict=False)
    async def test_google_unlink_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """POST /google/unlink without auth returns 401."""
        resp = await client.post("/api/v1/auth/google/unlink")
        assert resp.status_code == 401


class TestAdminAuthEndpoints:
    """Tests for admin-only auth endpoints."""

    @pytest.mark.xfail(reason="Admin auth endpoints not yet implemented", strict=False)
    async def test_admin_verify_email_success(self, client: AsyncClient, db_url: str) -> None:
        """Admin can force-verify a user's email."""
        engine = create_async_engine(db_url, echo=False)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        target_user_id = uuid.uuid4()
        async with session_factory() as session:
            admin = User(
                email="adminve@example.com",
                hashed_password=hash_password(_TP),
                role=UserRole.ADMIN,
            )
            session.add(admin)
            target = User(
                id=target_user_id,
                email="target@example.com",
                hashed_password=hash_password(_TP),
            )
            session.add(target)
            await session.commit()
        await engine.dispose()

        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "adminve@example.com", "password": _TP},
        )
        token = login_resp.json()["access_token"]
        resp = await client.post(
            f"/api/v1/auth/admin/verify-email/{target_user_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    @pytest.mark.xfail(reason="Admin auth endpoints not yet implemented", strict=False)
    async def test_non_admin_verify_email_returns_403(self, client: AsyncClient) -> None:
        """Non-admin user attempting admin endpoint receives 403."""
        tokens = await _register_and_login(client, "regular@example.com", _TP)
        some_id = uuid.uuid4()
        resp = await client.post(
            f"/api/v1/auth/admin/verify-email/{some_id}",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 403
