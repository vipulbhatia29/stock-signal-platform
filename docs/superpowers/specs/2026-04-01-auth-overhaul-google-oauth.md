# Auth Overhaul — Google OAuth, Email Verification, Account Management

**Date:** 2026-04-01
**Phase:** C — SaaS Auth Hardening
**JIRA Epic:** KAN-152 (Google OAuth) + new tickets TBD
**Status:** Requirements — expert-reviewed, awaiting design

---

## 1. Problem Statement

The platform currently supports only email/password authentication with no email verification, no password reset, no social login, and no account deletion. For SaaS launch readiness, users need:

- Frictionless signup/login via Google
- Confidence that their email is verified
- Ability to recover forgotten passwords
- Control over their account (settings, linked providers, deletion)
- Privacy-compliant account deletion with data purge

---

## 2. Scope

| Area | In Scope | Out of Scope |
|------|----------|--------------|
| Google OAuth | Login, register, auto-link | GitHub/Apple/other providers |
| Email verification | New signups, grandfather existing | Re-verification of existing users |
| Password reset | Forgot password via email token | SMS/2FA reset |
| Account settings | Link/unlink Google, change password, set password | Profile photo, display name, email change |
| Account deletion | Soft delete + 30-day purge | Immediate hard delete |
| Admin tools | Manual verify email, manage users | User impersonation |
| Session management | Deferred to later phase | Active sessions list, remote revoke |

---

## 3. Functional Requirements

### 3.1 Google OAuth — Login & Registration

**FR-3.1.1 — Google Sign-In Button**
- Login and register pages display "Sign in with Google" button
- Uses Google OAuth 2.0 Authorization Code flow (NOT implicit)
- Scopes requested: `openid`, `email`, `profile`

**FR-3.1.2 — New User via Google (no existing account)**
- If Google email matches no existing user → create new account
- `hashed_password` = NULL (no password set)
- `email_verified` = TRUE (Google verified it)
- `auth_provider` linked as `google` with Google `sub` (unique ID)
- Issue JWT tokens, set httpOnly cookies, redirect to dashboard
- Record in LoginAttempt with `method = "google_oauth"`

