"""KPI queries shared by the agents (Phase 4) and the dashboard (Phase 5).

Everything reads `v_comparable` (new goods, first-party, not unavailable), so every number in
the project uses the same definition of "comparable". Functions return pandas DataFrames and
degrade gracefully when there is only one week of data or a table doesn't exist yet.
"""

from __future__ import annotations

import duckdb
import pandas as pd


def has_table(con: duckdb.DuckDBPyConnection, name: str) -> bool:
    return bool(con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [name]
    ).fetchone()[0])


def weeks(con: duckdb.DuckDBPyConnection) -> list:
    return [w for (w,) in con.execute(
        "SELECT DISTINCT week FROM price_snapshots ORDER BY week").fetchall()]


def latest_week(con: duckdb.DuckDBPyConnection):
    return con.execute("SELECT max(week) FROM price_snapshots").fetchone()[0]


def coverage(con, week=None) -> pd.DataFrame:
    """Per retailer: offers, comparable offers, EAN coverage, last run status."""
    week = week or latest_week(con)
    return con.execute("""
        SELECT o.retailer,
               count(*) AS offers,
               count(*) FILTER (WHERE NOT o.is_marketplace AND NOT o.is_refurbished
                                AND o.availability_norm IN ('in_stock','delayed','unknown'))
                   AS comparable,
               round(100.0 * count(o.ean) / count(*), 1) AS ean_pct,
               count(*) FILTER (WHERE o.is_marketplace) AS marketplace,
               count(*) FILTER (WHERE o.is_refurbished) AS refurbished,
               (SELECT status FROM scrape_runs r WHERE r.retailer = o.retailer
                ORDER BY started_at DESC LIMIT 1) AS last_run
        FROM v_offers o WHERE o.week = ?
        GROUP BY o.retailer ORDER BY o.retailer""", [week]).df()


def _voltmarkt_vs_market(con, week) -> str:
    """CTE: our price per EAN vs each competitor's comparable price that week."""
    return f"""
        WITH ours AS (
            SELECT p.ean, p.category, p.title, p.strategic_role, w.our_price::DOUBLE AS our_price,
                   p.cost_price::DOUBLE AS cost, w.units_sold, w.stock_end
            FROM internal_products p JOIN internal_weekly w USING (sku)
            WHERE w.week = DATE '{week}'),
        comp AS (
            SELECT ean, retailer, min(price)::DOUBLE AS price
            FROM v_comparable WHERE week = DATE '{week}' AND ean IS NOT NULL
            GROUP BY ean, retailer)"""


def price_index(con, week=None) -> pd.DataFrame:
    """Per competitor & category: our price index (100 = same price; >100 = we're dearer)."""
    if not has_table(con, "internal_weekly"):
        return pd.DataFrame()
    week = week or latest_week(con)
    return con.execute(_voltmarkt_vs_market(con, week) + """
        SELECT comp.retailer, ours.category, count(*) AS shared_products,
               round(100 * exp(avg(ln(ours.our_price / comp.price))), 1) AS price_index,
               count(*) FILTER (WHERE ours.our_price <= comp.price) AS we_are_cheaper_or_equal
        FROM ours JOIN comp USING (ean)
        GROUP BY ALL ORDER BY 1, 2""").df()


def cheapest_share(con, week=None) -> pd.DataFrame:
    """How often each seller (incl. VoltMarkt) is the cheapest on products several sell."""
    week = week or latest_week(con)
    ours = ""
    if has_table(con, "internal_weekly"):
        ours = f"""UNION ALL
            SELECT p.ean, p.category, 'voltmarkt', w.our_price::DOUBLE
            FROM internal_products p JOIN internal_weekly w USING (sku)
            WHERE w.week = DATE '{week}'"""
    return con.execute(f"""
        WITH prices AS (
            SELECT ean, category, retailer, min(price)::DOUBLE AS price
            FROM v_comparable WHERE week = DATE '{week}' AND ean IS NOT NULL GROUP BY ALL
            {ours}),
        multi AS (SELECT ean FROM prices GROUP BY ean HAVING count(*) >= 2),
        best AS (SELECT ean, min(price) AS best FROM prices GROUP BY ean)
        SELECT retailer, count(*) AS shared_products,
               count(*) FILTER (WHERE price = best) AS cheapest,
               round(100.0 * count(*) FILTER (WHERE price = best) / count(*), 1) AS cheapest_pct,
               round(100 * median(price / best - 1), 1) AS median_pct_above_cheapest
        FROM prices JOIN multi USING (ean) JOIN best USING (ean)
        GROUP BY retailer ORDER BY cheapest_pct DESC""").df()


