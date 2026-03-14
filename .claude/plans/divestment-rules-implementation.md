# Divestment Rules Engine — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-03-14-divestment-rules-engine-design.md`
**Branch:** `feat/phase-3.5-portfolio-advanced`

## Pre-flight

- [ ] Read PROGRESS.md, verify branch state
- [ ] Run `uv run pytest tests/unit/ -v` — confirm baseline green (109 unit tests)
- [ ] Run `uv run pytest tests/api/ -v` — confirm API tests green (109 API tests)

---

## Step 1: Pure rule checker (`backend/tools/divestment.py`)

**Create** `backend/tools/divestment.py` with:

```python
def check_divestment_rules(
    position: dict,           # {ticker, unrealized_pnl_pct, allocation_pct, sector}
    sector_allocations: list[dict],  # [{sector, pct}]
    signal: dict | None,      # {composite_score} or None
    prefs: UserPreference,    # from backend.models.user
) -> list[dict]:
```

Rules (4):
1. **stop_loss**: `unrealized_pnl_pct <= -prefs.default_stop_loss_pct` → severity `critical`
2. **position_concentration**: `allocation_pct > prefs.max_position_pct` → severity `warning`
3. **sector_concentration**: find position's sector in `sector_allocations`, check `pct > prefs.max_sector_pct` → severity `warning`
4. **weak_fundamentals**: `composite_score < 3` → severity `warning`

Null safety: skip rule when the dependent value is `None`.

Each alert dict: `{rule, severity, message, value, threshold}`

**Test:** `tests/unit/test_divestment.py` — 11 tests per spec test plan.

**Verify:** `uv run pytest tests/unit/test_divestment.py -v`

---

## Step 2: Schemas (`backend/schemas/portfolio.py`)

**Edit** `backend/schemas/portfolio.py` to add:

1. `DivestmentAlert` — with `Literal` types for `rule` and `severity`
2. `PositionWithAlerts(PositionResponse)` — adds `alerts: list[DivestmentAlert] = []`
3. `UserPreferenceResponse` — 4 float fields + `from_attributes`
4. `UserPreferenceUpdate` — 4 optional float fields with `Field(None, gt=0, le=100)`

**Also edit** `PositionResponse` to add `sector: str | None = None` field.

**Also edit** `SectorAllocation` comment to remove hardcoded "30" reference.

**Verify:** No test needed yet — schemas tested via API tests.

---

## Step 3: Update `get_positions_with_pnl()` to include sector

**Edit** `backend/tools/portfolio.py`:

In `get_positions_with_pnl()` (line 207):
- After fetching positions, do a bulk query to get `Stock.sector` for all tickers (same pattern already used in `get_portfolio_summary()` lines 300-306)
- Add `sector` to each `PositionResponse` output

**Also update** `_group_sectors()` to accept an optional `max_sector_pct` parameter (default 30.0) instead of hardcoding 30.

**Also update** `get_portfolio_summary()` to pass `max_sector_pct` through if available (for now keep 30.0 default — will be wired to user prefs in Step 5).

**Verify:** `uv run pytest tests/unit/test_portfolio.py tests/api/test_portfolio.py -v` — existing tests should still pass, `sector` field added with default `None` is backward-compatible.

---

## Step 4: Preferences router (`backend/routers/preferences.py`)

**Create** `backend/routers/preferences.py`:

```python
router = APIRouter(prefix="/preferences", tags=["preferences"])

@router.get("", response_model=UserPreferenceResponse)
async def get_preferences(current_user, db):
    # Query UserPreference by user_id
    # If not found, create with defaults, flush, return

@router.patch("", response_model=UserPreferenceResponse)
async def update_preferences(body: UserPreferenceUpdate, current_user, db):
    # Get or create pref
    # Apply only non-None fields from body
    # Commit, return updated
```

**Register** in `backend/main.py`:
```python
from backend.routers import preferences
app.include_router(preferences.router, prefix="/api/v1")
```

**Test:** `tests/api/test_preferences.py` — 6 tests per spec:
- `test_get_preferences_unauthenticated` → 401
- `test_get_preferences_creates_defaults` → returns default values
- `test_get_preferences_returns_existing` → returns saved values
- `test_patch_preferences_partial_update` → only updates supplied fields
- `test_patch_preferences_unauthenticated` → 401
- `test_patch_preferences_validation_error` → negative/over-100 → 422

