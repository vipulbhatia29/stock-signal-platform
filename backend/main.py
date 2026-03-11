"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.config import settings
from backend.rate_limit import limiter
from backend.routers import auth, indexes, stocks
from backend.routers.tasks import router as tasks_router

app = FastAPI(
    title="Stock Signal Platform",
    description="Automated signal detection and investment recommendations for US equities.",
    version="0.1.0",
)

# --- Middleware ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# --- Health Check ---
@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


# --- Routers ---
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(indexes.router, prefix="/api/v1/indexes", tags=["indexes"])
app.include_router(stocks.router, prefix="/api/v1/stocks", tags=["stocks"])
app.include_router(tasks_router, prefix="/api/v1")
