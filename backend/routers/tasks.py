"""Task status API endpoints."""

import logging

from celery.result import AsyncResult
from fastapi import APIRouter, Depends

from backend.dependencies import get_current_user
from backend.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}/status")
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get the current state of a Celery background task.

    Args:
        task_id: The Celery task ID returned when the task was enqueued.

    Returns:
        A dict with task_id and state (PENDING, STARTED, SUCCESS, FAILURE).
    """
    # Task IDs are UUIDs (not enumerable), so cross-user risk is low.
    # TODO: For stricter isolation, store (task_id → user_id) in Redis at enqueue time.
    result = AsyncResult(task_id)
    # Only return state, never result payload (may contain other user's data)
    logger.debug("Task %s state: %s (user=%s)", task_id, result.state, current_user.id)
    return {"task_id": task_id, "state": result.state}
