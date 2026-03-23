# Auth & JWT Flow (updated Session 50)

## Token Architecture
- Access token: httpOnly, Secure, SameSite=Lax cookie (short-lived, ACCESS_TOKEN_EXPIRE_MINUTES)
- Refresh token: httpOnly, Secure, SameSite=Lax cookie (7-day, includes unique `jti` claim)
- JWT signed with JWT_SECRET_KEY, python-jose, passlib+bcrypt==4.2.x

## Token Revocation (Phase 5.5 — COMPLETE)
- Redis blocklist keyed by JTI (JWT ID) claims
- On /refresh: old JTI blocklisted (TTL = remaining expiry), checked BEFORE issuing
- On /logout: refresh token from cookie blocklisted
- Service: `backend/services/token_blocklist.py` (async Redis via redis.asyncio)
- Redis key: `blocklist:jti:{jti_value}`, auto-expiry, no manual cleanup
- Cleanup: `close()` called in FastAPI lifespan shutdown

## Key Types
- `decode_token()` returns `TokenPayload` dataclass (user_id: UUID, jti: str | None), NOT raw UUID
- All callers updated: auth router, MCP auth middleware, get_current_user

## Critical Files
- `backend/dependencies.py` — JWT functions, TokenPayload, get_current_user
- `backend/routers/auth.py` — login/refresh/logout + blocklist wiring
- `backend/services/token_blocklist.py` — Redis blocklist service
- `backend/config.py` — JWT_SECRET_KEY, token expiry settings

## Frontend
- credentials: "include" on all fetches, useAuth() hook, server-driven auth state
- No JWT parsing on frontend

## Security
- bcrypt pinned to 4.2.x (passlib compat)
- slowapi rate limiting on auth endpoints
- OWASP: httpOnly cookies, no XSS access, refresh revocation, sanitized errors