**FR-3.1.3 — Existing User via Google (account linking)**
- If Google email matches an existing user AND Google `email_verified` = true:
  - Auto-link Google provider to existing account (trust Google's verification)
  - Issue JWT tokens, log in as that user
  - Do NOT overwrite existing password — user retains both login methods
- If Google `email_verified` = false: reject with error "Google account email not verified"

**FR-3.1.4 — Returning Google User (already linked)**
- If Google `sub` already linked to a user → log in directly
- If Google `sub` linked to user A but Google email now matches user B → use `sub` (stable identifier), not email

**FR-3.1.5 — One Google Account Per User**
- A user can link at most one Google account
- A Google `sub` can be linked to at most one user
- Attempting to link a Google account already linked to another user → error

**FR-3.1.6 — OAuth State + Nonce (CSRF + Replay Protection)**
- Generate random `state` parameter, store in Redis (5-min TTL)
- Generate random `nonce`, include in auth request and store alongside state
- Validate `state` on callback — reject if missing or mismatched
- Validate `nonce` in returned ID token — prevents token replay attacks
- Prevents CSRF attacks on OAuth callback

**FR-3.1.7 — Backend OAuth Flow**
- Frontend redirects to `/api/v1/auth/google/authorize` → backend builds Google auth URL with state
- Google redirects back to `/api/v1/auth/google/callback` with auth code
- Backend exchanges code for tokens server-side (auth code never exposed to frontend)
- Backend extracts user info from Google ID token
- Backend issues our JWT tokens + sets cookies + redirects to frontend

### 3.2 Email Verification

**FR-3.2.1 — User Model Changes**
- Add `email_verified: bool` field (default FALSE)
- Add `email_verified_at: datetime | null`

**FR-3.2.2 — Grandfather Existing Users**
- Migration sets `email_verified = TRUE` and `email_verified_at = NOW()` for all existing users
- No re-verification required for current accounts

**FR-3.2.3 — New Registration Verification**
- On email/password registration: send verification email with signed token (URL-safe, 24h expiry)
- Token stored in Redis: `email_verify:{token}` → `user_id` (24h TTL)
- `GET /api/v1/auth/verify-email?token=xxx` → renders confirmation page, auto-submits POST via JS (prevents bot/prefetch token consumption)
- `POST /api/v1/auth/verify-email` with `{ token }` → validates token, sets `email_verified = TRUE`
- Token is single-use — deleted from Redis after verification

**FR-3.2.4 — Resend Verification**
- `POST /api/v1/auth/resend-verification` (authenticated)
- Rate limited: 3/hour
- Invalidates previous token, generates new one

**FR-3.2.5 — Soft-Block Unverified Users**
- Unverified users CAN: log in, view dashboards, view stock data (read-only)
- Unverified users CANNOT: create/modify portfolios, run agent queries, create watchlists, configure alerts
- Frontend shows persistent banner: "Please verify your email to unlock all features" with resend button
- Backend enforces via dependency: `require_verified_email(user)` on write endpoints

**FR-3.2.6 — Google OAuth Auto-Verification**
- Users who sign up or link via Google with `email_verified = true` → automatically set `email_verified = TRUE`

**FR-3.2.7 — Dev-Mode Auto-Verify**
- When `ENVIRONMENT == "development"` (local dev — matches `config.py` settings):
  - Skip sending verification email
  - Auto-set `email_verified = TRUE` on registration
  - Log verification token to console for manual testing if needed

### 3.3 Password Reset (Forgot Password)

**FR-3.3.1 — Request Reset**
- `POST /api/v1/auth/forgot-password` with `{ email }`
- Always returns 200 (no email enumeration — don't reveal if email exists)
- If email exists: send reset email with signed token (1h expiry)
- Token in Redis: `password_reset:{token}` → `user_id` (1h TTL)
- Rate limited: 3/hour per email

**FR-3.3.2 — Reset Password**
- `POST /api/v1/auth/reset-password` with `{ token, new_password }`
- Validates token, enforces password strength rules
- Updates `hashed_password`, deletes token
- Revokes all sessions via user-level revocation timestamp in Redis (`user_revocation:{user_id}` → timestamp; tokens with `iat` before this are rejected)
- Returns success — user must log in with new password

**FR-3.3.3 — Google-Only Users**
- If user has no password (Google-only), forgot-password email says: "You signed up with Google. Use Google Sign-In or set a password from Account Settings."

### 3.4 Account Settings Page

**FR-3.4.1 — Settings Page Layout**
- New frontend route: `/account` (under `(authenticated)` group)
- Sections: Profile, Security, Linked Accounts, Danger Zone

**FR-3.4.2 — Profile Section**
- Display email (read-only for now)
- Display email verification status with resend button if unverified

**FR-3.4.3 — Security Section — Change Password**
- For users WITH a password: current password + new password + confirm
- `POST /api/v1/auth/change-password` with `{ current_password, new_password }`
- Validates current password, enforces strength rules on new password
- Revokes all other sessions via user-level revocation timestamp (current session's token re-issued)
- Rate limited: 5/hour

**FR-3.4.4 — Security Section — Set Password (for Google-only users)**
- For users WITHOUT a password: new password + confirm (no current password needed)
- `POST /api/v1/auth/set-password` with `{ new_password }`
- Only allowed when `hashed_password IS NULL`

**FR-3.4.5 — Linked Accounts Section — Link Google**
- If Google not linked: show "Link Google Account" button
- Initiates Google OAuth flow, on callback links Google `sub` to existing user
- Must be authenticated — no auto-link ambiguity

**FR-3.4.6 — Linked Accounts Section — Unlink Google**
- If Google linked AND user has a password set: show "Unlink Google" button
- `POST /api/v1/auth/google/unlink` (authenticated)
- If Google linked AND user has NO password: button disabled with tooltip "Set a password first"
- Prevents lockout — at least one login method must remain

### 3.5 Account Deletion

**FR-3.5.1 — Delete Account Flow**
- Located in "Danger Zone" section of account settings
- Step 1: User clicks "Delete my account"
- Step 2: Modal explains consequences (data deleted after 30 days, irreversible)
- Step 3: Re-authentication depends on account type:
  - Password users: enter current password
  - Google-only users: active authenticated session is sufficient (no extra re-auth)
- Step 4: User must type "DELETE" in confirmation field
- Step 5: `POST /api/v1/auth/delete-account` with `{ confirmation: "DELETE", password?: string }`
  - Backend validates: password users must provide correct password; Google-only users pass `password = null`

**FR-3.5.2 — Immediate Actions on Deletion**
- Send deletion confirmation email to original email FIRST (before anonymizing)
- Set `is_active = FALSE`
- Set `deleted_at = NOW()` (new field)
- Anonymize email: `deleted_{uuid}@removed.local`
- Clear `hashed_password`
- Remove all OAuth provider links
- Revoke all tokens via user-level revocation timestamp
- Clear cookies, redirect to login with "Account scheduled for deletion" message

**FR-3.5.3 — 30-Day Grace Period**
- Account is deactivated but data remains for 30 days
- Login attempts show: "This account has been deleted. Contact support within 30 days to recover." (distinct from "Account is disabled")
- Admin can re-activate account within this window

**FR-3.5.4 — Hard Purge After 30 Days**
- Celery Beat task runs daily: find users where `deleted_at < NOW() - 30 days`
- Hard delete: cascade from User record (all child tables use `ON DELETE CASCADE` or `SET NULL`)
- Migration must ensure cascade FKs on: portfolios, watchlists, alerts, user_preferences, oauth_accounts
- LoginAttempts FK is `SET NULL` (preserves audit trail with anonymized data)
- Log purge action (admin audit trail, count of records purged per table)

**FR-3.5.5 — Data NOT Deleted**
- StockIndex records (shared)
- SignalSnapshots (per-stock, not per-user)
- Stock prices, fundamentals (shared reference data)

### 3.6 Admin Tools

**FR-3.6.1 — Manual Email Verification**
- `POST /api/v1/auth/admin/users/{user_id}/verify-email` (admin only)
- Sets `email_verified = TRUE`, `email_verified_at = NOW()`
- Use case: test users, customer support

**FR-3.6.2 — View Users (existing)**
- Already exists — extend to show `email_verified`, `auth_providers`, `deleted_at` fields

**FR-3.6.3 — Recover Deleted Account**
- `POST /api/v1/auth/admin/users/{user_id}/recover` with `{ new_email }` (admin only)
- Only works within 30-day window (`deleted_at` is set and < 30 days ago)
- Restores `is_active = TRUE`, clears `deleted_at`
- Sets email to admin-provided `new_email`, sets `email_verified = FALSE`
- User must verify new email and set a new password via forgot-password flow
- Admin communicates new email to user out-of-band

### 3.7 Login Audit Extension

**FR-3.7.1 — LoginAttempt Model Changes**
- Add `method: str` field — values: `"password"`, `"google_oauth"` (migration default: `"password"` for existing rows)
- Add `provider_sub: str | null` — Google `sub` for OAuth logins

**FR-3.7.2 — Track All Auth Events**
- Password login (existing)
- Google OAuth login/register
- Account linking/unlinking
- Password change/reset
- Account deletion
- Account recovery (admin)

---

## 4. Non-Functional Requirements

**NFR-1 — Security**
- OAuth auth codes exchanged server-side only (never exposed to browser)
- State + nonce parameters with Redis-backed CSRF and replay protection
- All tokens (verification, reset) are cryptographically random, single-use, time-limited
- Password reset/change revokes all sessions via user-level revocation timestamp
- No email enumeration on any endpoint
- Rate limiting on all new auth endpoints
- Password login gracefully rejects users with `hashed_password = NULL` ("No password set. Use Google Sign-In.")
- `CachedUser` model extended with `email_verified` field for `require_verified_email` checks

**NFR-2 — Rate Limits**

| Endpoint | Limit |
|----------|-------|
| `POST /auth/google/authorize` | 10/minute |
| `GET /auth/google/callback` | 10/minute |
| `POST /auth/forgot-password` | 3/hour per email |
| `POST /auth/reset-password` | 5/hour |
| `POST /auth/resend-verification` | 3/hour |
| `POST /auth/change-password` | 5/hour |
| `POST /auth/set-password` | 5/hour |
| `POST /auth/delete-account` | 3/hour |

**NFR-3 — Performance**
- OAuth flow completes in < 3s (excluding Google's response time)
- Email sending is async (Celery task) — does not block response

**NFR-4 — Email Infrastructure**
- **Provider: Resend** (free tier: 3,000/month, 100/day — sufficient for current scale)
- Python SDK: `resend` package via `uv add resend`
- Templates (HTML branded): verification, password reset, account deletion confirmation, Google-only forgot-password
- Dev mode (`DEBUG=True`): log to console instead of sending

**NFR-5 — Privacy / Data Retention**
- Deleted user data purged after 30 days — no manual intervention
- Anonymized email cannot be reversed to original
- Purge task is idempotent and logged

---

## 5. Data Model Changes

### New: `oauth_account` table

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `user_id` | UUID | FK → users, ON DELETE CASCADE |
| `provider` | VARCHAR(50) | `"google"` (extensible for future providers) |
| `provider_sub` | VARCHAR(255) | Google `sub` — unique per provider |
| `provider_email` | VARCHAR(255) | Email from provider (informational) |
| `linked_at` | TIMESTAMP | When linked |

- Unique constraint: `(provider, provider_sub)` — one user per Google account
- Unique constraint: `(user_id, provider)` — one Google link per user

### Modified: `users` table

| New Column | Type | Notes |
|------------|------|-------|
| `email_verified` | BOOLEAN | Default FALSE |
| `email_verified_at` | TIMESTAMP | Nullable |
| `deleted_at` | TIMESTAMP | Nullable — soft delete marker |
| `hashed_password` | VARCHAR(255) | Now NULLABLE (Google-only users) |

### Modified: `login_attempts` table

| New Column | Type | Notes |
|------------|------|-------|
| `method` | VARCHAR(20) | `"password"`, `"google_oauth"` — migration default `"password"` |
| `provider_sub` | VARCHAR(255) | Nullable — for OAuth logins |

### Modified: `CachedUser` (in-memory, not DB)

| New Field | Type | Notes |
|-----------|------|-------|
| `email_verified` | bool | Required for `require_verified_email()` on cached users |

### New: Redis key — User-level token revocation

| Key | Value | TTL | Notes |
|-----|-------|-----|-------|
| `user_revocation:{user_id}` | ISO timestamp | 7 days (refresh token lifetime) | Tokens with `iat` before this timestamp are rejected during decode |

### New: Frontend public routes

| Route | Purpose |
|-------|---------|
| `/auth/verify-email` | Email verification landing page (renders confirm + auto-POST) |
| `/auth/reset-password` | Password reset form (token in query string) |

---

## 6. User Stories & Acceptance Criteria

### US-1: Google Sign-Up (new user)
**As a** new user, **I want to** sign up with my Google account **so that** I don't need to create a password.

- [ ] Click "Sign in with Google" on register/login page
- [ ] Redirected to Google consent screen
- [ ] After consent, account created with verified email
- [ ] Redirected to dashboard, fully authenticated
- [ ] LoginAttempt recorded with method `google_oauth`

### US-2: Google Sign-In (returning user)
**As a** returning Google user, **I want to** log in with Google **so that** I don't need to remember a password.

- [ ] Click "Sign in with Google"
- [ ] Recognized by Google `sub`, logged in immediately
- [ ] No duplicate account created

### US-3: Google Auto-Link (existing email/password user)
**As an** existing user with a Gmail address, **I want to** log in with Google **so that** I have both options.

- [ ] Existing account with `user@gmail.com` + password
- [ ] Click "Sign in with Google" with same `user@gmail.com`
- [ ] Accounts auto-linked, logged in
- [ ] Can still log in with email/password on next visit
- [ ] Password NOT overwritten

### US-4: Email Verification (new signup)
**As a** new user signing up with email/password, **I want to** verify my email **so that** I can access all features.

- [ ] Register with email/password → receive verification email
- [ ] Click verification link → email marked as verified
- [ ] Before verification: can view dashboards but cannot create portfolios/watchlists
- [ ] Banner shown with resend button

### US-5: Forgot Password
**As a** user who forgot my password, **I want to** reset it via email **so that** I can regain access.

- [ ] Click "Forgot password" on login page
- [ ] Enter email → receive reset email (or silence if email doesn't exist)
- [ ] Click link → enter new password → password updated
- [ ] All other sessions revoked
- [ ] Must log in with new password

### US-6: Account Settings — Link/Unlink Google
**As a** user, **I want to** manage my Google connection from settings **so that** I control my login methods.

- [ ] Settings page shows linked Google account (or link button)
- [ ] Can link Google if not linked
- [ ] Can unlink Google only if password is set
- [ ] Cannot unlink if it would leave no login method

### US-7: Account Settings — Set/Change Password
**As a** Google-only user, **I want to** set a password **so that** I have a backup login method.

- [ ] Google-only users see "Set password" (no current password required)
- [ ] Password users see "Change password" (current password required)

### US-8: Account Deletion
**As a** user, **I want to** delete my account and data **so that** my information is removed.

- [ ] Click "Delete account" in settings → see consequences
- [ ] Re-authenticate (password or Google) + type "DELETE"
- [ ] Account deactivated immediately, data purged after 30 days
- [ ] Cannot log in after deletion
- [ ] Within 30 days: admin can recover account

### US-9: Admin Email Verification Override
**As an** admin, **I want to** manually verify a user's email **so that** I can help with support issues.

- [ ] `POST /admin/users/{id}/verify-email` succeeds
- [ ] User's `email_verified` set to TRUE

---

## 7. Edge Cases & Security Scenarios

| Scenario | Expected Behavior |
|----------|-------------------|
| Google email not verified by Google | Reject login — "Google email not verified" |
| Google `sub` linked to user A, email now matches user B | Use `sub` (stable ID) — log in as user A |
| User tries to link Google already linked to another user | Error: "This Google account is linked to another user" |
| Unlink Google with no password set | Blocked — "Set a password first" |
| Delete account then try to register same email | Within 30 days: "Account pending deletion, contact support". After 30 days: email available for new registration |
| OAuth callback with invalid/expired state | 400 error — "Invalid or expired session. Please try again." |
| Password reset for Google-only user | Email says "You use Google Sign-In. Link: account settings to set a password." |
| Verification email for `@example.com` in production | Email silently fails. Admin can manually verify. |
| Concurrent delete + login race condition | `is_active` check on login rejects deleted accounts |
| Google API downtime | "Google Sign-In temporarily unavailable. Use email/password." |
| Password login for Google-only user (no password) | Reject: "No password set. Use Google Sign-In or set a password in Account Settings." |
| Google-only user requests account deletion | Active session sufficient — no password prompt, only type "DELETE" |
| Admin recovers account after email anonymized | Admin provides new email in recovery request; user re-verifies |
| Link preview bot hits verification link | GET renders page with JS auto-POST; bot won't execute JS, token preserved |
| Existing LoginAttempt rows after migration | `method` column defaults to `"password"` for all existing rows |

---

## 8. Resolved Questions

| # | Question | Decision |
|---|----------|----------|
| 1 | Email provider | **Resend** — free tier (3K/month), simple Python SDK |
| 2 | Email templates | **HTML branded** — professional look |
| 3 | Google Cloud project | **User creates** OAuth client in Google Cloud Console |
| 4 | Frontend route | **`/account`** — under `(authenticated)` group |
| 5 | Deletion notification | **Yes** — send confirmation email on deletion |

---

## 9. Dependencies

- Google Cloud OAuth 2.0 client credentials (client ID + secret)
- Email sending service (SendGrid/SES/Resend) — API key
- New env vars: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `RESEND_API_KEY`, `EMAIL_FROM_ADDRESS`
- Alembic migration for User + LoginAttempt schema changes + new `oauth_account` table

---

## 10. Next Steps

1. `/sc:design` — architecture, API contracts, migration plan, component design
2. Create JIRA subtasks under KAN-152 epic
3. Implement in sprints

---

## 11. Expert Review Log

**Reviewed:** 2026-04-01 | **Panel:** Wiegers (Requirements), Fowler (Architecture), Nygard (Production), Crispin (Testing), Security

### Issues Found & Resolved

| ID | Severity | Issue | Fix Applied |
|----|----------|-------|-------------|
| C1 | Critical | `DEBUG` setting doesn't exist; config uses `ENVIRONMENT` | Changed to `ENVIRONMENT == "development"` |
| C2 | Critical | No mechanism to revoke ALL tokens for a user (JTI-only blocklist) | Added user-level revocation timestamp in Redis |
| C3 | Critical | `CachedUser` missing `email_verified` — `require_verified_email` would fail on cached users | Added `email_verified` to CachedUser spec |
| C4 | Critical | Frontend middleware only whitelists `/login`, `/register` — missing verification/reset routes | Added `/auth/verify-email` and `/auth/reset-password` as public routes |
| C5 | Critical | Delete account re-auth undefined for Google-only users (no password to enter) | Google-only: active session + "DELETE" sufficient |
| C6 | Critical | Account recovery email problem — admin recovers but email is anonymized | Admin provides `new_email` in recovery request |
| M1 | Major | `GET /verify-email` performs state change; bots could consume token | GET renders page with JS auto-POST; POST does actual verification |
| M2 | Major | Purge ordering unnecessary — FK cascades handle it | Simplified to cascade delete from User record |
| M3 | Major | Email change not mentioned | Explicitly listed as out of scope |
| M4 | Major | `method` default for existing LoginAttempt rows | Migration default `"password"` specified |
| M5 | Major | Env var naming mismatch (`EMAIL_API_KEY` vs Resend convention) | Changed to `RESEND_API_KEY` |
| M6 | Major | `hashed_password` nullable breaks login flow assumptions | Added guard: password login rejects NULL password gracefully |
| m1 | Minor | No `nonce` in OAuth (replay protection) | Added nonce to OAuth state + ID token validation |
| m2 | Minor | Deletion email sent after anonymizing email | Reordered: send email BEFORE anonymizing |
| m3 | Minor | No rate limit on `/auth/change-password` | Added 5/hour rate limit |
| m4 | Minor | `token_refresh` is not a login method | Removed from LoginAttempt method values |
| m5 | Minor | Purge lists OAuth links but FR-3.5.2 already removes them | Cascade handles it; no duplicate step |

**Quality Assessment Post-Review:** Completeness 9.5/10 | Security 9/10 | Testability 8.5/10 | Feasibility 9/10 | Clarity 9/10
