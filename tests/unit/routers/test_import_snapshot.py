"""Tests for import-snapshot endpoint validation logic.

Tests the pre-processing validation (content type, size, format)
by calling the endpoint handler's inner logic directly. Full HTTP-level
tests live in tests/api/ where Redis and Postgres are available.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile, status

from backend.schemas.attribution import ImportResult


def _make_mock_request() -> MagicMock:
    """Create a mock request with minimal Starlette API.

    We need `request.app.state.cache` for the endpoint logic and
    the rate limiter needs request.scope, request.url, etc.
    """
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/portfolio/import-snapshot",
        "query_string": b"",
        "headers": [(b"x-forwarded-for", b"127.0.0.1")],
        "server": ("localhost", 8181),
        "root_path": "",
        "state": {},
    }
    request = Request(scope)
    # Inject app state for cache
    app_mock = MagicMock()
    app_mock.state.cache = None
    request._app = app_mock  # noqa: SLF001
    scope["app"] = app_mock
    # slowapi writes view_rate_limit to request.state after check
    request.state.view_rate_limit = None
    return request


@pytest.fixture(autouse=True)
def _disable_rate_limiter():
    """Disable the slowapi rate limiter for unit tests."""
    with patch("backend.rate_limit.limiter._check_request_limit", new_callable=AsyncMock):
        yield


class TestImportSnapshotValidation:
    """Tests for import-snapshot endpoint validation logic."""

    @pytest.mark.anyio
    async def test_rejects_non_csv_content_type(self) -> None:
        """Non-CSV content type raises 400."""
        from backend.routers.portfolio import import_snapshot

        mock_file = MagicMock(spec=UploadFile)
        mock_file.content_type = "application/json"
        mock_file.read = AsyncMock(return_value=b"{}")

        mock_user = MagicMock()
        mock_user.email_verified = True
        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await import_snapshot(
                request=_make_mock_request(),
                file=mock_file,
                current_user=mock_user,
                db=mock_db,
            )
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "CSV" in exc_info.value.detail

    @pytest.mark.anyio
    async def test_rejects_oversized_file(self) -> None:
        """Files > 512KB raise 400."""
        from backend.routers.portfolio import import_snapshot

        mock_file = MagicMock(spec=UploadFile)
        mock_file.content_type = "text/csv"
        mock_file.read = AsyncMock(return_value=b"x" * (512 * 1024 + 1))

        mock_user = MagicMock()
        mock_user.email_verified = True
        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await import_snapshot(
                request=_make_mock_request(),
                file=mock_file,
                current_user=mock_user,
                db=mock_db,
            )
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "512KB" in exc_info.value.detail

    @pytest.mark.anyio
    async def test_rejects_invalid_csv_format(self) -> None:
        """CSV with no recognizable header raises 422."""
        from backend.routers.portfolio import import_snapshot

        mock_file = MagicMock(spec=UploadFile)
        mock_file.content_type = "text/csv"
        mock_file.read = AsyncMock(
            return_value=b"just some random text\nwith no recognizable columns\n"
        )

        mock_user = MagicMock()
        mock_user.email_verified = True
        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await import_snapshot(
                request=_make_mock_request(),
                file=mock_file,
                current_user=mock_user,
                db=mock_db,
            )
        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.anyio
    @patch("backend.routers.portfolio.import_portfolio_snapshot")
    @patch("backend.routers.portfolio.get_or_create_portfolio")
    async def test_successful_import_returns_result(
        self,
        mock_get_portfolio,
        mock_import,
    ) -> None:
        """Valid CSV with mocked services returns ImportResult."""
        from backend.routers.portfolio import import_snapshot

        valid_csv = (
            '"Symbol","Description","Qty (Quantity)","Price",'
            '"Cost Basis","Mkt Val (Market Value)","Asset Type"\n'
            '"AAPL","APPLE INC","10.0","270.84","$2,708.40","$2,708.40","Equity"\n'
        )

        mock_file = MagicMock(spec=UploadFile)
        mock_file.content_type = "text/csv"
        mock_file.read = AsyncMock(return_value=valid_csv.encode())

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.email_verified = True
        mock_db = AsyncMock()

        mock_get_portfolio.return_value = MagicMock(id=uuid.uuid4())
        mock_import.return_value = ImportResult(imported=1, changes_detected=0, is_baseline=True)

        result = await import_snapshot(
            request=_make_mock_request(),
            file=mock_file,
            current_user=mock_user,
            db=mock_db,
        )
        assert result.imported == 1
        assert result.is_baseline is True

    @pytest.mark.anyio
    @patch("backend.routers.portfolio.import_portfolio_snapshot")
    @patch("backend.routers.portfolio.get_or_create_portfolio")
    async def test_duplicate_csv_raises_409(
        self,
        mock_get_portfolio,
        mock_import,
    ) -> None:
        """Same CSV uploaded twice raises 409 Conflict."""
        from backend.routers.portfolio import import_snapshot

        valid_csv = (
            '"Symbol","Description","Qty (Quantity)","Price",'
            '"Cost Basis","Mkt Val (Market Value)","Asset Type"\n'
            '"AAPL","APPLE INC","10.0","270.84","$2,708.40","$2,708.40","Equity"\n'
        )

        mock_file = MagicMock(spec=UploadFile)
        mock_file.content_type = "text/csv"
        mock_file.read = AsyncMock(return_value=valid_csv.encode())

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.email_verified = True
        mock_db = AsyncMock()

        mock_get_portfolio.return_value = MagicMock(id=uuid.uuid4())
        mock_import.return_value = ImportResult(imported=0, is_duplicate=True)

        with pytest.raises(HTTPException) as exc_info:
            await import_snapshot(
                request=_make_mock_request(),
                file=mock_file,
                current_user=mock_user,
                db=mock_db,
            )
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.anyio
    async def test_non_utf8_file_raises_400(self) -> None:
        """Non-UTF8 encoded file raises 400."""
        from backend.routers.portfolio import import_snapshot

        mock_file = MagicMock(spec=UploadFile)
        mock_file.content_type = "text/csv"
        mock_file.read = AsyncMock(return_value=b"\x80\x81\x82\x83" * 100)

        mock_user = MagicMock()
        mock_user.email_verified = True
        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await import_snapshot(
                request=_make_mock_request(),
                file=mock_file,
                current_user=mock_user,
                db=mock_db,
            )
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "UTF-8" in exc_info.value.detail
