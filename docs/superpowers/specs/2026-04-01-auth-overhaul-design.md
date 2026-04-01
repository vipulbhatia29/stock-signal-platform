# Auth Overhaul — Architecture & Design

**Date:** 2026-04-01
**Phase:** C — SaaS Auth Hardening
**Spec:** `2026-04-01-auth-overhaul-google-oauth.md`
**Status:** Design — reviewed, ready for implementation

---

## 1. System Architecture

### 1.1 OAuth Flow (Sequence)

```
Browser                    FastAPI Backend              Google          Redis
  │                             │                        │               │
  │  GET /auth/google/authorize │                        │               │
  │────────────────────────────>│                        │               │
  │                             │  store state+nonce     │               │
  │                             │───────────────────────>│               │
  │                             │                        │    oauth_state│
  │    302 → Google consent     │                        │    :{state}   │
  │<────────────────────────────│                        │               │
  │                             │                        │               │
  │  User consents at Google    │                        │               │
  │────────────────────────────>│                        │               │
  │                             │                        │               │
  │  GET /auth/google/callback  │                        │               │
  │  ?code=XXX&state=YYY       │                        │               │
  │────────────────────────────>│                        │               │
  │                             │  validate state        │               │
  │                             │<──────────────────────>│               │
  │                             │                        │               │
  │                             │  exchange code→tokens  │               │
  │                             │───────────────────────>│               │
  │                             │<──────────────────────│               │
  │                             │  validate nonce in ID token            │
  │                             │                        │               │
  │                             │  lookup/create user    │               │
  │                             │  link oauth_account    │               │
  │                             │  issue JWT cookies     │               │
  │                             │                        │               │
  │    302 → /dashboard         │                        │               │
  │    (Set-Cookie: access_token, refresh_token)         │               │
  │<────────────────────────────│                        │               │
```

### 1.2 Token Revocation Model

Current: JTI-based blocklist (single token).
New: **User-level revocation timestamp** (all tokens for a user).

```
Redis key: user_revocation:{user_id}
Value: ISO timestamp (e.g., "2026-04-01T12:00:00Z")
TTL: 7 days (REFRESH_TOKEN_EXPIRE_DAYS)

PREREQUISITE: Add `iat` claim to both create_access_token and create_refresh_token
(currently missing — tokens only have sub, exp, type, jti)

During token decode:
  1. Decode JWT → get user_id, iat (issued-at) — add iat to TokenPayload
  2. Check Redis: user_revocation:{user_id}
  3. If exists AND iat < revocation_timestamp → reject token
  4. Continue normal validation
```

Triggered by: password reset, password change, account deletion, admin recovery.

### 1.3 Email Verification Flow

```
Register → Celery task → Resend API → user inbox
                ↓ (dev mode)
           log token to console

Verify link: GET /auth/verify-email?token=XXX
  → renders minimal HTML page with JS auto-POST
  → POST /auth/verify-email {token}
  → validates Redis key email_verify:{token}
  → sets email_verified = TRUE
  → deletes Redis key
  → redirects to /dashboard with success toast
```

---

## 2. API Contracts

### 2.1 Google OAuth Endpoints

#### `GET /api/v1/auth/google/authorize`

Builds Google OAuth URL and redirects.

**Query params:** `next` (optional, URL to redirect after login, default `/dashboard`)

**Response:** `302 Redirect` to Google consent screen

**Redis side-effect:** Stores `oauth_state:{state}` → `{nonce, next_url}` (5-min TTL)

---

#### `GET /api/v1/auth/google/callback`

Handles Google's redirect. Exchanges code, creates/links user, sets cookies.

**Query params:** `code`, `state` (from Google)

**Success:** `302 Redirect` to `next_url` (from state) with cookies set

**Error responses:**
| Status | Detail | When |
|--------|--------|------|
| 400 | Invalid or expired session | Missing/invalid state |
| 400 | Google email not verified | Google `email_verified` = false |
| 409 | Google account linked to another user | `sub` already linked elsewhere |
| 502 | Google Sign-In temporarily unavailable | Google API error |

---

#### `POST /api/v1/auth/google/unlink`

Unlinks Google from authenticated user's account.

**Auth:** Required (JWT cookie)

**Request body:** None

**Response 200:**
```json
{ "message": "Google account unlinked" }
```

**Error responses:**
| Status | Detail | When |
|--------|--------|------|
| 400 | No Google account linked | No oauth_account row |
| 400 | Set a password before unlinking Google | No password, only auth method |

---

### 2.2 Email Verification Endpoints

#### `POST /api/v1/auth/verify-email`

Verifies email with token.

**Request body:**
```json
{ "token": "string" }
```

**Response 200:**
```json
{ "message": "Email verified" }
```

**Errors:** 400 (invalid/expired token)

---

#### `GET /api/v1/auth/verify-email`

Renders minimal HTML page that auto-POSTs the token (bot protection).

**Query params:** `token`

**Response:** HTML page with embedded JS

---

#### `POST /api/v1/auth/resend-verification`

Resends verification email.

**Auth:** Required

**Response 200:**
```json
{ "message": "Verification email sent" }
```

**Rate limit:** 3/hour

---

### 2.3 Password Reset Endpoints

