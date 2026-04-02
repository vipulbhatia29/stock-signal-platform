"""Tests for event-driven CacheInvalidator."""

from unittest.mock import AsyncMock

import pytest

from backend.services.cache_invalidator import CacheInvalidator


@pytest.fixture
def mock_redis():
    """Provide a mock Redis client with async methods."""
    redis = AsyncMock()
    redis.delete = AsyncMock(return_value=1)
    redis.scan = AsyncMock(return_value=(0, []))
    return redis


@pytest.fixture
def invalidator(mock_redis):
    """Provide a CacheInvalidator with mock Redis."""
    return CacheInvalidator(redis=mock_redis)


@pytest.mark.asyncio
async def test_on_signals_updated_clears_convergence(invalidator, mock_redis):
    """Signal update invalidates convergence and rationale caches."""
    await invalidator.on_signals_updated(["AAPL", "MSFT"])
    calls = [str(c) for c in mock_redis.delete.call_args_list]
    assert any("app:convergence:AAPL" in c for c in calls)
    assert any("app:convergence:MSFT" in c for c in calls)
    assert any("app:convergence:rationale:AAPL" in c for c in calls)


@pytest.mark.asyncio
async def test_on_signals_updated_does_not_clear_unrelated(invalidator, mock_redis):
    """Invalidating AAPL should NOT touch MSFT cache."""
    await invalidator.on_signals_updated(["AAPL"])
    calls = [str(c) for c in mock_redis.delete.call_args_list]
    assert not any("MSFT" in c for c in calls)


@pytest.mark.asyncio
async def test_on_prices_updated_clears_convergence_and_forecast(invalidator, mock_redis):
    """Price update clears convergence, rationale, forecast, and sector caches."""
    await invalidator.on_prices_updated(["AAPL"])
    calls = [str(c) for c in mock_redis.delete.call_args_list]
    assert any("app:convergence:AAPL" in c for c in calls)
    assert any("app:forecast:AAPL" in c for c in calls)
    # Also clears sector caches via SCAN
    mock_redis.scan.assert_called()


@pytest.mark.asyncio
async def test_on_prices_updated_does_not_clear_bl_cache(invalidator, mock_redis):
    """BL/MC/CVaR caches rely on TTL, not explicit invalidation on price update."""
    await invalidator.on_prices_updated(["AAPL"])
    calls = [str(c) for c in mock_redis.delete.call_args_list]
    assert not any("bl-forecast" in c for c in calls)
    assert not any("monte-carlo" in c for c in calls)
    assert not any("cvar" in c for c in calls)


@pytest.mark.asyncio
async def test_on_portfolio_changed_clears_user_caches(invalidator, mock_redis):
    """Portfolio change clears BL, Monte Carlo, and CVaR caches for user."""
    user_id = "user-123"
    await invalidator.on_portfolio_changed(user_id)
    calls = [str(c) for c in mock_redis.delete.call_args_list]
    assert any(f"bl-forecast:{user_id}" in c for c in calls)
    assert any(f"monte-carlo:{user_id}" in c for c in calls)
    assert any(f"cvar:{user_id}" in c for c in calls)


@pytest.mark.asyncio
async def test_on_forecast_updated_clears_forecast_and_convergence(invalidator, mock_redis):
    """Forecast update clears forecast, convergence, rationale caches."""
    await invalidator.on_forecast_updated(["AAPL"])
    calls = [str(c) for c in mock_redis.delete.call_args_list]
    assert any("app:forecast:AAPL" in c for c in calls)
    assert any("app:convergence:AAPL" in c for c in calls)


@pytest.mark.asyncio
async def test_on_forecast_updated_clears_sector_and_bl(invalidator, mock_redis):
    """Forecast update also clears sector-forecast and bl-forecast via SCAN."""
    await invalidator.on_forecast_updated(["AAPL"])
    scan_calls = [str(c) for c in mock_redis.scan.call_args_list]
    assert any("sector-forecast" in c for c in scan_calls)
    assert any("bl-forecast" in c for c in scan_calls)


@pytest.mark.asyncio
async def test_on_backtest_completed_clears_backtest_cache(invalidator, mock_redis):
    """Backtest completion clears backtest result cache."""
    await invalidator.on_backtest_completed(["AAPL", "MSFT"])
    calls = [str(c) for c in mock_redis.delete.call_args_list]
    assert any("app:backtest:AAPL" in c for c in calls)
    assert any("app:backtest:MSFT" in c for c in calls)


@pytest.mark.asyncio
async def test_on_sentiment_scored_clears_sentiment_and_convergence(invalidator, mock_redis):
    """Sentiment scoring clears sentiment and convergence caches."""
    await invalidator.on_sentiment_scored(["AAPL"])
    calls = [str(c) for c in mock_redis.delete.call_args_list]
    assert any("app:sentiment:AAPL" in c for c in calls)
    assert any("app:convergence:AAPL" in c for c in calls)


@pytest.mark.asyncio
async def test_on_stock_ingested_does_not_delete(invalidator, mock_redis):
    """New stock ingestion has nothing to invalidate."""
    await invalidator.on_stock_ingested("NEWSTOCK")
    mock_redis.delete.assert_not_called()


@pytest.mark.asyncio
async def test_clear_pattern_uses_scan(invalidator, mock_redis):
    """Pattern-based clearing uses SCAN, not KEYS."""
    mock_redis.scan = AsyncMock(
        side_effect=[
            (42, [b"app:sector-forecast:tech", b"app:sector-forecast:energy"]),
            (0, []),
        ]
    )
    deleted = await invalidator._clear_pattern("app:sector-forecast:*")
    assert deleted == 2
    assert mock_redis.scan.call_count == 2


@pytest.mark.asyncio
async def test_redis_failure_does_not_propagate(mock_redis):
    """Redis failure logs warning but does not raise."""
    mock_redis.delete = AsyncMock(side_effect=ConnectionError("Redis down"))
    invalidator = CacheInvalidator(redis=mock_redis)
    # Should not raise
    await invalidator.on_prices_updated(["AAPL"])
    await invalidator.on_signals_updated(["AAPL"])
    await invalidator.on_portfolio_changed("user-1")
