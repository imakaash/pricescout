from datetime import datetime

from pricescout.db import store
from pricescout.models import Offer


def make_offer(price: float, when: datetime, ean: str | None = "4000000000001") -> Offer:
    return Offer(retailer="mediamarkt", retailer_sku="1", category="tv", title="TV",
                 url="https://x/1", ean=ean, price=price, scraped_at=when)


def test_same_week_rerun_overwrites_snapshot():
    con = store.connect(":memory:")
    store.save_offers(con, [make_offer(500, datetime(2026, 11, 3))], "run1")
    store.save_offers(con, [make_offer(450, datetime(2026, 11, 5))], "run2")  # same ISO week
    rows = con.execute("SELECT price, run_id FROM price_snapshots").fetchall()
    assert [(float(p), r) for p, r in rows] == [(450.0, "run2")]


def test_new_week_appends_and_product_keeps_first_seen():
    con = store.connect(":memory:")
    store.save_offers(con, [make_offer(500, datetime(2026, 11, 3))], "run1")
    store.save_offers(con, [make_offer(480, datetime(2026, 11, 10), ean=None)], "run2")
    assert con.execute("SELECT count(*) FROM price_snapshots").fetchall()[0][0] == 2
    first_seen, last_seen, ean = con.execute(
        "SELECT first_seen, last_seen, ean FROM products").fetchall()[0]
    assert first_seen == datetime(2026, 11, 3)
    assert last_seen == datetime(2026, 11, 10)
    assert ean == "4000000000001"  # a missing EAN later doesn't erase a known one
