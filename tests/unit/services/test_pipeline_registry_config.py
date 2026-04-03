"""Tests for pipeline registry configuration.

Verifies that build_registry() produces a correctly populated PipelineRegistry
with all 7 groups, correct task counts, ordering, and no validation errors.
"""

from __future__ import annotations

EXPECTED_GROUPS = {
    "seed",
    "nightly",
    "intraday",
    "warm_data",
    "maintenance",
    "model_training",
    "news_sentiment",
}


class TestBuildRegistry:
    """Tests for the build_registry() factory function."""

    def test_returns_pipeline_registry_instance(self) -> None:
        """build_registry() returns a PipelineRegistry object."""
        from backend.services.pipeline_registry import PipelineRegistry
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        assert isinstance(registry, PipelineRegistry)

    def test_all_seven_groups_present(self) -> None:
        """Registry contains all 7 expected task groups."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        groups = set(registry.get_groups().keys())
        assert groups == EXPECTED_GROUPS

    def test_each_group_has_at_least_one_task(self) -> None:
        """Every group has at least one registered task."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        for group_name, tasks in registry.get_groups().items():
            assert len(tasks) >= 1, f"Group '{group_name}' has no tasks"

    def test_validation_passes(self) -> None:
        """validate() returns no errors for the fully populated registry."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        errors = registry.validate()
        assert errors == [], f"Registry validation failed: {errors}"

    def test_all_task_definitions_have_display_name(self) -> None:
        """Every task definition has a non-empty display_name."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        for group_name, tasks in registry.get_groups().items():
            for task in tasks:
                assert task.display_name, (
                    f"Task '{task.name}' in group '{group_name}' is missing display_name"
                )

    def test_all_task_definitions_have_group_set(self) -> None:
        """Every task definition has a non-empty group field matching its registered group."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        for group_name, tasks in registry.get_groups().items():
            for task in tasks:
                assert task.group == group_name, (
                    f"Task '{task.name}' group field '{task.group}' "
                    f"!= registered group '{group_name}'"
                )

    def test_build_registry_is_idempotent(self) -> None:
        """Calling build_registry() twice returns independent registries with same groups."""
        from backend.services.pipeline_registry_config import build_registry

        r1 = build_registry()
        r2 = build_registry()
        assert set(r1.get_groups().keys()) == set(r2.get_groups().keys())


class TestSeedGroup:
    """Tests for the 'seed' task group."""

    def test_seed_group_has_nine_tasks(self) -> None:
        """Seed group has exactly 9 tasks.

        admin_user + sp500 + indexes + etfs + prices + dividends + fundamentals
        + forecasts + reason_tier.
        """
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        tasks = registry.get_group("seed")
        assert len(tasks) == 9

    def test_seed_group_sp500_is_order_one(self) -> None:
        """S&P 500 sync is order=1 (first to run)."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        task = registry.get_task("backend.tasks.seed_tasks.seed_sp500_task")
        assert task is not None
        assert task.order == 1

    def test_seed_group_indexes_and_etfs_are_order_two(self) -> None:
        """Index sync and ETF seed are order=2 (run in parallel after sp500)."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        indexes_task = registry.get_task("backend.tasks.seed_tasks.seed_indexes_task")
        etfs_task = registry.get_task("backend.tasks.seed_tasks.seed_etfs_task")
        assert indexes_task is not None and indexes_task.order == 2
        assert etfs_task is not None and etfs_task.order == 2

    def test_seed_group_prices_dividends_fundamentals_are_order_three(self) -> None:
        """Prices, dividends, and fundamentals are order=3 (parallel after indexes/etfs)."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        for name in [
            "backend.tasks.seed_tasks.seed_prices_task",
            "backend.tasks.seed_tasks.seed_dividends_task",
            "backend.tasks.seed_tasks.seed_fundamentals_task",
        ]:
            task = registry.get_task(name)
            assert task is not None, f"Task '{name}' not found"
            assert task.order == 3, f"Task '{name}' has order {task.order}, expected 3"

    def test_seed_group_forecasts_and_reason_tier_are_order_four(self) -> None:
        """Forecasts and reason_tier are order=4 (parallel, depend on prices/fundamentals)."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        for name in [
            "backend.tasks.seed_tasks.seed_forecasts_task",
            "backend.tasks.seed_tasks.seed_reason_tier_task",
        ]:
            task = registry.get_task(name)
            assert task is not None, f"Task '{name}' not found"
            assert task.order == 4, f"Task '{name}' has order {task.order}, expected 4"

    def test_seed_group_all_tasks_are_seed(self) -> None:
        """All tasks in the seed group have is_seed=True."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        for task in registry.get_group("seed"):
            assert task.is_seed, f"Task '{task.name}' in seed group has is_seed=False"

    def test_seed_group_execution_plan_has_five_phases(self) -> None:
        """Seed group resolves to exactly 5 execution phases (admin_user first)."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        plan = registry.resolve_execution_plan("seed")
        assert len(plan) == 5

    def test_seed_group_first_phase_is_admin_user(self) -> None:
        """First seed phase contains only the admin_user task."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        plan = registry.resolve_execution_plan("seed")
        assert plan[0] == ["backend.tasks.seed_tasks.seed_admin_user_task"]

    def test_seed_group_second_phase_is_sp500(self) -> None:
        """Second seed phase contains only the sp500 task."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        plan = registry.resolve_execution_plan("seed")
        assert plan[1] == ["backend.tasks.seed_tasks.seed_sp500_task"]


class TestNightlyGroup:
    """Tests for the 'nightly' task group."""

    def test_nightly_group_has_tasks(self) -> None:
        """Nightly group has at least 8 tasks."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        tasks = registry.get_group("nightly")
        assert len(tasks) >= 8

    def test_nightly_price_refresh_is_first(self) -> None:
        """Nightly price refresh task is order=1 (starts the chain)."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        task = registry.get_task("backend.tasks.market_data.nightly_price_refresh_task")
        assert task is not None
        assert task.order == 1


class TestIntradayGroup:
    """Tests for the 'intraday' task group."""

    def test_intraday_has_watchlist_task(self) -> None:
        """Intraday group contains the watchlist refresh task."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        task = registry.get_task("backend.tasks.market_data.refresh_all_watchlist_tickers_task")
        assert task is not None
        assert task.group == "intraday"

    def test_intraday_execution_plan_single_phase(self) -> None:
        """Intraday group resolves to a single execution phase."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        plan = registry.resolve_execution_plan("intraday")
        assert len(plan) == 1


class TestWarmDataGroup:
    """Tests for the 'warm_data' task group."""

    def test_warm_data_has_three_tasks(self) -> None:
        """Warm data group has exactly 3 tasks (analyst, fred, institutional)."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        tasks = registry.get_group("warm_data")
        assert len(tasks) == 3

    def test_warm_data_all_tasks_parallel(self) -> None:
        """All warm data tasks have order=1 (run in parallel)."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        for task in registry.get_group("warm_data"):
            assert task.order == 1, (
                f"Warm data task '{task.name}' has order {task.order}, expected 1"
            )

    def test_warm_data_execution_plan_single_phase(self) -> None:
        """Warm data group resolves to a single parallel execution phase."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        plan = registry.resolve_execution_plan("warm_data")
        assert len(plan) == 1
        assert len(plan[0]) == 3


