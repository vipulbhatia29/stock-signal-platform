"""Pydantic v2 schemas for authentication endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserRegisterRequest(BaseModel):
    """Registration request body."""

    email: EmailStr
    password: str = Field(min_length=8, description="Minimum 8 chars, 1 uppercase, 1 digit")


class UserRegisterResponse(BaseModel):
    """Registration response."""

    id: uuid.UUID
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserLoginRequest(BaseModel):
    """Login request body."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT token pair response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenRefreshRequest(BaseModel):
    """Token refresh request body."""

    refresh_token: str


class UserProfileResponse(BaseModel):
    """Authenticated user's profile."""

    id: uuid.UUID
    email: str
    role: str
    is_active: bool
    email_verified: bool = False


# --- Auth Overhaul Schemas ---


class ForgotPasswordRequest(BaseModel):
    """Forgot password request."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Reset password with token."""

    token: str
    new_password: str = Field(min_length=8, description="Min 8 chars, 1 uppercase, 1 digit")


class ChangePasswordRequest(BaseModel):
    """Change password (requires current password)."""

    current_password: str
    new_password: str = Field(min_length=8, description="Min 8 chars, 1 uppercase, 1 digit")


class SetPasswordRequest(BaseModel):
    """Set password for Google-only users (no current password)."""

    new_password: str = Field(min_length=8, description="Min 8 chars, 1 uppercase, 1 digit")


class DeleteAccountRequest(BaseModel):
    """Delete account request."""

    confirmation: str = Field(description='Must be "DELETE"')
    password: str | None = None


class VerifyEmailRequest(BaseModel):
    """Verify email with token."""

    token: str


class AdminRecoverAccountRequest(BaseModel):
    """Admin: recover deleted account."""

    new_email: EmailStr


class AccountInfoResponse(BaseModel):
    """Account info for settings page."""

    id: uuid.UUID
    email: str
    email_verified: bool
    has_password: bool
    google_linked: bool
    google_email: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str
