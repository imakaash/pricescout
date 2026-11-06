from datetime import datetime

from pricescout.db import store
from pricescout.models import Offer

WHEN = datetime(2026, 11, 3)


def _offer(sku, title="TV", availability="AVAILABLE", marketplace=False, seller="Shop"):
    return Offer(retailer="r", retailer_sku=sku, category="tv", title=title, url=f"https://x/{sku}",
                 price=100, availability=availability, is_marketplace=marketplace, seller=seller,
                 scraped_at=WHEN)


def test_availability_mapping_and_comparable_filter():
    con = store.connect(":memory:")
    store.save_offers(con, [
        _offer("1", availability="AVAILABLE"),
        _offer("2", availability="Sofort verfügbar"),
        _offer("3", availability="Ware neu eingetroffen, in Kürze verfügbar"),
        _offer("4", availability="TEMPORARILY_NOT_AVAILABLE"),
        _offer("5", title="Galaxy A54 Generalüberholt"),
        _offer("6", seller="AfB gemeinnützige GmbH", marketplace=True, availability="MP_OFFER"),
        _offer("7", availability="Lieferung in 1-3 Werktagen"),
    ], "run")
    norm = dict(con.execute(
        "SELECT retailer_sku, availability_norm FROM v_offers ORDER BY 1").fetchall())
    assert norm == {"1": "in_stock", "2": "in_stock", "3": "delayed", "4": "out_of_stock",
                    "5": "in_stock", "6": "in_stock", "7": "in_stock"}
    refurb = {r[0] for r in con.execute(
        "SELECT retailer_sku FROM v_offers WHERE is_refurbished").fetchall()}
    assert refurb == {"5", "6"}
    comparable = {r[0] for r in con.execute("SELECT retailer_sku FROM v_comparable").fetchall()}
    assert comparable == {"1", "2", "3", "7"}  # not out of stock, refurbished or marketplace
