# Divestment Rules Engine — Design Spec

**Date:** 2026-03-14
**Phase:** 3.5, Item 9
**Branch:** `feat/phase-3.5-portfolio-advanced`

## Overview

Add an on-demand divestment rules engine that flags positions needing attention.
Alerts surface inline on the portfolio positions table. Thresholds are
user-configurable via a settings sheet on the portfolio page, with sensible
defaults pre-filled.

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Computation model | On-demand (not pre-computed) | Portfolio is viewed infrequently; avoids Celery complexity |
| Alert delivery | Bundled into positions endpoint response | Minimizes DB round-trips (3 queries total) |
| Frontend placement | Inline badges on position rows | No separate alert panel; keeps portfolio page focused |
| Threshold source | `UserPreference` model (already exists) | Fields already defined: `default_stop_loss_pct`, `max_position_pct`, `max_sector_pct`, `min_cash_reserve_pct` |
| Cash reserve rule | Deferred to Phase 4 | Requires cash tracking which doesn't exist yet |
| Fundamentals thresholds | Absolute (Piotroski < 4, composite < 3) | Simpler than historical-drop detection; no extra DB queries |

## Scope

### In Scope

- Pure function `check_divestment_rules()` with 4 rule types
- `GET /api/v1/auth/preferences` and `PATCH /api/v1/auth/preferences` endpoints
- Enhanced positions endpoint returning alerts per position
- Portfolio page: alert badges column + settings sheet for thresholds
- Unit tests (rule logic) + API tests (endpoints)

### Out of Scope

- Cash reserve warnings (Phase 4)
- Push notifications / email alerts
- Alert history or acknowledgment tracking
- Automated sell execution

## Backend

### 1. Pure Rule Checker

**File:** `backend/tools/divestment.py`

```python
def check_divestment_rules(
    position: dict,
    sector_allocations: list[dict],
    signal: dict | None,
    prefs: UserPreference,
) -> list[dict]:
    """Check divestment rules for a single position.

    Args:
        position: Dict with keys: ticker, shares, avg_cost_basis,
            current_price, unrealized_pnl_pct, allocation_pct, sector.
        sector_allocations: List of dicts with keys: sector, pct.
        signal: Dict with keys: composite_score, piotroski_score.
            None if no signal data available.
        prefs: User's preference record with threshold fields.

    Returns:
        List of alert dicts, each with keys:
            rule (str), severity (str), message (str),
            value (float), threshold (float).
    """
```

**Rules:**

| Rule | Condition | Severity | Example Message |
|---|---|---|---|
| `stop_loss` | `unrealized_pnl_pct <= -prefs.default_stop_loss_pct` | `critical` | "Down 23.4% (limit: 20%)" |
| `position_concentration` | `allocation_pct > prefs.max_position_pct` | `warning` | "7.2% of portfolio (limit: 5%)" |
| `sector_concentration` | position's sector `pct > prefs.max_sector_pct` | `warning` | "Technology at 35.1% (limit: 30%)" |
| `weak_fundamentals` | `piotroski_score < 4` or `composite_score < 3` | `warning` | "Piotroski F-Score: 2" or "Composite: 1.8" |

The function is pure — no DB calls, no side effects. It receives all data it
needs as arguments.

### 2. Schemas

**File:** `backend/schemas/portfolio.py` (additions)

```python
class DivestmentAlert(BaseModel):
    rule: str           # "stop_loss" | "position_concentration" | "sector_concentration" | "weak_fundamentals"
    severity: str       # "critical" | "warning"
    message: str
    value: float
    threshold: float

class PositionWithAlerts(PositionResponse):
    alerts: list[DivestmentAlert] = []

class UserPreferenceResponse(BaseModel):
    default_stop_loss_pct: float
    max_position_pct: float
    max_sector_pct: float
    min_cash_reserve_pct: float
    model_config = {"from_attributes": True}

class UserPreferenceUpdate(BaseModel):
    default_stop_loss_pct: float | None = None
    max_position_pct: float | None = None
    max_sector_pct: float | None = None
    min_cash_reserve_pct: float | None = None
```

### 3. Positions Endpoint Enhancement

**File:** `backend/routers/portfolio.py`

The existing `GET /portfolio/positions` endpoint changes its response model
from `list[PositionResponse]` to `list[PositionWithAlerts]`.

**Query plan (3 queries total):**