**Verify:** `uv run pytest tests/api/test_preferences.py -v`

---

## Step 5: Wire alerts into positions endpoint

**Edit** `backend/routers/portfolio.py`:

In `list_positions()`:
1. Import `UserPreference`, `check_divestment_rules`, `PositionWithAlerts`
2. After getting positions, fetch user's `UserPreference` (get-or-create pattern)
3. Bulk-fetch latest `composite_score` from `SignalSnapshot` for held tickers
4. Build sector allocations from positions in-memory
5. For each position, call `check_divestment_rules()`, create `PositionWithAlerts`
6. Change `response_model` to `list[PositionWithAlerts]`

**Also wire** `max_sector_pct` from user prefs into `get_portfolio_summary()` → `_group_sectors()` so pie chart `over_limit` matches user threshold. This requires:
- `get_portfolio_summary()` gains optional `max_sector_pct` param
- `get_summary` endpoint fetches user prefs and passes `max_sector_pct`

**Test additions** in `tests/api/test_portfolio.py`:
- `test_positions_include_alerts` — verify alerts field present
- `test_positions_alerts_respect_user_prefs` — custom prefs change alert behavior

**Verify:** `uv run pytest tests/api/test_portfolio.py -v`

---

## Step 6: Frontend types and hooks

**Edit** `frontend/src/types/api.ts`:
- Add `DivestmentAlert` interface (with union types for rule/severity)
- Update `Position` to include `alerts: DivestmentAlert[]` and `sector: string | null`
- Add `UserPreferences` and `UserPreferencesUpdate` interfaces

**Edit** `frontend/src/hooks/use-stocks.ts`:
- Add `usePreferences()` hook — `GET /preferences`, staleTime 5min
- Add `useUpdatePreferences()` mutation — `PATCH /preferences`, invalidates `["preferences"]` and `["portfolio"]`

**Verify:** `cd frontend && npm run lint && npm run build`

---

## Step 7: Portfolio settings sheet component

**Create** `frontend/src/components/portfolio-settings-sheet.tsx`:

A shadcn `Sheet` with:
- Number inputs for stop-loss %, max position %, max sector %
- Disabled input for min cash reserve % with "(Coming soon)" label
- Pre-filled via `usePreferences()` hook
- "Reset Defaults" button (20, 5, 30)
- "Save" button calls `useUpdatePreferences()` mutation
- Uses shadcn `Input`, `Button`, `Label`, `Sheet`/`SheetContent`/`SheetHeader`/`SheetTitle`

**Verify:** `cd frontend && npm run lint && npm run build`

---

## Step 8: Wire alerts + settings into portfolio page

**Edit** `frontend/src/app/(authenticated)/portfolio/portfolio-client.tsx`:

1. Import `PortfolioSettingsSheet`, gear icon from lucide
2. Add gear button next to "Log Transaction" that opens the sheet
3. Add "Alerts" column to `PositionsTable`
4. Render alert badges per position:
   - `critical` → red badge (`bg-red-500/10 text-loss border border-red-500/20`)
   - `warning` → amber badge (`bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/20`)
5. Stack multiple alerts vertically, empty cell if none

**Verify:** `cd frontend && npm run lint && npm run build`

---

## Step 9: Full test suite + lint

```bash
uv run ruff check backend/ tests/ --fix
uv run ruff format backend/ tests/
uv run pytest tests/unit/ -v
uv run pytest tests/api/ -v
cd frontend && npm run lint && npm run build
```

All tests must pass. Zero lint errors.

---

## Step 10: Commit and push

Commit each logical unit separately:
1. `feat: divestment rules pure checker + unit tests`
2. `feat: preferences router + API tests`
3. `feat: wire alerts into positions endpoint`
4. `feat: portfolio settings sheet + alert badges UI`

Push to `feat/phase-3.5-portfolio-advanced`.

---

## Post-implementation

- Update `PROGRESS.md` with session entry
- Update `project-plan.md` — mark item 9 complete
- Update Serena memories (`project_overview`)
- Update `MEMORY.md` with new resume point
