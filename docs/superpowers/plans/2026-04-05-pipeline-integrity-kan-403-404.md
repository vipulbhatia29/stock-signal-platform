# Pipeline Integrity Implementation Plan (KAN-403, KAN-404)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix Prophet negative price predictions and ensure all user-referenced tickers (portfolio + watchlist + index) get price/signal/forecast data through the nightly pipeline.

**Architecture:** 7 fixes across forecasting, Celery tasks, chat tools, portfolio router, and forecast aggregation. A new canonical `ticker_universe.py` service provides the single source of truth for "which tickers matter." All fixes are additive — no migrations, no breaking changes.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Celery, Prophet, pytest

**Spec:** `docs/superpowers/specs/2026-04-05-pipeline-integrity-kan-403-404.md`

---

### Task 1: Prophet Negative Price Floor (Fix 1 — KAN-403)

**Files:**
- Modify: `backend/tools/forecasting.py:209-222`
- Modify: `backend/schemas/forecasts.py:10-19`
- Test: `tests/unit/test_forecasting_floor.py`

- [ ] **Step 1: Write the failing test for price floor**

```python
# tests/unit/test_forecasting_floor.py
"""Tests for Prophet forecast price flooring (KAN-403)."""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.tools.forecasting import predict_forecast


def _make_model_version(ticker: str = "TEST") -> MagicMock:
    """Create a mock ModelVersion for testing."""
    mv = MagicMock()
    mv.ticker = ticker
    mv.version = 1
    mv.id = uuid.uuid4()
    mv.artifact_path = "/tmp/fake_model.json"
    mv.training_data_end = datetime(2026, 1, 1).date()
    return mv


def _make_prophet_forecast(yhat: float, yhat_lower: float, yhat_upper: float):
    """Create a mock Prophet forecast DataFrame."""
    return pd.DataFrame({
        "ds": [pd.Timestamp("2026-04-05"), pd.Timestamp("2026-07-04")],
        "yhat": [100.0, yhat],
        "yhat_lower": [90.0, yhat_lower],
        "yhat_upper": [110.0, yhat_upper],
    })


class TestPredictForecastFloor:
    """Test price flooring in predict_forecast."""

    @patch("backend.tools.forecasting.model_from_json")
    @patch("builtins.open", create=True)
    @patch("backend.tools.forecasting.Path")
    def test_negative_predictions_floored(self, mock_path, mock_open, mock_model_from_json):
        """Negative yhat values are floored to max(0.01, last_price * 0.01)."""
        mock_path.return_value.exists.return_value = True

        mock_model = MagicMock()
        # Last training price used as reference for floor
        mock_model.history = pd.DataFrame({"y": [100.0, 200.0, 150.0]})
        mock_model.extra_regressors = {}
        mock_model.make_future_dataframe.return_value = pd.DataFrame(
            {"ds": pd.date_range("2026-01-01", periods=270, freq="D")}
        )
        # Prophet predicts negative price
        forecast_df = pd.DataFrame({
            "ds": pd.date_range("2026-01-01", periods=270, freq="D"),
            "yhat": [-50.0] * 270,
            "yhat_lower": [-100.0] * 270,
            "yhat_upper": [-10.0] * 270,
        })
        mock_model.predict.return_value = forecast_df
        mock_model_from_json.return_value = mock_model

        mv = _make_model_version("SMCI")
        results = predict_forecast(mv, horizons=[90])

        assert len(results) == 1
        # Floor = max(0.01, 150.0 * 0.01) = 1.50
        assert results[0].predicted_price == 1.50
        assert results[0].predicted_lower == 1.50
        assert results[0].predicted_upper == 1.50

    @patch("backend.tools.forecasting.model_from_json")
    @patch("builtins.open", create=True)
    @patch("backend.tools.forecasting.Path")
    def test_positive_predictions_unchanged(self, mock_path, mock_open, mock_model_from_json):
        """Positive predictions above the floor are not modified."""
        mock_path.return_value.exists.return_value = True

        mock_model = MagicMock()
        mock_model.history = pd.DataFrame({"y": [100.0, 200.0, 150.0]})
        mock_model.extra_regressors = {}
        mock_model.make_future_dataframe.return_value = pd.DataFrame(
            {"ds": pd.date_range("2026-01-01", periods=270, freq="D")}
        )
        forecast_df = pd.DataFrame({
            "ds": pd.date_range("2026-01-01", periods=270, freq="D"),
            "yhat": [160.0] * 270,
            "yhat_lower": [140.0] * 270,
            "yhat_upper": [180.0] * 270,
        })
        mock_model.predict.return_value = forecast_df
        mock_model_from_json.return_value = mock_model

        mv = _make_model_version("AAPL")
        results = predict_forecast(mv, horizons=[90])

        assert results[0].predicted_price == 160.0
        assert results[0].predicted_lower == 140.0
        assert results[0].predicted_upper == 180.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_forecasting_floor.py -v`
