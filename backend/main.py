"""FastAPI application entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import Response

from backend.config import settings
from backend.rate_limit import limiter
from backend.routers import (
    admin,
    admin_pipelines,
    alerts,
    auth,
    backtesting,
    chat,
    convergence,
    forecasts,
    health,
    indexes,
    market,
    news,
    observability,
    portfolio,
    preferences,
    sectors,
    sentiment,
    stocks,
)
from backend.routers.tasks import router as tasks_router

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize AI subsystem on startup, clean up on shutdown."""
    # --- Startup ---
    # 0a. Structured logging — before any logger.info() calls
    from backend.core.logging import configure_structlog

    configure_structlog()

    # 0b. Shared HTTP client pool — must be initialised before any provider uses it
    from backend.services.http_client import startup_http_client

    await startup_http_client()
    logger.info("Shared HTTP client pool initialised")

    # 1. Database schema validation — catch stale alembic_version early
    from sqlalchemy import select, text

    from backend.agents.llm_client import LLMClient
    from backend.agents.providers.anthropic import AnthropicProvider
    from backend.agents.providers.groq import GroqProvider
    from backend.database import async_session_factory
    from backend.mcp_server.server import create_mcp_app
    from backend.tools.build_registry import build_registry

    _CRITICAL_TABLES = ["users", "stocks", "stock_prices", "signal_snapshots"]
    async with async_session_factory() as session:
        for table in _CRITICAL_TABLES:
            result = await session.execute(
                text(
                    "SELECT EXISTS ("
                    "  SELECT 1 FROM information_schema.tables"
                    "  WHERE table_schema = 'public' AND table_name = :t"
                    ")"
                ),
                {"t": table},
            )
            if not result.scalar():
                logger.critical(
                    "TABLE '%s' MISSING — alembic_version may be stale. "
                    "Fix: DELETE FROM alembic_version; then: uv run alembic upgrade head",
                    table,
                )
                raise SystemExit(
                    f"Database schema incomplete: table '{table}' not found. "
                    "Run: uv run alembic upgrade head"
                )
    logger.info("Database schema validated: all critical tables present")

    # 1. Tool Registry — build with all internal tools + MCP adapters
    registry = build_registry()
    logger.info("ToolRegistry ready: %d tools registered", len(registry.discover()))

    # 3. Load model cascade config from DB + build providers
    from backend.agents.model_config import ModelConfigLoader
    from backend.observability.token_budget import TokenBudget

    config_loader = ModelConfigLoader()
    async with async_session_factory() as config_session:
        tier_configs = await config_loader.load(config_session)

    # Shared Redis pool — used by cache, token budget, blocklist
    from backend.services.cache import CacheService
    from backend.services.redis_pool import get_redis

    cache_redis = await get_redis()

    token_budget = TokenBudget(redis=cache_redis)

    # Observability collector — fire-and-forget writes + DB-backed reads
    from backend.observability.collector import ObservabilityCollector
    from backend.observability.writer import write_event

    collector = ObservabilityCollector()
    collector.set_db_writer(write_event)
    app.state.collector = collector

    # Cache service — Redis cache-aside with TTL tiers
    cache_service = CacheService(cache_redis)
    app.state.cache = cache_service
    app.state.cache_redis = cache_redis
    logger.info("CacheService initialized")

    # HTTP metrics middleware — Redis-backed request tracking
    from backend.observability.metrics.http_middleware import HttpMetricsCollector

    http_metrics = HttpMetricsCollector(redis=cache_redis)
    app.state.http_metrics = http_metrics

    # Langfuse tracing — parallel to ObservabilityCollector (fire-and-forget)
    from backend.observability.langfuse import LangfuseService

    langfuse_service = LangfuseService(
        secret_key=settings.LANGFUSE_SECRET_KEY,
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        base_url=settings.LANGFUSE_BASEURL,
    )
    app.state.langfuse = langfuse_service

    # Publish app-level singletons to task_tracer for non-agent Celery tasks
    from backend.services.observability.task_tracer import (
        set_langfuse_service,
        set_observability_collector,
    )

    set_langfuse_service(langfuse_service)
    set_observability_collector(collector)

    # Cache warmup — pre-load indexes
    try:
        from backend.services.cache import CacheTier

        async with async_session_factory() as warmup_db:
            from backend.models.index import StockIndex

            idx_result = await warmup_db.execute(select(StockIndex))
            indexes = idx_result.scalars().all()
            if indexes:
                import json

                idx_data = json.dumps([{"slug": i.slug, "name": i.name} for i in indexes])
                await cache_service.set("app:indexes", idx_data, CacheTier.STABLE)
                logger.info("Cache warmup: %d index entries", len(indexes))
    except Exception:
        logger.warning("Cache warmup failed — will lazy-load", exc_info=True)

    providers = []
    if settings.GROQ_API_KEY:
        # Extract Groq model names from DB config (planner tier, ordered by priority)
        groq_models = []
        for tier_models in tier_configs.values():
            for mc in tier_models:
                if mc.provider == "groq" and mc.model_name not in groq_models:
                    groq_models.append(mc.model_name)
        # Load budget limits from all Groq configs
        all_groq = [mc for ms in tier_configs.values() for mc in ms if mc.provider == "groq"]
        token_budget.load_limits(all_groq)

        providers.append(
            GroqProvider(
                api_key=settings.GROQ_API_KEY,
                models=groq_models or None,
                token_budget=token_budget,
            )
        )
    if settings.ANTHROPIC_API_KEY:
        providers.append(AnthropicProvider(api_key=settings.ANTHROPIC_API_KEY))

    # Inject observability onto all providers (base class attrs)
    pricing = config_loader.get_pricing_map()
    for provider in providers:
        provider.collector = collector
        provider.pricing = pricing

    llm_client = LLMClient(
        providers=providers, collector=collector, langfuse_service=langfuse_service
    )

    app.state.config_loader = config_loader
    app.state.token_budget = token_budget

    # 4. MCP subprocess (when MCP_TOOLS enabled)
    mcp_manager = None
    if settings.MCP_TOOLS:
        from backend.mcp_server.lifecycle import MCPSubprocessManager

        mcp_manager = MCPSubprocessManager()
        try:
            await mcp_manager.start()
            app.state.mcp_manager = mcp_manager
        except RuntimeError:
            logger.warning("MCP Tool Server failed to start — falling back to direct calls")
            mcp_manager = None

    # 5. Build tool executor + agent graph
    if providers:
        # Tool executor: MCP when available, direct fallback
        async def _tool_executor(tool_name: str, params: dict):  # noqa: ANN202
            if mcp_manager and mcp_manager.healthy:
                try:
                    return await mcp_manager.call_tool(tool_name, params)
                except ConnectionError:
                    logger.warning("MCP fallback to direct for tool: %s", tool_name)
            return await registry.execute(tool_name, params)

        # Always expose tool_executor (used by both ReAct and fast path)
        app.state.tool_executor = _tool_executor

        if not settings.REACT_AGENT:
            # Old pipeline: Plan→Execute→Synthesize graph
            from backend.agents.executor import execute_plan
            from backend.agents.graph import build_agent_graph
            from backend.agents.planner import plan_query
            from backend.agents.simple_formatter import format_simple_result
            from backend.agents.synthesizer import synthesize_results

            tool_infos = registry.discover()
            tools_desc = "\n".join(f"- **{t.name}**: {t.description}" for t in tool_infos)

            async def _plan_fn(query: str, tools_description: str, user_context: dict) -> dict:
                return await plan_query(
                    query=query,
                    tools_description=tools_description,
                    user_context=user_context,
                    llm_chat=lambda **kw: llm_client.chat(**kw, tier="planner"),
                )

            async def _synthesize_fn(tool_results: list, user_context: dict) -> dict:
                return await synthesize_results(
                    tool_results=tool_results,
                    user_context=user_context,
                    llm_chat=lambda **kw: llm_client.chat(**kw, tier="synthesizer"),
                )

            app.state.agent_graph = build_agent_graph(
                plan_fn=_plan_fn,
                execute_fn=lambda steps, tool_executor, on_step=None: execute_plan(
                    steps,
                    tool_executor,
                    on_step=on_step,
                    collector=collector,
                    cache=cache_service,
                ),
                synthesize_fn=_synthesize_fn,
                format_simple_fn=format_simple_result,
                tool_executor=_tool_executor,
                tools_description=tools_desc,
            )
            logger.info("Agent graph compiled (Plan→Execute→Synthesize, REACT_AGENT=false)")
        else:
            app.state.agent_graph = None
            logger.info("ReAct agent enabled (REACT_AGENT=true), old graph skipped")
    else:
        app.state.agent_graph = None
        app.state.tool_executor = None
        logger.warning("No LLM providers configured — chat disabled")

    # 5. MCP server (Layer 3 — Expose) with JWT auth middleware
    from backend.mcp_server.auth import MCPAuthMiddleware

    mcp_server = create_mcp_app(registry)
    mcp_app = mcp_server.http_app()
    mcp_app.add_middleware(MCPAuthMiddleware)
    app.mount("/mcp", mcp_app)
    logger.info("FastMCP server mounted at /mcp (JWT auth enforced)")

    # 5b. Observability MCP server — 13 read-only intelligence tools
    from backend.mcp_server.observability_tools import create_obs_mcp_app

    obs_mcp = create_obs_mcp_app()
    app.mount("/obs-mcp", obs_mcp.http_app())
    logger.info("Observability MCP server mounted at /obs-mcp")

    # Store on app.state (not module globals — rule #7)
    app.state.registry = registry
    app.state.tool_registry = registry  # alias for get_tool_schemas_for_group()
    app.state.llm_client = llm_client

    # --- Observability SDK (PR2a) ---
    from backend.observability.bootstrap import build_client_from_settings, obs_client_var

    obs_client = build_client_from_settings()
    await obs_client.start()
    app.state.obs_client = obs_client
    obs_client_var.set(obs_client)

    yield

    # --- Shutdown ---
    from backend.services.http_client import shutdown_http_client
    from backend.services.redis_pool import close_redis

    if mcp_manager:
        await mcp_manager.stop()
    await close_redis()  # closes shared pool (cache + blocklist)
    await shutdown_http_client()
    if hasattr(app.state, "langfuse"):
        app.state.langfuse.shutdown()
    # Clear task_tracer singletons so hot-reload does not carry stale references.
    set_langfuse_service(None)
    set_observability_collector(None)
    # Drain + stop observability SDK client (PR2a).
    if hasattr(app.state, "obs_client"):
        await app.state.obs_client.stop()
        obs_client_var.set(None)
    logger.info("Application shutting down")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Stock Signal Platform",
    description="Automated signal detection and investment recommendations for US equities.",
    version="0.1.0",
    lifespan=lifespan,
)

