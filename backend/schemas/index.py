"""Pydantic v2 schemas for stock index endpoints."""

import uuid

from pydantic import BaseModel, Field


class IndexResponse(BaseModel):
    """Stock index with member count."""

    id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    stock_count: int = Field(description="Number of stocks in this index")

    model_config = {"from_attributes": True}


class IndexStockItem(BaseModel):
    """A stock within an index, with latest price and signal summary."""

    ticker: str
    name: str
    sector: str | None = None
    exchange: str | None = None
    latest_price: float | None = Field(None, description="Most recent adj_close")
    composite_score: float | None = Field(None, description="Latest composite signal score")
    rsi_signal: str | None = None
    macd_signal: str | None = None

    model_config = {"from_attributes": True}


class IndexStocksResponse(BaseModel):
    """Paginated list of stocks in an index."""

    index_name: str
    total: int
    items: list[IndexStockItem]
