from datetime import UTC, datetime

from pricescout.models import Offer
from pricescout.scrapers.base import RetailerScraper

PRODUCT_PAGE = ('<script type="application/ld+json">'
                '{"@type":"Product","gtin":"4000000000006"}</script>')


class CountingFetcher:
    def __init__(self):
        self.calls = 0

    def get(self, url, archive_name=None):
        self.calls += 1
        return PRODUCT_PAGE


class DummyScraper(RetailerScraper):
    name = "dummy"
    base_url = "https://example.com"

    def scrape_category(self, category, max_products):
        raise NotImplementedError


def _offer(sku):
    return Offer(retailer="dummy", retailer_sku=sku, category="tv", title="t",
                 url=f"https://example.com/{sku}", price=1, scraped_at=datetime.now(UTC))


def test_budget_limits_product_page_fetches_and_cache_is_free():
    fetcher = CountingFetcher()
    scraper = DummyScraper(fetcher, known_eans={"cached": "4000000000013"})
    scraper.detail_budget = 2

    assert scraper.resolve_ean(_offer("cached")) == "4000000000013"  # from cache: no request
    assert scraper.resolve_ean(_offer("a")) == "4000000000006"
    assert scraper.resolve_ean(_offer("b")) == "4000000000006"
    assert scraper.resolve_ean(_offer("c")) is None  # budget spent
    assert fetcher.calls == 2


def test_no_budget_means_unlimited():
    fetcher = CountingFetcher()
    scraper = DummyScraper(fetcher)
    for sku in "abcde":
        scraper.resolve_ean(_offer(sku))
    assert fetcher.calls == 5