# --- Middleware ---
app.state.limiter = limiter
_rate_limit_handler = cast(
    "Callable[[Request, Exception], Response | Awaitable[Response]]",
    _rate_limit_exceeded_handler,
)
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

from backend.middleware.csrf import CSRFMiddleware  # noqa: E402
from backend.middleware.error_handler import ErrorHandlerMiddleware  # noqa: E402
from backend.middleware.trace_id import TraceIdMiddleware  # noqa: E402
from backend.observability.instrumentation.http import ObsHttpMiddleware  # noqa: E402
from backend.observability.metrics.http_middleware import HttpMetricsMiddleware  # noqa: E402

# Middleware — added in reverse order of execution (last = outermost)
# Stack (outermost → innermost): TraceId → ObsHttp → ErrorHandler → CORS → CSRF → HttpMetrics → app
app.add_middleware(HttpMetricsMiddleware)
app.add_middleware(
    CSRFMiddleware,
    csrf_exempt_paths={
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/forgot-password",
        "/api/v1/auth/reset-password",
        "/api/v1/auth/verify-email",
        "/api/v1/auth/google/callback",
        "/api/v1/health",
        "/api/v1/health/detail",
        "/docs",
        "/openapi.json",
        "/obs/v1/events",  # OBS_INGEST_PATH — X-Obs-Secret auth, not cookie-based
        "/api/v1/observability/frontend-error",  # beacon requests don't carry CSRF cookies
        "/api/v1/observability/deploy-event",  # webhook auth via Bearer token, not cookies
    },
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token", "X-Obs-Secret", "X-Trace-Id"],
    expose_headers=["X-Trace-Id"],
)
app.add_middleware(ErrorHandlerMiddleware)
# ObsHttpMiddleware: sits BETWEEN ErrorHandler (inner) and TraceId (outer)
# Execution order: TraceId (outermost) → ObsHttp → ErrorHandler → routes
app.add_middleware(ObsHttpMiddleware)
app.add_middleware(TraceIdMiddleware)


