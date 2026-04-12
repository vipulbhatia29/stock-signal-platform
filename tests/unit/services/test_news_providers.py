"""Unit tests for all four news providers and their helper classifiers.

Tests are grouped by provider class. All HTTP calls are mocked via
unittest.mock so no live network requests are made.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.services.news.base import RawArticle
from backend.services.news.edgar_provider import (
    EdgarProvider,
    _classify_8k_items,
)
from backend.services.news.finnhub_provider import FinnhubProvider

# ---------------------------------------------------------------------------
# Lazy imports for providers created by parallel agent — fail gracefully at
# import time so test collection still works even if files aren't written yet.
# ---------------------------------------------------------------------------

try:
    from backend.services.news.fed_provider import (  # type: ignore[import]
        FedRssProvider,
        _classify_fed_press,
        _classify_fred_release,
    )

    _FED_AVAILABLE = True
except ImportError:
    _FED_AVAILABLE = False

try:
    from backend.services.news.google_provider import (  # type: ignore[import]
        GoogleNewsProvider,
    )

    _GOOGLE_AVAILABLE = True
except ImportError:
    _GOOGLE_AVAILABLE = False


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "news"


def _load_fixture(name: str) -> str:
    """Load raw fixture file content."""
    return (FIXTURES_DIR / name).read_text()


def _mock_response(
    status_code: int = 200,
    json_data: object = None,
    text_data: str | None = None,
) -> MagicMock:
    """Build a mock httpx.Response with configurable status and body."""
    resp = MagicMock()
    resp.status_code = status_code
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status = MagicMock()
    if json_data is not None:
        resp.json.return_value = json_data
    if text_data is not None:
        resp.text = text_data
    return resp


def _mock_client(resp: MagicMock) -> AsyncMock:
    """Wrap a mock response in a client returned by get_http_client()."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    return client


# ===========================================================================
# TestRawArticle — base dataclass behaviour
# ===========================================================================


class TestRawArticle:
    """Tests for RawArticle dataclass post-init logic."""

    def test_dedupe_hash_computed_automatically(self) -> None:
        """dedupe_hash is set after construction when left empty."""
        article = RawArticle(
            headline="Test headline",
            summary=None,
            source="finnhub",
            source_url=None,
            ticker="AAPL",
            published_at=datetime(2024, 3, 28, tzinfo=timezone.utc),
        )
        assert article.dedupe_hash != ""
        assert len(article.dedupe_hash) == 64  # sha256 hex

    def test_dedupe_hash_deterministic_same_inputs(self) -> None:
        """Same headline+source+date always produces the same hash."""
        kwargs = dict(
            headline="Repeatable headline",
            summary=None,
            source="finnhub",
            source_url=None,
            ticker="AAPL",
            published_at=datetime(2024, 3, 28, tzinfo=timezone.utc),
        )
        a1 = RawArticle(**kwargs)  # type: ignore[arg-type]
        a2 = RawArticle(**kwargs)  # type: ignore[arg-type]
        assert a1.dedupe_hash == a2.dedupe_hash

    def test_dedupe_hash_differs_on_different_headline(self) -> None:
        """Different headlines must produce different hashes."""
        base = dict(
            summary=None,
            source="finnhub",
            source_url=None,
            ticker="AAPL",
            published_at=datetime(2024, 3, 28, tzinfo=timezone.utc),
        )
        a1 = RawArticle(headline="Headline A", **base)  # type: ignore[arg-type]
        a2 = RawArticle(headline="Headline B", **base)  # type: ignore[arg-type]
        assert a1.dedupe_hash != a2.dedupe_hash

    def test_headline_truncated_to_500_chars(self) -> None:
        """Headlines longer than 500 chars are silently truncated."""
        long_headline = "x" * 600
        article = RawArticle(
            headline=long_headline,
            summary=None,
            source="finnhub",
            source_url=None,
            ticker="AAPL",
            published_at=datetime(2024, 3, 28, tzinfo=timezone.utc),
        )
        assert len(article.headline) == 500

    def test_explicit_dedupe_hash_not_overwritten(self) -> None:
        """Pre-supplied dedupe_hash is preserved unchanged."""
        custom_hash = "abc123"
        article = RawArticle(
            headline="Test",
            summary=None,
            source="finnhub",
            source_url=None,
            ticker="AAPL",
            published_at=datetime(2024, 3, 28, tzinfo=timezone.utc),
            dedupe_hash=custom_hash,
        )
        assert article.dedupe_hash == custom_hash

    def test_dedupe_hash_formula_matches_implementation(self) -> None:
        """Verify the hash formula: sha256(headline|source|date)."""
        pub = datetime(2024, 3, 28, tzinfo=timezone.utc)
        article = RawArticle(
            headline="Formula check",
            summary=None,
            source="test_src",
            source_url=None,
            ticker=None,
            published_at=pub,
        )
        expected = hashlib.sha256(
            f"Formula check|test_src|{pub.date().isoformat()}".encode()
        ).hexdigest()
        assert article.dedupe_hash == expected