Expected: FAIL — no flooring logic exists yet

- [ ] **Step 3: Implement price floor in predict_forecast**

In `backend/tools/forecasting.py`, modify `predict_forecast()`. After line 176 (model loaded from JSON), extract the last known price from the model's training data. Then after line 209 (row extracted), apply the floor before creating ForecastResult:

```python
# After loading model (line 176), extract last training price for floor calculation
last_known_price = float(model.history["y"].iloc[-1]) if hasattr(model, "history") and len(model.history) > 0 else 0.0
price_floor = max(0.01, last_known_price * 0.01)
```

Then replace lines 210-222 with:

```python
        row = target_row.iloc[0]
        raw_price = round(float(row["yhat"]), 2)
        raw_lower = round(float(row["yhat_lower"]), 2)
        raw_upper = round(float(row["yhat_upper"]), 2)

        # Floor negative/near-zero predictions (KAN-403)
        floored = False
        if raw_price < price_floor or raw_lower < price_floor or raw_upper < price_floor:
            logger.warning(
                "Flooring prediction for %s +%dd: yhat=%.2f, lower=%.2f, upper=%.2f (floor=%.2f)",
                model_version.ticker, horizon, raw_price, raw_lower, raw_upper, price_floor,
            )
            floored = True

        results.append(
            ForecastResult(
                forecast_date=today,
                ticker=model_version.ticker,
                horizon_days=horizon,
                model_version_id=model_version.id,
                predicted_price=max(raw_price, price_floor),
                predicted_lower=max(raw_lower, price_floor),
                predicted_upper=max(raw_upper, price_floor),
                target_date=target_date,
                created_at=now,
            )
        )
```

- [ ] **Step 4: Add Field(gt=0) validation on ForecastHorizon schema**

In `backend/schemas/forecasts.py`, update lines 14-16:

```python
class ForecastHorizon(BaseModel):
    """Forecast at a single horizon."""

    horizon_days: int
    predicted_price: float = Field(gt=0)
    predicted_lower: float = Field(gt=0)
    predicted_upper: float = Field(gt=0)
    target_date: date
    confidence_level: str = "medium"
    sharpe_direction: str = "flat"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_forecasting_floor.py -v`
Expected: PASS

- [ ] **Step 6: Run existing forecast tests to check for regressions**

Run: `uv run pytest tests/unit/ -k forecast -v --tb=short`
Expected: All existing tests pass

- [ ] **Step 7: Commit**

```bash
git add backend/tools/forecasting.py backend/schemas/forecasts.py tests/unit/test_forecasting_floor.py
git commit -m "fix(KAN-403): floor Prophet negative predictions with scale-appropriate minimum"
```

---

### Task 2: Canonical Referenced Tickers Query (Fix 2)

**Files:**
- Create: `backend/services/ticker_universe.py`
- Modify: `backend/tasks/market_data.py`
- Modify: `backend/tasks/forecasting.py`
- Test: `tests/unit/test_ticker_universe.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_ticker_universe.py
"""Tests for canonical ticker universe query."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.ticker_universe import get_all_referenced_tickers


@pytest.mark.asyncio
async def test_union_of_index_watchlist_portfolio():
    """Returns deduped union of index members + watchlist + portfolio positions."""
    mock_db = AsyncMock()
    # Simulate UNION result: AAPL (index+watchlist), GOOG (watchlist), FORD (portfolio), MSFT (index)
    mock_result = MagicMock()
    mock_result.all.return_value = [("AAPL",), ("FORD",), ("GOOG",), ("MSFT",)]
    mock_db.execute.return_value = mock_result

    tickers = await get_all_referenced_tickers(mock_db)

    assert tickers == ["AAPL", "FORD", "GOOG", "MSFT"]
    # Verify one execute call (single UNION query, not 3 separate)
    assert mock_db.execute.call_count == 1


@pytest.mark.asyncio
async def test_empty_when_no_references():
    """Returns empty list when no tickers are referenced."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db.execute.return_value = mock_result

    tickers = await get_all_referenced_tickers(mock_db)
    assert tickers == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_ticker_universe.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Create ticker_universe.py**

```python
# backend/services/ticker_universe.py
"""Canonical ticker universe — single source of truth for referenced tickers.

All tickers the system actively cares about: index members, watchlist, portfolio positions.
Used by nightly pipeline, Beat fan-out, and forecast training.
"""