#### `POST /api/v1/auth/forgot-password`

Initiates password reset. Always returns 200 (no email enumeration).

**Request body:**
```json
{ "email": "user@example.com" }
```

**Response 200:**
```json
{ "message": "If an account with that email exists, a reset link has been sent" }
```

**Rate limit:** 3/hour per email

---

#### `POST /api/v1/auth/reset-password`

Resets password with token.

**Request body:**
```json
{
  "token": "string",
  "new_password": "string (8+ chars, 1 upper, 1 digit)"
}
```

**Response 200:**
```json
{ "message": "Password reset. Please log in." }
```

**Side-effects:** Sets `user_revocation:{user_id}` in Redis (revokes all sessions)

**Errors:** 400 (invalid token), 422 (weak password)

---

### 2.4 Account Settings Endpoints

#### `POST /api/v1/auth/change-password`

For users WITH a password.

**Auth:** Required

**Request body:**
```json
{
  "current_password": "string",
  "new_password": "string"
}
```

**Response 200:**
```json
{ "message": "Password changed" }
```

**Side-effects:** Sets `user_revocation:{user_id}` (except current token re-issued)

**Errors:** 400 (wrong current password), 422 (weak new password)

**Rate limit:** 5/hour

---

#### `POST /api/v1/auth/set-password`

For Google-only users (no existing password).

**Auth:** Required

**Request body:**
```json
{ "new_password": "string" }
```

**Response 200:**
```json
{ "message": "Password set" }
```

**Errors:** 400 (password already set — use change-password), 422 (weak password)

**Rate limit:** 5/hour

---

#### `GET /api/v1/auth/account`

Returns account info for settings page.

**Auth:** Required

**Response 200:**
```json
{
  "id": "uuid",
  "email": "string",
  "email_verified": true,
  "has_password": true,
  "google_linked": true,
  "google_email": "user@gmail.com",
  "created_at": "2026-01-01T00:00:00Z"
}
```

---

### 2.5 Account Deletion Endpoints

#### `POST /api/v1/auth/delete-account`

Soft-deletes account.

**Auth:** Required

**Request body:**
```json
{
  "confirmation": "DELETE",
  "password": "string | null"
}
```

- `password` required if user has a password set; null for Google-only users

**Response 200:**
```json
{ "message": "Account scheduled for deletion" }
```

**Side-effects:** Sends deletion email, anonymizes, deactivates, revokes all tokens, clears cookies

**Errors:** 400 (wrong confirmation text), 401 (wrong password)

**Rate limit:** 3/hour

---

### 2.6 Admin Endpoints

#### `POST /api/v1/admin/users/{user_id}/verify-email`

**Auth:** Admin required

**Response 200:**
```json
{ "message": "Email verified for user {user_id}" }
```

---

#### `POST /api/v1/admin/users/{user_id}/recover`

Recovers soft-deleted account within 30-day window.

**Auth:** Admin required

**Request body:**
```json
{ "new_email": "user-new@example.com" }
```

**Response 200:**
```json
{ "message": "Account recovered. User must verify new email." }
```

**Errors:** 404 (user not found), 400 (not deleted or past 30-day window)

---

### 2.7 Modified Existing Endpoints

#### `POST /api/v1/auth/login` — Changes

Add guard for NULL password:
```python
if user.hashed_password is None:
    raise HTTPException(400, "No password set. Use Google Sign-In or set a password in Account Settings.")
```

Add differentiation for deleted accounts:
```python
if user.deleted_at is not None:
    raise HTTPException(401, "This account has been deleted. Contact support within 30 days to recover.")
if not user.is_active:
    raise HTTPException(401, "Account is disabled")
```

Add `method="password"` to LoginAttempt recording.

#### `POST /api/v1/auth/register` — Changes

- Send verification email via Celery task (or auto-verify in dev mode)
- Set `email_verified = False` (or True in dev mode)

#### `GET /api/v1/auth/me` — Changes

Add to response: `email_verified`, `has_password`, `google_linked`

---

## 3. Data Model — Migration Plan

### Migration 023: Auth overhaul schema changes

```python
"""023_auth_overhaul.py"""

# --- users table modifications ---
op.add_column("users", sa.Column("email_verified", sa.Boolean(), nullable=False, server_default="false"))
op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
op.alter_column("users", "hashed_password", nullable=True)  # Allow Google-only users

# Grandfather existing users as verified
op.execute("UPDATE users SET email_verified = true, email_verified_at = NOW()")

# --- oauth_account table ---
op.create_table(
    "oauth_accounts",
    sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
    sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    sa.Column("provider", sa.String(50), nullable=False),
    sa.Column("provider_sub", sa.String(255), nullable=False),
    sa.Column("provider_email", sa.String(255), nullable=True),
    sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
)
op.create_unique_constraint("uq_oauth_provider_sub", "oauth_accounts", ["provider", "provider_sub"])
op.create_unique_constraint("uq_oauth_user_provider", "oauth_accounts", ["user_id", "provider"])
op.create_index("ix_oauth_accounts_user_id", "oauth_accounts", ["user_id"])

# --- login_attempts table modifications ---
op.add_column("login_attempts", sa.Column("method", sa.String(20), nullable=False, server_default="password"))
op.add_column("login_attempts", sa.Column("provider_sub", sa.String(255), nullable=True))

# --- TECH DEBT FIX: chat_sessions FK missing ondelete CASCADE ---
op.drop_constraint("chat_sessions_user_id_fkey", "chat_sessions", type_="foreignkey")
op.create_foreign_key("chat_sessions_user_id_fkey", "chat_sessions", "users", ["user_id"], ["id"], ondelete="CASCADE")

# --- downgrade ---
def downgrade():
    op.drop_column("login_attempts", "provider_sub")
    op.drop_column("login_attempts", "method")
    op.drop_table("oauth_accounts")
    op.alter_column("users", "hashed_password", nullable=False)
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "email_verified")
```

