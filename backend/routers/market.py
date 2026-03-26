"""Market overview router — briefing, sector performance."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from backend.dependencies import get_current_user
from backend.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/briefing")
async def get_market_briefing(
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    """Get today's market briefing — indexes, sectors, portfolio news, earnings.

    Returns a comprehensive daily market overview including major index
    performance, sector ETF changes, news for portfolio holdings,
    and upcoming earnings dates.
    """
    from backend.services.cache import CacheTier
    from backend.tools.market_briefing import MarketBriefingTool

    cache = getattr(request.app.state, "cache", None)
    cache_key = "app:market_briefing"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            import json

            return json.loads(cached)

    tool = MarketBriefingTool()
    result = await tool.execute({})

    if result.status == "ok" and result.data and cache:
        import json

        await cache.set(cache_key, json.dumps(result.data, default=str), CacheTier.VOLATILE)

    return result.data or {"error": result.error}
