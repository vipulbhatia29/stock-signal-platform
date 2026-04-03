"""Unit tests for admin pipeline API endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.models.user import User, UserRole
from backend.routers.admin_pipelines import (
    CACHE_CLEAR_WHITELIST,
    _normalise_pattern,
    _run_dict_to_response,
    clear_all_caches,
    clear_cache_by_pattern,
    get_group_history,
    get_pipeline_group,
    get_run_status,
    list_pipeline_groups,
    trigger_group_run,
)
from backend.schemas.admin_pipeline import CacheClearRequest, TriggerGroupRequest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_user() -> User:
    """Provide an admin user for testing."""
    return User(
        id=uuid.uuid4(),
        email="admin@test.com",
        hashed_password="hashed",
        role=UserRole.ADMIN,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def regular_user() -> User:
    """Provide a non-admin user for testing."""
    return User(
        id=uuid.uuid4(),
        email="user@test.com",
        hashed_password="hashed",
        role=UserRole.USER,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_db() -> AsyncMock:
    """Provide a mocked async DB session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def sample_run_dict() -> dict:
    """Provide a sample pipeline run dict as stored in Redis."""
    return {
        "run_id": "run-abc-123",
        "group": "seed",
        "status": "running",
        "started_at": "2026-04-02T10:00:00+00:00",
        "completed_at": None,
        "task_names": ["task_a", "task_b"],
        "completed": 1,
        "failed": 0,
        "total": 2,
        "task_statuses": {"task_a": "success", "task_b": "pending"},
        "errors": {},
    }


# ---------------------------------------------------------------------------
# Tests: GET /groups
# ---------------------------------------------------------------------------


class TestListPipelineGroups:
    """Tests for GET /admin/pipelines/groups."""

    @pytest.mark.asyncio
    async def test_returns_all_groups(self, admin_user: User) -> None:
        """Returns a PipelineGroupListResponse with all registered groups."""
        result = await list_pipeline_groups(user=admin_user)
        # build_registry() registers 7 groups
        assert len(result.groups) == 7
        group_names = {g.name for g in result.groups}
        assert "seed" in group_names
        assert "nightly" in group_names

    @pytest.mark.asyncio
    async def test_each_group_has_tasks(self, admin_user: User) -> None:
        """Each returned group contains at least one task."""
        result = await list_pipeline_groups(user=admin_user)
        for group in result.groups:
            assert len(group.tasks) > 0

    @pytest.mark.asyncio
    async def test_each_group_has_execution_plan(self, admin_user: User) -> None:
        """Each returned group has a non-empty execution plan."""
        result = await list_pipeline_groups(user=admin_user)
        for group in result.groups:
            assert len(group.execution_plan) > 0

    @pytest.mark.asyncio
    async def test_raises_403_for_non_admin(self, regular_user: User) -> None:
        """Returns 403 when called by a non-admin user."""
        with pytest.raises(HTTPException) as exc_info:
            await list_pipeline_groups(user=regular_user)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Tests: GET /groups/{group}
# ---------------------------------------------------------------------------


class TestGetPipelineGroup:
    """Tests for GET /admin/pipelines/groups/{group}."""

    @pytest.mark.asyncio
    async def test_returns_seed_group(self, admin_user: User) -> None:
        """Returns details for the seed group including tasks and execution plan."""
        result = await get_pipeline_group(group="seed", user=admin_user)
        assert result.name == "seed"
        assert len(result.tasks) > 0
        assert len(result.execution_plan) > 0

    @pytest.mark.asyncio
    async def test_raises_404_for_unknown_group(self, admin_user: User) -> None:
        """Returns 404 when the group name does not exist in the registry."""
        with pytest.raises(HTTPException) as exc_info:
            await get_pipeline_group(group="nonexistent_group_xyz", user=admin_user)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_raises_403_for_non_admin(self, regular_user: User) -> None:
        """Returns 403 when called by a non-admin user."""
        with pytest.raises(HTTPException) as exc_info:
            await get_pipeline_group(group="seed", user=regular_user)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Tests: POST /groups/{group}/run
# ---------------------------------------------------------------------------