# --- Routers ---
app.include_router(health.router, prefix="/api/v1", tags=["system"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(indexes.router, prefix="/api/v1/indexes", tags=["indexes"])
app.include_router(stocks.router, prefix="/api/v1/stocks", tags=["stocks"])
app.include_router(sectors.router, prefix="/api/v1/sectors", tags=["sectors"])
app.include_router(portfolio.router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(preferences.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(forecasts.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(market.router, prefix="/api/v1")
app.include_router(news.router, prefix="/api/v1")
app.include_router(observability.router, prefix="/api/v1")
app.include_router(backtesting.router, prefix="/api/v1")
app.include_router(sentiment.router, prefix="/api/v1")
app.include_router(convergence.router, prefix="/api/v1")
app.include_router(convergence.sector_router, prefix="/api/v1")
app.include_router(admin_pipelines.router, prefix="/api/v1")

from backend.observability.routers.command_center import (  # noqa: E402
    router as command_center_router,
)

app.include_router(command_center_router, prefix="/api/v1")

from backend.observability.routers.deploy_events import (  # noqa: E402
    router as deploy_events_router,
)
from backend.observability.routers.frontend_errors import (  # noqa: E402
    router as frontend_errors_router,
)
from backend.observability.routers.ingest import (  # noqa: E402
    router as obs_ingest_router,
)

app.include_router(frontend_errors_router, prefix="/api/v1")
app.include_router(deploy_events_router, prefix="/api/v1")
app.include_router(obs_ingest_router)  # no /api/v1 prefix — spec §2.2b
