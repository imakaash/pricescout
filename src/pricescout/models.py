"""Core data model shared by scrapers, the database and (later) the agents."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["tv", "laptop", "smartphone"]


class Offer(BaseModel):
    """One product as seen at one retailer at one moment: the unit we store every week."""

    retailer: str
    retailer_sku: str = Field(description="The retailer's own product id")
    category: Category
    title: str
    url: str
    brand: str | None = None
    ean: str | None = Field(None, description="GTIN-13/EAN barcode: the key for cross-retailer matching")

    price: float = Field(description="Current selling price incl. VAT")
    currency: str = "EUR"
    strike_price: float | None = Field(None, description="Crossed-out reference price, if shown")
    strike_price_type: str | None = Field(None, description="e.g. RRP (=UVP) or LOP (30-day low)")
    shipping_cost: float | None = None

    is_marketplace: bool = False
    seller: str | None = None
    availability: str | None = None

    rating: float | None = None
    review_count: int | None = None
    list_rank: int | None = Field(None, description="Position in the category listing (1 = top)")

    scraped_at: datetime

    @property
    def week(self) -> date:
        """Monday of the ISO week: one snapshot per product per week."""
        d = self.scraped_at.date()
        return d - timedelta(days=d.weekday())