# ===========================================================================
# TestFinnhubProvider
# ===========================================================================


class TestFinnhubProvider:
    """Tests for FinnhubProvider."""

    @pytest.mark.asyncio
    async def test_parses_fixture_into_raw_articles(self) -> None:
        """Provider returns a RawArticle for each item in the fixture JSON."""
        fixture = json.loads(_load_fixture("finnhub_aapl.json"))
        resp = _mock_response(json_data=fixture)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.finnhub_provider.get_http_client",
            return_value=client,
        ):
            provider = FinnhubProvider(api_key="test-key")
            articles = await provider.fetch_stock_news("AAPL", date(2024, 3, 1))

        assert len(articles) == 3

    @pytest.mark.asyncio
    async def test_ticker_set_on_all_articles(self) -> None:
        """All articles carry the requested ticker in uppercase."""
        fixture = json.loads(_load_fixture("finnhub_aapl.json"))
        resp = _mock_response(json_data=fixture)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.finnhub_provider.get_http_client",
            return_value=client,
        ):
            provider = FinnhubProvider(api_key="test-key")
            articles = await provider.fetch_stock_news("aapl", date(2024, 3, 1))

        assert all(a.ticker == "AAPL" for a in articles)

    @pytest.mark.asyncio
    async def test_source_name_is_finnhub(self) -> None:
        """source field is always 'finnhub'."""
        fixture = json.loads(_load_fixture("finnhub_aapl.json"))
        resp = _mock_response(json_data=fixture)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.finnhub_provider.get_http_client",
            return_value=client,
        ):
            provider = FinnhubProvider(api_key="test-key")
            articles = await provider.fetch_stock_news("AAPL", date(2024, 3, 1))

        assert all(a.source == "finnhub" for a in articles)

    @pytest.mark.asyncio
    async def test_dedupe_hash_populated_for_each_article(self) -> None:
        """Every returned article has a non-empty dedupe_hash."""
        fixture = json.loads(_load_fixture("finnhub_aapl.json"))
        resp = _mock_response(json_data=fixture)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.finnhub_provider.get_http_client",
            return_value=client,
        ):
            provider = FinnhubProvider(api_key="test-key")
            articles = await provider.fetch_stock_news("AAPL", date(2024, 3, 1))

        assert all(a.dedupe_hash for a in articles)

    @pytest.mark.asyncio
    async def test_returns_empty_when_api_key_not_set(self) -> None:
        """No HTTP call is made and empty list returned when api_key is falsy."""
        with patch("backend.services.news.finnhub_provider.settings") as mock_settings:
            mock_settings.FINNHUB_API_KEY = ""
            provider = FinnhubProvider(api_key="")
            articles = await provider.fetch_stock_news("AAPL", date(2024, 3, 1))

        assert articles == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_http_error(self) -> None:
        """HTTP errors are swallowed and empty list returned."""
        resp = _mock_response(status_code=500)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.finnhub_provider.get_http_client",
            return_value=client,
        ):
            provider = FinnhubProvider(api_key="test-key")
            articles = await provider.fetch_stock_news("AAPL", date(2024, 3, 1))

        assert articles == []

    @pytest.mark.asyncio
    async def test_category_mapped_to_event_type(self) -> None:
        """'company news' category maps to 'general' event_type."""
        fixture = json.loads(_load_fixture("finnhub_aapl.json"))
        # All fixture articles have category 'company news'
        resp = _mock_response(json_data=fixture)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.finnhub_provider.get_http_client",
            return_value=client,
        ):
            provider = FinnhubProvider(api_key="test-key")
            articles = await provider.fetch_stock_news("AAPL", date(2024, 3, 1))

        assert all(a.event_type == "general" for a in articles)

    @pytest.mark.asyncio
    async def test_first_article_headline_matches_fixture(self) -> None:
        """First article headline matches the first fixture item."""
        fixture = json.loads(_load_fixture("finnhub_aapl.json"))
        resp = _mock_response(json_data=fixture)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.finnhub_provider.get_http_client",
            return_value=client,
        ):
            provider = FinnhubProvider(api_key="test-key")
            articles = await provider.fetch_stock_news("AAPL", date(2024, 3, 1))

        assert articles[0].headline == "Apple Reports Record Q1 Revenue of $119.6B"

    @pytest.mark.asyncio
    async def test_null_summary_handled_gracefully(self) -> None:
        """Article with null summary produces RawArticle with summary=None."""
        fixture = json.loads(_load_fixture("finnhub_aapl.json"))
        # Third item has "summary": null
        resp = _mock_response(json_data=fixture)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.finnhub_provider.get_http_client",
            return_value=client,
        ):
            provider = FinnhubProvider(api_key="test-key")
            articles = await provider.fetch_stock_news("AAPL", date(2024, 3, 1))

        assert articles[2].summary is None

    @pytest.mark.asyncio
    async def test_fetch_macro_news_returns_empty_without_key(self) -> None:
        """fetch_macro_news returns [] when no API key is configured."""
        with patch("backend.services.news.finnhub_provider.settings") as mock_settings:
            mock_settings.FINNHUB_API_KEY = ""
            provider = FinnhubProvider(api_key="")
            articles = await provider.fetch_macro_news(date(2024, 3, 1))

        assert articles == []


