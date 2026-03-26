"""Test pagination schemas validate correctly."""

from backend.schemas.portfolio import TransactionListResponse
from backend.schemas.stock import RecommendationListResponse


class TestPaginationSchemas:
    def test_transaction_list_response_shape(self) -> None:
        """TransactionListResponse should accept empty list and zero total."""
        resp = TransactionListResponse(transactions=[], total=0)
        assert resp.total == 0
        assert resp.transactions == []

    def test_recommendation_list_response_shape(self) -> None:
        """RecommendationListResponse should accept empty list and zero total."""
        resp = RecommendationListResponse(recommendations=[], total=0)
        assert resp.total == 0
        assert resp.recommendations == []
