"""SYNTHETIC internal data for our fictional retailer ("VoltMarkt" by default).

Scraping tells us what competitors charge. Pricing *recommendations* also need facts only the
company knows: purchase cost, margin floor, stock and sales. We don't have a real company, so
we simulate one, anchored to the real scraped market so the numbers are plausible:

- Assortment: real products (by EAN) that competitors sell, preferring EANs carried by several
  retailers so there is something to compare against.
- Cost: a category-dependent share of the real market price (phones have thin margins, TVs fat).
- Demand: responds to our price relative to the cheapest competitor (price elasticity), so a
  pricing decision has a measurable consequence the agents can learn from.
- Everything is deterministic for a given seed and lives in `internal_*` tables, separate from
  the real scraped data. Nothing here describes a real company.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import date, timedelta

import duckdb
import numpy as np

INTERNAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS internal_products (
    sku               VARCHAR PRIMARY KEY,  -- derived from the EAN, so one row per EAN
    ean               VARCHAR NOT NULL,
    category          VARCHAR NOT NULL,
    brand             VARCHAR,
    title             VARCHAR NOT NULL,
    cost_price        DECIMAL(10, 2) NOT NULL,
    min_margin_pct    DOUBLE NOT NULL,   -- price may not go below cost * (1 + min_margin_pct)
    strategic_role    VARCHAR NOT NULL,  -- traffic_driver | standard | margin
    base_demand       DOUBLE NOT NULL,   -- expected units/week at market-level price
    elasticity        DOUBLE NOT NULL    -- % demand change per % price change (positive number)
);

CREATE TABLE IF NOT EXISTS internal_weekly (
    sku          VARCHAR NOT NULL,
    week         DATE NOT NULL,
    our_price    DECIMAL(10, 2) NOT NULL,
    market_ref   DECIMAL(10, 2),       -- cheapest first-party competitor price that week
    units_sold   INTEGER NOT NULL,
    stock_end    INTEGER NOT NULL,     -- units in stock at the end of the week
    restocked    INTEGER NOT NULL,     -- units received this week
    PRIMARY KEY (sku, week)
);

CREATE TABLE IF NOT EXISTS internal_meta (
    key   VARCHAR PRIMARY KEY,
    value VARCHAR
);
"""


@dataclass(frozen=True)
class CategoryProfile:
    cost_share: tuple[float, float]  # cost as share of market price (low, high)
    min_margin: float
    elasticity: tuple[float, float]


# Rough, plausible consumer-electronics economics (not real figures).
PROFILES: dict[str, CategoryProfile] = {
    "smartphone": CategoryProfile((0.84, 0.93), 0.04, (2.5, 3.5)),
    "laptop": CategoryProfile((0.78, 0.89), 0.06, (1.8, 2.6)),
    "tv": CategoryProfile((0.70, 0.84), 0.08, (2.0, 3.0)),
}
ROLES = ("traffic_driver", "standard", "margin")
ROLE_WEIGHTS = (0.2, 0.5, 0.3)
ROLE_PRICE_INDEX = {"traffic_driver": (0.96, 1.01), "standard": (0.99, 1.06), "margin": (1.03, 1.10)}


def charm_price(x: float) -> float:
    """German retail style: 449.00, 1.299.00, 89.99 for cheap items."""
    if x < 100:
        return math.floor(x) + 0.99 if x % 1 else x - 0.01
    step = 10 if x < 1000 else 50
    return float(math.ceil(x / step) * step - 1)


def market_reference(con: duckdb.DuckDBPyConnection, week: date | None = None) -> list[tuple]:
    """Per EAN: (ean, category, brand, title, cheapest first-party price, #retailers, best rank)
    for the given week (default: latest week with data)."""
    week_sql = "(SELECT max(week) FROM price_snapshots)" if week is None else "?"
    params = [] if week is None else [week]
    return con.execute(
        f"""
        SELECT p.ean, any_value(p.category), any_value(p.brand),
               arg_min(p.title, s.price), min(s.price)::DOUBLE,
               count(DISTINCT p.retailer), min(s.list_rank)
        FROM price_snapshots s
        JOIN products p USING (retailer, retailer_sku)
        WHERE s.week = {week_sql} AND p.ean IS NOT NULL AND NOT s.is_marketplace
        GROUP BY p.ean
        """,
        params,
    ).fetchall()