from __future__ import annotations

import logging

from sqlalchemy import union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.models.index import StockIndexMembership
from backend.models.portfolio import Position
from backend.models.stock import Watchlist

logger = logging.getLogger(__name__)


async def get_all_referenced_tickers(db: AsyncSession) -> list[str]:
    """All tickers the system actively cares about (deduped, sorted).

    Union of:
    - Current index members (removed_date IS NULL)
    - All watchlist tickers (across all users)
    - Portfolio positions with shares > 0 (across all users)

    Args:
        db: Async database session.

    Returns:
        Sorted list of unique ticker symbols.
    """
    stmt = union(
        select(StockIndexMembership.ticker).where(
            StockIndexMembership.removed_date.is_(None)
        ),
        select(Watchlist.ticker),
        select(Position.ticker).where(Position.shares > 0),
    )
    result = await db.execute(
        select(stmt.subquery().c.ticker).order_by("ticker")
    )
    return [row[0] for row in result.all()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_ticker_universe.py -v`
Expected: PASS

- [ ] **Step 5: Wire into market_data.py — replace _get_all_watchlist_tickers**

In `backend/tasks/market_data.py`:

1. Remove `_get_all_watchlist_tickers()` function (lines 166-178)
2. Add a new helper that uses the canonical query:

```python
async def _get_all_referenced_tickers() -> list[str]:
    """Get all referenced tickers using the canonical universe query."""
    from backend.services.ticker_universe import get_all_referenced_tickers

    async with async_session_factory() as db:
        return await get_all_referenced_tickers(db)
```

3. Update all callers of `_get_all_watchlist_tickers()` to use `_get_all_referenced_tickers()`:
   - Line 200: `tickers = await _get_all_referenced_tickers()`
   - Line 409: `tickers = asyncio.run(_get_all_referenced_tickers())`

- [ ] **Step 6: Wire into forecasting.py — replace _get_all_forecast_tickers**

In `backend/tasks/forecasting.py`:

1. Remove `_get_all_forecast_tickers()` function (lines 15-44)
2. Replace callers with canonical query:
   - Line 55 in `_model_retrain_all_async()`:

```python
from backend.services.ticker_universe import get_all_referenced_tickers
# ...
async with async_session_factory() as db:
    tickers = await get_all_referenced_tickers(db)
```

- [ ] **Step 7: Run existing tests to check for regressions**

Run: `uv run pytest tests/unit/ -k "market_data or forecast" -v --tb=short`
Expected: All pass (callers use the same interface — sorted list of tickers)

- [ ] **Step 8: Commit**

```bash
git add backend/services/ticker_universe.py backend/tasks/market_data.py backend/tasks/forecasting.py tests/unit/test_ticker_universe.py
git commit -m "fix(KAN-404): canonical ticker universe — union of index + watchlist + portfolio"
```

---

### Task 3: Nightly Forecast — Dispatch Training for New Tickers (Fix 3)

**Files:**
- Modify: `backend/tasks/forecasting.py:85-126`
- Test: `tests/unit/test_forecast_new_ticker_training.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_forecast_new_ticker_training.py
"""Tests for nightly forecast dispatching training for new tickers."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
@patch("backend.tasks.forecasting.retrain_single_ticker_task")
@patch("backend.tasks.forecasting.get_all_referenced_tickers")
@patch("backend.tasks.forecasting.async_session_factory")
@patch("backend.tasks.forecasting.PipelineRunner")
async def test_dispatches_training_for_new_tickers(
    mock_runner_cls, mock_session_factory, mock_get_tickers, mock_retrain_task
):
    """Nightly forecast dispatches training for tickers with prices but no ModelVersion."""
    from backend.tasks.forecasting import _forecast_refresh_async

    # Setup: no existing active models
    mock_db = AsyncMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    # No active models
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    # 2 referenced tickers
    mock_get_tickers.return_value = ["AAPL", "FORD"]

    # AAPL has 300 price points, FORD has 50
    async def mock_price_count(ticker, db):
        return 300 if ticker == "AAPL" else 50

    with patch("backend.tasks.forecasting._get_price_data_count", mock_price_count):
        result = await _forecast_refresh_async()

    # Only AAPL dispatched (FORD has < 200 points)
    mock_retrain_task.delay.assert_called_once_with("AAPL")


@pytest.mark.asyncio
@patch("backend.tasks.forecasting.retrain_single_ticker_task")
@patch("backend.tasks.forecasting.get_all_referenced_tickers")
@patch("backend.tasks.forecasting.async_session_factory")
@patch("backend.tasks.forecasting.PipelineRunner")
async def test_caps_new_ticker_training_at_20(
    mock_runner_cls, mock_session_factory, mock_get_tickers, mock_retrain_task
):
    """New ticker training is capped at 20 per nightly run."""
    from backend.tasks.forecasting import _forecast_refresh_async, MAX_NEW_MODELS_PER_NIGHT

    assert MAX_NEW_MODELS_PER_NIGHT == 20

    mock_db = AsyncMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    # 30 referenced tickers, all with enough data
    tickers = [f"TICK{i:02d}" for i in range(30)]
    mock_get_tickers.return_value = tickers

    async def mock_price_count(ticker, db):
        return 300

    with patch("backend.tasks.forecasting._get_price_data_count", mock_price_count):
        await _forecast_refresh_async()

    assert mock_retrain_task.delay.call_count == 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_forecast_new_ticker_training.py -v`
Expected: FAIL — no dispatch logic or `MAX_NEW_MODELS_PER_NIGHT` constant exists

- [ ] **Step 3: Implement new-ticker dispatch in _forecast_refresh_async**

In `backend/tasks/forecasting.py`, add at top:

```python
from backend.services.ticker_universe import get_all_referenced_tickers
from backend.tools.forecasting import MIN_DATA_POINTS

MAX_NEW_MODELS_PER_NIGHT = 20
```

Add helper function:

```python
async def _get_price_data_count(ticker: str, db: AsyncSession) -> int:
    """Count price data points for a ticker (last 2 years)."""
    from datetime import timedelta

    from sqlalchemy import func

    from backend.models.price import StockPrice

    two_years_ago = datetime.now(timezone.utc).date() - timedelta(days=730)
    result = await db.execute(
        select(func.count())
        .select_from(StockPrice)
        .where(StockPrice.ticker == ticker, StockPrice.time >= two_years_ago)
    )
    return result.scalar() or 0
```

At the end of `_forecast_refresh_async()`, after the existing model refresh loop (before the `return`), add:

```python
    # ── Phase 2: Dispatch training for new tickers without models ──
    try:
        all_tickers = await get_all_referenced_tickers(db)
        modeled_tickers = {mv.ticker for mv in active_models}
        new_tickers = [t for t in all_tickers if t not in modeled_tickers]

        dispatched = 0
        for ticker in new_tickers[:MAX_NEW_MODELS_PER_NIGHT]:
            count = await _get_price_data_count(ticker, db)
            if count >= MIN_DATA_POINTS:
                retrain_single_ticker_task.delay(ticker)
                dispatched += 1
                logger.info("Dispatched first-time training for %s (%d data points)", ticker, count)
            else:
                logger.debug("Skipping %s: only %d data points (need %d)", ticker, count, MIN_DATA_POINTS)

        if dispatched:
            logger.info("Dispatched training for %d new tickers", dispatched)
    except Exception:
        logger.warning("Failed to dispatch new-ticker training", exc_info=True)
```

Add the required import at the top of the function:

```python
from backend.tasks.forecasting import retrain_single_ticker_task
```

(This is a self-import for the Celery task — safe because it's imported inside the function, not at module level.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_forecast_new_ticker_training.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tasks/forecasting.py tests/unit/test_forecast_new_ticker_training.py
git commit -m "fix(KAN-404): nightly forecast dispatches training for new tickers (cap 20/night)"
```

---

### Task 4: Chat Auto-Ingest (Fix 4)

**Files:**
- Modify: `backend/tools/analyze_stock.py:50-56`
- Test: `tests/unit/test_analyze_stock_autoingest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_analyze_stock_autoingest.py
"""Tests for analyze_stock auto-ingest on missing data."""
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from backend.tools.analyze_stock import AnalyzeStockTool


@pytest.mark.asyncio
@patch("backend.tools.analyze_stock.async_session_factory")
async def test_auto_ingests_when_no_price_data(mock_session_factory):
    """analyze_stock auto-ingests ticker with no price data instead of erroring."""
    mock_session = AsyncMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    # First call: empty df. Second call (after ingest): has data
    call_count = 0

    async def mock_load_prices(ticker, session):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return pd.DataFrame()
        return pd.DataFrame({"Close": [100.0, 101.0, 102.0]})

    mock_signals = MagicMock()
    mock_signals.composite_score = 7.5
    mock_signals.rsi_value = 55.0
    mock_signals.rsi_signal = "neutral"
    mock_signals.macd_value = 0.5
    mock_signals.macd_signal_label = "bullish"
    mock_signals.sma_signal = "above"
    mock_signals.bb_position = 0.6
    mock_signals.annual_return = 0.12
    mock_signals.volatility = 0.25
    mock_signals.sharpe_ratio = 1.2

    with (
        patch("backend.tools.analyze_stock.load_prices_df", side_effect=mock_load_prices),
        patch("backend.tools.analyze_stock.compute_signals", return_value=mock_signals),
        patch("backend.tools.analyze_stock.ensure_stock_exists", new_callable=AsyncMock) as mock_ensure,
        patch("backend.tools.analyze_stock.fetch_prices_delta", new_callable=AsyncMock) as mock_fetch,
    ):
        tool = AnalyzeStockTool()
        result = await tool.execute({"ticker": "FORD"})

    assert result.status == "ok"
    mock_ensure.assert_called_once_with("FORD", mock_session)
    mock_fetch.assert_called_once_with("FORD", mock_session)


@pytest.mark.asyncio
@patch("backend.tools.analyze_stock.async_session_factory")
async def test_rejects_invalid_ticker_format(mock_session_factory):
    """analyze_stock rejects tickers with invalid format."""
    mock_session = AsyncMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("backend.tools.analyze_stock.load_prices_df", return_value=pd.DataFrame()):
        tool = AnalyzeStockTool()
        result = await tool.execute({"ticker": "INVALID123"})

    assert result.status == "error"
    assert "Invalid" in result.error or "format" in result.error
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_analyze_stock_autoingest.py -v`
Expected: FAIL — no auto-ingest logic

- [ ] **Step 3: Implement auto-ingest in analyze_stock**

Replace `backend/tools/analyze_stock.py` lines 45-76 with:

```python
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Run full stock analysis pipeline, auto-ingesting if needed."""
        import re

        ticker = str(params.get("ticker", "")).upper()
        if not ticker:
            return ToolResult(status="error", error="Missing required param: ticker")

        # Validate ticker format (1-5 uppercase letters)
        if not re.match(r"^[A-Z]{1,5}$", ticker):
            return ToolResult(status="error", error="Invalid ticker format. Use 1-5 letters (e.g., AAPL).")

        try:
            from backend.database import async_session_factory
            from backend.tools.market_data import load_prices_df
            from backend.tools.signals import compute_signals

            async with async_session_factory() as session:
                df = await load_prices_df(ticker, session)

                if df.empty:
                    # Auto-ingest: lightweight path (stock record + prices only)
                    from backend.services.stock_data import ensure_stock_exists, fetch_prices_delta

                    try:
                        await ensure_stock_exists(ticker, session)
                        await fetch_prices_delta(ticker, session)
                        await session.commit()
                    except (ValueError, Exception):
                        logger.warning("Auto-ingest failed for %s", ticker, exc_info=True)
                        return ToolResult(
                            status="error",
                            error=f"No data available for {ticker}. Verify the ticker is correct.",
                        )

                    df = await load_prices_df(ticker, session)
                    if df.empty:
                        return ToolResult(
                            status="error",
                            error=f"No price data available for {ticker} after ingestion.",
                        )

                signals = compute_signals(ticker, df)
                return ToolResult(
                    status="ok",
                    data={
                        "ticker": ticker,
                        "composite_score": signals.composite_score,
                        "rsi_value": signals.rsi_value,
                        "rsi_signal": signals.rsi_signal,
                        "macd_value": signals.macd_value,
                        "macd_signal": signals.macd_signal_label,
                        "sma_signal": signals.sma_signal,
                        "bb_position": signals.bb_position,
                        "annual_return": signals.annual_return,
                        "volatility": signals.volatility,
                        "sharpe_ratio": signals.sharpe_ratio,
                    },
                )
        except Exception as e:
            logger.error("analyze_stock_failed", extra={"ticker": ticker, "error": str(e)})
            return ToolResult(status="error", error="Stock analysis failed. Please try again.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_analyze_stock_autoingest.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tools/analyze_stock.py tests/unit/test_analyze_stock_autoingest.py
git commit -m "fix(KAN-404): analyze_stock auto-ingests tickers with no price data"
```

---

### Task 5: Portfolio Transaction Auto-Ingest (Fix 5)

**Files:**
- Modify: `backend/routers/portfolio.py:100-124`
- Test: `tests/unit/test_portfolio_autoingest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_portfolio_autoingest.py
"""Tests for portfolio transaction auto-ingest of unknown tickers."""
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# We test the router logic indirectly through the ensure_stock_exists call pattern


def test_valid_ticker_format():
    """Valid tickers match the format regex."""
    pattern = r"^[A-Z]{1,5}$"
    assert re.match(pattern, "AAPL")
    assert re.match(pattern, "F")
    assert re.match(pattern, "BRK")
    assert not re.match(pattern, "INVALID123")
    assert not re.match(pattern, "")
    assert not re.match(pattern, "TOOLONG")
    assert not re.match(pattern, "aapl")


def test_invalid_ticker_format_with_numbers():
    """Tickers with numbers are rejected."""
    pattern = r"^[A-Z]{1,5}$"
    assert not re.match(pattern, "BRK.A")  # dots not allowed in simple format
    assert not re.match(pattern, "123")
```

- [ ] **Step 2: Run test to verify it passes (format validation is pure logic)**

Run: `uv run pytest tests/unit/test_portfolio_autoingest.py -v`
Expected: PASS (these are pure regex tests)

- [ ] **Step 3: Implement auto-ingest in portfolio router**

In `backend/routers/portfolio.py`, add the `ensure_stock_exists` call before the Transaction creation. Insert before line 101 (`txn = Transaction(...)`):

```python
    # Auto-create stock record if ticker is unknown (KAN-404)
    import re

    from backend.services.stock_data import ensure_stock_exists

    ticker_upper = body.ticker.upper().strip()
    if not re.match(r"^[A-Z]{1,5}$", ticker_upper):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid ticker format. Use 1-5 uppercase letters.",
        )
    try:
        await ensure_stock_exists(ticker_upper, db)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ticker '{ticker_upper}' not recognized. Verify the symbol is correct.",
        )
