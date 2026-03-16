---
scope: project
category: architecture
---

# Auth & JWT Flow

## Architecture

### Token Storage
- **Access token**: httpOnly, Secure, SameSite=Lax cookie — NOT localStorage
- **No refresh token** (Phase 3 implementation): single JWT per login, expires per `JWT_EXPIRE_MINUTES`
- JWT signed with `JWT_SECRET_KEY` from `backend/config.py` (Pydantic Settings)

### Request Flow
```
Browser → POST /api/v1/auth/login (email+password)
        → backend/routers/auth.py
        → get_password_hash() in backend/dependencies.py  (bcrypt via passlib)
        → create_access_token()                            (python-jose)
        → Set-Cookie: access_token=<jwt>; HttpOnly; Secure; SameSite=Lax
        → 200 OK

Subsequent requests:
Browser → any protected endpoint (cookie sent automatically)
        → FastAPI dependency: get_current_user(token: str = Cookie(...))
        → backend/dependencies.py: jose.jwt.decode(token, JWT_SECRET_KEY)
        → DB lookup: SELECT user WHERE id = payload["sub"]
        → returns User ORM object, injected into endpoint
```

### Key Implementation Details
- `python-jose` for JWT encode/decode (`jose.jwt.encode` / `jose.jwt.decode`)
- `passlib` + `bcrypt==4.2.1` for password hashing — **bcrypt MUST be pinned to 4.2.x** (bcrypt >= 5.0 broke passlib API)
- Auth logic lives entirely in `backend/dependencies.py` — `get_current_user` is the FastAPI dependency
- `backend/routers/auth.py` — `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`
- Rate limiting on auth endpoints via `slowapi` (stricter limits than other endpoints)

### Frontend Auth Pattern
- `lib/api.ts` — all fetch calls include `credentials: "include"` to send the httpOnly cookie
- `useAuth()` hook wraps `GET /api/v1/auth/me` via TanStack Query
- Auth state is server-driven: if `/auth/me` returns 401, the user is logged out
- No JWT decoding on the frontend — the server is the source of truth

## Security Rules

- NEVER commit `.env` files, API keys, or JWT secrets.
- NEVER store tokens in localStorage (XSS exposure).
- All user input validated via Pydantic schemas at API boundary.
- Ticker sanitization: `ticker.upper().strip()`, reject non-alphanumeric (except `.` and `-`).
- Error messages to end users MUST NOT reveal stack traces, file paths, or internal details.
- SQL injection prevention: SQLAlchemy ORM only — never raw SQL strings.

## OWASP Checklist

| Risk | Mitigation |
|------|-----------|
| Injection | SQLAlchemy ORM + Pydantic validation at all boundaries |
| Broken auth | JWT with expiry + httpOnly cookie (no XSS access) |
| Sensitive data exposure | Error messages sanitized; no stack traces to client |
| XSS | No `dangerouslySetInnerHTML`; cookie not accessible to JS |
| Rate limiting | slowapi on all endpoints; aggressive on auth + ingestion |

## Critical Files

| File | Why |
|------|-----|
| `backend/dependencies.py` | JWT decode + `get_current_user` — breaking changes lock out all users |
| `backend/config.py` | `JWT_SECRET_KEY` + `JWT_ALGORITHM` + `JWT_EXPIRE_MINUTES` defaults |
| `backend/routers/auth.py` | Login/logout/me endpoints |
