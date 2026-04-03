"""Admin pipeline API — task groups, manual triggers, cache management."""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user, require_admin
from backend.models.audit import AdminAuditLog
from backend.models.user import User
from backend.schemas.admin_pipeline import (
    CacheClearRequest,
    CacheClearResponse,
    PipelineGroupListResponse,
    PipelineGroupResponse,
    PipelineRunResponse,
    RunHistoryResponse,
    TaskDefinitionResponse,
    TriggerGroupRequest,
    TriggerGroupResponse,
)
from backend.services.pipeline_registry import GroupRunManager, TaskDefinition, run_group
from backend.services.pipeline_registry_config import build_registry
from backend.services.redis_pool import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/pipelines", tags=["admin-pipelines"])

# Whitelist of allowed cache-clear patterns (full Redis key patterns).
# Keys under `app:` namespace are used by cache_invalidator and market_data tasks.
CACHE_CLEAR_WHITELIST: frozenset[str] = frozenset(
    {
        "app:convergence:*",
        "app:forecast:*",
        "app:sentiment:*",
        "app:bl-forecast:*",
        "app:monte-carlo:*",
        "app:cvar:*",
        "app:sector-forecast:*",
        "app:screener:*",
        "app:sectors:*",
        "app:signals:*",
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalise_pattern(pattern: str) -> str:
    """Ensure the pattern carries the ``app:`` prefix used in Redis.

    Args:
        pattern: Raw pattern from request body (may or may not have ``app:``).

    Returns:
        Pattern prefixed with ``app:`` if it was missing.
    """
    return pattern if pattern.startswith("app:") else f"app:{pattern}"


async def _scan_and_delete(redis_client: aioredis.Redis, pattern: str) -> int:
    """Delete all Redis keys matching *pattern* using SCAN (not KEYS).

    Args:
        redis_client: Async Redis client.
        pattern: Full Redis key pattern (e.g. ``app:forecast:*``).

    Returns:
        Number of keys deleted.
    """
    deleted = 0
    batch: list[str | bytes] = []
    async for key in redis_client.scan_iter(match=pattern, count=100):
        batch.append(key)
        if len(batch) >= 100:
            await redis_client.delete(*batch)
            deleted += len(batch)
            batch.clear()
    if batch:
        await redis_client.delete(*batch)
        deleted += len(batch)
    return deleted


async def _safe_run_group(
    group: str,
    redis_client: aioredis.Redis,
    failure_mode: str,
) -> None:
    """Fire-and-forget wrapper around run_group that swallows exceptions.

    Exceptions are logged; the calling request has already returned 202.

    Args:
        group: Pipeline group name.
        redis_client: Async Redis client for GroupRunManager.
        failure_mode: One of ``stop_on_failure``, ``continue``, or
            ``threshold:N``.
    """
    registry = build_registry()
    try:
        await run_group(registry, group, redis_client, failure_mode)
    except Exception:
        logger.exception("Background run_group failed for group '%s'", group)


def _task_def_to_response(task: TaskDefinition) -> TaskDefinitionResponse:
    """Convert a TaskDefinition dataclass to a Pydantic response model.

    Args:
        task: A ``TaskDefinition`` instance from the pipeline registry.

    Returns:
        Populated ``TaskDefinitionResponse``.
    """
    return TaskDefinitionResponse(
        name=task.name,
        display_name=task.display_name,
        group=task.group,
        order=task.order,
        is_seed=task.is_seed,
        schedule=task.schedule,
        estimated_duration=task.estimated_duration,
        idempotent=task.idempotent,
        incremental=task.incremental,
        rationale=task.rationale,
        depends_on=list(task.depends_on),
    )


def _run_dict_to_response(data: dict) -> PipelineRunResponse:
    """Convert a raw run dict (from Redis) to a ``PipelineRunResponse``.

    Args:
        data: Raw dict stored in Redis by GroupRunManager.

    Returns:
        Populated ``PipelineRunResponse``.
    """
    return PipelineRunResponse(
        run_id=data["run_id"],
        group=data["group"],
        status=data["status"],
        started_at=data["started_at"],
        completed_at=data.get("completed_at"),
        task_names=data.get("task_names", []),
        completed=data.get("completed", 0),
        failed=data.get("failed", 0),
        total=data.get("total", 0),
        task_statuses=data.get("task_statuses", {}),
        errors=data.get("errors", {}),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/groups",
    response_model=PipelineGroupListResponse,
    summary="List all pipeline groups",
    description=(
        "Returns all registered pipeline task groups with their tasks and "
        "execution plans. Admin-only."
    ),
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not admin"},
    },
)
async def list_pipeline_groups(
    user: Annotated[User, Depends(get_current_user)],
) -> PipelineGroupListResponse:
    """List all pipeline groups with their tasks and resolved execution plans."""
    require_admin(user)

    registry = build_registry()
    groups_data = registry.get_groups()

    groups = []
    for group_name, tasks in groups_data.items():
        execution_plan = registry.resolve_execution_plan(group_name)
        groups.append(
            PipelineGroupResponse(
                name=group_name,
                tasks=[_task_def_to_response(t) for t in tasks],
                execution_plan=execution_plan,
            )
        )

    return PipelineGroupListResponse(groups=groups)


@router.get(
    "/groups/{group}",
    response_model=PipelineGroupResponse,
    summary="Get a single pipeline group",
    description="Returns task list and execution plan for a specific pipeline group.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not admin"},
        404: {"description": "Pipeline group not found"},
    },
)
async def get_pipeline_group(
    group: Annotated[str, Path(pattern=r"^[a-z_]{1,50}$")],
    user: Annotated[User, Depends(get_current_user)],
) -> PipelineGroupResponse:
    """Return details for a single pipeline group by name."""
    require_admin(user)

    registry = build_registry()
    tasks = registry.get_group(group)
    if not tasks:
        raise HTTPException(status_code=404, detail="Pipeline group not found")

    execution_plan = registry.resolve_execution_plan(group)
    return PipelineGroupResponse(
        name=group,
        tasks=[_task_def_to_response(t) for t in tasks],
        execution_plan=execution_plan,
    )


