"""Tests for ObservedHttpClient integration into all external providers.

Verifies that each provider passes an ObservedHttpClient (or equivalent) to
the underlying SDK / HTTP call, so every outbound API call is instrumented.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from backend.observability.instrumentation.external_api import ObservedHttpClient
from backend.observability.instrumentation.providers import ExternalProvider

# ─────────────────────────────────────────────────────────────────────────────
# LLM providers
# ─────────────────────────────────────────────────────────────────────────────


class TestOpenAIUsesObservedClient:
    """OpenAI provider passes ObservedHttpClient to AsyncOpenAI."""

    @pytest.mark.asyncio
    async def test_openai_uses_observed_client(self) -> None:
        """AsyncOpenAI must receive an ObservedHttpClient as http_client= kwarg."""
        captured: dict[str, Any] = {}

        def fake_openai(**kwargs: Any) -> MagicMock:
            captured.update(kwargs)
            mock = MagicMock()
            mock.chat.completions.create = MagicMock(return_value=_fake_openai_response())
            return mock

        with patch("openai.AsyncOpenAI", side_effect=fake_openai):
            from backend.agents.providers.openai import OpenAIProvider

            provider = OpenAIProvider(api_key="test-key")
            try:
                await provider.chat(
                    messages=[{"role": "user", "content": "hi"}],
                    tools=[],
                )
            except Exception:
                # We only care that AsyncOpenAI was called with the right kwarg.
                pass

        assert "http_client" in captured, "http_client kwarg not passed to AsyncOpenAI"
        assert isinstance(captured["http_client"], ObservedHttpClient), (
            f"Expected ObservedHttpClient, got {type(captured['http_client'])}"
        )
        assert captured["http_client"]._provider == ExternalProvider.OPENAI


class TestAnthropicUsesObservedClient:
    """Anthropic provider passes ObservedHttpClient to AsyncAnthropic."""

    @pytest.mark.asyncio
    async def test_anthropic_uses_observed_client(self) -> None:
        """AsyncAnthropic must receive an ObservedHttpClient as http_client= kwarg."""
        captured: dict[str, Any] = {}

        class FakeAnthropic:
            def __init__(self, **kwargs: Any) -> None:
                captured.update(kwargs)
                self.messages = MagicMock()
                self.messages.create = MagicMock(return_value=_fake_anthropic_response())

        import anthropic

        with patch.object(anthropic, "AsyncAnthropic", FakeAnthropic):
            from backend.agents.providers.anthropic import AnthropicProvider

            provider = AnthropicProvider(api_key="test-key")
            try:
                await provider.chat(
                    messages=[{"role": "user", "content": "hi"}],
                    tools=[],
                )
            except Exception:
                pass

        assert "http_client" in captured, "http_client kwarg not passed to AsyncAnthropic"
        assert isinstance(captured["http_client"], ObservedHttpClient), (
            f"Expected ObservedHttpClient, got {type(captured['http_client'])}"
        )
        assert captured["http_client"]._provider == ExternalProvider.ANTHROPIC


class TestGroqUsesObservedClient:
    """Groq provider passes ObservedHttpClient to AsyncGroq."""

    @pytest.mark.asyncio
    async def test_groq_uses_observed_client(self) -> None:
        """AsyncGroq must receive an ObservedHttpClient as http_client= kwarg."""
        captured: dict[str, Any] = {}

        class FakeGroq:
            def __init__(self, **kwargs: Any) -> None:
                captured.update(kwargs)
                self.chat = MagicMock()
                self.chat.completions = MagicMock()
                self.chat.completions.create = MagicMock(return_value=_fake_groq_response())

        with patch("groq.AsyncGroq", FakeGroq):
            from backend.agents.providers.groq import GroqProvider

            provider = GroqProvider(api_key="test-key")
            try:
                await provider.chat(
                    messages=[{"role": "user", "content": "hi"}],
                    tools=[],
                )
            except Exception:
                pass

        assert "http_client" in captured, "http_client kwarg not passed to AsyncGroq"
        assert isinstance(captured["http_client"], ObservedHttpClient), (
            f"Expected ObservedHttpClient, got {type(captured['http_client'])}"
        )
        assert captured["http_client"]._provider == ExternalProvider.GROQ


# ─────────────────────────────────────────────────────────────────────────────
# News providers
# ─────────────────────────────────────────────────────────────────────────────


class TestFinnhubUsesObservedClient:
    """FinnhubProvider passes ExternalProvider.FINNHUB to get_observed_http_client."""

    @pytest.mark.asyncio
    async def test_finnhub_uses_observed_client(self) -> None:
        """get_observed_http_client must be called with ExternalProvider.FINNHUB."""
        captured_providers: list[ExternalProvider] = []

        def fake_get_observed(provider: ExternalProvider, **kwargs: Any) -> MagicMock:
            captured_providers.append(provider)
            mock = MagicMock()
            mock.get = (MagicMock(return_value=_async_mock_response([])),)
            # Return a coroutine-compatible mock for await client.get(...)

            async def fake_get(*a: Any, **kw: Any) -> MagicMock:
                resp = MagicMock()
                resp.raise_for_status = MagicMock()
                resp.json.return_value = []
                return resp

            mock.get = fake_get
            return mock

        with patch(
            "backend.services.news.finnhub_provider.get_observed_http_client",
            side_effect=fake_get_observed,
        ):
            from datetime import date

            from backend.services.news.finnhub_provider import FinnhubProvider

            provider = FinnhubProvider(api_key="test-key")
            await provider.fetch_stock_news("AAPL", date(2026, 1, 1))

        assert len(captured_providers) >= 1, "get_observed_http_client was not called"
        assert ExternalProvider.FINNHUB in captured_providers


class TestEdgarUsesObservedClient:
    """EdgarProvider passes ExternalProvider.EDGAR to get_observed_http_client."""

    @pytest.mark.asyncio
    async def test_edgar_uses_observed_client(self) -> None:
        """get_observed_http_client must be called with ExternalProvider.EDGAR."""
        captured_providers: list[ExternalProvider] = []

        async def fake_get(*a: Any, **kw: Any) -> MagicMock:
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"hits": {"hits": []}}
            return resp

        def fake_get_observed(provider: ExternalProvider, **kwargs: Any) -> MagicMock:
            captured_providers.append(provider)
            mock = MagicMock()
            mock.get = fake_get
            return mock

        with patch(
            "backend.services.news.edgar_provider.get_observed_http_client",
            side_effect=fake_get_observed,
        ):
            from datetime import date

            from backend.services.news.edgar_provider import EdgarProvider

            provider = EdgarProvider(user_agent="test@example.com")
            await provider.fetch_stock_news("AAPL", date(2026, 1, 1))

        assert ExternalProvider.EDGAR in captured_providers


# ─────────────────────────────────────────────────────────────────────────────
# YfinanceObservedSession
# ─────────────────────────────────────────────────────────────────────────────


class TestYfinanceSessionEmitsEvent:
    """YfinanceObservedSession emits an EXTERNAL_API_CALL event on each request."""

    def test_yfinance_session_emits_on_success(self) -> None:
        """Successful request emits event with provider=YFINANCE and no error_reason."""
        from backend.observability.instrumentation.yfinance_session import YfinanceObservedSession
        from backend.observability.schema.external_api_events import ExternalApiCallEvent

        emitted: list[ExternalApiCallEvent] = []

        mock_client = MagicMock()
        mock_client.emit_sync = lambda event: emitted.append(event)

        mock_response = MagicMock()
        mock_response.status_code = 200

        session = YfinanceObservedSession()
        with (
            patch(
                "backend.observability.instrumentation.yfinance_session._maybe_get_obs_client",
                return_value=mock_client,
            ),
            patch.object(
                session.__class__.__bases__[0],
                "request",
                return_value=mock_response,
            ),
        ):
            result = session.request(
                "GET", "https://finance.yahoo.com/v1/finance/quoteSummary/AAPL"
            )

        assert result is mock_response
        assert len(emitted) == 1
        event = emitted[0]
        assert event.provider == ExternalProvider.YFINANCE.value
        assert event.method == "GET"
        assert event.error_reason is None

    def test_yfinance_session_emits_on_timeout(self) -> None:
        """Timeout exception emits event with error_reason=timeout and re-raises."""
        import requests

        from backend.observability.instrumentation.yfinance_session import YfinanceObservedSession
        from backend.observability.schema.external_api_events import ExternalApiCallEvent

        emitted: list[ExternalApiCallEvent] = []

        mock_client = MagicMock()
        mock_client.emit_sync = lambda event: emitted.append(event)

        session = YfinanceObservedSession()
        with (
            patch(
                "backend.observability.instrumentation.yfinance_session._maybe_get_obs_client",
                return_value=mock_client,
            ),
            patch.object(
                session.__class__.__bases__[0],
                "request",
                side_effect=requests.Timeout("timeout"),
            ),
        ):
            with pytest.raises(requests.Timeout):
                session.request("GET", "https://finance.yahoo.com/v1/whatever")

        assert len(emitted) == 1
        assert emitted[0].error_reason == "timeout"

    def test_yfinance_session_silent_when_no_obs_client(self) -> None:
        """When no obs client is set, request succeeds silently (no emission attempt fails)."""
        from backend.observability.instrumentation.yfinance_session import YfinanceObservedSession

        mock_response = MagicMock()
        mock_response.status_code = 200

        session = YfinanceObservedSession()
        with (
            patch(
                "backend.observability.instrumentation.yfinance_session._maybe_get_obs_client",
                return_value=None,
            ),
            patch.object(
                session.__class__.__bases__[0],
                "request",
                return_value=mock_response,
            ),
        ):
            result = session.request(
                "GET", "https://finance.yahoo.com/v1/finance/quoteSummary/AAPL"
            )

        assert result is mock_response  # no exception, clean return


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — fake SDK response objects
# ─────────────────────────────────────────────────────────────────────────────


def _fake_openai_response() -> MagicMock:
    """Return a minimal fake OpenAI chat completion response object."""
    msg = MagicMock()
    msg.content = "hello"
    msg.tool_calls = None
    choice = MagicMock()
    choice.message = msg
    usage = MagicMock()
    usage.prompt_tokens = 10
    usage.completion_tokens = 5
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


def _fake_anthropic_response() -> MagicMock:
    """Return a minimal fake Anthropic messages response object."""
    block = MagicMock()
    block.type = "text"
    block.text = "hello"
    usage = MagicMock()
    usage.input_tokens = 10
    usage.output_tokens = 5
    resp = MagicMock()
    resp.content = [block]
    resp.usage = usage
    return resp


def _fake_groq_response() -> MagicMock:
    """Return a minimal fake Groq chat completion response object."""
    msg = MagicMock()
    msg.content = "hello"
    msg.tool_calls = None
    choice = MagicMock()
    choice.message = msg
    usage = MagicMock()
    usage.prompt_tokens = 10
    usage.completion_tokens = 5
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


def _async_mock_response(data: Any) -> Any:
    """Placeholder — not used directly (replaced by async fake_get)."""
    return data
