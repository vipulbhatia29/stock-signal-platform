"""Auth router package — combines domain sub-routers into a single router.

Mounts: core, email_verification, password, oauth, oidc, admin.
The combined `router` is imported by main.py as before.
"""

from fastapi import APIRouter

from backend.routers.auth.admin import router as admin_router
from backend.routers.auth.core import router as core_router
from backend.routers.auth.email_verification import router as email_router
from backend.routers.auth.oauth import router as oauth_router
from backend.routers.auth.oidc import router as oidc_router
from backend.routers.auth.password import router as password_router

router = APIRouter()

router.include_router(core_router)
router.include_router(email_router)
router.include_router(password_router)
router.include_router(oauth_router)
router.include_router(oidc_router)
router.include_router(admin_router)
