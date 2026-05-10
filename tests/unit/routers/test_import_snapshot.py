"""Tests for POST /portfolio/import-snapshot endpoint."""

from __future__ import annotations

import io
import uuid
from unittest.mock import AsyncMock, patch

from fastapi import status

VALID_CSV_BYTES = (
    b'"Positions for account Designated Bene Individual as of 02:41 AM ET, 2026/04/30"\n'
    b"\n"
    b'"Symbol","Description","Qty (Quantity)","Price","Cost Basis","Mkt Val (Market Value)","Asset Type"\n'  # noqa: E501
    b'"AAPL","APPLE INC","27.4355","270.84","$2,989.79","$7,430.63","Equity"\n'
)

INVALID_CSV_BYTES = b"just some random text\nwith no recognizable columns\n"

MAX_FILE_SIZE = 512 * 1024  # 512KB


class TestImportSnapshotEndpoint:
    """Endpoint-level tests for CSV import."""

    def test_rejects_non_csv_content_type(self, client, auth_headers) -> None:
        """Non-CSV content type should be rejected."""
        response = client.post(
            "/api/v1/portfolio/import-snapshot",
            files={"file": ("test.json", io.BytesIO(b"{}"), "application/json")},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_oversized_file(self, client, auth_headers) -> None:
        """Files > 512KB should be rejected."""
        big_content = b"x" * (MAX_FILE_SIZE + 1)
        response = client.post(
            "/api/v1/portfolio/import-snapshot",
            files={"file": ("big.csv", io.BytesIO(big_content), "text/csv")},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_invalid_csv_format(self, client, auth_headers) -> None:
        """CSV with no recognizable header should return 422."""
        response = client.post(
            "/api/v1/portfolio/import-snapshot",
            files={"file": ("bad.csv", io.BytesIO(INVALID_CSV_BYTES), "text/csv")},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        body = response.json()
        assert "errors" in body.get("detail", {})

    def test_unauthenticated_returns_401(self, client) -> None:
        """No auth token should be rejected."""
        response = client.post(
            "/api/v1/portfolio/import-snapshot",
            files={"file": ("test.csv", io.BytesIO(VALID_CSV_BYTES), "text/csv")},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("backend.routers.portfolio.import_portfolio_snapshot")
    @patch("backend.routers.portfolio.parse_fidelity_csv")
    @patch("backend.routers.portfolio.get_or_create_portfolio")
    def test_successful_import_returns_201(
        self,
        mock_get_portfolio,
        mock_parse,
        mock_import,
        client,
        auth_headers,
    ) -> None:
        """Valid CSV should return 201 with ImportResult."""
        from backend.schemas.attribution import ImportResult, SnapshotRowSchema

        mock_get_portfolio.return_value = AsyncMock(id=uuid.uuid4())
        mock_parse.return_value = (
            [
                SnapshotRowSchema(
                    ticker="AAPL",
                    shares=10,
                    price=270,
                    cost_basis=2700,
                    market_value=2700,
                    avg_cost_basis=270,
                )
            ],
            [],  # warnings
            [],  # errors
        )
        mock_import.return_value = ImportResult(imported=1, changes_detected=0, is_baseline=True)

        response = client.post(
            "/api/v1/portfolio/import-snapshot",
            files={"file": ("test.csv", io.BytesIO(VALID_CSV_BYTES), "text/csv")},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_201_CREATED
        body = response.json()
        assert body["imported"] == 1
        assert body["is_baseline"] is True

    @patch("backend.routers.portfolio.import_portfolio_snapshot")
    @patch("backend.routers.portfolio.parse_fidelity_csv")
    @patch("backend.routers.portfolio.get_or_create_portfolio")
    def test_duplicate_csv_returns_409(
        self,
        mock_get_portfolio,
        mock_parse,
        mock_import,
        client,
        auth_headers,
    ) -> None:
        """Same CSV uploaded twice should return 409."""
        from backend.schemas.attribution import ImportResult, SnapshotRowSchema

        mock_get_portfolio.return_value = AsyncMock(id=uuid.uuid4())
        mock_parse.return_value = (
            [
                SnapshotRowSchema(
                    ticker="AAPL",
                    shares=10,
                    price=270,
                    cost_basis=2700,
                    market_value=2700,
                    avg_cost_basis=270,
                )
            ],
            [],
            [],
        )
        mock_import.return_value = ImportResult(imported=0, is_duplicate=True)

        response = client.post(
            "/api/v1/portfolio/import-snapshot",
            files={"file": ("test.csv", io.BytesIO(VALID_CSV_BYTES), "text/csv")},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_409_CONFLICT
