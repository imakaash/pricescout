"""Common interface every retailer scraper implements."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping

from pricescout.gtin import normalize_gtin
from pricescout.models import Category, Offer
from pricescout.scrapers.common import jsonld_of_type
from pricescout.scrapers.http import ArchiveFetcher, PoliteFetcher

log = logging.getLogger(__name__)


class RetailerScraper(ABC):
    name: str  # short id stored in the DB, e.g. "mediamarkt"
    base_url: str

    def __init__(
        self,
        fetcher: PoliteFetcher | ArchiveFetcher,
        known_eans: Mapping[str, str] | None = None,
    ):
        self.fetcher = fetcher
        # retailer_sku -> EAN already in the DB, so scrapers can skip detail-page requests.
        self.known_eans = known_eans or {}

    @abstractmethod
    def scrape_category(self, category: Category, max_products: int) -> Iterator[Offer]:
        """Yield up to `max_products` offers for one category, fetching politely."""

    def resolve_ean(self, offer: Offer) -> str | None:
        """EAN from the DB cache, else fetch the product page once (EANs never change)."""
        if ean := self.known_eans.get(offer.retailer_sku):
            return ean
        html = self.fetcher.get(offer.url, archive_name=f"product_{offer.retailer_sku}")
        ean = product_page_ean(html)
        if ean is None:
            log.warning("no valid EAN on %s", offer.url)
        return ean


def product_page_ean(html: str) -> str | None:
    """EAN from a product page's schema.org JSON-LD, whatever gtin* key the shop uses.

    Shops mislabel these (Alternate puts 13-digit EANs in `gtin8`), so every key is tried and
    check-digit validation decides.
    """
    product = jsonld_of_type(html, "Product") or {}
    for key in ("gtin13", "gtin", "gtin8", "gtin12", "gtin14", "ean"):
        if ean := normalize_gtin(product.get(key)):
            return ean
    return None