# ===========================================================================
# TestEdgarProvider
# ===========================================================================


class TestEdgarProvider:
    """Tests for EdgarProvider."""

    @pytest.mark.asyncio
    async def test_parses_fixture_into_raw_articles(self) -> None:
        """Provider returns one RawArticle per EDGAR hit in the fixture."""
        fixture = json.loads(_load_fixture("edgar_8k_sample.json"))
        resp = _mock_response(json_data=fixture)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.edgar_provider.get_http_client",
            return_value=client,
        ):
            provider = EdgarProvider(user_agent="TestAgent/1.0 test@example.com")
            articles = await provider.fetch_stock_news("AAPL", date(2024, 3, 1))

        assert len(articles) == 2

    @pytest.mark.asyncio
    async def test_item_2_02_classified_as_earnings(self) -> None:
        """8-K with items '2.02,9.01' is classified as 'earnings'."""
        fixture = json.loads(_load_fixture("edgar_8k_sample.json"))
        resp = _mock_response(json_data=fixture)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.edgar_provider.get_http_client",
            return_value=client,
        ):
            provider = EdgarProvider(user_agent="TestAgent/1.0 test@example.com")
            articles = await provider.fetch_stock_news("AAPL", date(2024, 3, 1))

        # First filing has items "2.02,9.01" → earnings
        assert articles[0].event_type == "earnings"

    @pytest.mark.asyncio
    async def test_item_5_02_classified_as_management(self) -> None:
        """8-K with item '5.02' is classified as 'management'."""
        fixture = json.loads(_load_fixture("edgar_8k_sample.json"))
        resp = _mock_response(json_data=fixture)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.edgar_provider.get_http_client",
            return_value=client,
        ):
            provider = EdgarProvider(user_agent="TestAgent/1.0 test@example.com")
            articles = await provider.fetch_stock_news("AAPL", date(2024, 3, 1))

        # Second filing has items "5.02" → management
        assert articles[1].event_type == "management"

    @pytest.mark.asyncio
    async def test_fetch_macro_news_returns_empty(self) -> None:
        """EDGAR does not provide macro news — always returns []."""
        provider = EdgarProvider(user_agent="TestAgent/1.0 test@example.com")
        articles = await provider.fetch_macro_news(date(2024, 3, 1))
        assert articles == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_http_error(self) -> None:
        """HTTP errors are caught and empty list returned."""
        resp = _mock_response(status_code=503)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.edgar_provider.get_http_client",
            return_value=client,
        ):
            provider = EdgarProvider(user_agent="TestAgent/1.0 test@example.com")
            articles = await provider.fetch_stock_news("AAPL", date(2024, 3, 1))

        assert articles == []

    @pytest.mark.asyncio
    async def test_source_name_is_edgar(self) -> None:
        """source field is always 'edgar'."""
        fixture = json.loads(_load_fixture("edgar_8k_sample.json"))
        resp = _mock_response(json_data=fixture)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.edgar_provider.get_http_client",
            return_value=client,
        ):
            provider = EdgarProvider(user_agent="TestAgent/1.0 test@example.com")
            articles = await provider.fetch_stock_news("AAPL", date(2024, 3, 1))

        assert all(a.source == "edgar" for a in articles)

    @pytest.mark.asyncio
    async def test_ticker_uppercased_on_all_articles(self) -> None:
        """Ticker is uppercased in all returned articles."""
        fixture = json.loads(_load_fixture("edgar_8k_sample.json"))
        resp = _mock_response(json_data=fixture)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.edgar_provider.get_http_client",
            return_value=client,
        ):
            provider = EdgarProvider(user_agent="TestAgent/1.0 test@example.com")
            articles = await provider.fetch_stock_news("aapl", date(2024, 3, 1))

        assert all(a.ticker == "AAPL" for a in articles)