**FK Cascade Audit** (verified against codebase):
| Table | Current FK ondelete | Status |
|-------|-------------------|--------|
| `oauth_accounts` | New — `CASCADE` | ✅ In migration |
| `user_preferences` | `CASCADE` | ✅ Already correct |
| `portfolios` | `CASCADE` | ✅ Already correct |
| `watchlists` | `CASCADE` | ✅ Already correct |
| `alerts` (InAppAlert) | `CASCADE` | ✅ Already correct |
| `chat_sessions` | **NONE (RESTRICT)** | ⚠️ **FIX in migration** — will block user delete |
| `recommendation_outcomes` | `CASCADE` | ✅ Already correct |
| `login_attempts` | `SET NULL` | ✅ Keep — preserves audit trail |

**Tech debt fix included:** ChatSession FK constraint altered to CASCADE in migration 023.

---

## 4. File-Level Component Design

### 4.1 New Backend Files

```
backend/
├── models/
│   └── oauth_account.py          # OAuthAccount model (NEW)
├── schemas/
│   └── auth.py                   # Extended with new request/response schemas (EDIT)
├── services/
│   ├── email.py                  # EmailService — Resend API wrapper (NEW)
│   ├── google_oauth.py           # GoogleOAuthService — token exchange, user info (NEW)
│   └── token_blocklist.py        # Add user-level revocation (EDIT)
├── routers/
│   └── auth.py                   # Add OAuth + verification + reset + settings endpoints (EDIT)
├── tasks/
│   └── audit.py                  # Add purge_deleted_accounts_task (EDIT)
├── config.py                     # Add GOOGLE_*, RESEND_*, EMAIL_FROM settings (EDIT)
└── dependencies.py               # Add require_verified_email, update CachedUser (EDIT)
```

### 4.2 New Frontend Files

```
frontend/src/
├── app/
│   ├── (authenticated)/
│   │   └── account/
│   │       ├── page.tsx                    # Account settings page (NEW)
│   │       └── _components/
│   │           ├── profile-section.tsx     # Email + verification status (NEW)
│   │           ├── security-section.tsx    # Change/set password (NEW)
│   │           ├── linked-accounts.tsx     # Google link/unlink (NEW)
│   │           └── danger-zone.tsx         # Account deletion (NEW)
│   ├── auth/
│   │   ├── verify-email/
│   │   │   └── page.tsx                   # Email verification landing (NEW)
│   │   ├── forgot-password/
│   │   │   └── page.tsx                   # Forgot password — enter email (NEW)
│   │   └── reset-password/
│   │       └── page.tsx                   # Reset password — enter new password (NEW)
│   ├── login/
│   │   └── page.tsx                       # Add Google button + forgot password link (EDIT)
│   └── register/
│       └── page.tsx                       # Add Google button (EDIT)
├── lib/
│   ├── api.ts                             # Add auth API functions (EDIT)
│   └── auth.ts                            # Update AuthContextValue (EDIT)
├── hooks/
│   └── use-current-user.ts                # Extend with email_verified, has_password, google_linked (EDIT)
├── components/
│   └── email-verification-banner.tsx      # Persistent banner for unverified users (NEW)
└── middleware.ts                           # Add public routes (EDIT)
```

### 4.3 Backend Component Details

#### `backend/models/oauth_account.py`

```python
class OAuthAccount(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "oauth_accounts"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # "google"
    provider_sub: Mapped[str] = mapped_column(String(255), nullable=False)  # Google sub (stable ID)
    provider_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="oauth_accounts")

    # ALSO ADD to User model (backend/models/user.py):
    # oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(
    #     back_populates="user", cascade="all, delete-orphan"
    # )

    __table_args__ = (
        UniqueConstraint("provider", "provider_sub", name="uq_oauth_provider_sub"),
        UniqueConstraint("user_id", "provider", name="uq_oauth_user_provider"),
    )
```

#### `backend/services/google_oauth.py`

```python
class GoogleOAuthService:
    """Handles Google OAuth 2.0 Authorization Code flow."""

    GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
    GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

    async def build_auth_url(self, redis: Redis) -> tuple[str, str]:
        """Build Google OAuth URL with state + nonce. Returns (url, state)."""

    async def exchange_code(self, code: str, state: str, redis: Redis) -> GoogleUserInfo:
        """Exchange auth code for tokens, validate state+nonce, extract user info."""

    async def _validate_id_token(self, id_token: str, nonce: str) -> dict:
        """Validate Google ID token via httpx + PyJWT (no authlib needed).
        Fetches Google's public keys, verifies signature + nonce."""
```