def _sku(ean: str) -> str:
    return "VM-" + hashlib.sha1(ean.encode()).hexdigest()[:8].upper()


def build_assortment(
    con: duckdb.DuckDBPyConnection, per_category: int = 50, seed: int = 42
) -> int:
    """Pick our assortment from the real market and invent cost/role/demand parameters."""
    rng = np.random.default_rng(seed)
    market = market_reference(con)
    rows = []
    for cat, prof in PROFILES.items():
        # Prefer products several competitors carry, then the best-ranked ones.
        cands = sorted((m for m in market if m[1] == cat), key=lambda m: (-m[5], m[6] or 999))
        for ean, _, brand, title, ref, _n, rank in cands[:per_category]:
            role = rng.choice(ROLES, p=ROLE_WEIGHTS)
            base = 60 / math.sqrt(rank or 50) * rng.uniform(0.6, 1.4)
            rows.append((
                _sku(ean), ean, cat, brand, title,
                round(ref * rng.uniform(*prof.cost_share), 2),
                prof.min_margin, str(role), round(base, 2), round(rng.uniform(*prof.elasticity), 2),
            ))
    con.executemany(
        "INSERT OR REPLACE INTO internal_products VALUES (?,?,?,?,?,?,?,?,?,?)", rows
    )
    return len(rows)


def simulate_week(
    con: duckdb.DuckDBPyConnection,
    week: date,
    seed: int = 42,
    price_overrides: dict[str, float] | None = None,
) -> int:
    """Simulate one week of sales/stock for every internal product.

    Our price defaults to last week's price (or an initial role-based price on first sight);
    `price_overrides` lets Phase 4's accepted recommendations change it.
    Demand = base * (our_price / market_ref) ** -elasticity, with Poisson noise.
    """
    rng = np.random.default_rng([seed, week.toordinal()])
    market = {m[0]: m[4] for m in market_reference(con, week)}
    products = con.execute(
        "SELECT sku, ean, strategic_role, base_demand, elasticity, cost_price::DOUBLE, "
        "min_margin_pct FROM internal_products ORDER BY sku"
    ).fetchall()
    prev = {
        sku: (price, stock)
        for sku, price, stock in con.execute(
            "SELECT sku, our_price::DOUBLE, stock_end FROM internal_weekly WHERE week = ?",
            [week - timedelta(days=7)],
        ).fetchall()
    }
    rows = []
    for sku, ean, role, base, elast, cost, min_margin in products:
        ref = market.get(ean)
        last_price, stock = prev.get(sku, (None, None))
        if price_overrides and sku in price_overrides:
            price = price_overrides[sku]
        elif last_price is not None:
            price = last_price
        elif ref is not None:
            price = charm_price(ref * rng.uniform(*ROLE_PRICE_INDEX[role]))
        else:
            continue  # never priced and no market signal: skip
        price = max(price, round(cost * (1 + min_margin), 2))  # never below the margin floor

        if stock is None:  # opening stock: 3-10 weeks of cover
            stock = int(base * rng.uniform(3, 10))
        restocked = 0
        if stock < base * 2:  # simple reorder rule: top up to ~6 weeks of cover
            restocked = int(base * 6) - stock
            stock += restocked

        rel = price / ref if ref else 1.0
        demand = rng.poisson(max(base * rel ** (-elast), 0.0))
        sold = int(min(demand, stock))
        rows.append((sku, week, price, ref, sold, stock - sold, restocked))
    con.executemany("INSERT OR REPLACE INTO internal_weekly VALUES (?,?,?,?,?,?,?)", rows)
    return len(rows)


def generate(
    con: duckdb.DuckDBPyConnection, company: str, per_category: int = 50, seed: int = 42
) -> tuple[int, int]:
    con.execute(INTERNAL_SCHEMA)
    n_products = build_assortment(con, per_category, seed)
    weeks = [w for (w,) in con.execute(
        "SELECT DISTINCT week FROM price_snapshots ORDER BY week").fetchall()]
    for w in weeks:
        simulate_week(con, w, seed)
    con.executemany("INSERT OR REPLACE INTO internal_meta VALUES (?, ?)", [
        ("company", company),
        ("synthetic", "true: all internal_* data is simulated, not from a real company"),
        ("seed", str(seed)),
        ("generated_on", date.today().isoformat()),
    ])
    return n_products, len(weeks)