# ===========================================================================
# TestFedRssProvider
# ===========================================================================


@pytest.mark.skipif(not _FED_AVAILABLE, reason="fed_provider not yet implemented")
class TestFedRssProvider:
    """Tests for FedRssProvider."""

    @pytest.mark.asyncio
    async def test_parses_fixture_xml_into_raw_articles(self) -> None:
        """Provider returns one RawArticle per <item> in the fixture XML."""
        xml_data = _load_fixture("fed_rss_sample.xml")
        resp = _mock_response(text_data=xml_data)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.fed_provider.get_http_client",
            return_value=client,
        ):
            provider = FedRssProvider()
            articles = await provider.fetch_macro_news(date(2024, 3, 1))

        assert len(articles) == 3

    @pytest.mark.asyncio
    async def test_fomc_item_classified_as_fed_rate(self) -> None:
        """Item containing 'FOMC' in title maps to event_type 'fed_rate'."""
        xml_data = _load_fixture("fed_rss_sample.xml")
        resp = _mock_response(text_data=xml_data)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.fed_provider.get_http_client",
            return_value=client,
        ):
            provider = FedRssProvider()
            articles = await provider.fetch_macro_news(date(2024, 3, 1))

        fomc_articles = [
            a for a in articles if "fomc" in a.headline.lower() or a.event_type == "fed_rate"
        ]
        assert len(fomc_articles) >= 1
        assert fomc_articles[0].event_type == "fed_rate"

    @pytest.mark.asyncio
    async def test_employment_item_classified_correctly(self) -> None:
        """Item about employment data is classified as 'employment'."""
        xml_data = _load_fixture("fed_rss_sample.xml")
        resp = _mock_response(text_data=xml_data)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.fed_provider.get_http_client",
            return_value=client,
        ):
            provider = FedRssProvider()
            articles = await provider.fetch_macro_news(date(2024, 3, 1))

        employment_articles = [a for a in articles if a.event_type == "employment"]
        assert len(employment_articles) >= 1

    @pytest.mark.asyncio
    async def test_cpi_item_classified_correctly(self) -> None:
        """Item about CPI inflation is classified as 'cpi'."""
        xml_data = _load_fixture("fed_rss_sample.xml")
        resp = _mock_response(text_data=xml_data)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.fed_provider.get_http_client",
            return_value=client,
        ):
            provider = FedRssProvider()
            articles = await provider.fetch_macro_news(date(2024, 3, 1))

        cpi_articles = [a for a in articles if a.event_type == "cpi"]
        assert len(cpi_articles) >= 1

    @pytest.mark.asyncio
    async def test_filters_articles_before_since_date(self) -> None:
        """Articles published before the `since` date are excluded."""
        xml_data = _load_fixture("fed_rss_sample.xml")
        resp = _mock_response(text_data=xml_data)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.fed_provider.get_http_client",
            return_value=client,
        ):
            provider = FedRssProvider()
            # Use a future since date — all fixture articles should be filtered out
            articles = await provider.fetch_macro_news(date(2025, 1, 1))

        assert articles == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_http_error(self) -> None:
        """HTTP errors are caught and empty list returned."""
        resp = _mock_response(status_code=500)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.fed_provider.get_http_client",
            return_value=client,
        ):
            provider = FedRssProvider()
            articles = await provider.fetch_macro_news(date(2024, 3, 1))

        assert articles == []

    @pytest.mark.asyncio
    async def test_fetch_stock_news_returns_empty(self) -> None:
        """Fed RSS has no stock-specific news — always returns []."""
        provider = FedRssProvider()
        articles = await provider.fetch_stock_news("AAPL", date(2024, 3, 1))
        assert articles == []

    @pytest.mark.asyncio
    async def test_source_name_is_fed_rss(self) -> None:
        """source field is always 'fed_rss'."""
        xml_data = _load_fixture("fed_rss_sample.xml")
        resp = _mock_response(text_data=xml_data)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.fed_provider.get_http_client",
            return_value=client,
        ):
            provider = FedRssProvider()
            articles = await provider.fetch_macro_news(date(2024, 3, 1))

        assert all(a.source == "fed_rss" for a in articles)