class TestTriggerGroupRun:
    """Tests for POST /admin/pipelines/groups/{group}/run."""

    @pytest.mark.asyncio
    async def test_triggers_run_202(self, admin_user: User, mock_db: AsyncMock) -> None:
        """Returns 202 with group name and accepted status when no active run exists."""
        mock_manager = AsyncMock()
        mock_manager.get_active_run = AsyncMock(return_value=None)

        with (
            patch(
                "backend.routers.admin_pipelines.GroupRunManager",
                return_value=mock_manager,
            ),
            patch(
                "backend.routers.admin_pipelines.get_redis",
                new_callable=AsyncMock,
                return_value=AsyncMock(),
            ),
            patch("backend.routers.admin_pipelines.asyncio.create_task"),
        ):
            result = await trigger_group_run(
                group="seed",
                body=TriggerGroupRequest(failure_mode="stop_on_failure"),
                user=admin_user,
                db=mock_db,
            )

        assert result.group == "seed"
        assert result.status == "accepted"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_409_on_concurrent_run(
        self, admin_user: User, mock_db: AsyncMock, sample_run_dict: dict
    ) -> None:
        """Returns 409 when a run is already active for the group."""
        mock_manager = AsyncMock()
        mock_manager.get_active_run = AsyncMock(return_value=sample_run_dict)

        with (
            patch(
                "backend.routers.admin_pipelines.GroupRunManager",
                return_value=mock_manager,
            ),
            patch(
                "backend.routers.admin_pipelines.get_redis",
                new_callable=AsyncMock,
                return_value=AsyncMock(),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await trigger_group_run(
                    group="seed",
                    body=TriggerGroupRequest(),
                    user=admin_user,
                    db=mock_db,
                )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_returns_404_for_unknown_group(
        self, admin_user: User, mock_db: AsyncMock
    ) -> None:
        """Returns 404 when the specified group does not exist in the registry."""
        with pytest.raises(HTTPException) as exc_info:
            await trigger_group_run(
                group="nonexistent_group_xyz",
                body=TriggerGroupRequest(),
                user=admin_user,
                db=mock_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_raises_403_for_non_admin(self, regular_user: User, mock_db: AsyncMock) -> None:
        """Returns 403 when called by a non-admin user."""
        with pytest.raises(HTTPException) as exc_info:
            await trigger_group_run(
                group="seed",
                body=TriggerGroupRequest(),
                user=regular_user,
                db=mock_db,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_audit_log_written(self, admin_user: User, mock_db: AsyncMock) -> None:
        """An AdminAuditLog row is added to the DB when a run is triggered."""
        mock_manager = AsyncMock()
        mock_manager.get_active_run = AsyncMock(return_value=None)

        with (
            patch(
                "backend.routers.admin_pipelines.GroupRunManager",
                return_value=mock_manager,
            ),
            patch(
                "backend.routers.admin_pipelines.get_redis",
                new_callable=AsyncMock,
                return_value=AsyncMock(),
            ),
            patch("backend.routers.admin_pipelines.asyncio.create_task"),
        ):
            await trigger_group_run(
                group="seed",
                body=TriggerGroupRequest(failure_mode="continue"),
                user=admin_user,
                db=mock_db,
            )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: GET /runs/{run_id}
# ---------------------------------------------------------------------------


class TestGetRunStatus:
    """Tests for GET /admin/pipelines/runs/{run_id}."""

    @pytest.mark.asyncio
    async def test_returns_run_data(self, admin_user: User, sample_run_dict: dict) -> None:
        """Returns PipelineRunResponse for an existing run_id."""
        mock_manager = AsyncMock()
        mock_manager.get_run = AsyncMock(return_value=sample_run_dict)

        with (
            patch(
                "backend.routers.admin_pipelines.GroupRunManager",
                return_value=mock_manager,
            ),
            patch(
                "backend.routers.admin_pipelines.get_redis",
                new_callable=AsyncMock,
                return_value=AsyncMock(),
            ),
        ):
            result = await get_run_status(run_id="run-abc-123", user=admin_user)

        assert result.run_id == "run-abc-123"
        assert result.group == "seed"
        assert result.status == "running"

    @pytest.mark.asyncio
    async def test_returns_404_for_missing_run(self, admin_user: User) -> None:
        """Returns 404 when the run_id does not exist in Redis."""
        mock_manager = AsyncMock()
        mock_manager.get_run = AsyncMock(return_value=None)

        with (
            patch(
                "backend.routers.admin_pipelines.GroupRunManager",
                return_value=mock_manager,
            ),
            patch(
                "backend.routers.admin_pipelines.get_redis",
                new_callable=AsyncMock,
                return_value=AsyncMock(),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_run_status(run_id="nonexistent-run-id", user=admin_user)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_raises_403_for_non_admin(self, regular_user: User) -> None:
        """Returns 403 when called by a non-admin user."""
        with pytest.raises(HTTPException) as exc_info:
            await get_run_status(run_id="some-run-id", user=regular_user)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Tests: GET /groups/{group}/history
# ---------------------------------------------------------------------------


class TestGetGroupHistory:
    """Tests for GET /admin/pipelines/groups/{group}/history."""

    @pytest.mark.asyncio
    async def test_returns_history(self, admin_user: User, sample_run_dict: dict) -> None:
        """Returns RunHistoryResponse with run entries for the group."""
        completed_run = {
            **sample_run_dict,
            "status": "success",
            "completed_at": "2026-04-02T10:05:00+00:00",
        }
        mock_manager = AsyncMock()
        mock_manager.get_history = AsyncMock(return_value=[completed_run])

        with (
            patch(
                "backend.routers.admin_pipelines.GroupRunManager",
                return_value=mock_manager,
            ),
            patch(
                "backend.routers.admin_pipelines.get_redis",
                new_callable=AsyncMock,
                return_value=AsyncMock(),
            ),
        ):
            result = await get_group_history(
                group="seed",
                user=admin_user,
                limit=10,
            )

        assert result.group == "seed"
        assert len(result.runs) == 1
        assert result.runs[0].status == "success"

    @pytest.mark.asyncio
    async def test_respects_limit_param(self, admin_user: User, sample_run_dict: dict) -> None:
        """Passes the limit parameter to GroupRunManager.get_history."""
        mock_manager = AsyncMock()
        mock_manager.get_history = AsyncMock(return_value=[])

        with (
            patch(
                "backend.routers.admin_pipelines.GroupRunManager",
                return_value=mock_manager,
            ),
            patch(
                "backend.routers.admin_pipelines.get_redis",
                new_callable=AsyncMock,
                return_value=AsyncMock(),
            ),
        ):
            await get_group_history(group="nightly", user=admin_user, limit=5)

        mock_manager.get_history.assert_called_once_with("nightly", limit=5)

    @pytest.mark.asyncio
    async def test_returns_empty_runs_for_new_group(self, admin_user: User) -> None:
        """Returns empty runs list when no history exists for the group."""
        mock_manager = AsyncMock()
        mock_manager.get_history = AsyncMock(return_value=[])

        with (
            patch(
                "backend.routers.admin_pipelines.GroupRunManager",
                return_value=mock_manager,
            ),
            patch(
                "backend.routers.admin_pipelines.get_redis",
                new_callable=AsyncMock,
                return_value=AsyncMock(),
            ),
        ):
            result = await get_group_history(group="maintenance", user=admin_user, limit=10)

        assert result.runs == []


# ---------------------------------------------------------------------------
# Tests: POST /cache/clear
# ---------------------------------------------------------------------------


class TestClearCacheByPattern:
    """Tests for POST /admin/pipelines/cache/clear."""

    @pytest.mark.asyncio
    async def test_clears_whitelisted_pattern(self, admin_user: User, mock_db: AsyncMock) -> None:
        """Deletes keys and returns CacheClearResponse for a valid whitelisted pattern."""
        with (
            patch(
                "backend.routers.admin_pipelines._scan_and_delete",
                new_callable=AsyncMock,
            ) as mock_scan,
            patch(
                "backend.routers.admin_pipelines.get_redis",
                new_callable=AsyncMock,
                return_value=AsyncMock(),
            ),
        ):
            mock_scan.return_value = 5

            result = await clear_cache_by_pattern(
                body=CacheClearRequest(pattern="app:forecast:*"),
                user=admin_user,
                db=mock_db,
            )

        assert result.keys_deleted == 5
        assert result.pattern == "app:forecast:*"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_adds_app_prefix_to_bare_pattern(
        self, admin_user: User, mock_db: AsyncMock
    ) -> None:
        """Automatically prefixes 'app:' to patterns that lack it."""
        with (
            patch(
                "backend.routers.admin_pipelines._scan_and_delete",
                new_callable=AsyncMock,
            ) as mock_scan,
            patch(
                "backend.routers.admin_pipelines.get_redis",
                new_callable=AsyncMock,
                return_value=AsyncMock(),
            ),
        ):
            mock_scan.return_value = 3

            result = await clear_cache_by_pattern(
                body=CacheClearRequest(pattern="screener:*"),
                user=admin_user,
                db=mock_db,
            )

        # Should have been normalised to app:screener:*
        assert result.pattern == "app:screener:*"

    @pytest.mark.asyncio
    async def test_rejects_non_whitelisted_pattern(
        self, admin_user: User, mock_db: AsyncMock
    ) -> None:
        """Returns 400 for a pattern that is not in the whitelist."""
        with pytest.raises(HTTPException) as exc_info:
            await clear_cache_by_pattern(
                body=CacheClearRequest(pattern="arbitrary:*"),
                user=admin_user,
                db=mock_db,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_rejects_dangerous_pattern(self, admin_user: User, mock_db: AsyncMock) -> None:
        """Returns 400 for a wildcard pattern that would match all keys."""
        with pytest.raises(HTTPException) as exc_info:
            await clear_cache_by_pattern(
                body=CacheClearRequest(pattern="*"),
                user=admin_user,
                db=mock_db,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_raises_403_for_non_admin(self, regular_user: User, mock_db: AsyncMock) -> None:
        """Returns 403 when called by a non-admin user."""
        with pytest.raises(HTTPException) as exc_info:
            await clear_cache_by_pattern(
                body=CacheClearRequest(pattern="app:forecast:*"),
                user=regular_user,
                db=mock_db,
            )
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Tests: POST /cache/clear-all
# ---------------------------------------------------------------------------


class TestClearAllCaches:
    """Tests for POST /admin/pipelines/cache/clear-all."""

    @pytest.mark.asyncio
    async def test_clears_all_patterns(self, admin_user: User, mock_db: AsyncMock) -> None:
        """Clears all whitelisted patterns and returns total keys deleted."""
        with (
            patch(
                "backend.routers.admin_pipelines._scan_and_delete",
                new_callable=AsyncMock,
            ) as mock_scan,
            patch(
                "backend.routers.admin_pipelines.get_redis",
                new_callable=AsyncMock,
                return_value=AsyncMock(),
            ),
        ):
            # Return 2 keys per pattern
            mock_scan.return_value = 2

            result = await clear_all_caches(user=admin_user, db=mock_db)

        # Should have called _scan_and_delete once per whitelisted pattern
        assert mock_scan.call_count == len(CACHE_CLEAR_WHITELIST)
        assert result.keys_deleted == 2 * len(CACHE_CLEAR_WHITELIST)
        assert result.pattern == "all"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_403_for_non_admin(self, regular_user: User, mock_db: AsyncMock) -> None:
        """Returns 403 when called by a non-admin user."""
        with pytest.raises(HTTPException) as exc_info:
            await clear_all_caches(user=regular_user, db=mock_db)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Tests: Helpers
# ---------------------------------------------------------------------------


class TestNormalisePattern:
    """Tests for the _normalise_pattern helper."""

    def test_adds_app_prefix_if_missing(self) -> None:
        """Pattern without 'app:' prefix gets it added."""
        assert _normalise_pattern("forecast:*") == "app:forecast:*"

    def test_keeps_app_prefix_if_present(self) -> None:
        """Pattern already prefixed with 'app:' is returned unchanged."""
        assert _normalise_pattern("app:forecast:*") == "app:forecast:*"


class TestRunDictToResponse:
    """Tests for the _run_dict_to_response helper."""

    def test_converts_dict_correctly(self, sample_run_dict: dict) -> None:
        """Converts a raw Redis run dict into a PipelineRunResponse."""
        response = _run_dict_to_response(sample_run_dict)
        assert response.run_id == "run-abc-123"
        assert response.group == "seed"
        assert response.total == 2
        assert response.completed == 1
        assert response.completed_at is None

    def test_handles_missing_optional_fields(self) -> None:
        """Missing optional fields default to empty/zero values."""
        minimal = {
            "run_id": "x",
            "group": "g",
            "status": "running",
            "started_at": "2026-01-01T00:00:00+00:00",
        }
        response = _run_dict_to_response(minimal)
        assert response.task_names == []
        assert response.completed == 0
        assert response.errors == {}