**GoogleUserInfo dataclass:**
```python
@dataclass
class GoogleUserInfo:
    sub: str           # Stable unique ID
    email: str
    email_verified: bool
    name: str | None
    picture: str | None
```

#### `backend/services/email.py`

```python
class EmailService:
    """Send transactional emails via Resend API."""

    async def send_verification_email(self, to: str, token: str) -> None:
        """Send email verification link."""

    async def send_password_reset_email(self, to: str, token: str) -> None:
        """Send password reset link."""

    async def send_password_reset_google_only(self, to: str) -> None:
        """Send 'you use Google' message for forgot-password."""

    async def send_deletion_confirmation(self, to: str) -> None:
        """Send account deletion confirmation."""

    def _send(self, to: str, subject: str, html: str) -> None:
        """Low-level send via Resend SDK. In dev mode, logs to console."""
```

#### `backend/services/token_blocklist.py` — Additions

```python
async def set_user_revocation(user_id: uuid.UUID, redis: Redis) -> None:
    """Set a user-level revocation timestamp. All tokens issued before this are invalid."""
    key = f"user_revocation:{user_id}"
    timestamp = datetime.now(timezone.utc).isoformat()
    ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400  # 7 days
    await redis.set(key, timestamp, ex=ttl)

async def check_user_revocation(user_id: uuid.UUID, token_iat: datetime, redis: Redis) -> bool:
    """Returns True if token is revoked (iat before revocation timestamp)."""
    key = f"user_revocation:{user_id}"
    revocation_ts = await redis.get(key)
    if revocation_ts is None:
        return False
    return token_iat < datetime.fromisoformat(revocation_ts.decode())
```

#### `backend/dependencies.py` — Changes

```python
# TokenPayload — add iat field
@dataclass(frozen=True)
class TokenPayload:
    user_id: uuid.UUID
    jti: str | None = None
    iat: datetime | None = None  # NEW — needed for revocation check

# CachedUser — add email_verified + has_password
class CachedUser(BaseModel):
    id: uuid.UUID
    email: str
    role: UserRole
    is_active: bool
    email_verified: bool    # NEW
    has_password: bool       # NEW — True if hashed_password is not None
    created_at: datetime
    updated_at: datetime

# Token creation — add iat to BOTH functions
def create_access_token(user_id: uuid.UUID) -> str:
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "access",
        "iat": datetime.now(timezone.utc),  # NEW — required for revocation
    }

def create_refresh_token(user_id: uuid.UUID) -> str:
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "iat": datetime.now(timezone.utc),  # NEW — required for revocation
    }

# decode_token — extract iat
def decode_token(token: str, expected_type: str = "access") -> TokenPayload:
    # ... existing validation ...
    iat_raw = payload.get("iat")
    iat = datetime.fromtimestamp(iat_raw, tz=timezone.utc) if iat_raw else None
    return TokenPayload(user_id=uuid.UUID(user_id_str), jti=payload.get("jti"), iat=iat)

# New dependency
def require_verified_email(user: User | CachedUser) -> User | CachedUser:
    """Raise 403 if user email is not verified."""
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Email verification required")
    return user

# get_current_user — add revocation check (async, fits existing pattern)
async def get_current_user(...) -> User | CachedUser:
    token_payload = decode_token(token)
    # After decoding, before cache/DB lookup:
    if token_payload.iat:
        if await check_user_revocation(token_payload.user_id, token_payload.iat, redis):
            raise HTTPException(401, "Session expired. Please log in again.")
    # ... rest of existing logic (cache → DB → return user)
```

#### `backend/schemas/auth.py` — New Schemas

```python
# --- New request schemas ---
class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)

class SetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8)

class DeleteAccountRequest(BaseModel):
    confirmation: str  # Must be "DELETE"
    password: str | None = None

class VerifyEmailRequest(BaseModel):
    token: str

class AdminRecoverAccountRequest(BaseModel):
    new_email: EmailStr

# --- New response schemas ---
class AccountInfoResponse(BaseModel):
    id: uuid.UUID
    email: str
    email_verified: bool
    has_password: bool
    google_linked: bool
    google_email: str | None
    created_at: datetime

class MessageResponse(BaseModel):
    message: str
```

#### `backend/config.py` — New Settings

```python
# --- Google OAuth ---
GOOGLE_CLIENT_ID: str = ""
GOOGLE_CLIENT_SECRET: str = ""
GOOGLE_OAUTH_REDIRECT_URI: str = "http://localhost:8181/api/v1/auth/google/callback"

# --- Email (Resend) ---
RESEND_API_KEY: str = ""
EMAIL_FROM_ADDRESS: str = "noreply@stocksignal.app"
```

#### `backend/tasks/audit.py` — New Task

```python
@celery_app.task(name="backend.tasks.audit.purge_deleted_accounts_task")
def purge_deleted_accounts_task() -> None:
    """Hard-delete users where deleted_at > 30 days ago."""
    asyncio.run(_purge_deleted_accounts_async())

async def _purge_deleted_accounts_async() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    async with async_session_factory() as session:
        # Find users past grace period
        result = await session.execute(
            select(User).where(User.deleted_at.isnot(None), User.deleted_at < cutoff)
        )
        users = result.scalars().all()
        for user in users:
            logger.info("Purging deleted user %s (deleted_at=%s)", user.id, user.deleted_at)
            await session.delete(user)  # CASCADE handles child records
        await session.commit()
        logger.info("Purged %d deleted accounts past 30-day grace period", len(users))
```

