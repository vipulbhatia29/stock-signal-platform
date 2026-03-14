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

import yfinance as yf

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
        piotroski_score=piotroski_score,
        piotroski_breakdown=piotroski_breakdown,
    )
