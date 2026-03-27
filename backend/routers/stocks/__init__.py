"""Stock-related API endpoints — split by domain.

Sub-routers:
  - data: price history, signals, fundamentals, news, intelligence
  - watchlist: CRUD + refresh for user watchlists
  - search: search + on-demand ingest
  - recommendations: recommendations, bulk signals, signal history
"""

from fastapi import APIRouter

from backend.routers.stocks.data import router as data_router
from backend.routers.stocks.recommendations import router as recommendations_router
from backend.routers.stocks.search import router as search_router
from backend.routers.stocks.watchlist import router as watchlist_router

router = APIRouter()
router.include_router(search_router)
router.include_router(data_router)
router.include_router(watchlist_router)
router.include_router(recommendations_router)