**Beat schedule addition:**
```python
"purge-deleted-accounts-daily": {
    "task": "backend.tasks.audit.purge_deleted_accounts_task",
    "schedule": crontab(hour=3, minute=15),  # 3:15 AM ET, after login purge
},
```

---

## 5. Frontend Component Details

### 5.1 Account Settings Page (`/account`)

```
┌─────────────────────────────────────────────────┐
│  Account Settings                                │
│                                                  │
│  ┌── Profile ──────────────────────────────────┐ │
│  │ Email: user@gmail.com                       │ │
│  │ Status: ✓ Verified  (or ⚠ Unverified [Resend]) │
│  └─────────────────────────────────────────────┘ │
│                                                  │
│  ┌── Security ─────────────────────────────────┐ │
│  │ [Change Password]  or  [Set Password]       │ │
│  │ (form with current + new + confirm)         │ │
│  └─────────────────────────────────────────────┘ │
│                                                  │
│  ┌── Linked Accounts ─────────────────────────┐ │
│  │ Google: user@gmail.com  [Unlink]            │ │
│  │   or                                        │ │
│  │ Google: Not linked  [Link Google Account]   │ │
│  └─────────────────────────────────────────────┘ │
│                                                  │
│  ┌── Danger Zone ──────────────────────────────┐ │
│  │ [Delete Account]                            │ │
│  │ → Opens modal with consequences,            │ │
│  │   password re-auth, type DELETE             │ │
│  └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

### 5.2 API Layer Additions (`frontend/src/lib/api.ts`)

```typescript
// --- Google OAuth ---
export function getGoogleAuthUrl(): string {
  return `${API_BASE}/auth/google/authorize`;
  // Browser navigates to this URL directly (not fetch)
}

// --- Email Verification ---
export function verifyEmail(token: string): Promise<void> {
  return post("/auth/verify-email", { token });
}

export function resendVerification(): Promise<void> {
  return post("/auth/resend-verification");
}

// --- Password Reset ---
export function forgotPassword(email: string): Promise<void> {
  return post("/auth/forgot-password", { email });
}

export function resetPassword(token: string, newPassword: string): Promise<void> {
  return post("/auth/reset-password", { token, new_password: newPassword });
}

// --- Account Settings ---
export function getAccountInfo(): Promise<AccountInfo> {
  return get("/auth/account");
}

export function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  return post("/auth/change-password", { current_password: currentPassword, new_password: newPassword });
}

export function setPassword(newPassword: string): Promise<void> {
  return post("/auth/set-password", { new_password: newPassword });
}

export function unlinkGoogle(): Promise<void> {
  return post("/auth/google/unlink");
}

