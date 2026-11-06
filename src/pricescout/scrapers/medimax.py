"""MEDIMAX (medimax.de) scraper: a German electronics chain, part of ElectronicPartner.

Strategy (same as Alternate):
1. Category listing pages (server-rendered SAP Commerce) -> weekly prices. Each tile carries
   `data-et-code` (SKU), `data-et-name` (model number) and `data-et-price`.
2. Product pages once per new product -> EAN from schema.org JSON-LD (`gtin`).

robots.txt asks for `Crawl-delay: 10`, which PoliteFetcher honours automatically.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime

from selectolax.lexbor import LexborHTMLParser as HTMLParser
from selectolax.lexbor import LexborNode as Node

from pricescout.models import Category, Offer
from pricescout.scrapers.base import RetailerScraper
from pricescout.scrapers.common import parse_euro

log = logging.getLogger(__name__)

BASE_URL = "https://www.medimax.de"
# Several listing paths per category: OLED TVs are not under "LCD & LED".
CATEGORY_PATHS: dict[str, list[str]] = {
    "tv": ["/c/112/tv-audio/tv-beamer/lcd-led", "/c/627/tv-audio/tv-beamer/oled-tv"],
    "laptop": ["/c/233/computer-gaming/notebooks/notebooks"],
    "smartphone": ["/c/116/telefon-navi/handy-smartphone/smartphones"],
}
# The site's own pagination links use this query (relevance order, in-stock only).
_QUERY = "q=%3Arelevance%3AhasStock%3Atrue"


def category_url(path: str, page: int) -> str:
    """Pages are 0-indexed (SAP Commerce convention): page 0 is the bare category URL."""
    return f"{BASE_URL}{path}" + (f"?{_QUERY}&page={page}" if page > 0 else "")


def _text(node: Node | None) -> str | None:
    return " ".join(node.text(separator=" ").split()) or None if node else None


def parse_listing(
    html: str, category: Category, page: int, scraped_at: datetime, rank_offset: int = 0
) -> list[Offer]:
    tree = HTMLParser(html)
    offers = []
    for pos, tile in enumerate(tree.css(".cmsproductlist-desktop-layout-item"), start=1):
        a = tile.attributes
        sku = a.get("data-et-code")
        link = tile.css_first("a.cmsproductlist-name-link")
        price = parse_euro(a.get("data-et-price")) or parse_euro(_text(tile.css_first(".offerPrice")))
        if not (sku and link and price):
            continue
        href = link.attributes.get("href") or ""
        brand = _text(tile.css_first(".cmsproductlist-brand"))
        model = a.get("data-et-name") or _text(tile.css_first(".cmsproductlist-name")) or ""
        rrp = tile.css_first(".rrp")
        offers.append(
            Offer(
                retailer="medimax",
                retailer_sku=sku,
                category=category,
                title=f"{brand} {model}".strip(),
                url=BASE_URL + href if href.startswith("/") else href,
                brand=brand.upper() if brand else None,
                price=price,
                strike_price=parse_euro(_text(rrp)) if rrp else None,
                strike_price_type="RRP" if rrp else None,  # always labelled "UVP"
                seller="MEDIMAX",
                availability=_text(tile.css_first("[class*=stock]")),
                list_rank=rank_offset + pos,
                scraped_at=scraped_at,
            )
        )
    return offers


def has_next_page(html: str, page: int) -> bool:
    return f"page={page + 1}" in html


class MedimaxScraper(RetailerScraper):
    name = "medimax"
    base_url = BASE_URL

    def scrape_category(self, category: Category, max_products: int) -> Iterator[Offer]:
        stamp = self.fetcher.clock()
        seen: set[str] = set()
        rank = 0
        for path in CATEGORY_PATHS[category]:
            slug = path.strip("/").replace("/", "_")
            page = 0
            while len(seen) < max_products:
                html = self.fetcher.get(category_url(path, page), archive_name=f"{slug}_p{page}")
                offers = parse_listing(html, category, page, stamp, rank_offset=rank)
                if not offers:
                    break
                rank += len(offers)
                for offer in offers:
                    if offer.retailer_sku in seen or len(seen) >= max_products:
                        continue
                    seen.add(offer.retailer_sku)
                    offer.ean = self.resolve_ean(offer)
                    yield offer
                if not has_next_page(html, page):
                    break
                page += 1
