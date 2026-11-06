"""Run extraction over the product catalogue and store results in `product_attributes`.

- regex: every product, every run (milliseconds).
- llm:   prioritised and capped per run (a few seconds per title on the local model);
         results are cached, so coverage grows run by run like the EAN budget.
- hybrid (what downstream code uses): regex for numbers, LLM for names/codes/colour.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

import duckdb

from pricescout.extraction import llm_extractor, regex_extractor
from pricescout.extraction.schemas import SCHEMAS

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS product_attributes (
    retailer      VARCHAR NOT NULL,
    retailer_sku  VARCHAR NOT NULL,
    method        VARCHAR NOT NULL,   -- regex | llm | hybrid
    attrs         JSON NOT NULL,
    extracted_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (retailer, retailer_sku, method)
);
"""

# Numbers are where regex is deterministic; names/codes are where the LLM shines.
REGEX_FIRST = {"screen_inches", "ram_gb", "storage_gb", "refresh_hz", "is_5g"}


def clean(attrs: dict) -> dict:
    out = {}
    for k, v in attrs.items():
        if isinstance(v, str):
            v = v.strip() or None
        out[k] = v
    if out.get("brand"):
        out["brand"] = out["brand"].upper()
    return out


def merge(regex_attrs: dict, llm_attrs: dict | None) -> dict:
    if not llm_attrs:
        return regex_attrs
    merged = {}
    for k in set(regex_attrs) | set(llm_attrs):
        r, m = regex_attrs.get(k), llm_attrs.get(k)
        merged[k] = (r if r is not None else m) if k in REGEX_FIRST else (m if m is not None else r)
    return merged


def _save(con, rows):
    if rows:
        con.executemany("INSERT OR REPLACE INTO product_attributes VALUES (?, ?, ?, ?, ?)", rows)


def run(con: duckdb.DuckDBPyConnection, llm_limit: int = 300) -> dict[str, int]:
    con.execute(SCHEMA)
    now = datetime.now()
    products = con.execute(
        "SELECT retailer, retailer_sku, category, title, brand FROM products").fetchall()

    regex_rows = []
    regex_by_key = {}
    for r, sku, cat, title, brand in products:
        attrs = clean(regex_extractor.extract(title, cat, brand).model_dump())
        regex_by_key[(r, sku)] = attrs
        regex_rows.append((r, sku, "regex", json.dumps(attrs), now))
    _save(con, regex_rows)

    # LLM priority: products in VoltMarkt's assortment, then EANs sold by several shops, then
    # products without an EAN (where attributes matter most for matching), then by rank.
    has_internal = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'internal_products'"
    ).fetchone()[0]
    voltmarkt = "p.ean IN (SELECT ean FROM internal_products)" if has_internal else "FALSE"
    todo = con.execute(f"""
        WITH shops AS (SELECT ean, count(DISTINCT retailer) n FROM products
                       WHERE ean IS NOT NULL GROUP BY ean)
        SELECT p.retailer, p.retailer_sku, p.category, p.title, p.brand
        FROM products p
        LEFT JOIN shops USING (ean)
        LEFT JOIN product_attributes a
               ON a.retailer = p.retailer AND a.retailer_sku = p.retailer_sku AND a.method = 'llm'
        WHERE a.retailer IS NULL
        ORDER BY {voltmarkt} DESC, coalesce(shops.n, 0) DESC, (p.ean IS NULL) DESC, p.retailer
        LIMIT ?""", [llm_limit]).fetchall()

    n_llm = 0
    for r, sku, cat, title, brand in todo:
        try:
            attrs = clean(llm_extractor.extract(title, cat, brand).model_dump())
        except Exception as exc:
            log.warning("LLM extraction failed for %s/%s: %s", r, sku, exc)
            continue
        _save(con, [(r, sku, "llm", json.dumps(attrs), datetime.now())])
        n_llm += 1

    llm_by_key = {(r, s): json.loads(a) for r, s, a in con.execute(
        "SELECT retailer, retailer_sku, attrs FROM product_attributes WHERE method = 'llm'"
    ).fetchall()}
    _save(con, [(r, s, "hybrid", json.dumps(merge(attrs, llm_by_key.get((r, s)))), now)
                for (r, s), attrs in regex_by_key.items()])
    return {"products": len(products), "llm_new": n_llm, "llm_total": len(llm_by_key)}


def consistency_report(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Label-free accuracy: the same EAN at two shops must yield the same attributes.

    Returns (method, field, pairs_compared, agreement_pct, coverage_pct).
    """
    fields = sorted({f for s in SCHEMAS.values() for f in s.model_fields} - {"brand", "color"})
    rows = []
    for method in ("regex", "llm", "hybrid"):
        pairs = con.execute("""
            SELECT a1.attrs, a2.attrs
            FROM products p1
            JOIN products p2 ON p1.ean = p2.ean AND p1.retailer < p2.retailer
            JOIN product_attributes a1 ON a1.retailer = p1.retailer
                 AND a1.retailer_sku = p1.retailer_sku AND a1.method = ?
            JOIN product_attributes a2 ON a2.retailer = p2.retailer
                 AND a2.retailer_sku = p2.retailer_sku AND a2.method = ?
            WHERE p1.ean IS NOT NULL""", [method, method]).fetchall()
        pairs = [(json.loads(a), json.loads(b)) for a, b in pairs]
        for f in fields:
            both = [(a.get(f), b.get(f)) for a, b in pairs if f in a or f in b]
            if not both:
                continue
            filled = [(x, y) for x, y in both if x is not None and y is not None]
            agree = sum(_same(x, y) for x, y in filled)
            rows.append((method, f, len(filled),
                         round(100 * agree / len(filled), 1) if filled else None,
                         round(100 * len(filled) / len(both), 1)))
    return rows


def _same(x, y) -> bool:
    if isinstance(x, str) and isinstance(y, str):
        norm = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())
        return norm(x) == norm(y) or norm(x) in norm(y) or norm(y) in norm(x)
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        return abs(x - y) < 0.15
    return x == y
