"""DuckDB storage: schema + idempotent writes.

Tables
- products         one row per (retailer, retailer_sku): slowly-changing descriptive data
- price_snapshots  one row per (retailer, retailer_sku, week): the time series we analyse
- scrape_runs      one row per scraper run: for monitoring / data-quality checks
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

import duckdb

from pricescout.models import Offer

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    retailer      VARCHAR NOT NULL,
    retailer_sku  VARCHAR NOT NULL,
    category      VARCHAR NOT NULL,
    title         VARCHAR NOT NULL,
    brand         VARCHAR,
    ean           VARCHAR,
    url           VARCHAR NOT NULL,
    first_seen    TIMESTAMP NOT NULL,
    last_seen     TIMESTAMP NOT NULL,
    PRIMARY KEY (retailer, retailer_sku)
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    retailer          VARCHAR NOT NULL,
    retailer_sku      VARCHAR NOT NULL,
    week              DATE NOT NULL,
    scraped_at        TIMESTAMP NOT NULL,
    price             DECIMAL(10, 2) NOT NULL,
    currency          VARCHAR NOT NULL,
    strike_price      DECIMAL(10, 2),
    strike_price_type VARCHAR,
    shipping_cost     DECIMAL(10, 2),
    is_marketplace    BOOLEAN NOT NULL,
    seller            VARCHAR,
    availability      VARCHAR,
    rating            DOUBLE,
    review_count      INTEGER,
    list_rank         INTEGER,
    run_id            VARCHAR,
    PRIMARY KEY (retailer, retailer_sku, week)
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    run_id         VARCHAR PRIMARY KEY,
    retailer       VARCHAR NOT NULL,
    started_at     TIMESTAMP NOT NULL,
    finished_at    TIMESTAMP,
    pages_fetched  INTEGER,
    offers         INTEGER,
    errors         INTEGER,
    status         VARCHAR
);
"""


def connect(db_path: str | Path) -> duckdb.DuckDBPyConnection:
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute(SCHEMA)
    return con


def save_offers(con: duckdb.DuckDBPyConnection, offers: Iterable[Offer], run_id: str) -> int:
    """Upsert offers. Re-running in the same week overwrites that week's snapshot."""
    n = 0
    for o in offers:
        con.execute(
            """
            INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (retailer, retailer_sku) DO UPDATE SET
                category = excluded.category, title = excluded.title,
                brand = excluded.brand, ean = COALESCE(excluded.ean, products.ean),
                url = excluded.url, last_seen = excluded.last_seen
            """,
            [o.retailer, o.retailer_sku, o.category, o.title, o.brand, o.ean, o.url,
             o.scraped_at, o.scraped_at],
        )
        con.execute(
            "INSERT OR REPLACE INTO price_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [o.retailer, o.retailer_sku, o.week, o.scraped_at, o.price, o.currency,
             o.strike_price, o.strike_price_type, o.shipping_cost, o.is_marketplace, o.seller,
             o.availability, o.rating, o.review_count, o.list_rank, run_id],
        )
        n += 1
    return n


def start_run(con: duckdb.DuckDBPyConnection, run_id: str, retailer: str) -> None:
    con.execute(
        "INSERT INTO scrape_runs (run_id, retailer, started_at, status) VALUES (?, ?, ?, 'running')",
        [run_id, retailer, datetime.now()],
    )


def finish_run(
    con: duckdb.DuckDBPyConnection, run_id: str, pages: int, offers: int, errors: int, status: str
) -> None:
    con.execute(
        """UPDATE scrape_runs SET finished_at = ?, pages_fetched = ?, offers = ?, errors = ?,
           status = ? WHERE run_id = ?""",
        [datetime.now(), pages, offers, errors, status, run_id],
    )
