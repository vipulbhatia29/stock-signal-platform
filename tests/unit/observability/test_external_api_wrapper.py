"""Unit tests for ObservedHttpClient + ExternalApiCallEvent emission.

Each test constructs a test-scoped ObservabilityClient backed by MemoryTarget,
monkeypatches ``_maybe_get_obs_client`` in the ``external_api`` module, and
verifies that the correct event fields are emitted (or that emission failures
are silently swallowed).

Transport is provided via ``httpx.MockTransport`` so no real network is needed.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from backend.observability.client import ObservabilityClient
from backend.observability.instrumentation.external_api import ObservedHttpClient
from backend.observability.instrumentation.providers import ExternalProvider
from backend.observability.schema.external_api_events import ExternalApiCallEvent
from backend.observability.targets.memory import MemoryTarget

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_obs_client(tmp_path: Path) -> ObservabilityClient:
    """Create a lightweight ObservabilityClient backed by MemoryTarget.

    Args:
        tmp_path: Temporary directory for spool (disabled but required by API).

    Returns:
        A fully configured ObservabilityClient with MemoryTarget.
    """
    target = MemoryTarget()
    return ObservabilityClient(
        target=target,
        spool_dir=tmp_path,
        spool_enabled=False,
        flush_interval_ms=50,
        buffer_size=100,
        enabled=True,
    )


def _mock_transport(status: int = 200, body: bytes = b"ok") -> httpx.MockTransport:
    """Build an httpx.MockTransport that always returns the given status and body.

    Args:
        status: HTTP status code to return.
        body: Response body bytes.

    Returns:
        An httpx.MockTransport handler.
    """

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body)

    return httpx.MockTransport(_handler)


def _mock_transport_with_rl_headers(
    status: int = 200,
    rl_remaining: str = "42",
    rl_reset: str = "1700000000",
) -> httpx.MockTransport:
    """Build a MockTransport that includes X-RateLimit-* headers.

    Args:
        status: HTTP status code.
        rl_remaining: Value for X-RateLimit-Remaining header.
        rl_reset: Value for X-RateLimit-Reset header (Unix epoch string).

    Returns:
        An httpx.MockTransport handler.
    """

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            content=b"{}",
            headers={
                "X-RateLimit-Remaining": rl_remaining,
                "X-RateLimit-Reset": rl_reset,
            },
        )

    return httpx.MockTransport(_handler)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def obs_and_target(tmp_path: Path):
    """Provide a started ObservabilityClient + its MemoryTarget.

    Yields:
        Tuple of (ObservabilityClient, MemoryTarget).
    """
    target = MemoryTarget()
    client = ObservabilityClient(
        target=target,
        spool_dir=tmp_path,
        spool_enabled=False,
        flush_interval_ms=50,
        buffer_size=100,
        enabled=True,
    )
    await client.start()
    yield client, target
    await client.stop()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_observed_http_client_emits_event_on_success(obs_and_target, monkeypatch) -> None:
    """A 200 response triggers exactly one EXTERNAL_API_CALL event with correct fields."""
    obs_client, target = obs_and_target
    monkeypatch.setattr(
        "backend.observability.instrumentation.external_api._maybe_get_obs_client",
        lambda: obs_client,
    )

    transport = _mock_transport(status=200, body=b"hello")
    async with ObservedHttpClient(provider=ExternalProvider.FINNHUB, transport=transport) as client:
        response = await client.get("https://finnhub.io/api/v1/quote?symbol=AAPL")

    assert response.status_code == 200
    await obs_client.flush()
    assert len(target.events) == 1

    event = target.events[0]
    assert isinstance(event, ExternalApiCallEvent)
    assert event.provider == "finnhub"
    assert event.endpoint == "/api/v1/quote"
    assert event.method == "GET"
    assert event.status_code == 200
    assert event.error_reason is None
    assert event.latency_ms >= 0
    assert event.retry_count == 0


@pytest.mark.asyncio
async def test_observed_http_client_classifies_429(obs_and_target, monkeypatch) -> None:
    """A 429 response sets error_reason to 'rate_limit_429'."""
    obs_client, target = obs_and_target
    monkeypatch.setattr(
        "backend.observability.instrumentation.external_api._maybe_get_obs_client",
        lambda: obs_client,
    )

    transport = _mock_transport(status=429)
    async with ObservedHttpClient(provider=ExternalProvider.OPENAI, transport=transport) as client:
        response = await client.post("https://api.openai.com/v1/chat/completions", content=b"{}")

    assert response.status_code == 429
    await obs_client.flush()
    assert len(target.events) == 1

    event = target.events[0]
    assert isinstance(event, ExternalApiCallEvent)
    assert event.error_reason == "rate_limit_429"
    assert event.status_code == 429


@pytest.mark.asyncio
async def test_observed_http_client_classifies_5xx(obs_and_target, monkeypatch) -> None:
    """A 500 response sets error_reason to 'server_error_5xx'."""
    obs_client, target = obs_and_target
    monkeypatch.setattr(
        "backend.observability.instrumentation.external_api._maybe_get_obs_client",
        lambda: obs_client,
    )

    transport = _mock_transport(status=500)
    async with ObservedHttpClient(
        provider=ExternalProvider.ANTHROPIC, transport=transport
    ) as client:
        response = await client.post("https://api.anthropic.com/v1/messages", content=b"{}")

    assert response.status_code == 500
    await obs_client.flush()
    assert len(target.events) == 1

    event = target.events[0]
    assert isinstance(event, ExternalApiCallEvent)
    assert event.error_reason == "server_error_5xx"


@pytest.mark.asyncio
async def test_observed_http_client_classifies_timeout(obs_and_target, monkeypatch) -> None:
    """An httpx.TimeoutException is classified as 'timeout' and re-raised."""
    obs_client, target = obs_and_target
    monkeypatch.setattr(
        "backend.observability.instrumentation.external_api._maybe_get_obs_client",
        lambda: obs_client,
    )

    def _timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    transport = httpx.MockTransport(_timeout_handler)

    with pytest.raises(httpx.ReadTimeout):
        async with ObservedHttpClient(
            provider=ExternalProvider.FRED, transport=transport
        ) as client:
            await client.get("https://api.stlouisfed.org/fred/series")

    await obs_client.flush()
    assert len(target.events) == 1

    event = target.events[0]
    assert isinstance(event, ExternalApiCallEvent)
    assert event.error_reason == "timeout"
    assert event.status_code is None


@pytest.mark.asyncio
async def test_observed_http_client_classifies_connection_error(
    obs_and_target, monkeypatch
) -> None:
    """An httpx.ConnectError is classified as 'connection_refused' and re-raised."""
    obs_client, target = obs_and_target
    monkeypatch.setattr(
        "backend.observability.instrumentation.external_api._maybe_get_obs_client",
        lambda: obs_client,
    )

    def _connect_error_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    transport = httpx.MockTransport(_connect_error_handler)

    with pytest.raises(httpx.ConnectError):
        async with ObservedHttpClient(
            provider=ExternalProvider.EDGAR, transport=transport
        ) as client:
            await client.get("https://data.sec.gov/submissions/CIK001.json")

    await obs_client.flush()
    assert len(target.events) == 1

    event = target.events[0]
    assert isinstance(event, ExternalApiCallEvent)
    assert event.error_reason == "connection_refused"
    assert event.status_code is None


@pytest.mark.asyncio
async def test_emission_failure_does_not_mask_http_error(obs_and_target, monkeypatch) -> None:
    """When emit_sync raises, the original HTTP response is still returned correctly."""
    obs_client, target = obs_and_target

    def _exploding_emit_sync(event: object) -> None:
        raise RuntimeError("emission kaboom")

    monkeypatch.setattr(
        "backend.observability.instrumentation.external_api._maybe_get_obs_client",
        lambda: obs_client,
    )
    monkeypatch.setattr(obs_client, "emit_sync", _exploding_emit_sync)

    transport = _mock_transport(status=200, body=b"safe")
    async with ObservedHttpClient(provider=ExternalProvider.GROQ, transport=transport) as client:
        # Must NOT raise despite broken emit_sync
        response = await client.get("https://api.groq.com/openai/v1/models")

    assert response.status_code == 200
    assert response.content == b"safe"


@pytest.mark.asyncio
async def test_endpoint_strips_query_params(obs_and_target, monkeypatch) -> None:
    """The emitted endpoint field must contain only the URL path, not query params."""
    obs_client, target = obs_and_target
    monkeypatch.setattr(
        "backend.observability.instrumentation.external_api._maybe_get_obs_client",
        lambda: obs_client,
    )

    transport = _mock_transport(status=200)
    async with ObservedHttpClient(
        provider=ExternalProvider.YFINANCE, transport=transport
    ) as client:
        await client.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?interval=1d&range=1mo"
        )

    await obs_client.flush()
    assert len(target.events) == 1

    event = target.events[0]
    assert isinstance(event, ExternalApiCallEvent)
    # endpoint must NOT contain query string
    assert "?" not in event.endpoint
    assert "interval" not in event.endpoint
    assert event.endpoint == "/v8/finance/chart/AAPL"


@pytest.mark.asyncio
async def test_rate_limit_headers_parsed(obs_and_target, monkeypatch) -> None:
    """X-RateLimit-Remaining and X-RateLimit-Reset are parsed into event fields."""
    obs_client, target = obs_and_target
    monkeypatch.setattr(
        "backend.observability.instrumentation.external_api._maybe_get_obs_client",
        lambda: obs_client,
    )

    transport = _mock_transport_with_rl_headers(
        status=200, rl_remaining="15", rl_reset="1700000000"
    )
    async with ObservedHttpClient(provider=ExternalProvider.OPENAI, transport=transport) as client:
        await client.post("https://api.openai.com/v1/embeddings", content=b"{}")

    await obs_client.flush()
    assert len(target.events) == 1

    event = target.events[0]
    assert isinstance(event, ExternalApiCallEvent)
    assert event.rate_limit_remaining == 15
    assert event.rate_limit_reset_ts is not None
    assert event.rate_limit_reset_ts.tzinfo is not None
    assert event.rate_limit_headers is not None
    assert "x-ratelimit-remaining" in event.rate_limit_headers


@pytest.mark.asyncio
async def test_no_obs_client_does_not_raise(monkeypatch) -> None:
    """When _maybe_get_obs_client returns None, the HTTP call proceeds without error."""
    monkeypatch.setattr(
        "backend.observability.instrumentation.external_api._maybe_get_obs_client",
        lambda: None,
    )

    transport = _mock_transport(status=200, body=b"ok")
    async with ObservedHttpClient(provider=ExternalProvider.RESEND, transport=transport) as client:
        response = await client.post("https://api.resend.com/emails", content=b"{}")

    assert response.status_code == 200
