"""Signal computation tool — technical indicators and composite scoring.

This module re-exports signal computation logic from the service layer.
All computation, constants, and DB persistence now live in
``backend.services.signals``. This file preserves the public API so that
existing imports (tools, tasks, tests) continue to work without changes.
"""

from backend.services.signals import (
    BB_PERIOD as BB_PERIOD,
)
from backend.services.signals import (
    BB_STD_DEV as BB_STD_DEV,
)
from backend.services.signals import (
    DEFAULT_RISK_FREE_RATE as DEFAULT_RISK_FREE_RATE,
)
from backend.services.signals import (
    MACD_FAST as MACD_FAST,
)
from backend.services.signals import (
    MACD_SIGNAL as MACD_SIGNAL,
)
from backend.services.signals import (
    MACD_SLOW as MACD_SLOW,
)
from backend.services.signals import (
    RSI_OVERBOUGHT as RSI_OVERBOUGHT,
)
from backend.services.signals import (
    RSI_OVERSOLD as RSI_OVERSOLD,
)
from backend.services.signals import (
    RSI_PERIOD as RSI_PERIOD,
)
from backend.services.signals import (
    SMA_LONG as SMA_LONG,
)
from backend.services.signals import (
    SMA_SHORT as SMA_SHORT,
)
from backend.services.signals import (
    TRADING_DAYS_PER_YEAR as TRADING_DAYS_PER_YEAR,
)
from backend.services.signals import (
    BBSignal as BBSignal,
)
from backend.services.signals import (
    MACDSignal as MACDSignal,
)
from backend.services.signals import (
    RSISignal as RSISignal,
)
from backend.services.signals import (
    SignalResult as SignalResult,
)
from backend.services.signals import (
    SMASignal as SMASignal,
)
from backend.services.signals import (
    compute_adx as compute_adx,
)
from backend.services.signals import (
    compute_atr as compute_atr,
)
from backend.services.signals import (
    compute_bollinger as compute_bollinger,
)
from backend.services.signals import (
    compute_composite_score as compute_composite_score,
)
from backend.services.signals import (
    compute_confirmation_gates as compute_confirmation_gates,
)
from backend.services.signals import (
    compute_macd as compute_macd,
)
from backend.services.signals import (
    compute_mfi as compute_mfi,
)
from backend.services.signals import (
    compute_obv_slope as compute_obv_slope,
)
from backend.services.signals import (
    compute_price_change as compute_price_change,
)
from backend.services.signals import (
    compute_risk_return as compute_risk_return,
)
from backend.services.signals import (
    compute_rsi as compute_rsi,
)
from backend.services.signals import (
    compute_signals as compute_signals,
)
from backend.services.signals import (
    compute_sma as compute_sma,
)
from backend.services.signals import (
    store_signal_snapshot as store_signal_snapshot,
)

__all__ = [
    "BB_PERIOD",
    "BB_STD_DEV",
    "BBSignal",
    "DEFAULT_RISK_FREE_RATE",
    "MACD_FAST",
    "MACD_SIGNAL",
    "MACD_SLOW",
    "MACDSignal",
    "RSI_OVERBOUGHT",
    "RSI_OVERSOLD",
    "RSI_PERIOD",
    "RSISignal",
    "SMA_LONG",
    "SMA_SHORT",
    "SMASignal",
    "TRADING_DAYS_PER_YEAR",
    "SignalResult",
    "compute_bollinger",
    "compute_composite_score",
    "compute_confirmation_gates",
    "compute_macd",
    "compute_price_change",
    "compute_risk_return",
    "compute_rsi",
    "compute_signals",
    "compute_sma",
    "store_signal_snapshot",
    "compute_adx",
    "compute_atr",
    "compute_mfi",
    "compute_obv_slope",
]