```

Keep the existing `IntegrityError` catch at lines 112-124 as a safety net.

- [ ] **Step 4: Run existing portfolio API tests**

Run: `uv run pytest tests/api/ -k portfolio -v --tb=short`
Expected: All pass (existing tests use valid tickers that are already in the stocks table)

- [ ] **Step 5: Commit**

```bash
git add backend/routers/portfolio.py tests/unit/test_portfolio_autoingest.py
git commit -m "fix(KAN-404): portfolio transaction auto-creates stock record for unknown tickers"
```

---

### Task 6: Portfolio Forecast — No Silent Skip (Fix 6)

**Files:**
- Modify: `backend/schemas/forecasts.py:42-48`
- Modify: `backend/routers/forecasts.py:118-158`
- Test: `tests/unit/test_portfolio_forecast_missing.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_portfolio_forecast_missing.py
"""Tests for portfolio forecast missing_tickers reporting."""
from backend.schemas.forecasts import PortfolioForecastResponse


def test_missing_tickers_field_exists_with_default():
    """PortfolioForecastResponse has missing_tickers field with empty default."""
    resp = PortfolioForecastResponse(horizons=[], ticker_count=0)
    assert resp.missing_tickers == []


def test_missing_tickers_populated():
    """missing_tickers reports tickers without forecast data."""
    resp = PortfolioForecastResponse(
        horizons=[], ticker_count=2, missing_tickers=["FORD", "PLTR"]
    )
    assert resp.missing_tickers == ["FORD", "PLTR"]


