"""MediaMarkt.de scraper.

Strategy: category listing pages only (12 products/page). Each listing page embeds
1. a schema.org `ItemList` (JSON-LD): order, URL, rating,
2. `window.__PRELOADED_STATE__.apolloState`: the GraphQL cache with EAN, brand, price,
   strike price, shipping, marketplace flag and availability for every product on the page.
So we never need to open individual product pages.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from datetime import datetime

from pricescout.gtin import normalize_gtin
from pricescout.models import Category, Offer
from pricescout.scrapers.base import RetailerScraper
from pricescout.scrapers.common import jsonld_of_type

log = logging.getLogger(__name__)

BASE_URL = "https://www.mediamarkt.de"
CATEGORY_SLUGS: dict[str, str] = {
    "tv": "fernseher-203",
    "laptop": "laptops-notebooks-362",
    "smartphone": "smartphones-579",
}
PAGE_SIZE = 12

_STATE_RE = re.compile(r"window\.__PRELOADED_STATE__\s*=\s*")
_UNDEFINED_RE = re.compile(r"(?<=[:\[,])undefined(?=[,}\]])")  # JS literal -> JSON null
_SKU_RE = re.compile(r"-(\d+)\.html")


def category_url(slug: str, page: int) -> str:
    return f"{BASE_URL}/de/category/{slug}.html" + (f"?page={page}" if page > 1 else "")


def extract_preloaded_state(html: str) -> dict:
    m = _STATE_RE.search(html)
    if not m:
        raise ValueError("no __PRELOADED_STATE__ found; page layout may have changed")
    obj, _ = json.JSONDecoder().raw_decode(_UNDEFINED_RE.sub("null", html[m.end():]))
    return obj


def extract_item_list(html: str) -> list[dict]:
    return (jsonld_of_type(html, "ItemList") or {}).get("itemListElement", [])


def _by_id(apollo: dict, typename: str, sku: str) -> dict:
    """Find an apollo cache entry like 'CofrPriceFeature:{"id":"Media:de:123",...}'."""
    direct = apollo.get(f"{typename}:Media:de:{sku}") or apollo.get(f"{typename}:Media:de-DE:{sku}")
    if direct:
        return direct
    for key, value in apollo.items():
        if key.startswith(typename + ":") and value.get("id") == f"Media:de:{sku}":
            return value
    return {}


def _seller_name(raw) -> str | None:
    # Real shape: {"__typename": "CofrMarketplaceOfferApiActiveOffer", "sellerName": "...", ...}
    if isinstance(raw, dict):
        return raw.get("sellerName") or raw.get("name")
    return raw if isinstance(raw, str) else None


def parse_listing(
    html: str, category: Category, page: int, scraped_at: datetime
) -> tuple[list[Offer], int | None]:
    """Parse one listing page. Returns (offers, max_page)."""
    apollo = extract_preloaded_state(html).get("apolloState", {})
    max_page = next(
        (v.get("maxPage") for k, v in apollo.items() if k.startswith("ProductList:")), None
    )

    offers = []
    for element in extract_item_list(html):
        item = element.get("item", {})
        url = item.get("url", "")
        if not (m := _SKU_RE.search(url)):
            continue
        sku = m.group(1)
        product = _by_id(apollo, "GraphqlProduct", sku)
        core = _by_id(apollo, "CofrCoreFeature", sku)
        price = _by_id(apollo, "CofrPriceFeature", sku)
        status = _by_id(apollo, "CofrOnlineStatusFeature", sku)

        amount = (price.get("price") or {}).get("amount") or (item.get("offers") or {}).get("price")
        if amount is None:
            log.warning("no price for sku %s, skipping", sku)
            continue
        strike = price.get("strikePrice") or {}
        rating = item.get("aggregateRating") or {}
        is_marketplace = bool(price.get("isProductOfTypeMarketplace"))
        # Only first-party offers may default to "MediaMarkt"; an unknown marketplace seller
        # stays NULL so it can't be mistaken for MediaMarkt's own price.
        seller = _seller_name(price.get("marketplaceSeller")) or (
            None if is_marketplace else "MediaMarkt"
        )
        offers.append(
            Offer(
                retailer="mediamarkt",
                retailer_sku=sku,
                category=category,
                title=product.get("title") or item.get("name", ""),
                url=url if url.startswith("http") else BASE_URL + url,
                brand=core.get("manufacturerName") or product.get("manufacturer"),
                ean=normalize_gtin(core.get("ean")),
                price=float(amount),
                currency=price.get("currency", "EUR"),
                strike_price=strike.get("amount") if strike.get("shouldBeStruck", True) else None,
                strike_price_type=strike.get("type"),
                shipping_cost=(price.get("price") or {}).get("shippingCost"),
                is_marketplace=is_marketplace,
                seller=seller,
                availability=status.get("onlineStatus"),
                rating=rating.get("ratingValue"),
                review_count=rating.get("reviewCount"),
                list_rank=(page - 1) * PAGE_SIZE + element.get("position", 0),
                scraped_at=scraped_at,
            )
        )
    return offers, max_page


class MediaMarktScraper(RetailerScraper):
    name = "mediamarkt"
    base_url = BASE_URL

    def scrape_category(self, category: Category, max_products: int) -> Iterator[Offer]:
        slug = CATEGORY_SLUGS[category]
        stamp = self.fetcher.clock()
        seen: set[str] = set()
        page = 1
        while len(seen) < max_products:
            html = self.fetcher.get(category_url(slug, page), archive_name=f"{slug}_p{page}")
            offers, max_page = parse_listing(html, category, page, stamp)
            if not offers:
                log.warning("page %s of %s returned no offers; stopping", page, slug)
                break
            for offer in offers:
                # Rankings can shift between page requests, so a product may appear twice.
                if offer.retailer_sku in seen or len(seen) >= max_products:
                    continue
                seen.add(offer.retailer_sku)
                yield offer
            if max_page is not None and page >= max_page:
                break
            page += 1