@router.post(
    "/groups/{group}/run",
    response_model=TriggerGroupResponse,
    status_code=202,
    summary="Trigger a pipeline group run",
    description=(
        "Dispatch a full pipeline group run as a background task. "
        "Returns 202 immediately; poll GET /groups/{group}/runs for status. "
        "Returns 409 if a run is already active for this group."
    ),
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not admin"},
        404: {"description": "Pipeline group not found"},
        409: {"description": "A run is already active for this group"},
    },
)
async def trigger_group_run(
    group: Annotated[str, Path(pattern=r"^[a-z_]{1,50}$")],
    body: TriggerGroupRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> TriggerGroupResponse:
    """Trigger a pipeline group run and return immediately (202 Accepted).

    The actual execution runs as a background asyncio task. Poll the active
    run endpoint for live status.
    """
    require_admin(user)

    registry = build_registry()
    tasks = registry.get_group(group)
    if not tasks:
        raise HTTPException(status_code=404, detail="Pipeline group not found")

    redis_client = await get_redis()
    manager = GroupRunManager(redis_client)

    active = await manager.get_active_run(group)
    if active:
        raise HTTPException(
            status_code=409,
            detail="A run is already active for this group",
        )

    # Fire and forget — run_group handles start_run, tracking, and complete_run.
    asyncio.create_task(_safe_run_group(group, redis_client, body.failure_mode))

    # Audit log the trigger action.
    audit = AdminAuditLog(
        user_id=user.id,
        action="trigger_group",
        target=group,
        metadata_={"failure_mode": body.failure_mode},
    )
    db.add(audit)
    await db.commit()

    logger.info(
        "Admin %s triggered pipeline group '%s' (failure_mode=%s)",
        user.email,
        group,
        body.failure_mode,
    )

    return TriggerGroupResponse(
        group=group,
        status="accepted",
        message=f"Pipeline group '{group}' run accepted — poll GET /groups/{group}/runs for status",
    )


@router.get(
    "/runs/{run_id}",
    response_model=PipelineRunResponse,
    summary="Get run status by ID",
    description="Returns live or historical run data for the given run_id.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not admin"},
        404: {"description": "Run not found"},
    },
)
async def get_run_status(
    run_id: str,
    user: Annotated[User, Depends(get_current_user)],
) -> PipelineRunResponse:
    """Return live run state by run_id (TTL: 24 hours)."""
    require_admin(user)

    redis_client = await get_redis()
    manager = GroupRunManager(redis_client)

    data = await manager.get_run(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Run not found")

    return _run_dict_to_response(data)


@router.get(
    "/groups/{group}/runs",
    response_model=PipelineRunResponse | None,
    summary="Get active run for a group",
    description="Returns the currently active run for the given group, or null if idle.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not admin"},
    },
)
async def get_active_run(
    group: Annotated[str, Path(pattern=r"^[a-z_]{1,50}$")],
    user: Annotated[User, Depends(get_current_user)],
) -> PipelineRunResponse | None:
    """Return the active run for a pipeline group, or None if the group is idle."""
    require_admin(user)

    redis_client = await get_redis()
    manager = GroupRunManager(redis_client)

    data = await manager.get_active_run(group)
    if data is None:
        return None

    return _run_dict_to_response(data)