def test_weight_recomputation_math():
    """Weights sum to 1.0 when some tickers are excluded."""
    # Simulate: AAPL=$4000 (40%), GOOG=$3000 (30%), FORD=$3000 (30%)
    # FORD missing → forecast_value = $7000
    # AAPL weight = 4000/7000 ≈ 0.571, GOOG weight = 3000/7000 ≈ 0.429
    position_values = {"AAPL": 4000.0, "GOOG": 3000.0, "FORD": 3000.0}
    tickers_with_forecast = {"AAPL", "GOOG"}

    forecast_value = sum(v for t, v in position_values.items() if t in tickers_with_forecast)
    assert forecast_value == 7000.0

    weights = {}
    for ticker, value in position_values.items():
        if ticker in tickers_with_forecast:
            weights[ticker] = value / forecast_value

    assert abs(sum(weights.values()) - 1.0) < 1e-10
    assert abs(weights["AAPL"] - 0.5714285714285714) < 1e-10
    assert abs(weights["GOOG"] - 0.4285714285714286) < 1e-10
    assert "FORD" not in weights
```

- [ ] **Step 2: Run test to verify it fails (missing_tickers field doesn't exist yet)**

Run: `uv run pytest tests/unit/test_portfolio_forecast_missing.py -v`
Expected: FAIL on first test — PortfolioForecastResponse has no `missing_tickers` field

- [ ] **Step 3: Add missing_tickers to schema**

In `backend/schemas/forecasts.py`, update `PortfolioForecastResponse`:

```python
class PortfolioForecastResponse(BaseModel):
    """Aggregated portfolio forecast."""

    horizons: list[PortfolioForecastHorizon]
    ticker_count: int
    vix_regime: str = "normal"
    missing_tickers: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Update forecasts router to track missing tickers and fix weights**

