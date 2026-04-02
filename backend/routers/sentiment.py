"""News sentiment API — article ingestion status and daily sentiment scores."""

from fastapi import APIRouter

router = APIRouter(prefix="/sentiment", tags=["sentiment"])
