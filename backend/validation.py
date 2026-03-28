"""Centralized API input validation — single source of truth for path/query param types.

Provides reusable Pydantic Annotated types for FastAPI path and query parameters.
All routers import from here instead of defining inline regex or ad-hoc constraints.
"""

from __future__ import annotations

import re
import uuid
from enum import Enum
from typing import Annotated

from fastapi import Path, Query

# ── Ticker ───────────────────────────────────────────────────────────────────

TICKER_RE = re.compile(r"^[A-Za-z0-9.\-^]{1,10}$")
"""Compiled ticker regex — also used by agent guards for tool param validation."""

TickerPath = Annotated[
    str,
    Path(
        description="Stock ticker symbol (e.g. AAPL, BRK.B)",
        min_length=1,
        max_length=10,
        pattern=r"^[A-Za-z0-9.\-\^]{1,10}$",
    ),
]

# ── UUID ─────────────────────────────────────────────────────────────────────

UUIDPath = Annotated[
    uuid.UUID,
    Path(description="Resource UUID"),
]

# ── Signal enums ─────────────────────────────────────────────────────────────


class RsiState(str, Enum):
    """RSI signal states stored in signal_snapshots."""

    OVERSOLD = "OVERSOLD"
    NEUTRAL = "NEUTRAL"
    OVERBOUGHT = "OVERBOUGHT"


class MacdState(str, Enum):
    """MACD signal states stored in signal_snapshots."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class SignalAction(str, Enum):
    """Recommendation actions stored in recommendation_snapshots."""

    BUY = "BUY"
    WATCH = "WATCH"
    AVOID = "AVOID"
    HOLD = "HOLD"
    SELL = "SELL"


class ConfidenceLevel(str, Enum):
    """Recommendation confidence levels."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ── Query param helpers ──────────────────────────────────────────────────────

RsiStateQuery = Annotated[
    RsiState | None,
    Query(description="Filter by RSI signal state"),
]

MacdStateQuery = Annotated[
    MacdState | None,
    Query(description="Filter by MACD signal state"),
]

SectorQuery = Annotated[
    str | None,
    Query(max_length=100, description="Filter by sector name"),
]

ActionQuery = Annotated[
    SignalAction | None,
    Query(description="Filter by recommendation action"),
]

ConfidenceQuery = Annotated[
    ConfidenceLevel | None,
    Query(description="Filter by confidence level"),
]
