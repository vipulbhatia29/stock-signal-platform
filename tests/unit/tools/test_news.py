"""Tests for news fetch functions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestFetchYfinanceNews:
    """Tests for yfinance news fetching."""

    def test_returns_list_of_articles(self) -> None:
        """Should return a list of news article dicts."""
        from backend.tools.news import fetch_yfinance_news

        mock_ticker = MagicMock()
        mock_ticker.news = [
            {
                "title": "AAPL Earnings Beat",
                "link": "https://example.com/1",
                "publisher": "Reuters",
                "providerPublishTime": 1711900000,
            },
            {
                "title": "Apple Event",
                "link": "https://example.com/2",
                "publisher": "CNBC",
                "providerPublishTime": 1711800000,
            },
        ]
        with patch("backend.tools.news.yf.Ticker", return_value=mock_ticker):
            articles = fetch_yfinance_news("AAPL")
        assert len(articles) == 2
        assert articles[0]["title"] == "AAPL Earnings Beat"
        assert articles[0]["source"] == "yfinance"

    def test_empty_news_returns_empty_list(self) -> None:
        """No news should return empty list."""
        from backend.tools.news import fetch_yfinance_news

        mock_ticker = MagicMock()
        mock_ticker.news = []
        with patch("backend.tools.news.yf.Ticker", return_value=mock_ticker):
            articles = fetch_yfinance_news("AAPL")
        assert articles == []

    def test_yfinance_error_returns_empty(self) -> None:
        """yfinance error should return empty list, not raise."""
        from backend.tools.news import fetch_yfinance_news

        with patch("backend.tools.news.yf.Ticker", side_effect=Exception("API down")):
            articles = fetch_yfinance_news("AAPL")
        assert articles == []


class TestFetchGoogleNewsRss:
    """Tests for Google News RSS fetching."""

    @pytest.mark.asyncio
    async def test_parses_rss_xml(self) -> None:
        """Should parse RSS XML into article dicts."""
        from backend.tools.news import fetch_google_news_rss

        mock_xml = """<?xml version="1.0"?>
        <rss><channel>
            <item>
                <title>AAPL surges</title>
                <link>https://news.google.com/1</link>
                <source>Bloomberg</source>
                <pubDate>Mon, 25 Mar 2026 10:00:00 GMT</pubDate>
            </item>
        </channel></rss>"""

        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = mock_xml

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.tools.news.httpx.AsyncClient", return_value=mock_client):
            articles = await fetch_google_news_rss("AAPL")
        assert len(articles) == 1
        assert articles[0]["title"] == "AAPL surges"
        assert articles[0]["source"] == "google_news"

    @pytest.mark.asyncio
    async def test_http_error_returns_empty(self) -> None:
        """HTTP error should return empty list."""
        from backend.tools.news import fetch_google_news_rss

        mock_resp = AsyncMock()
        mock_resp.status_code = 500

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.tools.news.httpx.AsyncClient", return_value=mock_client):
            articles = await fetch_google_news_rss("AAPL")
        assert articles == []


class TestMergeAndDeduplicate:
    """Tests for article merge/dedup."""

    def test_deduplicates_by_url(self) -> None:
        """Duplicate URLs should be removed."""
        from backend.tools.news import merge_and_deduplicate

        articles = [
            {"title": "A", "link": "https://example.com/1", "source": "yfinance"},
            {"title": "B", "link": "https://example.com/1", "source": "google_news"},
            {"title": "C", "link": "https://example.com/2", "source": "google_news"},
        ]
        result = merge_and_deduplicate(articles)
        assert len(result) == 2

    def test_caps_at_max(self) -> None:
        """Should return at most max_results articles."""
        from backend.tools.news import merge_and_deduplicate

        articles = [
            {"title": f"A{i}", "link": f"https://example.com/{i}", "source": "yf"}
            for i in range(30)
        ]
        result = merge_and_deduplicate(articles, max_results=10)
        assert len(result) == 10