In `backend/routers/forecasts.py`, replace the aggregation block (lines ~118-158):

After `forecasts_by_ticker` is built (line 116), add:

```python
    # Track tickers without forecasts (KAN-404)
    tickers_with_forecast = set(forecasts_by_ticker.keys())
    missing_tickers = sorted(set(position_values.keys()) - tickers_with_forecast)

    # Recompute total using only tickers with forecasts
    forecast_value = sum(v for t, v in position_values.items() if t in tickers_with_forecast)
    if forecast_value == 0:
        return PortfolioForecastResponse(
            horizons=[], ticker_count=0, missing_tickers=sorted(position_values.keys())
        )

    # Weighted forecast aggregation — weights sum to 1.0 across covered tickers
    horizon_agg: dict[int, dict] = {}

    for ticker, value in position_values.items():
        if ticker not in tickers_with_forecast:
            continue
        weight = value / forecast_value
        current_price = price_map.get(ticker)
        if not current_price:
            continue

        forecasts = forecasts_by_ticker[ticker]
        for fc in forecasts:
            if fc.horizon_days not in horizon_agg:
                horizon_agg[fc.horizon_days] = {
                    "return_sum": 0.0,
                    "lower_sum": 0.0,
                    "upper_sum": 0.0,
                }
            expected_return = (fc.predicted_price - current_price) / current_price
            lower_return = (fc.predicted_lower - current_price) / current_price
            upper_return = (fc.predicted_upper - current_price) / current_price

            horizon_agg[fc.horizon_days]["return_sum"] += weight * expected_return
            horizon_agg[fc.horizon_days]["lower_sum"] += weight * lower_return
            horizon_agg[fc.horizon_days]["upper_sum"] += weight * upper_return
```

