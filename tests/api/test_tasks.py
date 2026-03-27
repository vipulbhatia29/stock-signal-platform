"""Tests for task status and refresh-all endpoints."""

from unittest.mock import MagicMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.conftest import StockFactory


class TestTaskStatus:
    """Tests for GET /api/v1/tasks/{task_id}/status."""

    async def test_task_status_pending(self, authenticated_client: AsyncClient) -> None:
        """GET /tasks/{task_id}/status returns PENDING for unknown task."""
        with patch("backend.routers.tasks.AsyncResult") as mock_result:
            mock_result.return_value.state = "PENDING"
            response = await authenticated_client.get("/api/v1/tasks/fake-task-id/status")
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "PENDING"
        assert data["task_id"] == "fake-task-id"

    async def test_task_status_success(self, authenticated_client: AsyncClient) -> None:
        """GET /tasks/{task_id}/status returns SUCCESS for completed task."""
        with patch("backend.routers.tasks.AsyncResult") as mock_result:
            mock_result.return_value.state = "SUCCESS"
            response = await authenticated_client.get("/api/v1/tasks/done-task-id/status")
        assert response.status_code == 200
        assert response.json()["state"] == "SUCCESS"

    async def test_task_status_requires_auth(self, client: AsyncClient) -> None:
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/tasks/fake-task-id/status")
        assert response.status_code == 401


class TestRefreshAll:
    """Tests for POST /api/v1/stocks/watchlist/refresh-all."""

    async def test_refresh_all_enqueues_tasks(
        self, authenticated_client: AsyncClient, db_url: str
    ) -> None:
        """POST /watchlist/refresh-all returns task_ids for each watchlist ticker."""
        engine = create_async_engine(db_url, echo=False)
        factory_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory_() as session:
            stock = StockFactory.build(ticker="RFRSH", name="Refresh Test")
            session.add(stock)
            await session.commit()
        await engine.dispose()

        await authenticated_client.post(
            "/api/v1/stocks/watchlist",
            json={"ticker": "RFRSH"},
        )

        with patch("backend.routers.stocks.watchlist.refresh_ticker_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="mock-task-123")
            response = await authenticated_client.post(
                "/api/v1/stocks/watchlist/refresh-all",
            )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(item["ticker"] == "RFRSH" for item in data)
        assert all("task_id" in item for item in data)
