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
