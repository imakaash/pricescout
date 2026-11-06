from datetime import date, datetime

import pytest

from pricescout.db import store
from pricescout.internal.simulate import charm_price, generate, simulate_week
from pricescout.models import Offer

W1, W2 = date(2026, 11, 2), date(2026, 11, 9)


def _offer(retailer, sku, ean, price, when, category="tv", marketplace=False, rank=1):
    return Offer(retailer=retailer, retailer_sku=sku, category=category, title=f"T{ean}",
                 url=f"https://x/{sku}", ean=ean, price=price, is_marketplace=marketplace,
                 list_rank=rank, scraped_at=when)


@pytest.fixture
def con():
    c = store.connect(":memory:")
    when = datetime(2026, 11, 3)
    store.save_offers(c, [
        _offer("mediamarkt", "a", "4000000000006", 500, when),
        _offer("alternate", "b", "4000000000006", 480, when),
        _offer("mediamarkt", "c", "4000000000013", 300, when, marketplace=True),  # ignored
        _offer("medimax", "d", "4000000000013", 320, when),
        _offer("medimax", "e", "4000000000020", 999, when, category="laptop"),
    ], "run")
    return c


def test_generate_is_deterministic_and_respects_margin_floor(con):
    n_products, n_weeks = generate(con, "TestCo", per_category=10, seed=1)
    assert (n_products, n_weeks) == (3, 1)
    rows = con.execute("""
        SELECT p.ean, w.our_price::DOUBLE, w.market_ref::DOUBLE, p.cost_price::DOUBLE,
               p.min_margin_pct, w.units_sold, w.stock_end
        FROM internal_products p JOIN internal_weekly w USING (sku) ORDER BY p.ean""").fetchall()
    refs = {r[0]: r[2] for r in rows}
    assert refs["4000000000006"] == 480  # cheapest first-party price
    assert refs["4000000000013"] == 320  # marketplace offer (300) excluded
    for _, price, _, cost, floor, sold, stock in rows:
        assert price >= cost * (1 + floor)
        assert cost < price and sold >= 0 and stock >= 0

    # same seed -> identical data
    again = store.connect(":memory:")
    for r in con.execute("SELECT * FROM products").fetchall():
        again.execute("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?)", r)
    for r in con.execute("SELECT * FROM price_snapshots").fetchall():
        again.execute("INSERT INTO price_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", r)
    generate(again, "TestCo", per_category=10, seed=1)
    q = "SELECT * FROM internal_weekly ORDER BY sku"
    assert again.execute(q).fetchall() == con.execute(q).fetchall()


def test_price_override_changes_demand_direction(con):
    generate(con, "TestCo", per_category=10, seed=1)
    sku = con.execute(
        "SELECT sku FROM internal_products WHERE ean = '4000000000006'").fetchone()[0]
    # Same market next week; compare a high price vs a low price over many seeds.
    store.save_offers(con, [_offer("alternate", "b", "4000000000006", 480, datetime(2026, 11, 10))],
                      "run2")
    def units(price, seed):
        simulate_week(con, W2, seed=seed, price_overrides={sku: price})
        return con.execute("SELECT units_sold FROM internal_weekly WHERE sku=? AND week=?",
                           [sku, W2]).fetchone()[0]
    cheap = sum(units(470, s) for s in range(30))
    pricey = sum(units(560, s) for s in range(30))
    assert cheap > pricey  # elasticity: lower price sells more


@pytest.mark.parametrize(("x", "expected"), [(449.3, 449.0), (1230, 1249.0), (55.4, 55.99)])
def test_charm_price(x, expected):
    assert charm_price(x) == expected
