"""Generate SYNTHETIC internal data (assortment, costs, stock, sales) for our fictional retailer.

Anchored to the real scraped market; deterministic for a given --seed. Re-run after each weekly
scrape to simulate the new week.

  python scripts/generate_internal_data.py
  python scripts/generate_internal_data.py --per-category 80 --seed 7
"""

from __future__ import annotations

import argparse

from rich.console import Console

from pricescout.config import settings
from pricescout.db import store
from pricescout.internal.simulate import generate

console = Console()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--per-category", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    con = store.connect(settings.db_path)
    n_products, n_weeks = generate(con, settings.own_company_name, args.per_category, args.seed)
    console.print(f"[bold]{settings.own_company_name}[/bold] (fictional, synthetic data): "
                  f"{n_products} products, {n_weeks} week(s) simulated")
    console.print(con.sql("""
        SELECT p.category, count(*) AS products,
               round(avg(100 * (w.our_price - p.cost_price) / w.our_price), 1) AS avg_margin_pct,
               round(avg(100 * (w.our_price / w.market_ref - 1)), 1) AS avg_vs_cheapest_pct,
               sum(w.units_sold) AS units, round(sum(w.units_sold * w.our_price)) AS revenue_eur
        FROM internal_products p JOIN internal_weekly w USING (sku)
        WHERE w.week = (SELECT max(week) FROM internal_weekly)
        GROUP BY 1 ORDER BY 1
    """))
    con.close()


if __name__ == "__main__":
    main()
