"""FastAPI application entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.config import settings
from backend.rate_limit import limiter
from backend.routers import (
    admin,
    alerts,
    auth,
    chat,
    forecasts,
    health,
    indexes,
    portfolio,
    preferences,
    sectors,
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
    # 0. Database schema validation — catch stale alembic_version early
    from sqlalchemy import text

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
    from backend.agents.token_budget import TokenBudget

    config_loader = ModelConfigLoader()
    async with async_session_factory() as config_session:
        tier_configs = await config_loader.load(config_session)

    token_budget = TokenBudget()

    # Observability collector — in-memory metrics + fire-and-forget DB writes
    from backend.agents.observability import ObservabilityCollector
    from backend.agents.observability_writer import write_event

    collector = ObservabilityCollector()
    collector.set_db_writer(write_event)
    app.state.collector = collector

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
                collector=collector,
            )
        )
    if settings.ANTHROPIC_API_KEY:
        providers.append(AnthropicProvider(api_key=settings.ANTHROPIC_API_KEY))
    llm_client = LLMClient(providers=providers)

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

    # 5. Build Agent graph (Plan→Execute→Synthesize)
    if providers:
        from backend.agents.executor import execute_plan
        from backend.agents.graph import build_agent_graph
        from backend.agents.planner import plan_query
        from backend.agents.simple_formatter import format_simple_result
        from backend.agents.synthesizer import synthesize_results

        # Build tools description for planner prompt
        tool_infos = registry.discover()
        tools_desc = "\n".join(f"- **{t.name}**: {t.description}" for t in tool_infos)

        # Tool executor: MCP when available, direct fallback
        async def _tool_executor(tool_name: str, params: dict):  # noqa: ANN202
            if mcp_manager and mcp_manager.healthy:
                try:
                    return await mcp_manager.call_tool(tool_name, params)
                except ConnectionError:
                    logger.warning("MCP fallback to direct for tool: %s", tool_name)
            return await registry.execute(tool_name, params)

        # Bind LLM to plan/synthesize functions
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
                steps, tool_executor, on_step=on_step, collector=collector
            ),
            synthesize_fn=_synthesize_fn,
            format_simple_fn=format_simple_result,
            tool_executor=_tool_executor,
            tools_description=tools_desc,
        )
        logger.info("Agent graph compiled (Plan→Execute→Synthesize)")
    else:
        app.state.agent_graph = None
        logger.warning("No LLM providers configured — chat disabled")

    # 5. MCP server (Layer 3 — Expose) with JWT auth middleware
    from backend.mcp_server.auth import MCPAuthMiddleware

    mcp_server = create_mcp_app(registry)
    mcp_app = mcp_server.http_app()
    mcp_app.add_middleware(MCPAuthMiddleware)
    app.mount("/mcp", mcp_app)
    logger.info("FastMCP server mounted at /mcp (JWT auth enforced)")

    # Store on app.state (not module globals — rule #7)
    app.state.registry = registry
    app.state.llm_client = llm_client

    yield

    # --- Shutdown ---
    from backend.services.token_blocklist import close as close_blocklist

    if mcp_manager:
        await mcp_manager.stop()
    await close_blocklist()
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
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


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
