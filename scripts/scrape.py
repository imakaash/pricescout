"""Run a weekly scrape for one or more retailers and store results in DuckDB.

Examples:
  python scripts/scrape.py --retailer mediamarkt                      # all categories
  python scripts/scrape.py --retailer mediamarkt --category tv --max 12 --dry-run
"""

from __future__ import annotations

import argparse
import logging
import uuid
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from pricescout.config import settings
from pricescout.db import store
from pricescout.models import Offer
from pricescout.scrapers import SCRAPERS
from pricescout.scrapers.http import ArchiveFetcher, PoliteFetcher

CATEGORIES = ["tv", "laptop", "smartphone"]
console = Console()
log = logging.getLogger("pricescout.scrape")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--retailer", choices=sorted(SCRAPERS), required=True)
    ap.add_argument("--category", choices=CATEGORIES, action="append",
                    help="repeatable; default: all")
    ap.add_argument("--max", type=int,
                    help="max products per category (default: per-retailer limit / #categories)")
    ap.add_argument("--dry-run", action="store_true", help="print results, don't write to the DB")
    ap.add_argument("--from-raw", metavar="YYYY-MM-DD",
                    help="re-parse archived pages from that day instead of fetching (no network)")
    args = ap.parse_args()

    logging.basicConfig(level="INFO", format="%(message)s", handlers=[RichHandler(console=console)])
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per request is too noisy
    categories = args.category or CATEGORIES
    max_per_cat = args.max or settings.scraper_max_products_per_retailer // len(categories)

    scraper_cls = SCRAPERS[args.retailer]
    if args.from_raw:
        fetcher = ArchiveFetcher(Path("data/raw") / args.retailer / args.from_raw)
    else:
        fetcher = PoliteFetcher(
            scraper_cls.base_url,
            settings.scraper_user_agent,
            min_delay=settings.scraper_min_delay_seconds,
            raw_dir=Path("data/raw") / args.retailer / date.today().isoformat(),
        )
    scraper = scraper_cls(fetcher)
    day = args.from_raw or date.today().isoformat()
    run_id = f"{args.retailer}-{day}-{'reparse' if args.from_raw else uuid.uuid4().hex[:6]}"
    con = None if args.dry_run else store.connect(settings.db_path)
    if con:
        store.start_run(con, run_id, args.retailer)

    all_offers: list[Offer] = []
    errors = 0
    console.print(f"[bold]{run_id}[/bold]: {categories}, max {max_per_cat}/category, "
                  f"delay ≥{fetcher.delay:.0f}s")
    for cat in categories:
        offers: list[Offer] = []
        try:
            for offer in scraper.scrape_category(cat, max_per_cat):
                offers.append(offer)  # noqa: PERF402 - one by one so a failure keeps partial data
        except Exception:  # one category failing shouldn't kill the whole run
            log.exception("category %s failed after %d offers", cat, len(offers))
            errors += 1
        console.print(f"  {cat}: {len(offers)} offers")
        all_offers.extend(offers)
        if con:
            store.save_offers(con, offers, run_id)

    if con:
        status = "ok" if not errors else ("failed" if not all_offers else "partial")
        store.finish_run(con, run_id, fetcher.pages_fetched, len(all_offers), errors, status)
        con.close()
    fetcher.close()
    _summary(all_offers, fetcher.pages_fetched)


def _summary(offers: list[Offer], pages: int) -> None:
    t = Table(title=f"{len(offers)} offers from {pages} pages (sample)")
    for col in ["cat", "title", "price", "strike", "ship", "seller", "ean"]:
        t.add_column(col, no_wrap=True, overflow="ellipsis", max_width=32 if col == "title" else None)
    for o in offers[:: max(1, len(offers) // 10)][:10]:  # spread the sample across categories
        t.add_row(o.category, o.title, f"{o.price:.2f}",
                  f"{o.strike_price:.0f} {o.strike_price_type}" if o.strike_price else "",
                  f"{o.shipping_cost:.2f}" if o.shipping_cost is not None else "",
                  o.seller or "", o.ean or "")
    console.print(t)
    missing_ean = sum(o.ean is None for o in offers)
    console.print(f"EAN coverage: {len(offers) - missing_ean}/{len(offers)}")


if __name__ == "__main__":
    main()
