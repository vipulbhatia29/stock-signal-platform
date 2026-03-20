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
from backend.routers import auth, chat, indexes, portfolio, preferences, stocks
from backend.routers.tasks import router as tasks_router

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize AI subsystem on startup, clean up on shutdown."""
    # --- Startup ---
    from backend.agents.general_agent import GeneralAgent
    from backend.agents.graph import build_agent_graph
    from backend.agents.llm_client import LLMClient
    from backend.agents.providers.anthropic import AnthropicProvider
    from backend.agents.providers.groq import GroqProvider
    from backend.agents.stock_agent import StockAgent
    from backend.mcp_server.server import create_mcp_app
    from backend.tools.adapters.alpha_vantage import AlphaVantageAdapter
    from backend.tools.adapters.edgar import EdgarAdapter
    from backend.tools.adapters.finnhub import FinnhubAdapter
    from backend.tools.adapters.fred import FredAdapter
    from backend.tools.analyze_stock import AnalyzeStockTool
    from backend.tools.compute_signals_tool import ComputeSignalsTool
    from backend.tools.geopolitical import GeopoliticalEventsTool
    from backend.tools.ingest_stock_tool import IngestStockTool
    from backend.tools.portfolio_exposure import PortfolioExposureTool
    from backend.tools.recommendations_tool import RecommendationsTool
    from backend.tools.registry import ToolRegistry
    from backend.tools.screen_stocks import ScreenStocksTool
    from backend.tools.search_stocks_tool import SearchStocksTool
    from backend.tools.web_search import WebSearchTool

    # 1. Tool Registry — register 9 internal tools
    registry = ToolRegistry()
    for tool_cls in [
        AnalyzeStockTool,
        PortfolioExposureTool,
        ScreenStocksTool,
        ComputeSignalsTool,
        RecommendationsTool,
        WebSearchTool,
        GeopoliticalEventsTool,
        SearchStocksTool,
        IngestStockTool,
    ]:
        registry.register(tool_cls())

    # 2. MCP adapter tools — 4 external data sources
    for adapter in [
        EdgarAdapter(),
        AlphaVantageAdapter(api_key=settings.ALPHA_VANTAGE_API_KEY or ""),
        FredAdapter(api_key=settings.FRED_API_KEY or ""),
        FinnhubAdapter(api_key=settings.FINNHUB_API_KEY or ""),
    ]:
        registry.register_mcp(adapter)

    logger.info("ToolRegistry ready: %d tools registered", len(registry.discover()))

    # 3. LLM client with provider fallback chain
    providers = []
    if settings.GROQ_API_KEY:
        providers.append(GroqProvider(api_key=settings.GROQ_API_KEY))
    if settings.ANTHROPIC_API_KEY:
        providers.append(AnthropicProvider(api_key=settings.ANTHROPIC_API_KEY))
    llm_client = LLMClient(providers=providers)

    # 4. Build LangGraph agent graphs (one per agent type)
    if providers:
        active_llm = llm_client.get_active_chat_model()
        app.state.stock_graph = build_agent_graph(StockAgent(), registry, active_llm)
        app.state.general_graph = build_agent_graph(GeneralAgent(), registry, active_llm)
        logger.info("LangGraph agent graphs compiled (stock + general)")
    else:
        app.state.stock_graph = None
        app.state.general_graph = None
        logger.warning("No LLM providers configured — chat disabled")

    # 5. MCP server (Layer 3 — Expose)
    mcp_server = create_mcp_app(registry)
    app.mount("/mcp", mcp_server.http_app())
    logger.info("FastMCP server mounted at /mcp")

    # Store on app.state (not module globals — rule #7)
    app.state.registry = registry
    app.state.llm_client = llm_client

    yield

    # --- Shutdown ---
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


# --- Health Check ---
@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


# --- Routers ---
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(indexes.router, prefix="/api/v1/indexes", tags=["indexes"])
app.include_router(stocks.router, prefix="/api/v1/stocks", tags=["stocks"])
app.include_router(portfolio.router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(preferences.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
