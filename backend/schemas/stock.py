"""Pydantic v2 schemas for stock, signal, watchlist, and recommendation endpoints.

These schemas define the shape of data flowing in and out of our API.
Pydantic validates the data automatically — if a client sends invalid data,
FastAPI returns a clear 422 error before our code even runs.

Key concepts:
  - Request schemas: validate incoming data from the client
  - Response schemas: serialize our data into JSON for the client
  - model_config = {"from_attributes": True} tells Pydantic to read
    values from SQLAlchemy ORM objects (which use attributes, not dicts)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

# ─────────────────────────────────────────────────────────────────────────────
# Stock schemas
# ─────────────────────────────────────────────────────────────────────────────


class StockResponse(BaseModel):
    """Response for a single stock record.

    Returned when searching for stocks or looking up a specific ticker.
    """

    id: uuid.UUID
    ticker: str
    name: str
    exchange: str | None = None
    sector: str | None = None
    industry: str | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class StockSearchResponse(BaseModel):
    """Simplified stock info for search results."""

    ticker: str
    name: str
    exchange: str | None = None
    sector: str | None = None
    in_db: bool = True

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Price schemas
# ─────────────────────────────────────────────────────────────────────────────


class PricePointResponse(BaseModel):
    """A single OHLCV data point (one trading day).

    OHLCV stands for Open/High/Low/Close/Volume:
      - Open: price when the market opened that day
      - High: highest price during the day
      - Low: lowest price during the day
      - Close: price when the market closed
      - Volume: number of shares traded
    """

    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    model_config = {"from_attributes": True}


class PriceFormat(str, Enum):
    """Response format for price data.

    Controls the shape of the response from the prices endpoint:
      - list: default — array of PricePointResponse objects (one per day)
      - ohlc: candlestick — parallel arrays grouped by field, optimized
              for charting libraries
    """

    LIST = "list"
    OHLC = "ohlc"


class PricePeriod(str, Enum):
    """Valid period options for price history queries.

    These map to yfinance period strings. Each one defines how far back
    to look when fetching historical prices.
    """

    ONE_MONTH = "1mo"
    THREE_MONTHS = "3mo"
    SIX_MONTHS = "6mo"
    ONE_YEAR = "1y"
    TWO_YEARS = "2y"
    FIVE_YEARS = "5y"
    TEN_YEARS = "10y"


class OHLCResponse(BaseModel):
    """Candlestick-chart-friendly OHLC format with parallel arrays.

    Instead of an array of objects (one per day), this groups data by field
    into parallel arrays. All arrays have the same length (equal to ``count``).
    This format is optimized for charting libraries that expect columnar data.
    """

    ticker: str
    period: str
    count: int
    timestamps: list[datetime]
    open: list[float]
    high: list[float]
    low: list[float]
    close: list[float]
    volume: list[int]


# ─────────────────────────────────────────────────────────────────────────────
# Signal schemas
# ─────────────────────────────────────────────────────────────────────────────


class RSIResponse(BaseModel):
    """RSI (Relative Strength Index) signal breakdown."""

    value: float | None = None  # The RSI number (0-100)
    signal: str | None = None  # OVERSOLD, NEUTRAL, or OVERBOUGHT


class MACDResponse(BaseModel):
    """MACD (Moving Average Convergence Divergence) signal breakdown."""

    value: float | None = None  # MACD line value
    histogram: float | None = None  # MACD histogram value
    signal: str | None = None  # BULLISH or BEARISH


class SMAResponse(BaseModel):
    """SMA (Simple Moving Average) crossover signal breakdown."""

    sma_50: float | None = None  # 50-day SMA value
    sma_200: float | None = None  # 200-day SMA value
    signal: str | None = None  # GOLDEN_CROSS, DEATH_CROSS, etc.


class BollingerResponse(BaseModel):
    """Bollinger Bands signal breakdown."""

    upper: float | None = None  # Upper band value
    lower: float | None = None  # Lower band value
    position: str | None = None  # UPPER, MIDDLE, or LOWER


class ReturnsResponse(BaseModel):
    """Risk and return metrics."""

    annual_return: float | None = None  # Annualized return (decimal, e.g. 0.15 = 15%)
    volatility: float | None = None  # Annualized volatility
    sharpe: float | None = None  # Sharpe ratio


class SignalResponse(BaseModel):
    """Full signal response for a stock ticker.

    This is the main response from GET /stocks/{ticker}/signals.
    It nests all individual indicator responses for clean JSON structure.
    """

    ticker: str
    computed_at: datetime | None = None

    # Individual signal breakdowns (nested objects)
    rsi: RSIResponse
    macd: MACDResponse
    sma: SMAResponse
    bollinger: BollingerResponse
    returns: ReturnsResponse

    # Overall composite score (0-10)
    composite_score: float | None = None

    # Whether the signals are stale (older than 24 hours)
    is_stale: bool = False

    # Whether a background refresh has been dispatched (optimistic)
    is_refreshing: bool = False


class StockAnalyticsResponse(BaseModel):
    """QuantStats per-stock analytics from the latest signal snapshot."""

    ticker: str
    sortino: float | None = None
    max_drawdown: float | None = None
    alpha: float | None = None
    beta: float | None = None
    data_days: int | None = None

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Watchlist schemas
# ─────────────────────────────────────────────────────────────────────────────


class WatchlistAddRequest(BaseModel):
    """Request body to add a ticker to the user's watchlist."""

    ticker: str = Field(min_length=1, max_length=10, description="Stock ticker symbol, e.g. 'AAPL'")


