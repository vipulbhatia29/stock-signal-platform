"""POST events to ``/obs/v1/events`` on the same app (or future external host)."""

from __future__ import annotations

import httpx

from backend.observability.schema.v1 import ObsEventBase
from backend.observability.targets.base import BatchResult, TargetHealth


class InternalHTTPTarget:
    """HTTP target that sends batches to the ingest endpoint.

    Used in integration tests and as the transition path during microservice
    extraction — the only change at extraction time is swapping
    ``OBS_TARGET_URL`` to the external service host.
    """

    def __init__(
        self,
        base_url: str,
        secret: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = base_url.rstrip("/") + "/obs/v1/events"
        self._secret = secret
        self._client = client or httpx.AsyncClient(timeout=5.0)
        self.last_error: str | None = None

    async def send_batch(self, events: list[ObsEventBase]) -> BatchResult:
        """POST a batch to the ingest endpoint, returning sent/failed counts."""
        payload = {
            "events": [e.model_dump(mode="json") for e in events],
            "schema_version": "v1",
        }
        try:
            resp = await self._client.post(
                self._url, json=payload, headers={"X-Obs-Secret": self._secret}
            )
        except httpx.HTTPError as exc:
            self.last_error = type(exc).__name__
            return BatchResult(sent=0, failed=len(events), error=self.last_error)
        if resp.status_code == 202:
            self.last_error = None
            return BatchResult(sent=len(events), failed=0)
        self.last_error = f"status_{resp.status_code}"
        return BatchResult(sent=0, failed=len(events), error=self.last_error)

    async def health(self) -> TargetHealth:
        """Report health based on last batch result."""
        return TargetHealth(healthy=self.last_error is None, last_error=self.last_error)