@router.get(
    "/groups/{group}/history",
    response_model=RunHistoryResponse,
    summary="Get run history for a group",
    description="Returns the most recent completed runs for a pipeline group (newest first).",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not admin"},
    },
)
async def get_group_history(
    group: Annotated[str, Path(pattern=r"^[a-z_]{1,50}$")],
    user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(default=10, ge=1, le=50, description="Max runs to return"),
) -> RunHistoryResponse:
    """Return paginated run history for a pipeline group."""
    require_admin(user)

    redis_client = await get_redis()
    manager = GroupRunManager(redis_client)

    history = await manager.get_history(group, limit=limit)
    return RunHistoryResponse(
        group=group,
        runs=[_run_dict_to_response(entry) for entry in history],
    )


@router.post(
    "/cache/clear",
    response_model=CacheClearResponse,
    summary="Clear cache by pattern",
    description=(
        "Delete all Redis keys matching the given pattern. "
        "Only whitelisted patterns are accepted. "
        "Uses SCAN (not KEYS) to avoid blocking Redis."
    ),
    responses={
        400: {"description": "Pattern not in whitelist"},
        401: {"description": "Not authenticated"},
        403: {"description": "Not admin"},
    },
)
async def clear_cache_by_pattern(
    body: CacheClearRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> CacheClearResponse:
    """Clear Redis keys matching a whitelisted pattern."""
    require_admin(user)

    normalised = _normalise_pattern(body.pattern)
    if normalised not in CACHE_CLEAR_WHITELIST:
        raise HTTPException(
            status_code=400,
            detail="Pattern not in whitelist — only pre-approved cache patterns may be cleared",
        )

    redis_client = await get_redis()
    keys_deleted = await _scan_and_delete(redis_client, normalised)

    audit = AdminAuditLog(
        user_id=user.id,
        action="cache_clear",
        target=normalised,
        metadata_={"keys_deleted": keys_deleted},
    )
    db.add(audit)
    await db.commit()

    logger.info(
        "Admin %s cleared cache pattern '%s' — %d keys deleted",
        user.email,
        normalised,
        keys_deleted,
    )

    return CacheClearResponse(
        pattern=normalised,
        keys_deleted=keys_deleted,
        message=f"Cleared {keys_deleted} keys matching '{normalised}'",
    )


@router.post(
    "/cache/clear-all",
    response_model=CacheClearResponse,
    summary="Clear all whitelisted cache patterns",
    description=(
        "Iterate over all whitelisted cache patterns and delete every matching key. "
        "Useful after a major data reload or forced refresh."
    ),
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not admin"},
    },
)
async def clear_all_caches(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> CacheClearResponse:
    """Clear all whitelisted Redis cache patterns in one operation."""
    require_admin(user)

    redis_client = await get_redis()
    total_deleted = 0
    for pattern in CACHE_CLEAR_WHITELIST:
        total_deleted += await _scan_and_delete(redis_client, pattern)

    audit = AdminAuditLog(
        user_id=user.id,
        action="cache_clear_all",
        target="all",
        metadata_={"keys_deleted": total_deleted, "patterns": len(CACHE_CLEAR_WHITELIST)},
    )
    db.add(audit)
    await db.commit()

    logger.info(
        "Admin %s cleared all cache patterns — %d keys deleted across %d patterns",
        user.email,
        total_deleted,
        len(CACHE_CLEAR_WHITELIST),
    )

    return CacheClearResponse(
        pattern="all",
        keys_deleted=total_deleted,
        message=(
            f"Cleared {total_deleted} keys across all"
            f" {len(CACHE_CLEAR_WHITELIST)} whitelisted patterns"
        ),
    )