# ===========================================================================
# TestGoogleNewsProvider
# ===========================================================================


@pytest.mark.skipif(not _GOOGLE_AVAILABLE, reason="google_provider not yet implemented")
class TestGoogleNewsProvider:
    """Tests for GoogleNewsProvider."""

    @pytest.mark.asyncio
    async def test_parses_rss_into_raw_articles(self) -> None:
        """Provider returns one RawArticle per <item> in the fixture XML."""
        xml_data = _load_fixture("google_rss_sample.xml")
        resp = _mock_response(text_data=xml_data)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.google_provider.get_http_client",
            return_value=client,
        ):
            provider = GoogleNewsProvider()
            articles = await provider.fetch_stock_news("AAPL", date(2024, 3, 1))

        assert len(articles) == 2

    @pytest.mark.asyncio
    async def test_ticker_set_for_stock_queries(self) -> None:
        """Ticker is set on all articles from a stock-specific query."""
        xml_data = _load_fixture("google_rss_sample.xml")
        resp = _mock_response(text_data=xml_data)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.google_provider.get_http_client",
            return_value=client,
        ):
            provider = GoogleNewsProvider()
            articles = await provider.fetch_stock_news("AAPL", date(2024, 3, 1))

        assert all(a.ticker == "AAPL" for a in articles)

    @pytest.mark.asyncio
    async def test_ticker_none_for_macro_queries(self) -> None:
        """Macro news articles have ticker=None."""
        xml_data = _load_fixture("google_rss_sample.xml")
        resp = _mock_response(text_data=xml_data)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.google_provider.get_http_client",
            return_value=client,
        ):
            provider = GoogleNewsProvider()
            articles = await provider.fetch_macro_news(date(2024, 3, 1))

        assert all(a.ticker is None for a in articles)

    @pytest.mark.asyncio
    async def test_returns_empty_on_http_error(self) -> None:
        """HTTP errors are caught and empty list returned."""
        resp = _mock_response(status_code=429)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.google_provider.get_http_client",
            return_value=client,
        ):
            provider = GoogleNewsProvider()
            articles = await provider.fetch_stock_news("AAPL", date(2024, 3, 1))

        assert articles == []

    @pytest.mark.asyncio
    async def test_source_name_is_google_news(self) -> None:
        """source field is always 'google_news'."""
        xml_data = _load_fixture("google_rss_sample.xml")
        resp = _mock_response(text_data=xml_data)
        client = _mock_client(resp)

        with patch(
            "backend.services.news.google_provider.get_http_client",
            return_value=client,
        ):
            provider = GoogleNewsProvider()
            articles = await provider.fetch_stock_news("AAPL", date(2024, 3, 1))

        assert all(a.source == "google_news" for a in articles)