1. Fetch positions (existing query — unchanged)
2. Fetch `UserPreference` for current user (1 query, create with defaults if missing)
3. Fetch latest signals for all held tickers (1 bulk query)

Then for each position, call `check_divestment_rules()` in-memory and attach
the resulting alerts list.

### 4. Preferences Endpoints

**File:** `backend/routers/auth.py` (additions)

```
GET  /api/v1/auth/preferences  → UserPreferenceResponse
PATCH /api/v1/auth/preferences → UserPreferenceResponse
```

- GET creates a `UserPreference` row with defaults if none exists (idempotent)
- PATCH performs partial update — only supplied fields change
- Both require authentication (`get_current_user` dependency)

## Frontend

### 1. Alert Badges on Positions Table

**File:** `frontend/src/app/(authenticated)/portfolio/portfolio-client.tsx`

Add an "Alerts" column to the positions table. Each alert renders as a compact
badge:

| Severity | Style |
|---|---|
| `critical` | Red background, white text (`bg-red-500/10 text-loss border-red-500/20`) |
| `warning` | Amber background, dark text (`bg-amber-500/10 text-amber-700 border-amber-500/20`) |

Multiple alerts stack vertically. Empty cell if no alerts.

### 2. Settings Sheet

**File:** `frontend/src/components/portfolio-settings-sheet.tsx` (new)

A shadcn `Sheet` component triggered by a gear icon button in the portfolio
page header (next to "Log Transaction").

Contents:
- Number input for each threshold (stop-loss %, max position %, max sector %)
- Pre-filled with current user values (fetched via `GET /preferences`)
- "Reset Defaults" button restores model defaults (20, 5, 30)
- "Save" button calls `PATCH /preferences` and invalidates portfolio queries
- Min cash reserve field included but disabled with "(Coming soon)" label

### 3. Hooks

**File:** `frontend/src/hooks/use-stocks.ts` (additions)

```typescript
function usePreferences()    // GET /auth/preferences
function useUpdatePreferences()  // PATCH /auth/preferences mutation
```

### 4. Types

**File:** `frontend/src/types/api.ts` (additions)

```typescript
interface DivestmentAlert {
  rule: string;
  severity: "critical" | "warning";
  message: string;
  value: number;
  threshold: number;
}

interface PositionWithAlerts extends Position {
  alerts: DivestmentAlert[];
}

interface UserPreferences {
  default_stop_loss_pct: number;
  max_position_pct: number;
  max_sector_pct: number;
  min_cash_reserve_pct: number;
}

interface UserPreferencesUpdate {
  default_stop_loss_pct?: number;
  max_position_pct?: number;
  max_sector_pct?: number;
  min_cash_reserve_pct?: number;
}
```

## Testing

### Unit Tests (`tests/unit/test_divestment.py`)

| Test | Description |
|---|---|
| `test_no_alerts_healthy_position` | Position within all limits → empty list |
| `test_stop_loss_fires` | P&L below threshold → critical alert |
| `test_stop_loss_at_boundary` | Exactly at threshold → alert fires (<=) |
| `test_position_concentration_fires` | Allocation above limit → warning |
| `test_sector_concentration_fires` | Sector above limit → warning |
| `test_weak_piotroski_fires` | Piotroski < 4 → warning |
| `test_weak_composite_fires` | Composite < 3 → warning |
| `test_multiple_alerts_stack` | Position with 3 violations → 3 alerts |
| `test_null_signal_skips_fundamentals` | No signal data → no fundamentals alert |
| `test_custom_thresholds` | Non-default prefs → alerts use custom values |

### API Tests (`tests/api/test_preferences.py`)

| Test | Description |
|---|---|
| `test_get_preferences_unauthenticated` | 401 without token |
| `test_get_preferences_creates_defaults` | First call creates row with defaults |
| `test_get_preferences_returns_existing` | Returns previously set values |
| `test_patch_preferences_partial_update` | Only updates supplied fields |
| `test_patch_preferences_unauthenticated` | 401 without token |

### API Tests (`tests/api/test_portfolio.py` — additions)

| Test | Description |
|---|---|
| `test_positions_include_alerts` | Positions response has alerts field |
| `test_positions_alerts_respect_user_prefs` | Custom thresholds change alert behavior |

## Migration

No new migration required. `UserPreference` model and table already exist with
the threshold columns (`default_stop_loss_pct`, `max_position_pct`,
`max_sector_pct`, `min_cash_reserve_pct`).
