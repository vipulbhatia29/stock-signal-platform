"""API tests for alerts endpoints — real DB via testcontainers."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from backend.models.alert import InAppAlert


async def _seed_alerts(db_url: str, user_id: uuid.UUID) -> list[str]:
    """Seed 3 alerts for the given user, return their IDs."""
    engine = create_async_engine(db_url, echo=False)
    alert_ids = []
    async with engine.begin() as conn:
        for i, (sev, title, ticker, is_read) in enumerate(
            [
                ("critical", "Stop-Loss Triggered", "TSLA", False),
                ("warning", "Score Downgrade", "AAPL", False),
                ("info", "New BUY Signal", "MSFT", True),
            ]
        ):
            alert_id = uuid.uuid4()
            alert_ids.append(str(alert_id))
            await conn.execute(
                InAppAlert.__table__.insert().values(
                    id=alert_id,
                    user_id=user_id,
                    alert_type="divestment" if sev == "critical" else "signal_change",
                    severity=sev,
                    title=title,
                    ticker=ticker,
                    dedup_key=f"test:{ticker}:{i}",
                    message=f"Test alert for {ticker}",
                    metadata={"route": f"/stocks/{ticker}"},
                    is_read=is_read,
                    created_at=datetime.now(timezone.utc) - timedelta(hours=i),
                )
            )
    await engine.dispose()
    return alert_ids


class TestGetAlerts:
    """Tests for GET /api/v1/alerts."""

    async def test_returns_new_fields(self, authenticated_client: AsyncClient, db_url: str) -> None:
        """Response includes severity, title, ticker."""
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        await _seed_alerts(db_url, user.id)

        resp = await authenticated_client.get("/api/v1/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        assert data["total"] == 3
        assert data["unread_count"] == 2

        first = data["alerts"][0]
        assert "severity" in first
        assert "title" in first
        assert "ticker" in first
        assert first["severity"] in ("critical", "warning", "info")

    async def test_pagination(self, authenticated_client: AsyncClient, db_url: str) -> None:
        """Limit and offset work correctly."""
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        await _seed_alerts(db_url, user.id)

        resp = await authenticated_client.get("/api/v1/alerts?limit=1&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["alerts"]) == 1
        assert data["total"] == 3

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated request returns 401."""
        resp = await client.get("/api/v1/alerts")
        assert resp.status_code == 401


class TestMarkAlertsRead:
    """Tests for PATCH /api/v1/alerts/read."""

    async def test_marks_alerts_read(self, authenticated_client: AsyncClient, db_url: str) -> None:
        """Marking alerts as read returns updated count."""
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        alert_ids = await _seed_alerts(db_url, user.id)

        resp = await authenticated_client.patch(
            "/api/v1/alerts/read",
            json={"alert_ids": [alert_ids[0]]},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 1

    async def test_idor_protection(self, authenticated_client: AsyncClient) -> None:
        """Cannot mark non-existent alert IDs as read (returns 0 updated)."""
        fake_id = str(uuid.uuid4())
        resp = await authenticated_client.patch(
            "/api/v1/alerts/read",
            json={"alert_ids": [fake_id]},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 0


class TestUnreadCount:
    """Tests for GET /api/v1/alerts/unread-count."""

    async def test_returns_count(self, authenticated_client: AsyncClient, db_url: str) -> None:
        """Unread count matches seeded data."""
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        await _seed_alerts(db_url, user.id)

        resp = await authenticated_client.get("/api/v1/alerts/unread-count")
        assert resp.status_code == 200
        assert resp.json()["unread_count"] == 2