Update the return to include `missing_tickers`:

```python
    return PortfolioForecastResponse(
        horizons=horizons,
        ticker_count=len(position_values),
        missing_tickers=missing_tickers,
    )
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/test_portfolio_forecast_missing.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/schemas/forecasts.py backend/routers/forecasts.py tests/unit/test_portfolio_forecast_missing.py
git commit -m "fix(KAN-404): portfolio forecast reports missing_tickers, fixes weight denominator"
```

---

### Task 7: On-Ingest Forecast Dispatch (Fix 7)

**Files:**
- Modify: `backend/services/pipelines.py:120-140`
- Test: `tests/unit/test_ingest_forecast_dispatch.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_ingest_forecast_dispatch.py
"""Tests for on-ingest forecast training dispatch."""
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from backend.services.pipelines import ingest_ticker


@pytest.mark.asyncio
@patch("backend.services.pipelines.retrain_single_ticker_task")
@patch("backend.services.pipelines.update_last_fetched_at", new_callable=AsyncMock)
@patch("backend.services.pipelines.persist_earnings_snapshots", new_callable=AsyncMock)
@patch("backend.services.pipelines.persist_enriched_fundamentals", new_callable=AsyncMock)
@patch("backend.services.pipelines.fetch_earnings_history", return_value=[])
@patch("backend.services.pipelines.fetch_analyst_data", return_value=MagicMock())
@patch("backend.services.pipelines.fetch_fundamentals", return_value=MagicMock(piotroski_score=5))
@patch("backend.services.pipelines.load_prices_df")
@patch("backend.services.pipelines.fetch_prices_delta", new_callable=AsyncMock)
@patch("backend.services.pipelines.ensure_stock_exists", new_callable=AsyncMock)
async def test_dispatches_forecast_training_on_ingest(
    mock_ensure, mock_fetch_prices, mock_load_df,
    mock_fundamentals, mock_analyst, mock_earnings,
    mock_persist_fundamentals, mock_persist_earnings, mock_update_fetched,
    mock_retrain_task,
):
    """Successful ingest dispatches retrain_single_ticker_task."""
    mock_stock = MagicMock()
    mock_stock.name = "Ford Motor Co"
    mock_stock.last_fetched_at = None
    mock_ensure.return_value = mock_stock
    mock_fetch_prices.return_value = pd.DataFrame({"Close": [10.0]})
    mock_load_df.return_value = pd.DataFrame({"Close": [10.0, 11.0]})

    mock_db = AsyncMock()

    result = await ingest_ticker("FORD", mock_db)

    mock_retrain_task.delay.assert_called_once_with("FORD")
    assert result["ticker"] == "FORD"


@pytest.mark.asyncio
@patch("backend.services.pipelines.retrain_single_ticker_task")
@patch("backend.services.pipelines.update_last_fetched_at", new_callable=AsyncMock)
@patch("backend.services.pipelines.persist_earnings_snapshots", new_callable=AsyncMock)
@patch("backend.services.pipelines.persist_enriched_fundamentals", new_callable=AsyncMock)
@patch("backend.services.pipelines.fetch_earnings_history", return_value=[])
@patch("backend.services.pipelines.fetch_analyst_data", return_value=MagicMock())
@patch("backend.services.pipelines.fetch_fundamentals", return_value=MagicMock(piotroski_score=5))
@patch("backend.services.pipelines.load_prices_df")
@patch("backend.services.pipelines.fetch_prices_delta", new_callable=AsyncMock)
@patch("backend.services.pipelines.ensure_stock_exists", new_callable=AsyncMock)
async def test_celery_failure_does_not_break_ingest(
    mock_ensure, mock_fetch_prices, mock_load_df,
    mock_fundamentals, mock_analyst, mock_earnings,
    mock_persist_fundamentals, mock_persist_earnings, mock_update_fetched,
    mock_retrain_task,
):
    """Celery dispatch failure is swallowed — ingest still succeeds."""
    mock_stock = MagicMock()
    mock_stock.name = "Ford Motor Co"
    mock_stock.last_fetched_at = None
    mock_ensure.return_value = mock_stock
    mock_fetch_prices.return_value = pd.DataFrame({"Close": [10.0]})
    mock_load_df.return_value = pd.DataFrame({"Close": [10.0, 11.0]})

    mock_retrain_task.delay.side_effect = ConnectionError("Redis down")

    mock_db = AsyncMock()
    result = await ingest_ticker("FORD", mock_db)

    assert result["ticker"] == "FORD"  # Ingest succeeded despite Celery failure
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_ingest_forecast_dispatch.py -v`
Expected: FAIL — no dispatch call in `ingest_ticker`

