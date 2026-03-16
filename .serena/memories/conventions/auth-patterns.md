---
scope: project
category: conventions
---

# Auth Patterns

## JWT + httpOnly Cookies
- JWT signed with `JWT_SECRET_KEY` (from `backend/config.py` Pydantic Settings).
- Stored in httpOnly, Secure, SameSite=Lax cookie — NOT localStorage (XSS protection).
- `python-jose` for JWT encode/decode; `passlib` + `bcrypt==4.2.1` for password hashing.
- Auth logic: `backend/dependencies.py` → `get_current_user` → injected into all protected endpoints.
- CRITICAL: `bcrypt` pinned to 4.2.x — bcrypt >= 5.0 broke passlib API (passlib is unmaintained).

## Frontend Auth
- All API calls use `credentials: "include"` in `lib/api.ts` to send cookie automatically.
- `useAuth()` hook — TanStack Query wrapping `GET /api/v1/auth/me`. Auth state is server-driven.
- 401 response = user is logged out. No JWT parsing on the frontend.

## Rate Limiting
- `slowapi` on all endpoints.
- Aggressive limits on auth endpoints (login, register) and expensive endpoints (data ingestion, signal computation).

## Security Rules
- NEVER commit `.env` files, API keys, or JWT secrets.
- NEVER use localStorage for tokens.
- All user input validated via Pydantic schemas before processing.
- Ticker sanitization: `ticker.upper().strip()`, reject non-alphanumeric (except `.` and `-`).
- Error messages MUST NOT reveal stack traces or file paths to end users.
- SQL injection prevention: SQLAlchemy ORM / parameterized queries only — never raw SQL.

## Critical Files

| File | Why |
|------|-----|
| `backend/dependencies.py` | JWT validation + `get_current_user` — changes can lock out all users |
| `backend/config.py` | JWT secret + algorithm defaults |
| `backend/routers/auth.py` | Login/logout/me endpoints |
| `backend/.env` | All secrets — never commit |