class WatchlistItemResponse(BaseModel):
    """A single watchlist entry with its associated stock info."""

    id: uuid.UUID
    ticker: str
    name: str | None = None
    sector: str | None = None
    composite_score: float | None = None
    added_at: datetime
    current_price: float | None = None
    price_updated_at: datetime | None = None
    price_acknowledged_at: datetime | None = None

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Recommendation schemas
# ─────────────────────────────────────────────────────────────────────────────


class RecommendationResponse(BaseModel):
    """A single recommendation snapshot.

    This is what the user sees when they ask "what should I buy/sell/watch?"
    """

    ticker: str
    name: str | None = None  # Stock name from stocks table (JOIN)
    action: str  # BUY, WATCH, AVOID, HOLD, SELL
    confidence: str  # HIGH, MEDIUM, LOW
    composite_score: float
    price_at_recommendation: float  # Stock price when recommendation was made
    reasoning: dict | None = None  # Detailed explanation (JSONB)
    generated_at: datetime
    is_actionable: bool  # True if user should act on this
    suggested_amount: float | None = None  # dollar amount to invest (BUY only)

    model_config = {"from_attributes": True}


class RecommendationListResponse(BaseModel):
    """Paginated recommendation list."""

    recommendations: list[RecommendationResponse]
    total: int


# ─────────────────────────────────────────────────────────────────────────────
# Ingestion schemas
# ─────────────────────────────────────────────────────────────────────────────


class IngestResponse(BaseModel):
    """Response from the data ingestion endpoint."""

    ticker: str
    name: str
    rows_fetched: int
    composite_score: float | None = None
    status: str = Field(description="'created' if new, 'updated' if delta fetch")


# ─────────────────────────────────────────────────────────────────────────────
# Bulk signals schemas (screener)
# ─────────────────────────────────────────────────────────────────────────────


class BulkSignalItem(BaseModel):
    """A single stock's signal summary for the screener table."""

    ticker: str
    name: str
    sector: str | None = None
    composite_score: float | None = None
    rsi_value: float | None = None
    rsi_signal: str | None = None
    macd_signal: str | None = None
    sma_signal: str | None = None
    bb_position: str | None = None
    annual_return: float | None = None
    volatility: float | None = None
    sharpe_ratio: float | None = None
    computed_at: datetime | None = None
    is_stale: bool = False
    price_history: list[float] | None = None


class BulkSignalsResponse(BaseModel):
    """Paginated bulk signal response for the screener."""

    total: int
    items: list[BulkSignalItem]


# ─────────────────────────────────────────────────────────────────────────────
# Signal history schemas
# ─────────────────────────────────────────────────────────────────────────────


class SignalHistoryItem(BaseModel):
    """A single signal snapshot in a time series."""

    computed_at: datetime
    composite_score: float | None = None
    rsi_value: float | None = None
    rsi_signal: str | None = None
    macd_value: float | None = None
    macd_signal: str | None = None
    sma_signal: str | None = None
    bb_position: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Fundamentals schemas
# ─────────────────────────────────────────────────────────────────────────────


class PiotroskiBreakdown(BaseModel):
    """Binary Piotroski F-Score criteria (each 0 or 1)."""

    positive_roa: int | None = None
    positive_cfo: int | None = None
    improving_roa: int | None = None
    accruals: int | None = None
    decreasing_leverage: int | None = None
    improving_liquidity: int | None = None
    no_dilution: int | None = None
    improving_gross_margin: int | None = None
    improving_asset_turnover: int | None = None


class FundamentalsResponse(BaseModel):
    """Response for GET /stocks/{ticker}/fundamentals."""

    ticker: str
    pe_ratio: float | None = Field(None, description="Price-to-Earnings ratio")
    peg_ratio: float | None = Field(None, description="Price/Earnings-to-Growth ratio")
    fcf_yield: float | None = Field(None, description="Free Cash Flow yield (FCF / market cap)")
    debt_to_equity: float | None = Field(None, description="Total debt / shareholders equity")
    piotroski_score: int | None = Field(None, description="Piotroski F-Score (0-9)")
    piotroski_breakdown: PiotroskiBreakdown = Field(
        default_factory=PiotroskiBreakdown,
        description="Per-criterion breakdown of the Piotroski score",
    )

    # Enriched fields (materialized during ingestion)
    revenue_growth: float | None = Field(None, description="Revenue growth rate")
    gross_margins: float | None = Field(None, description="Gross margins")
    operating_margins: float | None = Field(None, description="Operating margins")
    profit_margins: float | None = Field(None, description="Profit margins")
    return_on_equity: float | None = Field(None, description="Return on equity")
    market_cap: float | None = Field(None, description="Market capitalization")

    # Analyst targets
    analyst_target_mean: float | None = Field(None, description="Mean analyst price target")
    analyst_target_high: float | None = Field(None, description="Highest analyst price target")
    analyst_target_low: float | None = Field(None, description="Lowest analyst price target")
    analyst_buy: int | None = Field(None, description="Number of buy recommendations")
    analyst_hold: int | None = Field(None, description="Number of hold recommendations")
    analyst_sell: int | None = Field(None, description="Number of sell recommendations")


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark comparison schemas
# ─────────────────────────────────────────────────────────────────────────────


class BenchmarkSeries(BaseModel):
    """A single normalized price series for benchmark comparison."""

    ticker: str
    name: str  # e.g. "S&P 500", "NASDAQ Composite"
    dates: list[datetime]
    pct_change: list[float]  # normalized % change from start


class BenchmarkComparisonResponse(BaseModel):
    """Response for GET /stocks/{ticker}/benchmark."""

    ticker: str
    period: str
    series: list[BenchmarkSeries]  # up to 3 series: stock, ^GSPC, ^IXIC
