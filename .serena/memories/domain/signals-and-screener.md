---
scope: project
category: domain
---

# Signals & Screener Domain

## Signal Computation
- `compute_signals()` in `backend/tools/signals.py` — accepts optional `piotroski_score` param.
- With piotroski_score: 50/50 blending of technical + fundamental composite.
- Without: pure technical composite.
- Depends on `backend/tools/fundamentals.py` for Piotroski F-Score calculation.

## Screener
- `backend/tools/screen_stocks.py` — filter + rank by composite criteria.
- Supports DensityProvider (compact/comfortable) on frontend.
- Screener results are pre-computed nightly by Celery tasks.

## Key Gotchas
- Market hours UTC: March (DST) = EDT (UTC-4). 09:00 EDT = 13:00 UTC (NOT 14:00 UTC).
- yfinance rate limiting: add 0.5s delay between ticker fetches in batch scripts.
- yfinance returns empty DataFrame for invalid/delisted tickers — validate before processing.
