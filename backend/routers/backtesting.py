"""Backtesting API — walk-forward validation results and accuracy badges."""

from fastapi import APIRouter

router = APIRouter(prefix="/backtests", tags=["backtesting"])
