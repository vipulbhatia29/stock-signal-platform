"""Ingest pipeline hardening tests — delta refresh, empty data, idempotency."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_stock(name: str = "Test Corp", last_fetched_at=None) -> MagicMock:
    """Create a mock Stock object with .name set correctly."""
    stock = MagicMock()
    # MagicMock.name is special — use configure_mock for reliable setting
    stock.configure_mock(name=name)
    stock.last_fetched_at = last_fetched_at
    return stock


def _mock_fund(piotroski_score=6) -> MagicMock:
    """Create a mock FundamentalResult."""
    result = MagicMock()
    result.piotroski_score = piotroski_score
    return result


def _mock_signal(composite_score=7.5) -> MagicMock:
    """Create a mock SignalResult."""
    result = MagicMock()
    result.composite_score = composite_score
    return result


# ===========================================================================
# Tests
# ===========================================================================


class TestIngestPipelineHardening:
    """Additional ingest pipeline tests beyond the basic 5 in test_ingest.py."""

    @patch("backend.tools.signals.store_signal_snapshot", new_callable=AsyncMock)
    @patch("backend.tools.signals.compute_signals")
    @patch("backend.tools.fundamentals.persist_earnings_snapshots", new_callable=AsyncMock)
    @patch("backend.tools.fundamentals.fetch_earnings_history", return_value=[])
    @patch("backend.tools.fundamentals.persist_enriched_fundamentals", new_callable=AsyncMock)
    @patch("backend.tools.fundamentals.fetch_analyst_data", return_value={})
    @patch("backend.tools.fundamentals.fetch_fundamentals")
    @patch("backend.tools.market_data.update_last_fetched_at", new_callable=AsyncMock)
    @patch("backend.tools.market_data.load_prices_df", new_callable=AsyncMock)
    @patch("backend.tools.market_data.fetch_prices_delta", new_callable=AsyncMock)
    @patch("backend.tools.market_data.ensure_stock_exists", new_callable=AsyncMock)
    async def test_delta_refresh_returns_updated_status(
        self,
        mock_ensure,
        mock_fetch_delta,
        mock_load,
        mock_update,
        mock_fundamentals,
        _a,
        _b,
        _c,
        _d,
        mock_compute,
        mock_store,
        authenticated_client: AsyncClient,
    ) -> None:
        """Delta refresh (existing ticker) returns status='updated'."""
        mock_ensure.return_value = _mock_stock(
            last_fetched_at=datetime.now(timezone.utc),
        )
        mock_fetch_delta.return_value = pd.DataFrame({"Close": [150.0, 151.0]})
        mock_load.return_value = pd.DataFrame({"Close": [148.0, 149.0, 150.0, 151.0]})
        mock_fundamentals.return_value = _mock_fund()
        mock_compute.return_value = _mock_signal()

        resp = await authenticated_client.post("/api/v1/stocks/AAPL/ingest")
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"

    @patch("backend.tools.signals.store_signal_snapshot", new_callable=AsyncMock)
    @patch("backend.tools.signals.compute_signals")
    @patch("backend.tools.fundamentals.persist_earnings_snapshots", new_callable=AsyncMock)
    @patch("backend.tools.fundamentals.fetch_earnings_history", return_value=[])
    @patch("backend.tools.fundamentals.persist_enriched_fundamentals", new_callable=AsyncMock)
    @patch("backend.tools.fundamentals.fetch_analyst_data", return_value={})
    @patch("backend.tools.fundamentals.fetch_fundamentals")
    @patch("backend.tools.market_data.update_last_fetched_at", new_callable=AsyncMock)
    @patch("backend.tools.market_data.load_prices_df", new_callable=AsyncMock)
    @patch("backend.tools.market_data.fetch_prices_delta", new_callable=AsyncMock)
    @patch("backend.tools.market_data.ensure_stock_exists", new_callable=AsyncMock)
    async def test_new_ticker_returns_created_status(
        self,
        mock_ensure,
        mock_fetch_delta,
        mock_load,
        mock_update,
        mock_fundamentals,
        _a,
        _b,
        _c,
        _d,
        mock_compute,
        mock_store,
        authenticated_client: AsyncClient,
    ) -> None:
        """New ticker (first ingest) returns status='created'."""
        mock_ensure.return_value = _mock_stock(last_fetched_at=None)
        mock_fetch_delta.return_value = pd.DataFrame({"Close": [150.0, 151.0]})
        mock_load.return_value = pd.DataFrame({"Close": [148.0, 150.0, 151.0]})
        mock_fundamentals.return_value = _mock_fund()
        mock_compute.return_value = _mock_signal()

        resp = await authenticated_client.post("/api/v1/stocks/NEWT/ingest")
        assert resp.status_code == 200
        assert resp.json()["status"] == "created"

    @patch("backend.tools.signals.store_signal_snapshot", new_callable=AsyncMock)
    @patch("backend.tools.signals.compute_signals")
    @patch("backend.tools.fundamentals.persist_earnings_snapshots", new_callable=AsyncMock)
    @patch("backend.tools.fundamentals.fetch_earnings_history", return_value=[])
    @patch("backend.tools.fundamentals.persist_enriched_fundamentals", new_callable=AsyncMock)
    @patch("backend.tools.fundamentals.fetch_analyst_data", return_value={})
    @patch("backend.tools.fundamentals.fetch_fundamentals")
    @patch("backend.tools.market_data.update_last_fetched_at", new_callable=AsyncMock)
    @patch("backend.tools.market_data.load_prices_df", new_callable=AsyncMock)
    @patch("backend.tools.market_data.fetch_prices_delta", new_callable=AsyncMock)
    @patch("backend.tools.market_data.ensure_stock_exists", new_callable=AsyncMock)
    async def test_empty_price_data_returns_zero_rows(
        self,
        mock_ensure,
        mock_fetch_delta,
        mock_load,
        mock_update,
        mock_fundamentals,
        _a,
        _b,
        _c,
        _d,
        mock_compute,
        mock_store,
        authenticated_client: AsyncClient,
    ) -> None:
        """Empty delta returns rows_fetched=0 and composite_score=None."""
        mock_ensure.return_value = _mock_stock()
        mock_fetch_delta.return_value = pd.DataFrame()
        mock_load.return_value = pd.DataFrame()
        mock_fundamentals.return_value = _mock_fund()
        mock_compute.return_value = _mock_signal(composite_score=None)

        resp = await authenticated_client.post("/api/v1/stocks/EMPT/ingest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["rows_fetched"] == 0
        assert data["composite_score"] is None

    @patch("backend.tools.signals.store_signal_snapshot", new_callable=AsyncMock)
    @patch("backend.tools.signals.compute_signals")
    @patch("backend.tools.fundamentals.persist_earnings_snapshots", new_callable=AsyncMock)
    @patch("backend.tools.fundamentals.fetch_earnings_history", return_value=[])
    @patch("backend.tools.fundamentals.persist_enriched_fundamentals", new_callable=AsyncMock)
    @patch("backend.tools.fundamentals.fetch_analyst_data", return_value={})
    @patch("backend.tools.fundamentals.fetch_fundamentals")
    @patch("backend.tools.market_data.update_last_fetched_at", new_callable=AsyncMock)
    @patch("backend.tools.market_data.load_prices_df", new_callable=AsyncMock)
    @patch("backend.tools.market_data.fetch_prices_delta", new_callable=AsyncMock)
    @patch("backend.tools.market_data.ensure_stock_exists", new_callable=AsyncMock)
    async def test_rows_fetched_matches_delta_length(
        self,
        mock_ensure,
        mock_fetch_delta,
        mock_load,
        mock_update,
        mock_fundamentals,
        _a,
        _b,
        _c,
        _d,
        mock_compute,
        mock_store,
        authenticated_client: AsyncClient,
    ) -> None:
        """rows_fetched in response matches the delta DataFrame length."""
        mock_ensure.return_value = _mock_stock()
        mock_fetch_delta.return_value = pd.DataFrame({"Close": [100.0 + i for i in range(12)]})
        mock_load.return_value = pd.DataFrame({"Close": [90.0 + i for i in range(20)]})
        mock_fundamentals.return_value = _mock_fund()
        mock_compute.return_value = _mock_signal()

        resp = await authenticated_client.post("/api/v1/stocks/ROWS/ingest")
        assert resp.status_code == 200
        assert resp.json()["rows_fetched"] == 12

    @patch("backend.tools.signals.store_signal_snapshot", new_callable=AsyncMock)
    @patch("backend.tools.signals.compute_signals")
    @patch("backend.tools.fundamentals.persist_earnings_snapshots", new_callable=AsyncMock)
    @patch("backend.tools.fundamentals.fetch_earnings_history", return_value=[])
    @patch("backend.tools.fundamentals.persist_enriched_fundamentals", new_callable=AsyncMock)
    @patch("backend.tools.fundamentals.fetch_analyst_data", return_value={})
    @patch("backend.tools.fundamentals.fetch_fundamentals")
    @patch("backend.tools.market_data.update_last_fetched_at", new_callable=AsyncMock)
    @patch("backend.tools.market_data.load_prices_df", new_callable=AsyncMock)
    @patch("backend.tools.market_data.fetch_prices_delta", new_callable=AsyncMock)
    @patch("backend.tools.market_data.ensure_stock_exists", new_callable=AsyncMock)
    async def test_signal_snapshot_stored_when_composite_available(
        self,
        mock_ensure,
        mock_fetch_delta,
        mock_load,
        mock_update,
        mock_fundamentals,
        _a,
        _b,
        _c,
        _d,
        mock_compute,
        mock_store,
        authenticated_client: AsyncClient,
    ) -> None:
        """store_signal_snapshot is called when composite_score is not None."""
        mock_ensure.return_value = _mock_stock()
        mock_fetch_delta.return_value = pd.DataFrame({"Close": [150.0]})
        mock_load.return_value = pd.DataFrame({"Close": [148.0, 150.0]})
        mock_fundamentals.return_value = _mock_fund()
        mock_compute.return_value = _mock_signal(composite_score=8.0)

        await authenticated_client.post("/api/v1/stocks/SIG1/ingest")
        mock_store.assert_called_once()

    @patch("backend.tools.signals.store_signal_snapshot", new_callable=AsyncMock)
    @patch("backend.tools.signals.compute_signals")
    @patch("backend.tools.fundamentals.persist_earnings_snapshots", new_callable=AsyncMock)
    @patch("backend.tools.fundamentals.fetch_earnings_history", return_value=[])
    @patch("backend.tools.fundamentals.persist_enriched_fundamentals", new_callable=AsyncMock)
    @patch("backend.tools.fundamentals.fetch_analyst_data", return_value={})
    @patch("backend.tools.fundamentals.fetch_fundamentals")
    @patch("backend.tools.market_data.update_last_fetched_at", new_callable=AsyncMock)
    @patch("backend.tools.market_data.load_prices_df", new_callable=AsyncMock)
    @patch("backend.tools.market_data.fetch_prices_delta", new_callable=AsyncMock)
    @patch("backend.tools.market_data.ensure_stock_exists", new_callable=AsyncMock)
    async def test_signal_snapshot_not_stored_when_no_composite(
        self,
        mock_ensure,
        mock_fetch_delta,
        mock_load,
        mock_update,
        mock_fundamentals,
        _a,
        _b,
        _c,
        _d,
        mock_compute,
        mock_store,
        authenticated_client: AsyncClient,
    ) -> None:
        """store_signal_snapshot is NOT called when composite_score is None."""
        mock_ensure.return_value = _mock_stock()
        mock_fetch_delta.return_value = pd.DataFrame({"Close": [150.0]})
        mock_load.return_value = pd.DataFrame({"Close": [148.0, 150.0]})
        mock_fundamentals.return_value = _mock_fund()
        mock_compute.return_value = _mock_signal(composite_score=None)

        await authenticated_client.post("/api/v1/stocks/SIG2/ingest")
        mock_store.assert_not_called()

    @patch("backend.tools.market_data.ensure_stock_exists", new_callable=AsyncMock)
    async def test_fetch_prices_delta_error_returns_404(
        self,
        mock_ensure,
        authenticated_client: AsyncClient,
    ) -> None:
        """ValueError from fetch_prices_delta returns 404."""
        mock_ensure.return_value = _mock_stock()

        with patch(
            "backend.tools.market_data.fetch_prices_delta",
            new_callable=AsyncMock,
            side_effect=ValueError("No price data for BADX"),
        ):
            resp = await authenticated_client.post("/api/v1/stocks/BADX/ingest")
        assert resp.status_code == 404

    @patch("backend.tools.signals.store_signal_snapshot", new_callable=AsyncMock)
    @patch("backend.tools.signals.compute_signals")
    @patch("backend.tools.fundamentals.persist_earnings_snapshots", new_callable=AsyncMock)
    @patch("backend.tools.fundamentals.fetch_earnings_history", return_value=[])
    @patch("backend.tools.fundamentals.persist_enriched_fundamentals", new_callable=AsyncMock)
    @patch("backend.tools.fundamentals.fetch_analyst_data", return_value={})
    @patch("backend.tools.fundamentals.fetch_fundamentals")
    @patch("backend.tools.market_data.update_last_fetched_at", new_callable=AsyncMock)
    @patch("backend.tools.market_data.load_prices_df", new_callable=AsyncMock)
    @patch("backend.tools.market_data.fetch_prices_delta", new_callable=AsyncMock)
    @patch("backend.tools.market_data.ensure_stock_exists", new_callable=AsyncMock)
    async def test_idempotent_double_ingest(
        self,
        mock_ensure,
        mock_fetch_delta,
        mock_load,
        mock_update,
        mock_fundamentals,
        _a,
        _b,
        _c,
        _d,
        mock_compute,
        mock_store,
        authenticated_client: AsyncClient,
    ) -> None:
        """Two consecutive ingests both succeed (idempotency)."""
        mock_ensure.return_value = _mock_stock(last_fetched_at=None)
        mock_fetch_delta.return_value = pd.DataFrame({"Close": [150.0]})
        mock_load.return_value = pd.DataFrame({"Close": [148.0, 150.0]})
        mock_fundamentals.return_value = _mock_fund()
        mock_compute.return_value = _mock_signal()

        resp1 = await authenticated_client.post("/api/v1/stocks/IDEM/ingest")
        assert resp1.status_code == 200

        # Second call — simulate already fetched
        mock_ensure.return_value = _mock_stock(
            last_fetched_at=datetime.now(timezone.utc),
        )
        resp2 = await authenticated_client.post("/api/v1/stocks/IDEM/ingest")
        assert resp2.status_code == 200

    @patch("backend.tools.signals.store_signal_snapshot", new_callable=AsyncMock)
    @patch("backend.tools.signals.compute_signals")
    @patch("backend.tools.fundamentals.persist_earnings_snapshots", new_callable=AsyncMock)
    @patch("backend.tools.fundamentals.fetch_earnings_history", return_value=[])
    @patch("backend.tools.fundamentals.persist_enriched_fundamentals", new_callable=AsyncMock)
    @patch("backend.tools.fundamentals.fetch_analyst_data", return_value={})
    @patch("backend.tools.fundamentals.fetch_fundamentals")
    @patch("backend.tools.market_data.update_last_fetched_at", new_callable=AsyncMock)
    @patch("backend.tools.market_data.load_prices_df", new_callable=AsyncMock)
    @patch("backend.tools.market_data.fetch_prices_delta", new_callable=AsyncMock)
    @patch("backend.tools.market_data.ensure_stock_exists", new_callable=AsyncMock)
    async def test_ticker_case_normalized_to_uppercase(
        self,
        mock_ensure,
        mock_fetch_delta,
        mock_load,
        mock_update,
        mock_fundamentals,
        _a,
        _b,
        _c,
        _d,
        mock_compute,
        mock_store,
        authenticated_client: AsyncClient,
    ) -> None:
        """Lowercase ticker is normalized to uppercase before processing."""
        mock_ensure.return_value = _mock_stock()
        mock_fetch_delta.return_value = pd.DataFrame({"Close": [100.0]})
        mock_load.return_value = pd.DataFrame()
        mock_fundamentals.return_value = _mock_fund()
        mock_compute.return_value = _mock_signal(composite_score=None)

        resp = await authenticated_client.post("/api/v1/stocks/aapl/ingest")
        assert resp.status_code == 200
        # Verify ensure_stock_exists received uppercase
        call_args = mock_ensure.call_args[0]
        assert call_args[0] == "AAPL"

    @patch("backend.tools.signals.store_signal_snapshot", new_callable=AsyncMock)
    @patch("backend.tools.signals.compute_signals")
    @patch("backend.tools.fundamentals.persist_earnings_snapshots", new_callable=AsyncMock)
    @patch("backend.tools.fundamentals.fetch_earnings_history", return_value=[])
    @patch("backend.tools.fundamentals.persist_enriched_fundamentals", new_callable=AsyncMock)
    @patch("backend.tools.fundamentals.fetch_analyst_data", return_value={})
    @patch("backend.tools.fundamentals.fetch_fundamentals")
    @patch("backend.tools.market_data.update_last_fetched_at", new_callable=AsyncMock)
    @patch("backend.tools.market_data.load_prices_df", new_callable=AsyncMock)
    @patch("backend.tools.market_data.fetch_prices_delta", new_callable=AsyncMock)
    @patch("backend.tools.market_data.ensure_stock_exists", new_callable=AsyncMock)
    async def test_last_fetched_at_updated_after_ingest(
        self,
        mock_ensure,
        mock_fetch_delta,
        mock_load,
        mock_update,
        mock_fundamentals,
        _a,
        _b,
        _c,
        _d,
        mock_compute,
        mock_store,
        authenticated_client: AsyncClient,
    ) -> None:
        """update_last_fetched_at is always called after a successful ingest."""
        mock_ensure.return_value = _mock_stock()
        mock_fetch_delta.return_value = pd.DataFrame({"Close": [150.0]})
        mock_load.return_value = pd.DataFrame({"Close": [148.0, 150.0]})
        mock_fundamentals.return_value = _mock_fund()
        mock_compute.return_value = _mock_signal()

        await authenticated_client.post("/api/v1/stocks/UPD1/ingest")
        mock_update.assert_called_once()
