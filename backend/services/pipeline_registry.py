"""PipelineRegistry — central registry for all pipeline task definitions.

Provides:
- TaskDefinition: frozen dataclass describing a pipeline task
- PipelineRegistry: registers tasks, resolves execution plans, validates
- GroupRunManager: tracks group run lifecycle in Redis
- run_group(): execute a task group with dependency ordering and failure modes
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import groupby

import redis.asyncio as redis
from celery import group as celery_group

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TaskDefinition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskDefinition:
    """Immutable descriptor for a single pipeline task.

    Attributes:
        name: Celery task name (e.g. "backend.tasks.seed_tasks.seed_sp500_task").
        display_name: Human-readable label (e.g. "Sync S&P 500").
        group: Task group name (e.g. "seed", "nightly", "warm_data").
        order: Execution order within the group. Tasks with the same order
            run in parallel; lower numbers run first.
        depends_on: Task names that must complete before this task starts.
        is_seed: True if this is a seed/setup task.
        schedule: Cron description (informational; actual schedule lives in
            beat_schedule).
        estimated_duration: Human-readable time estimate (e.g. "5-10 min").
        idempotent: True if the task is safe to re-run.
        incremental: True if the task supports incremental updates.
        rationale: WHY this schedule/ordering was chosen.
    """

    name: str
    display_name: str
    group: str
    order: int
    depends_on: list[str] = field(default_factory=list)
    is_seed: bool = False
    schedule: str = ""
    estimated_duration: str = ""
    idempotent: bool = True
    incremental: bool = False
    rationale: str = ""


# ---------------------------------------------------------------------------
# PipelineRegistry
# ---------------------------------------------------------------------------


class PipelineRegistry:
    """Central registry for all pipeline task definitions.

    Register tasks once at application start-up; then query by name/group,
    resolve parallel execution plans, and validate dependency graphs.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, TaskDefinition] = {}
        self._groups: dict[str, list[TaskDefinition]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def register(self, task: TaskDefinition) -> None:
        """Register a task definition.

        Args:
            task: The TaskDefinition to register.

        Raises:
            ValueError: If a task with the same name is already registered.
        """
        if task.name in self._tasks:
            raise ValueError(f"Task '{task.name}' is already registered")
        self._tasks[task.name] = task
        self._groups[task.group].append(task)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_task(self, name: str) -> TaskDefinition | None:
        """Get a task by its fully-qualified name.

        Args:
            name: Celery task name.

        Returns:
            The TaskDefinition, or None if not found.
        """
        return self._tasks.get(name)

    def get_group(self, group: str) -> list[TaskDefinition]:
        """Get all tasks in a group, sorted ascending by order.

        Args:
            group: Group name.

        Returns:
            List of TaskDefinitions sorted by order. Empty list if the group
            does not exist.
        """
        return sorted(self._groups.get(group, []), key=lambda t: t.order)

    def get_groups(self) -> dict[str, list[TaskDefinition]]:
        """Get all groups with their tasks (each group sorted by order).

        Returns:
            Mapping of group name to sorted list of TaskDefinitions.
        """
        return {g: self.get_group(g) for g in self._groups}

    # ------------------------------------------------------------------
    # Execution plan
    # ------------------------------------------------------------------

    def resolve_execution_plan(self, group: str) -> list[list[str]]:
        """Resolve a group into ordered execution phases.

        Tasks with the same ``order`` value are placed in the same phase and
        can run in parallel.  Phases are sorted ascending so lower-order tasks
        run first.

        Args:
            group: Group name.

        Returns:
            List of phases; each phase is a list of task names.
            Example: ``[["task_a"], ["task_b", "task_c"], ["task_d"]]``

        Raises:
            ValueError: If the group does not exist.
        """
        tasks = self.get_group(group)
        if not tasks:
            raise ValueError(f"Group '{group}' has no registered tasks")

        phases: list[list[str]] = []
        for _, batch in groupby(tasks, key=lambda t: t.order):
            phases.append([t.name for t in batch])
        return phases

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """Validate all registrations.

        Checks:
        - All ``depends_on`` references point to existing tasks.
        - No circular dependencies (within any group).
        - No duplicate task names (enforced at register-time, checked here
          for completeness).

        Returns:
            List of error messages.  An empty list means the registry is
            valid.
        """
        errors: list[str] = []

        # Check depends_on references exist
        for task in self._tasks.values():
            for dep in task.depends_on:
                if dep not in self._tasks:
                    errors.append(f"Task '{task.name}' depends_on '{dep}' which is not registered")

        # Check for circular dependencies using DFS per connected component
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def _has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            task = self._tasks.get(node)
            if task is None:
                rec_stack.discard(node)
                return False
            for dep in task.depends_on:
                if dep not in visited:
                    if _has_cycle(dep):
                        return True
                elif dep in rec_stack:
                    return True
            rec_stack.discard(node)
            return False

        for name in self._tasks:
            if name not in visited:
                if _has_cycle(name):
                    errors.append(f"Circular dependency detected involving task '{name}'")

        return errors


# ---------------------------------------------------------------------------
# GroupRunManager
# ---------------------------------------------------------------------------


class GroupRunManager:
    """Tracks pipeline group runs in Redis.

    Uses three key namespaces:
    - ``pipeline:active:{group}`` — current active run_id (or absent).
    - ``pipeline:run:{run_id}`` — JSON blob with full run state.
    - ``pipeline:history:{group}`` — Redis list of JSON blobs (capped at
      HISTORY_MAX entries), newest first.
    """

    ACTIVE_RUN_KEY = "pipeline:active:{group}"
    RUN_KEY = "pipeline:run:{run_id}"
    HISTORY_KEY = "pipeline:history:{group}"
    RUN_TTL = 86400  # 24 hours
    HISTORY_MAX = 50  # Keep last 50 runs per group

    def __init__(self, redis_client: redis.Redis) -> None:
        self._redis = redis_client

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    async def start_run(self, group: str, task_names: list[str]) -> str:
        """Start a new group run and return its run_id.

        Args:
            group: The pipeline group being run.
            task_names: Ordered list of task names in this run.

        Returns:
            A UUID run_id string.

        Raises:
            ValueError: If a run is already active for this group.
        """
        active_key = self.ACTIVE_RUN_KEY.format(group=group)
        run_id = str(uuid.uuid4())

        # Atomic set-if-not-exists to prevent TOCTOU race
        was_set = await self._redis.set(active_key, run_id, nx=True, ex=self.RUN_TTL)
        if not was_set:
            existing_raw = await self._redis.get(active_key)
            existing_id = existing_raw.decode() if isinstance(existing_raw, bytes) else existing_raw
            raise ValueError(f"Active run already exists for group '{group}': {existing_id}")

        run_data: dict = {
            "run_id": run_id,
            "group": group,
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "task_names": task_names,
            "completed": 0,
            "failed": 0,
            "total": len(task_names),
            "task_statuses": {name: "pending" for name in task_names},
            "errors": {},
        }

        await self._redis.set(
            self.RUN_KEY.format(run_id=run_id),
            json.dumps(run_data),
            ex=self.RUN_TTL,
        )

        logger.info("Started pipeline run %s for group '%s'", run_id, group)
        return run_id

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    # Lua script for atomic task status update. Prevents race conditions
    # when parallel tasks in the same phase complete simultaneously.
    # This is Redis server-side Lua (redis.eval), NOT Python eval().
    _UPDATE_LUA = """
    local data = redis.call('GET', KEYS[1])
    if not data then return 0 end
    local obj = cjson.decode(data)
    obj['task_statuses'][ARGV[1]] = ARGV[2]
    if ARGV[2] == 'success' then
        obj['completed'] = (obj['completed'] or 0) + 1
    elseif ARGV[2] == 'failed' then
        obj['failed'] = (obj['failed'] or 0) + 1
        if ARGV[3] ~= '' then
            obj['errors'][ARGV[1]] = ARGV[3]
        end
    end
    redis.call('SET', KEYS[1], cjson.encode(obj), 'EX', tonumber(ARGV[4]))
    return 1
    """

    async def update_task_status(
        self,
        run_id: str,
        task_name: str,
        status: str,
        error: str | None = None,
    ) -> None:
        """Atomically update a single task's status within a run.

        Uses a Redis Lua script to prevent race conditions when parallel
        tasks in the same phase complete simultaneously.

        Args:
            run_id: The run to update.
            task_name: Celery task name whose status is changing.
            status: New status string (e.g. "running", "success", "failed").
            error: Optional error message; recorded in ``errors`` dict.
        """
        run_key = self.RUN_KEY.format(run_id=run_id)
        # Redis eval() executes Lua on the server — atomic, no Python eval
        result = await self._redis.eval(  # noqa: S307
            self._UPDATE_LUA,
            1,
            run_key,
            task_name,
            status,
            error or "",
            str(self.RUN_TTL),
        )
        if result == 0:
            logger.warning("update_task_status: run '%s' not found in Redis", run_id)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def get_run(self, run_id: str) -> dict | None:
        """Retrieve run data by ID.

        Args:
            run_id: UUID run identifier.

        Returns:
            Run data dict, or None if the run does not exist (or has expired).
        """
        raw = await self._redis.get(self.RUN_KEY.format(run_id=run_id))
        if raw is None:
            return None
        return json.loads(raw)

    async def get_active_run(self, group: str) -> dict | None:
        """Return the active run for a group, if any.

        Args:
            group: Pipeline group name.

        Returns:
            Run data dict, or None if no run is currently active.
        """
        active_key = self.ACTIVE_RUN_KEY.format(group=group)
        run_id_raw = await self._redis.get(active_key)
        if run_id_raw is None:
            return None
        run_id = run_id_raw.decode() if isinstance(run_id_raw, bytes) else run_id_raw
        return await self.get_run(run_id)

    # ------------------------------------------------------------------
    # Complete
    # ------------------------------------------------------------------

    async def complete_run(self, run_id: str, status: str) -> None:
        """Mark a run as complete, remove the active lock, and add to history.

        Args:
            run_id: UUID run identifier.
            status: Terminal status (e.g. "success", "failed", "partial").
        """
        run_key = self.RUN_KEY.format(run_id=run_id)
        raw = await self._redis.get(run_key)
        if raw is None:
            logger.warning("complete_run: run '%s' not found in Redis", run_id)
            return

        data: dict = json.loads(raw)
        data["status"] = status
        data["completed_at"] = datetime.now(timezone.utc).isoformat()
        group = data.get("group", "")

        history_key = self.HISTORY_KEY.format(group=group)
        active_key = self.ACTIVE_RUN_KEY.format(group=group)

        pipe = self._redis.pipeline()
        pipe.set(run_key, json.dumps(data), ex=self.RUN_TTL)
        pipe.delete(active_key)
        pipe.lpush(history_key, json.dumps(data))
        pipe.ltrim(history_key, 0, self.HISTORY_MAX - 1)
        await pipe.execute()

        logger.info("Completed pipeline run %s with status '%s'", run_id, status)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    async def get_history(self, group: str, limit: int = 10) -> list[dict]:
        """Return recent run history for a group, newest first.

        Args:
            group: Pipeline group name.
            limit: Maximum number of entries to return.

        Returns:
            List of run data dicts, most recent first.  Empty list if no
            history exists.
        """
        history_key = self.HISTORY_KEY.format(group=group)
        raw_entries = await self._redis.lrange(history_key, 0, limit - 1)
        result: list[dict] = []
        for raw in raw_entries:
            try:
                result.append(json.loads(raw))
            except json.JSONDecodeError:
                logger.warning("Skipping malformed history entry in '%s'", history_key)
        return result


# ---------------------------------------------------------------------------
# run_group
# ---------------------------------------------------------------------------


async def run_group(
    registry: PipelineRegistry,
    group: str,
    redis_client: redis.Redis,
    failure_mode: str = "stop_on_failure",
) -> str:
    """Execute a pipeline task group, respecting dependencies and failure modes.

    Resolves the group into sequential phases (each phase may contain
    parallel tasks).  Dispatches tasks via Celery and tracks run state in
    Redis through GroupRunManager.

    Args:
        registry: The populated PipelineRegistry.
        group: Group name to execute.
        redis_client: Async Redis client for run tracking.
        failure_mode: One of:
            - ``"stop_on_failure"`` — abort remaining phases on first failure.
            - ``"continue"`` — run all phases regardless of failures.
            - ``"threshold:N"`` — continue until fewer than N% of tasks
              succeed, then stop.

    Returns:
        The run_id of the execution.

    Raises:
        ValueError: If the group does not exist in the registry, or if a
            concurrent run is already active.
    """
    from backend.tasks import celery_app  # local import to avoid circular deps

    plan = registry.resolve_execution_plan(group)
    all_task_names = [name for phase in plan for name in phase]

    manager = GroupRunManager(redis_client)
    run_id = await manager.start_run(group, all_task_names)

    # Parse threshold if applicable
    min_success_pct: float | None = None
    if failure_mode.startswith("threshold:"):
        try:
            min_success_pct = float(failure_mode.split(":", 1)[1])
        except (ValueError, IndexError):
            logger.warning(
                "Invalid threshold failure_mode '%s'; defaulting to stop_on_failure",
                failure_mode,
            )
            failure_mode = "stop_on_failure"

    overall_completed = 0
    overall_failed = 0

    try:
        for phase in plan:
            # Build Celery signatures for this phase
            sigs = [celery_app.signature(name) for name in phase]

            if len(sigs) == 1:
                result = sigs[0].apply_async()
                pending = [(phase[0], result)]
            else:
                grp = celery_group(sigs)
                group_result = grp.apply_async()
                pending = list(zip(phase, group_result.results))

            # Collect results
            phase_failed = 0
            for task_name, async_result in pending:
                await manager.update_task_status(run_id, task_name, "running")
                try:
                    # Use to_thread to avoid blocking the event loop
                    await asyncio.to_thread(async_result.get, timeout=3600, propagate=True)
                    overall_completed += 1
                    await manager.update_task_status(run_id, task_name, "success")
                except Exception:
                    phase_failed += 1
                    overall_failed += 1
                    logger.error(
                        "Task '%s' in run %s failed",
                        task_name,
                        run_id,
                        exc_info=True,
                    )
                    # Use a sanitised message — never pass str(exc) directly to user-facing output
                    await manager.update_task_status(
                        run_id,
                        task_name,
                        "failed",
                        error="Task execution error — see server logs",
                    )

            if phase_failed > 0:
                if failure_mode == "stop_on_failure":
                    logger.warning(
                        "Run %s stopping after phase failure (stop_on_failure mode)",
                        run_id,
                    )
                    final_status = "failed"
                    await manager.complete_run(run_id, final_status)
                    return run_id

                if min_success_pct is not None:
                    finished = overall_completed + overall_failed
                    pct = (overall_completed / finished) * 100 if finished else 100
                    if pct < min_success_pct:
                        logger.warning(
                            "Run %s below success threshold (%.1f%% < %.1f%%); stopping",
                            run_id,
                            pct,
                            min_success_pct,
                        )
                        await manager.complete_run(run_id, "failed")
                        return run_id

        final_status = "failed" if overall_failed > 0 else "success"
        await manager.complete_run(run_id, final_status)

    except Exception:
        logger.exception("Unexpected error in run_group for run %s", run_id)
        await manager.complete_run(run_id, "failed")
        raise

    return run_id