class TestMaintenanceGroup:
    """Tests for the 'maintenance' task group."""

    def test_maintenance_has_two_tasks(self) -> None:
        """Maintenance group has exactly 2 tasks."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        tasks = registry.get_group("maintenance")
        assert len(tasks) == 2

    def test_maintenance_purge_login_before_accounts(self) -> None:
        """Login attempt purge (order=1) runs before account purge (order=2)."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        login_task = registry.get_task("backend.tasks.audit.purge_login_attempts_task")
        account_task = registry.get_task("backend.tasks.audit.purge_deleted_accounts_task")
        assert login_task is not None and login_task.order == 1
        assert account_task is not None and account_task.order == 2


class TestModelTrainingGroup:
    """Tests for the 'model_training' task group."""

    def test_model_training_has_three_tasks(self) -> None:
        """Model training group has exactly 3 tasks."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        tasks = registry.get_group("model_training")
        assert len(tasks) == 3

    def test_model_retrain_is_first(self) -> None:
        """Model retrain task is order=1 (before backtest and calibration)."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        task = registry.get_task("backend.tasks.forecasting.model_retrain_all_task")
        assert task is not None
        assert task.order == 1

    def test_backtest_and_calibrate_are_parallel(self) -> None:
        """Backtest and calibration tasks are order=2 (run in parallel after retrain)."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        for name in [
            "backend.tasks.forecasting.run_backtest_task",
            "backend.tasks.forecasting.calibrate_seasonality_task",
        ]:
            task = registry.get_task(name)
            assert task is not None, f"Task '{name}' not found"
            assert task.order == 2, f"Task '{name}' has order {task.order}, expected 2"


class TestNewsSentimentGroup:
    """Tests for the 'news_sentiment' task group (Spec B placeholder)."""

    def test_news_sentiment_has_two_tasks(self) -> None:
        """News sentiment group has exactly 2 placeholder tasks."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        tasks = registry.get_group("news_sentiment")
        assert len(tasks) == 2

    def test_news_ingest_is_order_one(self) -> None:
        """News ingest task is order=1."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        task = registry.get_task("backend.tasks.news_sentiment.news_ingest_task")
        assert task is not None
        assert task.order == 1

    def test_sentiment_scoring_is_order_two(self) -> None:
        """Sentiment scoring task is order=2 (after ingest)."""
        from backend.services.pipeline_registry_config import build_registry

        registry = build_registry()
        task = registry.get_task("backend.tasks.news_sentiment.sentiment_scoring_task")
        assert task is not None
        assert task.order == 2