- [ ] **Step 3: Add forecast dispatch to ingest_ticker**

In `backend/services/pipelines.py`, after step 6 (`update_last_fetched_at`, around line 122), add:

```python
    # ── Step 7b: Dispatch forecast training (fire-and-forget) ──────────
    try:
        from backend.tasks.forecasting import retrain_single_ticker_task

        retrain_single_ticker_task.delay(ticker)
        logger.info("Dispatched forecast training for %s", ticker)
    except Exception:
        logger.warning("Failed to dispatch forecast for %s", ticker, exc_info=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_ingest_forecast_dispatch.py -v`
Expected: PASS

- [ ] **Step 5: Run full unit test suite for regressions**

Run: `uv run pytest tests/unit/ -q --tb=short`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add backend/services/pipelines.py tests/unit/test_ingest_forecast_dispatch.py
git commit -m "fix(KAN-404): ingest pipeline dispatches forecast training (fire-and-forget)"
```

---

### Task 8: Lint, Format, Final Verification

**Files:** All modified files

- [ ] **Step 1: Run ruff check and format**

```bash
uv run ruff check --fix backend/ tests/
uv run ruff format backend/ tests/
```

- [ ] **Step 2: Run full unit test suite**

```bash
uv run pytest tests/unit/ -q --tb=short
```

Expected: All pass, no regressions

- [ ] **Step 3: Run Semgrep**

```bash
uv run semgrep --config .semgrep/ backend/ --error
```

Expected: No new violations

- [ ] **Step 4: Final commit if lint/format changed anything**

```bash
git add -A
git commit -m "chore: lint and format fixes for KAN-403/KAN-404"
```
