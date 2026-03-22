"""Tests for Yahoo Finance external search helper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.routers.stocks import _yahoo_search


def _mock_httpx_client(json_data: dict) -> MagicMock:
    """Create a mock httpx.AsyncClient that returns the given JSON."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = json_data

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False

    return mock_client


@pytest.mark.asyncio
async def test_yahoo_search_returns_us_equities():
    """Yahoo search filters to US exchanges and returns StockSearchResponse."""
    client = _mock_httpx_client(
        {
            "quotes": [
                {
                    "symbol": "PLTR",
                    "longname": "Palantir Technologies Inc.",
                    "quoteType": "EQUITY",
                    "exchDisp": "NASDAQ",
                    "sectorDisp": "Technology",
                },
                {
                    "symbol": "PLTR.WA",
                    "shortname": "PALANTIR",
                    "quoteType": "EQUITY",
                    "exchDisp": "WSE",
                },
            ]
        }
    )

    with patch("backend.routers.stocks.httpx.AsyncClient", return_value=client):
        results = await _yahoo_search("palantir")

    assert len(results) == 1
    assert results[0].ticker == "PLTR"
    assert results[0].name == "Palantir Technologies Inc."
    assert results[0].in_db is False


@pytest.mark.asyncio
async def test_yahoo_search_includes_etfs():
    """Yahoo search includes ETF results."""
    client = _mock_httpx_client(
        {
            "quotes": [
                {
                    "symbol": "SPY",
                    "longname": "SPDR S&P 500 ETF Trust",
                    "quoteType": "ETF",
                    "exchDisp": "NYSEArca",
                    "sectorDisp": None,
                },
            ]
        }
    )

    with patch("backend.routers.stocks.httpx.AsyncClient", return_value=client):
        results = await _yahoo_search("spy")

    assert len(results) == 1
    assert results[0].ticker == "SPY"
    assert results[0].in_db is False


@pytest.mark.asyncio
async def test_yahoo_search_excludes_non_equity():
    """Yahoo search filters out mutual funds, options, etc."""
    client = _mock_httpx_client(
        {
            "quotes": [
                {
                    "symbol": "AAPL",
                    "longname": "Apple Inc.",
                    "quoteType": "EQUITY",
                    "exchDisp": "NASDAQ",
                },
                {
                    "symbol": "AAPL240119C00150000",
                    "shortname": "AAPL Option",
                    "quoteType": "OPTION",
                    "exchDisp": "OPR",
                },
                {
                    "symbol": "AAPLX",
                    "shortname": "Apple Fund",
                    "quoteType": "MUTUALFUND",
                    "exchDisp": "NasdaqGM",
                },
            ]
        }
    )

    with patch("backend.routers.stocks.httpx.AsyncClient", return_value=client):
        results = await _yahoo_search("aapl")

    assert len(results) == 1
    assert results[0].ticker == "AAPL"


@pytest.mark.asyncio
async def test_yahoo_search_handles_failure_gracefully():
    """Yahoo search returns empty list on network failure."""
    mock_client = AsyncMock()
    mock_client.get.side_effect = Exception("Network error")
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False

    with patch("backend.routers.stocks.httpx.AsyncClient", return_value=mock_client):
        results = await _yahoo_search("palantir")

    assert results == []


@pytest.mark.asyncio
async def test_yahoo_search_converts_dot_to_dash():
    """Yahoo search converts BRK.B → BRK-B for yfinance compatibility."""
    client = _mock_httpx_client(
        {
            "quotes": [
                {
                    "symbol": "BRK.B",
                    "longname": "Berkshire Hathaway Inc. Class B",
                    "quoteType": "EQUITY",
                    "exchDisp": "NYSE",
                },
            ]
        }
    )

    with patch("backend.routers.stocks.httpx.AsyncClient", return_value=client):
        results = await _yahoo_search("berkshire")

    assert results[0].ticker == "BRK-B"


@pytest.mark.asyncio
async def test_yahoo_search_uses_shortname_fallback():
    """Yahoo search falls back to shortname when longname is missing."""
    client = _mock_httpx_client(
        {
            "quotes": [
                {
                    "symbol": "NVDA",
                    "shortname": "NVIDIA Corporation",
                    "quoteType": "EQUITY",
                    "exchDisp": "NASDAQ",
                },
            ]
        }
    )

    with patch("backend.routers.stocks.httpx.AsyncClient", return_value=client):
        results = await _yahoo_search("nvidia")

    assert results[0].name == "NVIDIA Corporation"
