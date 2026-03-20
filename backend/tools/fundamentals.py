"""Fundamentals tool — fetch and score fundamental financial metrics.

This module fetches fundamental data from yfinance and computes:

1. Basic valuation ratios:
   - P/E Ratio (Price-to-Earnings): How much investors pay per $1 of earnings.
     High P/E may mean overvalued or high growth expectations. ~15-25 is typical.
   - PEG Ratio (Price/Earnings-to-Growth): P/E adjusted for earnings growth.
     PEG < 1.0 often signals undervaluation relative to growth rate.
   - FCF Yield (Free Cash Flow Yield): FCF / Market Cap.
     High FCF yield (>5%) means the business generates lots of cash relative
     to its price — a value investor's favorite metric.
   - Debt-to-Equity: Total debt / shareholders' equity.
     Lower is safer; >2.0 can indicate financial stress.

2. Piotroski F-Score (0–9):
   A 9-point binary scoring system developed by Stanford professor Joseph Piotroski.
   Each criterion scores 1 (met) or 0 (not met). Groups:

   Profitability (4 points):
     F1: Positive ROA (Return on Assets) — company is profitable
     F2: Positive operating cash flow (CFO) — cash is actually coming in
     F3: Improving ROA — profitability is trending upward
     F4: Accruals check — CFO > net income (earnings quality, harder to fake)

   Leverage / Liquidity (3 points):
     F5: Decreasing long-term debt ratio — less reliant on borrowing
     F6: Improving current ratio — better short-term liquidity
     F7: No share dilution — company isn't issuing new shares to fund itself

   Operating Efficiency (2 points):
     F8: Improving gross margin — pricing power / cost control improving
     F9: Improving asset turnover — generating more revenue per dollar of assets

   Score interpretation:
     0–2: Weak (financially distressed)
     3–6: Average
     7–9: Strong (financially healthy)

Data source:
   yfinance Ticker.info dict — free, no API key required, covers all major US equities.
   Some fields (especially trailing financials) may be missing for small-cap stocks.
   We degrade gracefully: missing data → None, never crash.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import yfinance as yf

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from backend.models.stock import Stock

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class FundamentalResult:
    """Container for all fundamental metrics for a single ticker.

    Fields that cannot be computed (missing yfinance data) are set to None.
    This lets callers distinguish "not available" from "zero".
    """

    ticker: str

    # Valuation
    pe_ratio: float | None
    peg_ratio: float | None
    fcf_yield: float | None  # 0.05 = 5%
    debt_to_equity: float | None  # e.g. 0.5 = 50% debt relative to equity

    # Piotroski
    piotroski_score: int | None  # 0–9

    # Growth & margins (materialized to Stock model during ingestion)
    revenue_growth: float | None = None
    gross_margins: float | None = None
    operating_margins: float | None = None
    profit_margins: float | None = None
    return_on_equity: float | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None

    piotroski_breakdown: dict = field(default_factory=dict)  # 9 binary criteria


# ─────────────────────────────────────────────────────────────────────────────
# Piotroski F-Score computation
# ─────────────────────────────────────────────────────────────────────────────


def compute_piotroski(info: dict) -> tuple[int | None, dict]:
    """Compute the Piotroski F-Score from a yfinance info dict.

    Each of the 9 criteria returns 1 if met, 0 if not, or is skipped if data
    is missing. If no criteria can be evaluated, returns (None, {}).

    Args:
        info: yfinance Ticker.info dictionary (or equivalent flat dict).

    Returns:
        Tuple of (total_score, breakdown_dict).
        breakdown_dict maps criterion name → 0 or 1.
        If data is insufficient, returns (None, {}).
    """
    if not info:
        return None, {}

    breakdown: dict[str, int] = {}

    # ── Helper: safe float fetch ─────────────────────────────────────
    def _get(key: str) -> float | None:
        val = info.get(key)
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    roa = _get("returnOnAssets")
    roa_prior = _get("returnOnAssetsPrior")
    cfo = _get("operatingCashflow")
    total_assets = _get("totalAssets")
    long_term_debt = _get("longTermDebt")
    long_term_debt_prior = _get("longTermDebtPrior")
    current_ratio = _get("currentRatio")
    current_ratio_prior = _get("currentRatioPrior")
    shares = _get("sharesOutstanding")
    shares_prior = _get("sharesPrior")
    gross_margin = _get("grossMargins")
    gross_margin_prior = _get("grossMarginsPrior")
    asset_turnover = _get("assetTurnover")
    asset_turnover_prior = _get("assetTurnoverPrior")

    # ── F1: Positive ROA ─────────────────────────────────────────────
    if roa is not None:
        breakdown["positive_roa"] = 1 if roa > 0 else 0

    # ── F2: Positive operating cash flow ─────────────────────────────
    if cfo is not None:
        breakdown["positive_cfo"] = 1 if cfo > 0 else 0

    # ── F3: Improving ROA ────────────────────────────────────────────
    if roa is not None and roa_prior is not None:
        breakdown["improving_roa"] = 1 if roa > roa_prior else 0

    # ── F4: Accruals — CFO > Net Income (ROA × Total Assets) ─────────
    # Net income ≈ ROA × Total Assets. If CFO > net income, the company's
    # cash generation exceeds its accounting earnings — a quality signal.
    if cfo is not None and roa is not None and total_assets is not None:
        net_income_est = roa * total_assets
        breakdown["accruals"] = 1 if cfo > net_income_est else 0

    # ── F5: Decreasing long-term debt ────────────────────────────────
    if long_term_debt is not None and long_term_debt_prior is not None:
        breakdown["decreasing_leverage"] = 1 if long_term_debt < long_term_debt_prior else 0

    # ── F6: Improving current ratio ──────────────────────────────────
    if current_ratio is not None and current_ratio_prior is not None:
        breakdown["improving_liquidity"] = 1 if current_ratio > current_ratio_prior else 0

    # ── F7: No share dilution ────────────────────────────────────────
    if shares is not None and shares_prior is not None:
        breakdown["no_dilution"] = 1 if shares <= shares_prior else 0

    # ── F8: Improving gross margin ───────────────────────────────────
    if gross_margin is not None and gross_margin_prior is not None:
        breakdown["improving_gross_margin"] = 1 if gross_margin > gross_margin_prior else 0

    # ── F9: Improving asset turnover ─────────────────────────────────
    if asset_turnover is not None and asset_turnover_prior is not None:
        breakdown["improving_asset_turnover"] = 1 if asset_turnover > asset_turnover_prior else 0

    if not breakdown:
        return None, {}

    total = sum(breakdown.values())
    return total, breakdown


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────


def _null_result(ticker: str) -> FundamentalResult:
    """Return an all-None FundamentalResult for a given ticker."""
    return FundamentalResult(
        ticker=ticker.upper(),
        pe_ratio=None,
        peg_ratio=None,
        fcf_yield=None,
        debt_to_equity=None,
        piotroski_score=None,
        piotroski_breakdown={},
    )


def fetch_fundamentals(ticker: str) -> FundamentalResult:
    """Fetch and compute fundamental metrics for a ticker via yfinance.

    Calls yfinance synchronously (this is a CPU/IO-bound operation that
    should be run in a thread pool when called from async FastAPI context).

    Args:
        ticker: Stock symbol (e.g. "AAPL"). Case-insensitive.

    Returns:
        FundamentalResult with all available metrics. Fields are None
        when yfinance does not provide the data.
    """
    ticker = ticker.upper().strip()

    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception:
        logger.warning("yfinance failed for %s fundamentals", ticker)
        return _null_result(ticker)

    # ── Valuation ratios ─────────────────────────────────────────────
    def _get(key: str) -> float | None:
        val = info.get(key)
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    pe_ratio = _get("trailingPE")
    peg_ratio = _get("pegRatio")
    debt_to_equity = _get("debtToEquity")

    # FCF yield = Free Cash Flow / Market Cap
    fcf = _get("freeCashflow")
    market_cap = _get("marketCap")
    if fcf is not None and market_cap and market_cap > 0:
        fcf_yield = round(fcf / market_cap, 4)
    else:
        fcf_yield = None

    # ── Growth & margins ─────────────────────────────────────────────
    revenue_growth = _get("revenueGrowth")
    gross_margins = _get("grossMargins")
    operating_margins = _get("operatingMargins")
    profit_margins = _get("profitMargins")
    return_on_equity = _get("returnOnEquity")
    enterprise_value = _get("enterpriseValue")

    # ── Piotroski F-Score ────────────────────────────────────────────
    piotroski_score, piotroski_breakdown = compute_piotroski(info)

    logger.info(
        "Fundamentals fetched for %s: PE=%.1f PEG=%.2f FCF_yield=%.3f Piotroski=%s",
        ticker,
        pe_ratio or 0,
        peg_ratio or 0,
        fcf_yield or 0,
        piotroski_score,
    )

    return FundamentalResult(
        ticker=ticker,
        pe_ratio=pe_ratio,
        peg_ratio=peg_ratio,
        fcf_yield=fcf_yield,
        debt_to_equity=debt_to_equity,
        revenue_growth=revenue_growth,
        gross_margins=gross_margins,
        operating_margins=operating_margins,
        profit_margins=profit_margins,
        return_on_equity=return_on_equity,
        market_cap=market_cap,
        enterprise_value=enterprise_value,
        piotroski_score=piotroski_score,
        piotroski_breakdown=piotroski_breakdown,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Persist enriched data to Stock model
# ─────────────────────────────────────────────────────────────────────────────


def fetch_analyst_data(ticker: str) -> dict:
    """Fetch analyst target and recommendation data from yfinance.

    Args:
        ticker: Stock symbol.

    Returns:
        Dict with analyst_target_mean/high/low, analyst_buy/hold/sell,
        business_summary, employees, website. Missing keys are omitted.
    """
    ticker = ticker.upper().strip()
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception:
        logger.warning("yfinance failed for %s analyst data", ticker)
        return {}

    def _get_float(key: str) -> float | None:
        val = info.get(key)
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    def _get_int(key: str) -> int | None:
        val = info.get(key)
        try:
            return int(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    result: dict = {}

    # Analyst targets
    for key, field_name in [
        ("targetMeanPrice", "analyst_target_mean"),
        ("targetHighPrice", "analyst_target_high"),
        ("targetLowPrice", "analyst_target_low"),
    ]:
        val = _get_float(key)
        if val is not None:
            result[field_name] = val

    # Recommendation breakdown
    recs = info.get("recommendationKey")  # noqa: F841 — we use breakdown below
    for key, field_name in [
        ("numberOfAnalystOpinions", "analyst_buy"),  # approximate; see below
    ]:
        pass  # yfinance doesn't split buy/hold/sell reliably from .info

    # Use .recommendations_summary if available for buy/hold/sell counts
    try:
        rec_summary = t.recommendations
        if rec_summary is not None and not rec_summary.empty:
            latest = rec_summary.iloc[-1]
            result["analyst_buy"] = int(latest.get("strongBuy", 0)) + int(latest.get("buy", 0))
            result["analyst_hold"] = int(latest.get("hold", 0))
            result["analyst_sell"] = int(latest.get("sell", 0)) + int(latest.get("strongSell", 0))
    except Exception:
        pass

    # Profile data
    summary = info.get("longBusinessSummary")
    if summary:
        result["business_summary"] = summary
    employees = _get_int("fullTimeEmployees")
    if employees is not None:
        result["employees"] = employees
    website = info.get("website")
    if website:
        result["website"] = str(website)

    return result


async def persist_enriched_fundamentals(
    stock: Stock,
    fundamentals: FundamentalResult,
    analyst_data: dict,
    db: AsyncSession,
) -> None:
    """Persist enriched fundamentals and analyst data to the Stock model.

    Args:
        stock: Stock ORM object to update.
        fundamentals: FundamentalResult from fetch_fundamentals().
        analyst_data: Dict from fetch_analyst_data().
        db: Async database session (caller manages commit).
    """
    # Growth & margins from FundamentalResult
    stock.revenue_growth = fundamentals.revenue_growth
    stock.gross_margins = fundamentals.gross_margins
    stock.operating_margins = fundamentals.operating_margins
    stock.profit_margins = fundamentals.profit_margins
    stock.return_on_equity = fundamentals.return_on_equity
    stock.market_cap = fundamentals.market_cap

    # Analyst data
    for field_name in (
        "analyst_target_mean",
        "analyst_target_high",
        "analyst_target_low",
        "analyst_buy",
        "analyst_hold",
        "analyst_sell",
        "business_summary",
        "employees",
        "website",
    ):
        val = analyst_data.get(field_name)
        if val is not None:
            setattr(stock, field_name, val)

    db.add(stock)
    logger.info("Persisted enriched fundamentals for %s", stock.ticker)


def fetch_earnings_history(ticker: str) -> list[dict]:
    """Fetch quarterly earnings history from yfinance.

    Args:
        ticker: Stock symbol.

    Returns:
        List of dicts with keys: quarter, eps_estimate, eps_actual, surprise_pct.
        Empty list on failure.
    """
    ticker = ticker.upper().strip()
    try:
        t = yf.Ticker(ticker)
        hist = t.earnings_history
        if hist is None or hist.empty:
            return []
    except Exception:
        logger.warning("yfinance failed for %s earnings history", ticker)
        return []

    results = []
    for _, row in hist.iterrows():
        quarter = str(row.get("Quarter", ""))
        eps_est = row.get("epsEstimate")
        eps_act = row.get("epsActual")
        surprise = row.get("surprisePercent")

        def _safe_float(v: object) -> float | None:
            try:
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        results.append(
            {
                "quarter": quarter,
                "eps_estimate": _safe_float(eps_est),
                "eps_actual": _safe_float(eps_act),
                "surprise_pct": _safe_float(surprise),
            }
        )
    return results


async def persist_earnings_snapshots(
    ticker: str,
    earnings: list[dict],
    db: AsyncSession,
) -> int:
    """Upsert earnings snapshots into the database.

    Args:
        ticker: Stock ticker.
        earnings: List of dicts from fetch_earnings_history().
        db: Async session (caller manages commit).

    Returns:
        Number of rows upserted.
    """
    if not earnings:
        return 0

    from sqlalchemy.dialects.postgresql import insert

    from backend.models.earnings import EarningsSnapshot

    rows = []
    for e in earnings:
        if not e.get("quarter"):
            continue
        rows.append(
            {
                "ticker": ticker.upper(),
                "quarter": e["quarter"],
                "eps_estimate": e.get("eps_estimate"),
                "eps_actual": e.get("eps_actual"),
                "surprise_pct": e.get("surprise_pct"),
            }
        )

    if not rows:
        return 0

    stmt = insert(EarningsSnapshot).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="earnings_snapshots_pkey",
        set_={
            "eps_estimate": stmt.excluded.eps_estimate,
            "eps_actual": stmt.excluded.eps_actual,
            "surprise_pct": stmt.excluded.surprise_pct,
        },
    )
    await db.execute(stmt)
    logger.info("Upserted %d earnings snapshots for %s", len(rows), ticker)
    return len(rows)
