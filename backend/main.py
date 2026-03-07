"""FastAPI application entry point."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend.config import settings
from backend.routers import auth, stocks

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
    storage_uri=settings.REDIS_URL,
)

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
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Health Check ---
@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


# --- Routers ---
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(stocks.router, prefix="/api/v1/stocks", tags=["stocks"])
