"""Tests for backend.services.pipeline_registry.

Covers TaskDefinition immutability, PipelineRegistry CRUD + execution plan
resolution + validation, and GroupRunManager Redis lifecycle.
"""

from __future__ import annotations

import fakeredis.aioredis
import pytest

from backend.services.pipeline_registry import (
    GroupRunManager,
    PipelineRegistry,
    TaskDefinition,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task(
    name: str = "backend.tasks.seed.seed_sp500",
    display_name: str = "Sync S&P 500",
    group: str = "seed",
    order: int = 1,
    **kwargs,
) -> TaskDefinition:
    """Create a TaskDefinition with sensible defaults."""
    return TaskDefinition(
        name=name,
        display_name=display_name,
        group=group,
        order=order,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# TestTaskDefinition
# ---------------------------------------------------------------------------


class TestTaskDefinition:
    """Tests for the TaskDefinition frozen dataclass."""

    def test_creation_with_required_fields(self):
        """TaskDefinition can be created with only required fields."""
        t = TaskDefinition(
            name="backend.tasks.seed.task_a",
            display_name="Task A",
            group="seed",
            order=1,
        )
        assert t.name == "backend.tasks.seed.task_a"
        assert t.display_name == "Task A"
        assert t.group == "seed"
        assert t.order == 1

    def test_default_values(self):
        """Unspecified optional fields use correct defaults."""
        t = _make_task()
        assert t.depends_on == []
        assert t.is_seed is False
        assert t.schedule == ""
        assert t.estimated_duration == ""
        assert t.idempotent is True
        assert t.incremental is False
        assert t.rationale == ""

    def test_creation_with_all_fields(self):
        """TaskDefinition stores all supplied fields correctly."""
        t = TaskDefinition(
            name="backend.tasks.nightly.refresh_prices",
            display_name="Refresh Prices",
            group="nightly",
            order=2,
            depends_on=["backend.tasks.seed.seed_sp500"],
            is_seed=False,
            schedule="0 2 * * *",
            estimated_duration="10-20 min",
            idempotent=True,
            incremental=True,
            rationale="Run after market close to capture end-of-day prices",
        )
        assert t.depends_on == ["backend.tasks.seed.seed_sp500"]
        assert t.schedule == "0 2 * * *"
        assert t.incremental is True
        assert t.rationale == "Run after market close to capture end-of-day prices"

    def test_frozen_prevents_attribute_mutation(self):
        """TaskDefinition is frozen — attribute assignment raises FrozenInstanceError."""
        t = _make_task()
        with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
            t.name = "something_else"  # type: ignore[misc]

    def test_equality_based_on_fields(self):
        """Two TaskDefinitions with identical fields are equal."""
        t1 = _make_task(name="a.b.c")
        t2 = _make_task(name="a.b.c")
        assert t1 == t2

    def test_inequality_on_different_fields(self):
        """Two TaskDefinitions with different names are not equal."""
        assert _make_task(name="a") != _make_task(name="b")


# ---------------------------------------------------------------------------
# TestPipelineRegistry
# ---------------------------------------------------------------------------


class TestPipelineRegistry:
    """Tests for PipelineRegistry register / query / validate operations."""

    @pytest.fixture()
    def registry(self) -> PipelineRegistry:
        """Provide a fresh empty registry."""
        return PipelineRegistry()

    @pytest.fixture()
    def seed_tasks(self) -> list[TaskDefinition]:
        """Three tasks in the 'seed' group at different orders."""
        return [
            _make_task(name="task.a", group="seed", order=1),
            _make_task(name="task.b", group="seed", order=2),
            _make_task(name="task.c", group="seed", order=3),
        ]

    # --- register / get_task ---

    def test_register_and_retrieve_single_task(self, registry):
        """Registering a task allows retrieval by name."""
        t = _make_task(name="task.x")
        registry.register(t)
        assert registry.get_task("task.x") is t

    def test_get_task_returns_none_for_unknown(self, registry):
        """get_task returns None for an unregistered name."""
        assert registry.get_task("does.not.exist") is None

    def test_register_duplicate_raises(self, registry):
        """Registering the same name twice raises ValueError."""
        t = _make_task(name="task.dup")
        registry.register(t)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(t)

    # --- get_group ---

    def test_get_group_returns_sorted_by_order(self, registry, seed_tasks):
        """get_group returns tasks in ascending order regardless of registration order."""
        # Register in reverse order
        for t in reversed(seed_tasks):
            registry.register(t)
        result = registry.get_group("seed")
        orders = [t.order for t in result]
        assert orders == sorted(orders)

    def test_get_group_returns_empty_for_unknown_group(self, registry):
        """get_group returns an empty list for an unregistered group."""
        assert registry.get_group("nonexistent") == []

    def test_get_group_multiple_groups(self, registry):
        """Tasks from different groups are isolated."""
        registry.register(_make_task(name="seed.a", group="seed", order=1))
        registry.register(_make_task(name="nightly.a", group="nightly", order=1))
        assert len(registry.get_group("seed")) == 1
        assert len(registry.get_group("nightly")) == 1

    # --- get_groups ---

    def test_get_groups_returns_all_groups(self, registry, seed_tasks):
        """get_groups returns a mapping containing every registered group."""
        for t in seed_tasks:
            registry.register(t)
        registry.register(_make_task(name="nightly.a", group="nightly", order=1))
        groups = registry.get_groups()
        assert set(groups.keys()) == {"seed", "nightly"}

    # --- resolve_execution_plan ---

    def test_resolve_plan_single_sequential_group(self, registry, seed_tasks):
        """Single-phase sequential tasks produce one task per phase."""
        for t in seed_tasks:
            registry.register(t)
        plan = registry.resolve_execution_plan("seed")
        assert plan == [["task.a"], ["task.b"], ["task.c"]]

    def test_resolve_plan_parallel_tasks_same_order(self, registry):
        """Tasks with the same order are placed in the same parallel phase."""
        registry.register(_make_task(name="p.a", group="parallel", order=1))
        registry.register(_make_task(name="p.b", group="parallel", order=1))
        registry.register(_make_task(name="p.c", group="parallel", order=2))
        plan = registry.resolve_execution_plan("parallel")
        assert len(plan) == 2
        # First phase has both order-1 tasks (order within phase is stable)
        assert set(plan[0]) == {"p.a", "p.b"}
        assert plan[1] == ["p.c"]

    def test_resolve_plan_mixed_sequential_and_parallel(self, registry):
        """Mixed orders produce the correct phase structure."""
        registry.register(_make_task(name="m.a", group="mix", order=1))
        registry.register(_make_task(name="m.b", group="mix", order=2))
        registry.register(_make_task(name="m.c", group="mix", order=2))
        registry.register(_make_task(name="m.d", group="mix", order=3))
        plan = registry.resolve_execution_plan("mix")
        assert plan[0] == ["m.a"]
        assert set(plan[1]) == {"m.b", "m.c"}
        assert plan[2] == ["m.d"]

    def test_resolve_plan_raises_for_empty_group(self, registry):
        """resolve_execution_plan raises ValueError when the group is empty."""
        with pytest.raises(ValueError, match="no registered tasks"):
            registry.resolve_execution_plan("empty_group")

    # --- validate ---

    def test_validate_clean_registry(self, registry, seed_tasks):
        """A valid registry (no missing deps, no cycles) returns an empty error list."""
        for t in seed_tasks:
            registry.register(t)
        assert registry.validate() == []

    def test_validate_detects_missing_dependency(self, registry):
        """validate reports an error when a depends_on target is not registered."""
        registry.register(
            _make_task(
                name="task.b",
                group="g",
                order=2,
                depends_on=["task.a"],  # task.a is NOT registered
            )
        )
        errors = registry.validate()
        assert any("task.a" in e for e in errors)

    def test_validate_accepts_satisfied_dependency(self, registry):
        """validate is silent when depends_on targets are all registered."""
        registry.register(_make_task(name="task.a", group="g", order=1))
        registry.register(_make_task(name="task.b", group="g", order=2, depends_on=["task.a"]))
        assert registry.validate() == []

    def test_validate_detects_circular_dependency(self, registry):
        """validate reports an error when a dependency cycle exists."""
        # a → b → a
        registry.register(_make_task(name="cyc.a", group="g", order=1, depends_on=["cyc.b"]))
        registry.register(_make_task(name="cyc.b", group="g", order=2, depends_on=["cyc.a"]))
        errors = registry.validate()
        assert len(errors) > 0

    def test_validate_empty_registry(self, registry):
        """An empty registry is trivially valid."""
        assert registry.validate() == []


# ---------------------------------------------------------------------------
# TestGroupRunManager
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_redis():
    """In-memory async Redis instance via fakeredis."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture()
def manager(fake_redis) -> GroupRunManager:
    """GroupRunManager backed by fakeredis."""
    return GroupRunManager(fake_redis)


class TestGroupRunManager:
    """Tests for GroupRunManager Redis lifecycle."""

    @pytest.mark.asyncio
    async def test_start_run_creates_run_data(self, manager):
        """start_run stores full run data in Redis and returns a UUID."""
        task_names = ["task.a", "task.b"]
        run_id = await manager.start_run("seed", task_names)
        assert run_id  # non-empty string

        data = await manager.get_run(run_id)
        assert data is not None
        assert data["run_id"] == run_id
        assert data["group"] == "seed"
        assert data["status"] == "running"
        assert data["total"] == 2
        assert data["task_statuses"] == {"task.a": "pending", "task.b": "pending"}

    @pytest.mark.asyncio
    async def test_start_run_rejects_concurrent_run(self, manager):
        """start_run raises ValueError when a run is already active for the group."""
        await manager.start_run("seed", ["task.a"])
        with pytest.raises(ValueError, match="Active run already exists"):
            await manager.start_run("seed", ["task.b"])

    @pytest.mark.asyncio
    async def test_start_run_different_groups_allowed(self, manager):
        """Concurrent runs for different groups are permitted."""
        id1 = await manager.start_run("seed", ["task.a"])
        id2 = await manager.start_run("nightly", ["task.b"])
        assert id1 != id2

    @pytest.mark.asyncio
    async def test_update_task_status_success(self, manager):
        """update_task_status increments completed counter on 'success'."""
        run_id = await manager.start_run("seed", ["task.a", "task.b"])
        await manager.update_task_status(run_id, "task.a", "success")

        data = await manager.get_run(run_id)
        assert data["task_statuses"]["task.a"] == "success"
        assert data["completed"] == 1

    @pytest.mark.asyncio
    async def test_update_task_status_failed_records_error(self, manager):
        """update_task_status increments failed counter and stores error message."""
        run_id = await manager.start_run("seed", ["task.a"])
        await manager.update_task_status(run_id, "task.a", "failed", error="boom")

        data = await manager.get_run(run_id)
        assert data["task_statuses"]["task.a"] == "failed"
        assert data["failed"] == 1
        assert data["errors"]["task.a"] == "boom"

    @pytest.mark.asyncio
    async def test_update_task_status_noop_for_missing_run(self, manager):
        """update_task_status does not raise when the run_id is unknown."""
        # Should not raise — just logs a warning
        await manager.update_task_status("nonexistent-id", "task.a", "success")

    @pytest.mark.asyncio
    async def test_complete_run_removes_active_lock(self, fake_redis, manager):
        """complete_run deletes the active key so a new run can start."""
        run_id = await manager.start_run("seed", ["task.a"])
        await manager.complete_run(run_id, "success")

        # Active lock should be gone
        active_key = GroupRunManager.ACTIVE_RUN_KEY.format(group="seed")
        assert await fake_redis.get(active_key) is None

    @pytest.mark.asyncio
    async def test_complete_run_adds_to_history(self, manager):
        """complete_run pushes the run onto the history list."""
        run_id = await manager.start_run("seed", ["task.a"])
        await manager.complete_run(run_id, "success")

        history = await manager.get_history("seed")
        assert len(history) == 1
        assert history[0]["run_id"] == run_id
        assert history[0]["status"] == "success"

    @pytest.mark.asyncio
    async def test_complete_run_updates_run_status(self, manager):
        """complete_run sets the terminal status on the run blob."""
        run_id = await manager.start_run("seed", ["task.a"])
        await manager.complete_run(run_id, "failed")

        data = await manager.get_run(run_id)
        assert data["status"] == "failed"
        assert "completed_at" in data

    @pytest.mark.asyncio
    async def test_get_run_returns_none_for_missing(self, manager):
        """get_run returns None when the run_id is not in Redis."""
        assert await manager.get_run("does-not-exist") is None

    @pytest.mark.asyncio
    async def test_get_active_run_returns_none_when_no_active(self, manager):
        """get_active_run returns None when no run is active."""
        assert await manager.get_active_run("seed") is None

    @pytest.mark.asyncio
    async def test_get_active_run_returns_current_run(self, manager):
        """get_active_run returns the in-progress run data."""
        run_id = await manager.start_run("seed", ["task.a"])
        active = await manager.get_active_run("seed")
        assert active is not None
        assert active["run_id"] == run_id

    @pytest.mark.asyncio
    async def test_get_history_returns_empty_initially(self, manager):
        """get_history returns an empty list before any runs complete."""
        assert await manager.get_history("seed") == []

    @pytest.mark.asyncio
    async def test_get_history_respects_limit(self, manager):
        """get_history honours the limit parameter."""
        for i in range(5):
            run_id = await manager.start_run(f"g{i}", [f"task.{i}"])
            await manager.complete_run(run_id, "success")

        # Use the same group for multiple runs by completing between starts
        for i in range(5):
            run_id = await manager.start_run("batch", [f"task.{i}"])
            await manager.complete_run(run_id, "success")

        history = await manager.get_history("batch", limit=3)
        assert len(history) == 3

    @pytest.mark.asyncio
    async def test_history_capped_at_history_max(self, manager):
        """History list does not exceed HISTORY_MAX entries."""
        # Insert HISTORY_MAX + 5 entries
        cap = GroupRunManager.HISTORY_MAX
        for i in range(cap + 5):
            run_id = await manager.start_run("capped", [f"t.{i}"])
            await manager.complete_run(run_id, "success")

        history = await manager.get_history("capped", limit=cap + 10)
        assert len(history) <= cap

    @pytest.mark.asyncio
    async def test_run_ttl_is_set(self, fake_redis, manager):
        """start_run sets a TTL on the run key in Redis."""
        run_id = await manager.start_run("seed", ["task.a"])
        run_key = GroupRunManager.RUN_KEY.format(run_id=run_id)
        ttl = await fake_redis.ttl(run_key)
        # fakeredis returns -1 for no TTL, positive for TTL set
        assert ttl > 0
        assert ttl <= GroupRunManager.RUN_TTL


# ---------------------------------------------------------------------------
# TestRunGroup
# ---------------------------------------------------------------------------


def _make_celery_mock(task_results: dict[str, Exception | object]) -> object:
    """Build a mock celery_app whose tasks return or raise per task_results.

    Args:
        task_results: Mapping of task name → return value or Exception to raise.

    Returns:
        A MagicMock that mimics celery_app.signature(...).apply_async() and
        celery_group(...).apply_async().results.
    """
    from unittest.mock import MagicMock

    def _make_result(value: Exception | object) -> MagicMock:
        """Create a mock AsyncResult whose .get() returns or raises value."""
        result = MagicMock()
        if isinstance(value, Exception):
            result.get = MagicMock(side_effect=value)
        else:
            result.get = MagicMock(return_value=value)
        return result

    # Map task name → mock AsyncResult
    results_by_name: dict[str, MagicMock] = {
        name: _make_result(val) for name, val in task_results.items()
    }

    # celery_app.signature(name).apply_async() → the mock result for that name
    def _signature(name: str) -> MagicMock:
        sig = MagicMock()
        sig.apply_async.return_value = results_by_name[name]
        # store the name so the group mock can access it
        sig._task_name = name
        return sig

    mock_celery = MagicMock()
    mock_celery.signature.side_effect = _signature

    # celery.group(sigs).apply_async() → a GroupResult whose .results matches order
    def _group(sigs):  # type: ignore[no-untyped-def]
        group_result = MagicMock()
        group_result.results = [results_by_name[sig._task_name] for sig in sigs]
        group_mock = MagicMock()
        group_mock.apply_async.return_value = group_result
        return group_mock

    mock_celery._group_factory = _group
    return mock_celery, _group


async def _fake_to_thread(fn, *args, **kwargs):  # type: ignore[no-untyped-def]
    """Synchronously call fn(*args, **kwargs) instead of offloading to a thread.

    This avoids spawning a real thread in unit tests while still exercising the
    underlying .get() call.
    """
    return fn(*args, **kwargs)


def _build_registry(*tasks: tuple[str, int]) -> "PipelineRegistry":
    """Build a PipelineRegistry from (name, order) pairs all in group 'grp'.

    Args:
        *tasks: Variable-length sequence of (task_name, order) tuples.

    Returns:
        A PipelineRegistry with all tasks registered in group 'grp'.
    """
    registry = PipelineRegistry()
    for name, order in tasks:
        registry.register(
            TaskDefinition(
                name=name,
                display_name=name,
                group="grp",
                order=order,
            )
        )
    return registry


class TestRunGroup:
    """Tests for the run_group() pipeline execution function."""

    @pytest.mark.asyncio
    async def test_happy_path_all_succeed(self):
        """All tasks in a 2-phase plan succeed → run completes with 'success'."""
        from unittest.mock import patch

        from backend.services.pipeline_registry import run_group

        registry = _build_registry(("task.a", 1), ("task.b", 2))
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

        mock_celery, group_factory = _make_celery_mock(
            {"task.a": {"ok": True}, "task.b": {"ok": True}}
        )

        with (
            patch("backend.tasks.celery_app", mock_celery),
            patch("celery.group", side_effect=group_factory),
            patch("asyncio.to_thread", side_effect=_fake_to_thread),
        ):
            run_id = await run_group(registry, "grp", redis)

        manager = GroupRunManager(redis)
        data = await manager.get_run(run_id)
        assert data is not None
        assert data["status"] == "success"
        assert data["completed"] == 2
        assert data["failed"] == 0

    @pytest.mark.asyncio
    async def test_stop_on_failure_stops_at_first_failure(self):
        """Phase 1 task fails in stop_on_failure mode → run stops immediately with 'failed'."""
        from unittest.mock import patch

        from backend.services.pipeline_registry import run_group

        # phase 1: task.a fails; phase 2: task.b would succeed but never runs
        registry = _build_registry(("task.a", 1), ("task.b", 2))
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

        mock_celery, group_factory = _make_celery_mock(
            {"task.a": RuntimeError("boom"), "task.b": {"ok": True}}
        )

        with (
            patch("backend.tasks.celery_app", mock_celery),
            patch("celery.group", side_effect=group_factory),
            patch("asyncio.to_thread", side_effect=_fake_to_thread),
        ):
            run_id = await run_group(registry, "grp", redis, failure_mode="stop_on_failure")

        manager = GroupRunManager(redis)
        data = await manager.get_run(run_id)
        assert data is not None
        assert data["status"] == "failed"
        # task.b was never dispatched — its status remains 'pending'
        assert data["task_statuses"]["task.b"] == "pending"

    @pytest.mark.asyncio
    async def test_continue_mode_runs_all_phases(self):
        """Phase 1 fails in 'continue' mode → all phases still execute, status 'failed'."""
        from unittest.mock import patch

        from backend.services.pipeline_registry import run_group

        registry = _build_registry(("task.a", 1), ("task.b", 2))
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

        mock_celery, group_factory = _make_celery_mock(
            {"task.a": RuntimeError("phase1 fail"), "task.b": {"ok": True}}
        )

        with (
            patch("backend.tasks.celery_app", mock_celery),
            patch("celery.group", side_effect=group_factory),
            patch("asyncio.to_thread", side_effect=_fake_to_thread),
        ):
            run_id = await run_group(registry, "grp", redis, failure_mode="continue")

        manager = GroupRunManager(redis)
        data = await manager.get_run(run_id)
        assert data is not None
        assert data["status"] == "failed"
        # Both phases ran — task.b reached 'success' despite task.a failing
        assert data["task_statuses"]["task.a"] == "failed"
        assert data["task_statuses"]["task.b"] == "success"

    @pytest.mark.asyncio
    async def test_threshold_above_continues(self):
        """threshold:50 with 2/3 tasks succeeding stays above threshold → all phases run."""
        from unittest.mock import patch

        from backend.services.pipeline_registry import run_group

        # Phase 1: task.a + task.b run in parallel (same order=1); task.c is phase 2
        registry = _build_registry(("task.a", 1), ("task.b", 1), ("task.c", 2))
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

        # task.a succeeds, task.b fails → 1/2 = 50%, exactly at threshold; task.c succeeds
        mock_celery, group_factory = _make_celery_mock(
            {
                "task.a": {"ok": True},
                "task.b": RuntimeError("fail"),
                "task.c": {"ok": True},
            }
        )

        with (
            patch("backend.tasks.celery_app", mock_celery),
            patch("backend.services.pipeline_registry.celery_group", side_effect=group_factory),
            patch("asyncio.to_thread", side_effect=_fake_to_thread),
        ):
            run_id = await run_group(registry, "grp", redis, failure_mode="threshold:50")

        manager = GroupRunManager(redis)
        data = await manager.get_run(run_id)
        assert data is not None
        # 50% success == threshold (not below), so continues and finishes as failed
        # (because overall_failed > 0)
        assert data["task_statuses"]["task.c"] == "success"

    @pytest.mark.asyncio
    async def test_threshold_below_stops(self):
        """threshold:90 with 1/3 tasks succeeding falls below threshold → stops with 'failed'."""
        from unittest.mock import patch

        from backend.services.pipeline_registry import run_group

        # Phase 1: task.a, task.b, task.c all parallel (order=1); phase 2 would not run
        registry = _build_registry(
            ("task.a", 1),
            ("task.b", 1),
            ("task.c", 1),
            ("task.d", 2),
        )
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

        mock_celery, group_factory = _make_celery_mock(
            {
                "task.a": {"ok": True},
                "task.b": RuntimeError("fail"),
                "task.c": RuntimeError("fail"),
                "task.d": {"ok": True},
            }
        )

        with (
            patch("backend.tasks.celery_app", mock_celery),
            patch("backend.services.pipeline_registry.celery_group", side_effect=group_factory),
            patch("asyncio.to_thread", side_effect=_fake_to_thread),
        ):
            run_id = await run_group(registry, "grp", redis, failure_mode="threshold:90")

        manager = GroupRunManager(redis)
        data = await manager.get_run(run_id)
        assert data is not None
        assert data["status"] == "failed"
        # Phase 2 never ran — task.d stays 'pending'
        assert data["task_statuses"]["task.d"] == "pending"

    @pytest.mark.asyncio
    async def test_concurrent_run_raises(self):
        """start_run raises ValueError when a run is already active → propagated to caller."""
        from unittest.mock import patch

        from backend.services.pipeline_registry import run_group

        registry = _build_registry(("task.a", 1))
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

        mock_celery, group_factory = _make_celery_mock({"task.a": {"ok": True}})

        # Seed an active run so the second start_run call conflicts
        existing_manager = GroupRunManager(redis)
        await existing_manager.start_run("grp", ["task.a"])

        with (
            patch("backend.tasks.celery_app", mock_celery),
            patch("celery.group", side_effect=group_factory),
            patch("asyncio.to_thread", side_effect=_fake_to_thread),
            pytest.raises(ValueError, match="Active run already exists"),
        ):
            await run_group(registry, "grp", redis)

    @pytest.mark.asyncio
    async def test_invalid_threshold_falls_back_to_stop_on_failure(self):
        """threshold:abc is invalid → falls back to stop_on_failure, stops on first failure."""
        from unittest.mock import patch

        from backend.services.pipeline_registry import run_group

        registry = _build_registry(("task.a", 1), ("task.b", 2))
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

        mock_celery, group_factory = _make_celery_mock(
            {"task.a": RuntimeError("bad"), "task.b": {"ok": True}}
        )

        with (
            patch("backend.tasks.celery_app", mock_celery),
            patch("celery.group", side_effect=group_factory),
            patch("asyncio.to_thread", side_effect=_fake_to_thread),
        ):
            run_id = await run_group(registry, "grp", redis, failure_mode="threshold:abc")

        manager = GroupRunManager(redis)
        data = await manager.get_run(run_id)
        assert data is not None
        # Fell back to stop_on_failure → run stopped after phase 1 failed
        assert data["status"] == "failed"
        assert data["task_statuses"]["task.b"] == "pending"
