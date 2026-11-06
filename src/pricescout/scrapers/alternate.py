"""Alternate.de scraper.

Strategy:
1. Category listing pages (24 products/page, server-rendered HTML) -> weekly prices.
2. Product pages only for products whose EAN we don't know yet -> EAN via schema.org JSON-LD.
   EANs never change, so after the first run this costs only a few requests per week.

Alternate publishes /llms.txt (a full catalogue for AI tools) and has a permissive robots.txt.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from datetime import datetime

from selectolax.lexbor import LexborHTMLParser as HTMLParser
from selectolax.lexbor import LexborNode as Node

from pricescout.models import Category, Offer
from pricescout.scrapers.base import RetailerScraper
from pricescout.scrapers.common import parse_euro

log = logging.getLogger(__name__)

BASE_URL = "https://www.alternate.de"
CATEGORY_PATHS: dict[str, str] = {
    "tv": "/Alle-Fernseher",
    "laptop": "/Notebook/Alle-Notebooks",
    "smartphone": "/Smartphone/Alle-Smartphones",
}
_SKU_RE = re.compile(r"/html/product/(\d+)")
_STRIKE_TYPES = {"uvp": "RRP", "niedrigste": "LOP", "30 tage": "LOP"}


def category_url(path: str, page: int) -> str:
    return f"{BASE_URL}{path}" + (f"?page={page}" if page > 1 else "")


def _text(node: Node | None) -> str | None:
    return " ".join(node.text(separator=" ").split()) or None if node else None


def _strike_type(card: Node) -> str | None:
    hint = card.css_first("button.best-price")
    content = (hint.attributes.get("data-bs-content") or "").lower() if hint else ""
    return next((v for k, v in _STRIKE_TYPES.items() if k in content), "OTHER" if content else None)


def parse_listing(html: str, category: Category, page: int, scraped_at: datetime) -> list[Offer]:
    tree = HTMLParser(html)
    offers = []
    for pos, card in enumerate(tree.css("a.productBox"), start=1):
        href = card.attributes.get("href") or ""
        if not (m := _SKU_RE.search(href)):
            continue
        price = parse_euro(_text(card.css_first("span.price")))
        if price is None:
            log.warning("no price on card %s", href)
            continue
        name_node = card.css_first(".product-name")
        brand = _text(name_node.css_first("span")) if name_node else None
        strike = parse_euro(_text(card.css_first(".line-through")))
        offers.append(
            Offer(
                retailer="alternate",
                retailer_sku=m.group(1),
                category=category,
                title=_text(name_node) or "",
                url=BASE_URL + href if href.startswith("/") else href,
                brand=brand.upper() if brand else None,
                price=price,
                strike_price=strike,
                strike_price_type=_strike_type(card) if strike else None,
                seller="ALTERNATE",  # no marketplace on alternate.de
                availability=_text(card.css_first(".delivery-info")),
                list_rank=(page - 1) * 24 + pos,
                scraped_at=scraped_at,
            )
        )
    return offers


def has_next_page(html: str, page: int) -> bool:
    return f"page={page + 1}" in html


class AlternateScraper(RetailerScraper):
    name = "alternate"
    base_url = BASE_URL

    def scrape_category(self, category: Category, max_products: int) -> Iterator[Offer]:
        path = CATEGORY_PATHS[category]
        slug = path.strip("/").replace("/", "_")
        stamp = self.fetcher.clock()
        seen: set[str] = set()
        page = 1
        while len(seen) < max_products:
            html = self.fetcher.get(category_url(path, page), archive_name=f"{slug}_p{page}")
            offers = parse_listing(html, category, page, stamp)
            if not offers:
                break
            for offer in offers:
                if offer.retailer_sku in seen or len(seen) >= max_products:
                    continue
                seen.add(offer.retailer_sku)
                offer.ean = self.resolve_ean(offer)
                yield offer
            if not has_next_page(html, page):
                break
            page += 1
