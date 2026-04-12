"""Pipeline registry configuration — all task group definitions.

Registers all 8 pipeline task groups into a PipelineRegistry.
Import build_registry() at application start-up or in admin endpoints.
"""

from backend.services.pipeline_registry import PipelineRegistry, TaskDefinition


def build_registry() -> PipelineRegistry:
    """Build and return the fully populated pipeline registry.

    Groups registered:
    1. seed          — initial data population (ordered pipeline)
    2. nightly       — nightly data refresh pipeline
    3. intraday      — intraday watchlist refresh
    4. warm_data     — analyst/FRED/institutional data (parallel)
    5. maintenance   — audit record purges
    6. model_training — Prophet retraining + backtest + calibration
    7. news_sentiment — (Spec B placeholder) news ingestion + scoring
    8. data_quality  — nightly DQ checks + alert generation

    Returns:
        PipelineRegistry with all 8 task groups registered.
    """
    registry = PipelineRegistry()

    # ── 1. Seed group ───────────────────────────────────────────────────────────
    # Order: admin_user(0) → sp500(1) → [indexes(2), etfs(2)]
    #        → [prices(3), dividends(3), fundamentals(3)] → [forecasts(4), reason_tier(4)]
    registry.register(
        TaskDefinition(
            name="backend.tasks.seed_tasks.seed_admin_user_task",
            display_name="Create Admin User",
            group="seed",
            order=0,
            is_seed=True,
            estimated_duration="< 1 sec",
            rationale="Must run first — creates admin user from .env for pipeline control access",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.seed_tasks.seed_sp500_task",
            display_name="Sync S&P 500",
            group="seed",
            order=1,
            is_seed=True,
            estimated_duration="1-2 min",
            rationale="Must run first — populates stock universe for all other seeds",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.seed_tasks.seed_indexes_task",
            display_name="Sync Index Constituents",
            group="seed",
            order=2,
            depends_on=["backend.tasks.seed_tasks.seed_sp500_task"],
            is_seed=True,
            estimated_duration="1-2 min",
            rationale="Depends on sp500 universe; runs in parallel with ETF seed",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.seed_tasks.seed_etfs_task",
            display_name="Seed ETFs",
            group="seed",
            order=2,
            depends_on=["backend.tasks.seed_tasks.seed_sp500_task"],
            is_seed=True,
            estimated_duration="1-2 min",
            rationale="ETF list is static; runs in parallel with index sync",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.seed_tasks.seed_prices_task",
            display_name="Seed Historical Prices",
            group="seed",
            order=3,
            depends_on=[
                "backend.tasks.seed_tasks.seed_indexes_task",
                "backend.tasks.seed_tasks.seed_etfs_task",
            ],
            is_seed=True,
            estimated_duration="30-60 min",
            rationale="Requires full universe (sp500 + indexes + ETFs) to be present",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.seed_tasks.seed_dividends_task",
            display_name="Seed Historical Dividends",
            group="seed",
            order=3,
            depends_on=[
                "backend.tasks.seed_tasks.seed_indexes_task",
                "backend.tasks.seed_tasks.seed_etfs_task",
            ],
            is_seed=True,
            estimated_duration="10-20 min",
            rationale="Runs in parallel with prices and fundamentals after universe seed",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.seed_tasks.seed_fundamentals_task",
            display_name="Seed Fundamentals",
            group="seed",
            order=3,
            depends_on=[
                "backend.tasks.seed_tasks.seed_indexes_task",
                "backend.tasks.seed_tasks.seed_etfs_task",
            ],
            is_seed=True,
            estimated_duration="20-40 min",
            rationale="Runs in parallel with prices and dividends after universe seed",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.seed_tasks.seed_forecasts_task",
            display_name="Seed Initial Forecasts",
            group="seed",
            order=4,
            depends_on=[
                "backend.tasks.seed_tasks.seed_prices_task",
                "backend.tasks.seed_tasks.seed_fundamentals_task",
            ],
            is_seed=True,
            estimated_duration="60-120 min",
            rationale="Requires price and fundamental data to generate forecasts",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.seed_tasks.seed_reason_tier_task",
            display_name="Seed Reason Tiers",
            group="seed",
            order=4,
            depends_on=[
                "backend.tasks.seed_tasks.seed_prices_task",
                "backend.tasks.seed_tasks.seed_fundamentals_task",
            ],
            is_seed=True,
            estimated_duration="5-10 min",
            rationale="Runs in parallel with forecasts; needs fundamentals for tier logic",
        )
    )

    # ── 2. Nightly group ────────────────────────────────────────────────────────
    # Mirrors the dependency graph inside nightly_pipeline_chain_task:
    # price_refresh(1)
    # → [forecast_refresh(2), recommendations(2), evaluate_forecasts(2),
    #    evaluate_recommendations(2), snapshot_portfolios(2)]
    # → [drift_detection(3), convergence_snapshot(3)]
    # → [alerts(4), health(4)]
    #
    # Note: cache invalidation is handled inline within nightly_price_refresh_task
    # and is not a standalone Celery task.
    registry.register(
        TaskDefinition(
            name="backend.tasks.market_data.nightly_price_refresh_task",
            display_name="Nightly Price Refresh",
            group="nightly",
            order=1,
            schedule="21:30 ET daily",
            estimated_duration="5-15 min",
            incremental=True,
            rationale="Cache invalidation + price refresh; all downstream tasks depend on this",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.forecasting.forecast_refresh_task",
            display_name="Refresh Forecasts",
            group="nightly",
            order=2,
            depends_on=["backend.tasks.market_data.nightly_price_refresh_task"],
            schedule="21:30 ET daily",
            estimated_duration="10-30 min",
            incremental=True,
            rationale="Requires fresh prices; runs in parallel with recommendations and evaluation",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.recommendations.generate_recommendations_task",
            display_name="Generate Recommendations",
            group="nightly",
            order=2,
            depends_on=["backend.tasks.market_data.nightly_price_refresh_task"],
            schedule="21:30 ET daily",
            estimated_duration="5-10 min",
            incremental=True,
            rationale="Requires fresh prices; runs in parallel at nightly phase 2",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.evaluation.evaluate_forecasts_task",
            display_name="Evaluate Forecasts",
            group="nightly",
            order=2,
            depends_on=["backend.tasks.market_data.nightly_price_refresh_task"],
            schedule="21:30 ET daily",
            estimated_duration="2-5 min",
            incremental=True,
            rationale="Score yesterday's forecasts against today's actuals",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.evaluation.evaluate_recommendations_task",
            display_name="Evaluate Recommendations",
            group="nightly",
            order=2,
            depends_on=["backend.tasks.market_data.nightly_price_refresh_task"],
            schedule="21:30 ET daily",
            estimated_duration="2-5 min",
            incremental=True,
            rationale="Score yesterday's recommendations against today's actuals",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.portfolio.snapshot_all_portfolios_task",
            display_name="Snapshot All Portfolios",
            group="nightly",
            order=2,
            depends_on=["backend.tasks.market_data.nightly_price_refresh_task"],
            schedule="21:30 ET daily",
            estimated_duration="2-5 min",
            incremental=True,
            rationale="Capture portfolio values after prices are refreshed",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.evaluation.check_drift_task",
            display_name="Check Drift",
            group="nightly",
            order=3,
            depends_on=[
                "backend.tasks.forecasting.forecast_refresh_task",
                "backend.tasks.evaluation.evaluate_forecasts_task",
            ],
            schedule="21:30 ET daily",
            estimated_duration="2-5 min",
            rationale="Needs fresh forecasts + evaluations to compute drift metrics",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.convergence.compute_convergence_snapshot_task",
            display_name="Compute Convergence Snapshot",
            group="nightly",
            order=3,
            depends_on=[
                "backend.tasks.forecasting.forecast_refresh_task",
                "backend.tasks.recommendations.generate_recommendations_task",
            ],
            schedule="21:30 ET daily",
            estimated_duration="2-5 min",
            rationale="Needs fresh forecasts + recommendations to score convergence",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.alerts.generate_alerts_task",
            display_name="Generate Alerts",
            group="nightly",
            order=4,
            depends_on=[
                "backend.tasks.evaluation.check_drift_task",
                "backend.tasks.convergence.compute_convergence_snapshot_task",
            ],
            schedule="21:30 ET daily",
            estimated_duration="1-3 min",
            rationale="Consumes drift + convergence signals to fire alerts",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.portfolio.snapshot_health_task",
            display_name="Snapshot Portfolio Health",
            group="nightly",
            order=4,
            depends_on=[
                "backend.tasks.portfolio.snapshot_all_portfolios_task",
                "backend.tasks.convergence.compute_convergence_snapshot_task",
            ],
            schedule="21:30 ET daily",
            estimated_duration="1-3 min",
            rationale="Needs portfolio values and convergence scores for health metrics",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.portfolio.materialize_rebalancing_task",
            display_name="Materialize Rebalancing",
            group="nightly",
            order=4,
            depends_on=[
                "backend.tasks.portfolio.snapshot_all_portfolios_task",
            ],
            schedule="21:30 ET daily",
            estimated_duration="1-3 min",
            rationale="Generates rebalancing suggestions after portfolio snapshots",
        )
    )

    # ── 3. Intraday group ───────────────────────────────────────────────────────
    registry.register(
        TaskDefinition(
            name="backend.tasks.market_data.intraday_refresh_all_task",
            display_name="Intraday Refresh All",
            group="intraday",
            order=1,
            schedule="Every 30 min during market hours",
            estimated_duration="1-5 min",
            incremental=True,
            rationale="Keep watchlist data fresh during trading hours",
        )
    )

    # ── 4. Warm data group ──────────────────────────────────────────────────────
    # All run in parallel (same order=1)
    registry.register(
        TaskDefinition(
            name="backend.tasks.warm_data.sync_analyst_consensus_task",
            display_name="Sync Analyst Consensus",
            group="warm_data",
            order=1,
            schedule="6:00 AM ET daily",
            estimated_duration="5-10 min",
            incremental=True,
            rationale="Analyst ratings change infrequently; morning refresh before market open",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.warm_data.sync_fred_indicators_task",
            display_name="Sync FRED Indicators",
            group="warm_data",
            order=1,
            schedule="7:00 AM ET daily",
            estimated_duration="2-5 min",
            incremental=True,
            rationale="Macro indicators from FRED; runs in parallel with analyst and institutional",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.warm_data.sync_institutional_holders_task",
            display_name="Sync Institutional Holders",
            group="warm_data",
            order=1,
            schedule="2:00 AM ET Sunday",
            estimated_duration="10-20 min",
            incremental=True,
            rationale="13F filings update weekly; Sunday early morning avoids peak load",
        )
    )

    # ── 5. Maintenance group ────────────────────────────────────────────────────
    registry.register(
        TaskDefinition(
            name="backend.tasks.audit.purge_login_attempts_task",
            display_name="Purge Login Attempts",
            group="maintenance",
            order=1,
            schedule="3:00 AM ET daily",
            estimated_duration="< 1 min",
            idempotent=True,
            rationale="Purge stale login attempts first; purge deleted accounts after",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.audit.purge_deleted_accounts_task",
            display_name="Purge Deleted Accounts",
            group="maintenance",
            order=2,
            depends_on=["backend.tasks.audit.purge_login_attempts_task"],
            schedule="3:15 AM ET daily",
            estimated_duration="< 1 min",
            idempotent=True,
            rationale="Run after login attempt purge to maintain audit log integrity",
        )
    )

    # ── 6. Model training group ─────────────────────────────────────────────────
    registry.register(
        TaskDefinition(
            name="backend.tasks.forecasting.model_retrain_all_task",
            display_name="Retrain All Models",
            group="model_training",
            order=1,
            schedule="2:00 AM ET biweekly (Sunday)",
            estimated_duration="60-180 min",
            rationale="Full Prophet retrain; must complete before backtest and calibration",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.forecasting.run_backtest_task",
            display_name="Run Backtest",
            group="model_training",
            order=2,
            depends_on=["backend.tasks.forecasting.model_retrain_all_task"],
            estimated_duration="30-60 min",
            rationale="Walk-forward backtest after retrain; runs in parallel with calibration",
        )
    )

    # ── 7. News sentiment group (Spec B placeholder) ────────────────────────────
    registry.register(
        TaskDefinition(
            name="backend.tasks.news_sentiment.news_ingest_task",
            display_name="News Ingest",
            group="news_sentiment",
            order=1,
            estimated_duration="5-10 min",
            incremental=True,
            rationale="[Spec B placeholder] Ingest articles from news sources",
        )
    )
    registry.register(
        TaskDefinition(
            name="backend.tasks.news_sentiment.news_sentiment_scoring_task",
            display_name="Sentiment Scoring",
            group="news_sentiment",
            order=2,
            depends_on=["backend.tasks.news_sentiment.news_ingest_task"],
            estimated_duration="5-15 min",
            incremental=True,
            rationale="[Spec B placeholder] Score ingested articles after ingest completes",
        )
    )

    # ── 8. Data quality group ───────────────────────────────────────────────────
    registry.register(
        TaskDefinition(
            name="backend.tasks.dq_scan.dq_scan_task",
            display_name="DQ Scan",
            group="data_quality",
            order=1,
            schedule="4:00 AM ET daily",
            estimated_duration="1-5 min",
            idempotent=True,
            rationale="Run 10 data quality checks; persist findings and fire critical alerts",
        )
    )

    return registry
