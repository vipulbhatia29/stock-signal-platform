"""Admin pipeline API — task groups, manual triggers, seed hydration."""

from fastapi import APIRouter

router = APIRouter(prefix="/admin/pipelines", tags=["admin-pipelines"])
