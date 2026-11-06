"""Common interface every retailer scraper implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from pricescout.models import Category, Offer
from pricescout.scrapers.http import ArchiveFetcher, PoliteFetcher


class RetailerScraper(ABC):
    name: str  # short id stored in the DB, e.g. "mediamarkt"
    base_url: str

    def __init__(self, fetcher: PoliteFetcher | ArchiveFetcher):
        self.fetcher = fetcher

    @abstractmethod
    def scrape_category(self, category: Category, max_products: int) -> Iterator[Offer]:
        """Yield up to `max_products` offers for one category, fetching politely."""
