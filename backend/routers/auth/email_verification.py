"""Email verification endpoints."""

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.rate_limit import limiter
from backend.routers.auth._helpers import _send_verification_bg
from backend.schemas.auth import MessageResponse, VerifyEmailRequest
from backend.services.email import generate_token
from backend.services.redis_pool import get_redis

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/verify-email", response_class=HTMLResponse)
async def verify_email_page(token: str = "") -> HTMLResponse:
    """Render HTML page that auto-POSTs the verification token (bot protection)."""
    # Sanitize token — only allow URL-safe base64 chars (defense-in-depth)
    safe_token = re.sub(r"[^A-Za-z0-9_\-]", "", token)
    html = f"""<!DOCTYPE html>
<html><head><title>Verifying email...</title></head>
<body>
<p id="msg">Verifying your email...</p>
<script>
function setMessage(text) {{
    var el = document.getElementById('msg');
    if (el) el.textContent = text;
}}
fetch('/api/v1/auth/verify-email', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{token: '{safe_token}'}}),
    credentials: 'include'
}}).then(r => {{
    if (r.ok) window.location.href = '/login?verified=true';
    else setMessage('Invalid or expired link. Please request a new one.');
}}).catch(() => {{
    setMessage('Something went wrong. Please try again.');
}});
</script>
</body></html>"""
    return HTMLResponse(content=html)


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    body: VerifyEmailRequest,
    db: AsyncSession = Depends(get_async_session),
) -> MessageResponse:
    """Verify email address with token."""
    redis = await get_redis()
    if not redis:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    key = f"email_verify:{body.token}"
    user_id_str = await redis.get(key)
    if not user_id_str:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    # Decode user_id (might be bytes from Redis)
    if isinstance(user_id_str, bytes):
        user_id_str = user_id_str.decode()

    user_id = uuid.UUID(user_id_str)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid verification token")

    # Delete token first (single-use, prevents race condition)
    await redis.delete(key)

    user.email_verified = True
    user.email_verified_at = datetime.now(timezone.utc)
    await db.commit()

    return MessageResponse(message="Email verified")


@router.post("/resend-verification", response_model=MessageResponse)
@limiter.limit("3/hour")
async def resend_verification(
    request: Request,
    user: User = Depends(get_current_user),
) -> MessageResponse:
    """Resend verification email. Rate limited to 3/hour."""
    if user.email_verified:
        return MessageResponse(message="Email already verified")

    token = generate_token()
    redis = await get_redis()
    if redis:
        # Invalidate previous token if tracked
        old_token = await redis.get(f"email_verify_current:{user.id}")
        if old_token:
            if isinstance(old_token, bytes):
                old_token = old_token.decode()
            await redis.delete(f"email_verify:{old_token}")

        # Store new token + track it per user
        await redis.set(  # nosemgrep: no-unbounded-redis-key
            f"email_verify:{token}", str(user.id), ex=86400
        )
        await redis.set(  # nosemgrep: no-unbounded-redis-key
            f"email_verify_current:{user.id}", token, ex=86400
        )

    asyncio.create_task(_send_verification_bg(user.email, token))
    return MessageResponse(message="Verification email sent")