# ===========================================================================
# TestClassifiers — pure function tests (no I/O)
# ===========================================================================


class TestClassify8kItems:
    """Tests for the _classify_8k_items helper in edgar_provider."""

    def test_earnings_takes_priority_over_other_items(self) -> None:
        """When both 2.02 (earnings) and 9.01 (other) present, returns 'earnings'."""
        result = _classify_8k_items("2.02,9.01")
        assert result == "earnings"

    def test_empty_string_returns_other(self) -> None:
        """Empty items string defaults to 'other'."""
        result = _classify_8k_items("")
        assert result == "other"

    def test_single_item_management(self) -> None:
        """Item 5.02 alone maps to 'management'."""
        result = _classify_8k_items("5.02")
        assert result == "management"

    def test_m_and_a_priority_over_governance(self) -> None:
        """m_and_a ranks above governance — 2.01 beats 5.07."""
        result = _classify_8k_items("2.01,5.07")
        assert result == "m_and_a"

    def test_unknown_item_number_returns_other(self) -> None:
        """Unrecognised item numbers fall through to 'other'."""
        result = _classify_8k_items("99.99")
        assert result == "other"

    def test_earnings_priority_over_m_and_a(self) -> None:
        """earnings rank higher than m_and_a: 2.02 > 2.01."""
        result = _classify_8k_items("2.01,2.02")
        assert result == "earnings"

    def test_whitespace_around_item_numbers_handled(self) -> None:
        """Items string with spaces around commas is parsed correctly."""
        result = _classify_8k_items("5.02 , 9.01")
        assert result == "management"


@pytest.mark.skipif(not _FED_AVAILABLE, reason="fed_provider not yet implemented")
class TestClassifyFedPress:
    """Tests for _classify_fed_press helper."""

    def test_fomc_title_returns_fed_rate(self) -> None:
        """Title containing 'FOMC' returns 'fed_rate'."""
        result = _classify_fed_press("Federal Reserve issues FOMC statement on rate decision")
        assert result == "fed_rate"

    def test_rate_keyword_returns_fed_rate(self) -> None:
        """Title mentioning 'rate' is classified as 'fed_rate'."""
        result = _classify_fed_press("Federal Reserve raises interest rate by 25 bps")
        assert result == "fed_rate"

    def test_unknown_title_returns_macro(self) -> None:
        """Title without known keywords falls back to 'macro'."""
        result = _classify_fed_press("Federal Reserve general announcement")
        assert result == "macro"

    def test_case_insensitive_matching(self) -> None:
        """Classification is case-insensitive."""
        result = _classify_fed_press("FOMC MEETING MINUTES RELEASED")
        assert result == "fed_rate"


@pytest.mark.skipif(not _FED_AVAILABLE, reason="fed_provider not yet implemented")
class TestClassifyFredRelease:
    """Tests for _classify_fred_release helper."""

    def test_cpi_title_returns_cpi(self) -> None:
        """Title containing 'CPI' returns 'cpi'."""
        result = _classify_fred_release("Annual CPI inflation update for February")
        assert result == "cpi"

    def test_inflation_title_returns_cpi(self) -> None:
        """Title mentioning 'inflation' maps to 'cpi'."""
        result = _classify_fred_release("Consumer price inflation rose 3.2 percent")
        assert result == "cpi"

    def test_employment_title_returns_employment(self) -> None:
        """Title mentioning 'employment' returns 'employment'."""
        result = _classify_fred_release("Nonfarm employment report February 2024")
        assert result == "employment"

    def test_gdp_title_returns_macro(self) -> None:
        """Title mentioning 'GDP' falls through to 'macro' (no dedicated GDP bucket)."""
        result = _classify_fred_release("GDP growth slows in Q4 2023")
        assert result == "macro"

    def test_unknown_title_returns_macro(self) -> None:
        """Unrecognised data release title falls back to 'macro'."""
        result = _classify_fred_release("Random economic indicator")
        assert result == "macro"
