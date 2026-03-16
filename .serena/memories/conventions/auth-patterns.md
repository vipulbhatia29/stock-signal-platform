---
scope: project
category: conventions
---

# Auth Patterns

## JWT + httpOnly Cookies
- JWT signed with `JWT_SECRET_KEY` (from `backend/config.py` Pydantic Settings).
- Stored in httpOnly, Secure, SameSite=Lax cookies — NOT localStorage.
- `python-jose` for JWT encode/decode; `passlib` + `bcrypt==4.2.1` for password hashing.
- Auth logic: `backend/dependencies.py` -> `get_current_user` -> inject into endpoints.
- CRITICAL: `bcrypt` must be pinned to 4.2.x — bcrypt >= 5.0 broke passlib API.

## Rate Limiting
- `slowapi` on all endpoints.
- Aggressive limits on expensive endpoints: data ingestion, signal computation.

## Security Rules
- NEVER commit `.env` files, API keys, or JWT secrets.
- All user input validated via Pydantic schemas before processing.
- Ticker sanitization: `ticker.upper().strip()`, reject non-alphanumeric (except `.` and `-`).
- Error messages MUST NOT reveal stack traces or file paths to end users.
- SQL injection prevention: always use SQLAlchemy ORM / parameterized queries.
