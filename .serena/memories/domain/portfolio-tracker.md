---
scope: project
category: domain
---

# Portfolio Tracker Domain

## Key Tools
- `backend/tools/portfolio.py` — positions, cost basis, P&L, allocation.
- `backend/tools/recommendations.py` — Buy/Hold/Sell decisions, position sizing.
- Portfolio-aware recommendations blend signal scores with current allocation.

## API Gotcha
- `API_BASE = "/api/v1"` in `lib/api.ts`.
- Frontend hooks must use paths like `/portfolio/positions` NOT `/api/v1/portfolio/positions`.
- Double-prefix bug: the api.ts wrapper already prepends API_BASE.

## Rebalancing
- Divestment rules, rebalancing logic, and portfolio-aware recs built in Phase 3.5 (Sessions 21-25).
- Snapshots and dividend tracking included.

## patch helper
- `lib/api.ts` exports `patch<T>()` for PATCH requests — use for partial position updates.