export function deleteAccount(confirmation: string, password?: string): Promise<void> {
  return post("/auth/delete-account", { confirmation, password: password ?? null });
}
```

### 5.3 Middleware Changes (`frontend/src/middleware.ts`)

```typescript
const PUBLIC_ROUTES = [
  "/login",
  "/register",
  "/auth/verify-email",
  "/auth/forgot-password",
  "/auth/reset-password",
];
```

### 5.4 Email Verification Banner

Shown in the authenticated layout when `email_verified = false`:

```typescript
// frontend/src/components/email-verification-banner.tsx
"use client";
export function EmailVerificationBanner() {
  // Uses useCurrentUser() to check email_verified
  // Shows yellow banner: "Please verify your email to unlock all features [Resend]"
  // Resend button calls resendVerification() API
  // Dismisses on success with "Verification email sent" toast
}
```

Integrated in `frontend/src/app/(authenticated)/layout.tsx` above the main content.

---

## 6. Redis Key Map

| Key Pattern | Value | TTL | Purpose |
|-------------|-------|-----|---------|
| `oauth_state:{state}` | `{nonce, next_url}` | 5 min | OAuth CSRF + replay protection |
| `email_verify:{token}` | `user_id` | 24 hours | Email verification token |
| `password_reset:{token}` | `user_id` | 1 hour | Password reset token |
| `user_revocation:{user_id}` | ISO timestamp | 7 days | Revoke all tokens before timestamp |
| `user:{user_id}:auth` | CachedUser JSON | ~300s | Existing user auth cache (add email_verified) |

---

## 7. Build Sequence

Implementation in 6 sprints, ordered by dependency:

### Sprint 1 — Foundation (no UI changes)
**Files:** `config.py`, `models/oauth_account.py`, `models/user.py`, `models/__init__.py`, `dependencies.py`, `schemas/auth.py`, migration 023, `services/token_blocklist.py`

| Task | Files | Tests |
|------|-------|-------|
| 1a. Add settings: GOOGLE_*, RESEND_*, EMAIL_FROM | `config.py` | Unit: settings load |
| 1b. User model: add `email_verified`, `email_verified_at`, `deleted_at`, nullable `hashed_password` | `models/user.py` | Unit: model fields |
| 1c. OAuthAccount model | `models/oauth_account.py`, `models/__init__.py` | Unit: model + relationships |
| 1d. LoginAttempt: add `method`, `provider_sub` | `models/login_attempt.py` | Unit: model fields |
| 1e. Add `iat` claim to `create_access_token` + `create_refresh_token` | `dependencies.py` | Unit: iat in decoded token |
| 1f. Add `iat` to `TokenPayload`, extract in `decode_token` | `dependencies.py` | Unit: token decode |
| 1g. Alembic migration 023 (includes ChatSession FK fix) | `alembic/versions/023_*.py` | Test: up + down migration |
| 1h. CachedUser: add `email_verified` + `has_password` | `dependencies.py` | Unit: cache serialization |
| 1i. User-level revocation in token_blocklist | `services/token_blocklist.py`, `dependencies.py` | Unit: revocation check |
| 1j. `require_verified_email` dependency | `dependencies.py` | Unit: 403 on unverified |
| 1k. New Pydantic schemas | `schemas/auth.py` | Unit: validation |

### Sprint 2 — Email Service + Verification
**Files:** `services/email.py`, `routers/auth.py`, `tasks/` (Celery)

| Task | Files | Tests |
|------|-------|-------|
| 2a. EmailService (Resend wrapper + dev console fallback) | `services/email.py` | Unit: mock Resend, test dev mode |
| 2b. Register endpoint: send verification email | `routers/auth.py` | API: register → check Redis token |
| 2c. `POST /auth/verify-email` endpoint | `routers/auth.py` | API: valid token, expired token, reuse |
| 2d. `GET /auth/verify-email` HTML page | `routers/auth.py` | API: returns HTML |
| 2e. `POST /auth/resend-verification` endpoint | `routers/auth.py` | API: rate limit, invalidates old |
| 2f. Dev-mode auto-verify in register | `routers/auth.py` | API: ENVIRONMENT=development |

### Sprint 3 — Google OAuth
**Files:** `services/google_oauth.py`, `routers/auth.py`

| Task | Files | Tests |
|------|-------|-------|
| 3a. GoogleOAuthService (auth URL, code exchange, ID token validation) | `services/google_oauth.py` | Unit: mock Google responses |
| 3b. `GET /auth/google/authorize` endpoint | `routers/auth.py` | API: redirect URL, state in Redis |
| 3c. `GET /auth/google/callback` — new user flow | `routers/auth.py` | API: creates user, links oauth, sets cookies |
| 3d. Callback — existing user auto-link | `routers/auth.py` | API: links without overwriting password |
| 3e. Callback — returning user login | `routers/auth.py` | API: sub lookup, direct login |
| 3f. Callback — error cases (invalid state, unverified email, duplicate sub) | `routers/auth.py` | API: 400/409 responses |
| 3g. Login endpoint: guard NULL password, differentiate deleted accounts | `routers/auth.py` | API: proper error messages |

### Sprint 4 — Password Reset + Account Settings
**Files:** `routers/auth.py`, `services/email.py`

| Task | Files | Tests |
|------|-------|-------|
| 4a. `POST /auth/forgot-password` (no enumeration) | `routers/auth.py` | API: always 200, sends email |
| 4b. `POST /auth/reset-password` (token + revoke all) | `routers/auth.py` | API: resets, revokes sessions |
| 4c. Forgot-password for Google-only user | `services/email.py` | API: sends "use Google" email |
| 4d. `POST /auth/change-password` | `routers/auth.py` | API: validates current, revokes |
| 4e. `POST /auth/set-password` | `routers/auth.py` | API: only when no password |
| 4f. `POST /auth/google/unlink` | `routers/auth.py` | API: blocks if no password |
| 4g. `GET /auth/account` | `routers/auth.py` | API: returns account info |

### Sprint 5 — Account Deletion + Admin + Purge
**Files:** `routers/auth.py`, `tasks/audit.py`, `tasks/__init__.py`

| Task | Files | Tests |
|------|-------|-------|
| 5a. `POST /auth/delete-account` (soft delete flow) | `routers/auth.py` | API: anonymize, deactivate, revoke |
| 5b. Deletion email (sent before anonymizing) | `services/email.py` | Unit: email content |
| 5c. `POST /admin/users/{id}/verify-email` | `routers/auth.py` | API: admin-only |
| 5d. `POST /admin/users/{id}/recover` | `routers/auth.py` | API: within 30 days, new email |
| 5e. Celery purge task + beat schedule | `tasks/audit.py`, `tasks/__init__.py` | Unit: purge logic |
| 5f. `require_verified_email` on 11 write endpoints: | See list below | API: 403 when unverified |

**Write endpoints requiring `require_verified_email` guard (Sprint 5f):**
| Router | Endpoint | Method |
|--------|----------|--------|
| portfolio | `/portfolio/transactions` | POST |
| portfolio | `/portfolio/transactions/{id}` | DELETE |
| chat | `/chat/stream` | POST |
| chat | `/chat/sessions/{id}/messages/{id}/feedback` | PATCH |
| chat | `/chat/sessions/{id}` | DELETE |
| alerts | `/alerts/read` | PATCH |
| preferences | `/preferences` | PATCH |
| watchlist | `/watchlist` | POST |
| watchlist | `/watchlist/{ticker}` | DELETE |
| watchlist | `/watchlist/{ticker}/acknowledge` | POST |
| watchlist | `/watchlist/refresh-all` | POST |

### Sprint 6 — Frontend
**Files:** All frontend files listed in Section 4.2

| Task | Files | Tests |
|------|-------|-------|
| 6a. API layer additions | `lib/api.ts` | — |
| 6b. Login page: wire Google button + add forgot password link | `login/page.tsx` | Jest: renders |
| 6c. Register page: Google button | `register/page.tsx` | Jest: renders |
| 6d. Middleware: add public routes | `middleware.ts` | — |
| 6e. Email verification landing page | `auth/verify-email/page.tsx` | Jest: token handling |
| 6f. Forgot password page (enter email) | `auth/forgot-password/page.tsx` | Jest: form + submit |
| 6g. Reset password page (enter new password) | `auth/reset-password/page.tsx` | Jest: form + submit |
| 6h. Account settings page (4 sections) | `account/page.tsx` + components | Jest: all sections |
| 6i. Email verification banner in layout | `components/email-verification-banner.tsx`, `layout.tsx` | Jest: show/hide |
| 6j. useCurrentUser hook: extend response | `hooks/use-current-user.ts` | — |
| 6k. Auth context: update for new flows | `lib/auth.ts` | — |

---

## 8. Test Plan Summary

| Category | Count (est.) | What |
|----------|-------------|------|
| Unit: models | ~10 | OAuthAccount, User new fields, CachedUser |
| Unit: services | ~15 | GoogleOAuth mock, EmailService mock, token revocation |
| Unit: schemas | ~8 | Validation for all new schemas |
| API: OAuth flow | ~10 | Authorize, callback (new/link/return/errors) |
| API: Verification | ~8 | Verify, resend, dev-mode, rate limits |
| API: Password | ~10 | Forgot, reset, change, set, Google-only |
| API: Deletion | ~8 | Delete, re-auth, admin recover, purge |
| API: Settings | ~6 | Account info, unlink, edge cases |
| Frontend: Jest | ~12 | Login, register, settings, verification, reset |
| **Total** | **~87** | |

---

## 9. Package Dependencies

### Backend
```
uv add resend     # Email sending (only new dependency)
# httpx — already installed (used by 7 files)
# PyJWT — already installed (used for JWT)
# No authlib needed — Google OAuth via httpx + PyJWT (fewer deps, consistent with codebase)
```

### Frontend
```
# No new packages — using existing fetch + shadcn components
```

---

## 10. Environment Variables Summary

| Variable | Required | Default | Where | Status |
|----------|----------|---------|-------|--------|
| `GOOGLE_CLIENT_ID` | For OAuth | `""` (disabled) | `backend/.env` | ✅ Added |
| `GOOGLE_CLIENT_SECRET` | For OAuth | `""` (disabled) | `backend/.env` | ✅ Added |
| `GOOGLE_OAUTH_REDIRECT_URI` | For OAuth | `http://localhost:8181/api/v1/auth/google/callback` | `backend/.env` | Add to .env |
| `RESEND_API_KEY` | For email | `""` (dev: console) | `backend/.env` | ✅ Added |
| `EMAIL_FROM_ADDRESS` | For email | `noreply@stocksignal.app` | `backend/.env` | ✅ Added |

