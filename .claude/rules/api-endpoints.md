---
paths:
  - "backend/routers/**/*.py"
---
# API Endpoint Rules

- Every endpoint MUST have Pydantic v2 request and response models in schemas/
- Include OpenAPI summary, description, and response status codes
- All endpoints require JWT authentication except /auth/login and /auth/register
- Use FastAPI Depends() for dependency injection (db session, current user, etc.)
- Return consistent error responses using HTTPException
- Write corresponding tests in tests/api/test_{router_name}.py covering:
  - Unauthenticated request returns 401
  - Happy path with valid data
  - Validation error returns 422
  - Not found returns 404 where applicable