def promotions(con, week=None, min_discount_pct: float = 15) -> pd.DataFrame:
    """Strike-price promos this week. LOP (30-day low) is the honest promo signal; RRP/UVP
    discounts are often permanent, so they need a higher bar."""
    week = week or latest_week(con)
    return con.execute("""
        SELECT retailer, category, title, ean, price::DOUBLE AS price,
               strike_price::DOUBLE AS strike_price, strike_price_type,
               round(100 * (1 - price / strike_price), 1) AS discount_pct
        FROM v_comparable
        WHERE week = ? AND strike_price > price
          AND (strike_price_type = 'LOP' OR 100 * (1 - price / strike_price) >= ?)
        ORDER BY strike_price_type = 'LOP' DESC, discount_pct DESC""",
        [week, min_discount_pct]).df()


def price_changes(con, min_change_pct: float = 5) -> pd.DataFrame:
    """Week-over-week price moves (empty until there are two weeks of data)."""
    ws = weeks(con)
    if len(ws) < 2:
        return pd.DataFrame()
    prev, cur = ws[-2], ws[-1]
    return con.execute("""
        SELECT c.retailer, c.category, c.title, c.ean, p.price::DOUBLE AS old_price,
               c.price::DOUBLE AS new_price, round(100 * (c.price / p.price - 1), 1) AS change_pct
        FROM v_comparable c JOIN v_comparable p
          ON c.retailer = p.retailer AND c.retailer_sku = p.retailer_sku AND p.week = ?
        WHERE c.week = ? AND abs(c.price / p.price - 1) * 100 >= ?
        ORDER BY abs(c.price / p.price - 1) DESC""", [prev, cur, min_change_pct]).df()


def assortment_gaps(con, week=None, min_shops: int = 2) -> pd.DataFrame:
    """Products several competitors sell that VoltMarkt doesn't (by EAN)."""
    if not has_table(con, "internal_products"):
        return pd.DataFrame()
    week = week or latest_week(con)
    return con.execute("""
        SELECT category, any_value(brand) AS brand, arg_min(title, price) AS title, ean,
               count(DISTINCT retailer) AS shops, min(price)::DOUBLE AS cheapest
        FROM v_comparable
        WHERE week = ? AND ean IS NOT NULL AND ean NOT IN (SELECT ean FROM internal_products)
        GROUP BY category, ean HAVING count(DISTINCT retailer) >= ?
        ORDER BY shops DESC, min(list_rank)""", [week, min_shops]).df()


def voltmarkt_performance(con) -> pd.DataFrame:
    """Weekly revenue, gross profit, units and margin per category (synthetic company)."""
    if not has_table(con, "internal_weekly"):
        return pd.DataFrame()
    return con.execute("""
        SELECT w.week, p.category, sum(w.units_sold) AS units,
               round(sum(w.units_sold * w.our_price)) AS revenue,
               round(sum(w.units_sold * (w.our_price - p.cost_price))) AS gross_profit,
               round(100 * sum(w.units_sold * (w.our_price - p.cost_price))
                     / nullif(sum(w.units_sold * w.our_price), 0), 1) AS margin_pct,
               sum(w.stock_end) AS stock_units
        FROM internal_weekly w JOIN internal_products p USING (sku)
        GROUP BY ALL ORDER BY 1, 2""").df()


def voltmarkt_positions(con, week=None) -> pd.DataFrame:
    """Per VoltMarkt product: price vs cheapest competitor, margin, stock cover."""
    if not has_table(con, "internal_weekly"):
        return pd.DataFrame()
    week = week or con.execute("SELECT max(week) FROM internal_weekly").fetchone()[0]
    return con.execute("""
        WITH hist AS (SELECT sku, avg(units_sold) AS avg_units FROM internal_weekly GROUP BY sku)
        SELECT p.sku, p.ean, p.category, p.brand, p.title, p.strategic_role,
               p.cost_price::DOUBLE AS cost, p.min_margin_pct, p.elasticity, p.base_demand,
               w.our_price::DOUBLE AS our_price, w.market_ref::DOUBLE AS cheapest_competitor,
               round(100 * (w.our_price / w.market_ref - 1), 1) AS vs_cheapest_pct,
               round(100 * (w.our_price - p.cost_price) / w.our_price, 1) AS margin_pct,
               w.units_sold, w.stock_end,
               round(w.stock_end / greatest(h.avg_units, 0.5), 1) AS weeks_of_cover
        FROM internal_products p JOIN internal_weekly w USING (sku) JOIN hist h USING (sku)
        WHERE w.week = ?
        ORDER BY p.category, vs_cheapest_pct DESC""", [week]).df()


def matches_summary(con) -> pd.DataFrame:
    if not has_table(con, "product_matches"):
        return pd.DataFrame()
    return con.execute("""SELECT method, count(*) AS pairs, round(avg(score), 3) AS avg_score
                          FROM product_matches GROUP BY method""").df()