**CI additions** (`GitHub Actions Secrets`):
| Secret | Purpose |
|--------|---------|
| `CI_GOOGLE_CLIENT_ID` | Test OAuth (can use dummy) |
| `CI_GOOGLE_CLIENT_SECRET` | Test OAuth (can use dummy) |
| `CI_RESEND_API_KEY` | Not needed (tests mock email) |

---

## 11. Complete File Manifest

### Backend — NEW files (3)
| File | Purpose |
|------|---------|
| `backend/models/oauth_account.py` | OAuthAccount model |
| `backend/services/email.py` | EmailService (Resend wrapper) |
| `backend/services/google_oauth.py` | GoogleOAuthService (httpx + PyJWT) |

### Backend — EDIT files (9)
| File | Changes |
|------|---------|
| `backend/config.py` | Add GOOGLE_*, RESEND_*, EMAIL_FROM settings |
| `backend/models/user.py` | Add email_verified, email_verified_at, deleted_at fields; nullable hashed_password; oauth_accounts relationship |
| `backend/models/login_attempt.py` | Add method, provider_sub fields |
| `backend/models/__init__.py` | Import OAuthAccount |
| `backend/dependencies.py` | Add iat to token creation/decode, TokenPayload.iat, CachedUser.email_verified + has_password, require_verified_email, revocation check in get_current_user |
| `backend/schemas/auth.py` | Add 9 new Pydantic schemas |
| `backend/routers/auth.py` | Add 13 new endpoints, modify login/register/me |
| `backend/services/token_blocklist.py` | Add set_user_revocation, check_user_revocation |
| `backend/tasks/audit.py` | Add purge_deleted_accounts_task |

### Backend — EDIT files (write-endpoint guards, Sprint 5f)
| File | Changes |
|------|---------|
| `backend/routers/portfolio.py` | Add require_verified_email to 2 endpoints |
| `backend/routers/chat.py` | Add require_verified_email to 3 endpoints |
| `backend/routers/alerts.py` | Add require_verified_email to 1 endpoint |
| `backend/routers/preferences.py` | Add require_verified_email to 1 endpoint |
| `backend/routers/stocks/watchlist.py` | Add require_verified_email to 4 endpoints |
| `backend/tasks/__init__.py` | Add purge-deleted-accounts to beat schedule |

### Migration (1)
| File | Purpose |
|------|---------|
| `alembic/versions/023_auth_overhaul.py` | users + oauth_accounts + login_attempts + ChatSession FK fix |

### Frontend — NEW files (9)
| File | Purpose |
|------|---------|
| `frontend/src/app/(authenticated)/account/page.tsx` | Account settings page |
| `frontend/src/app/(authenticated)/account/_components/profile-section.tsx` | Email + verification |
| `frontend/src/app/(authenticated)/account/_components/security-section.tsx` | Password management |
| `frontend/src/app/(authenticated)/account/_components/linked-accounts.tsx` | Google link/unlink |
| `frontend/src/app/(authenticated)/account/_components/danger-zone.tsx` | Account deletion |
| `frontend/src/app/auth/verify-email/page.tsx` | Email verification landing |
| `frontend/src/app/auth/forgot-password/page.tsx` | Forgot password form |
| `frontend/src/app/auth/reset-password/page.tsx` | Reset password form |
| `frontend/src/components/email-verification-banner.tsx` | Verification banner |

### Frontend — EDIT files (6)
| File | Changes |
|------|---------|
| `frontend/src/app/login/page.tsx` | Wire Google button, add forgot password link |
| `frontend/src/app/register/page.tsx` | Wire Google button |
| `frontend/src/lib/api.ts` | Add 10 new API functions |
| `frontend/src/lib/auth.ts` | Update AuthContextValue |
| `frontend/src/hooks/use-current-user.ts` | Extend with email_verified, has_password, google_linked |
| `frontend/src/middleware.ts` | Add 3 public routes |
| `frontend/src/app/(authenticated)/layout.tsx` | Add EmailVerificationBanner |

### Test files — NEW (est. 6-8)
| File | Purpose |
|------|---------|
| `tests/unit/auth/test_google_oauth.py` | GoogleOAuthService unit tests |
| `tests/unit/auth/test_email_service.py` | EmailService unit tests |
| `tests/unit/auth/test_token_revocation.py` | User-level revocation tests |
| `tests/unit/auth/test_auth_schemas.py` | New schema validation tests |
| `tests/api/test_auth_oauth.py` | OAuth flow integration tests |
| `tests/api/test_auth_verification.py` | Email verification integration tests |
| `tests/api/test_auth_password_reset.py` | Password reset integration tests |
| `tests/api/test_auth_account.py` | Account settings + deletion tests |

### **Totals: 3 new backend + 9 new frontend + 1 migration + ~8 test files = ~21 new files | 22 edited files**

---

## 12. Tech Debt Register

| # | Debt | Found By | Fix |
|---|------|----------|-----|
| TD1 | ChatSession.user_id FK missing `ondelete="CASCADE"` — defaults to RESTRICT | Review | Fixed in migration 023 |
| TD2 | JWT tokens missing `iat` claim — blocks revocation feature | Review | Fixed in Sprint 1 (dependencies.py) |
| TD3 | `CachedUser` excludes password info — can't determine if user has_password | Review | Add `has_password: bool` to CachedUser |
| TD4 | Login page placeholder Google button (toast "coming soon") | Existing | Replaced in Sprint 6 |
| TD5 | Register page placeholder Google button | Existing | Replaced in Sprint 6 |
| TD6 | No "Forgot password" link on login page | Existing | Added in Sprint 6 |
| TD7 | `UserProfileResponse` missing email_verified, has_password, google_linked | Design gap | Extended /auth/me response |

---

## 13. Design Review Log

**Reviewed:** 2026-04-01 | **Scope:** Full design review including all code blocks

### Issues Found & Resolved

| ID | Severity | Issue | Fix |
|----|----------|-------|-----|
| D1 | Critical | `iat` missing from JWT payload — revocation mechanism broken | Added iat to create_access_token + create_refresh_token + TokenPayload |
| D2 | Critical | ChatSession FK missing CASCADE — user delete would fail with IntegrityError | Added FK constraint fix to migration 023 |
| D3 | Critical | `authlib` dependency unnecessary — project uses httpx + PyJWT already | Dropped authlib, using httpx + PyJWT only |
| D4 | Critical | TokenPayload missing iat field — decode_token discards it | Added iat to TokenPayload dataclass |
| M1 | Major | Write endpoints not enumerated — 11 endpoints need verification guard | Listed all 11 endpoints in Sprint 5f |
| M2 | Major | User model missing `oauth_accounts` relationship | Added relationship definition |
| M3 | Major | CachedUser missing `has_password` — can't determine password status | Added has_password field |
| M4 | Major | Forgot-password page missing from frontend — only reset-password page listed | Added `/auth/forgot-password` page + public route |
| M5 | Major | get_current_user revocation check must be async — design showed sync | Clarified async flow matches existing pattern |
| M6 | Major | Login page forgot-password link not specified | Included in Sprint 6b |
