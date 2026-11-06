"""Candidate pairs + labelled training data for product matching.

Labels come for free from EANs: same EAN at two shops = same product (positive).
Hard negatives: same brand + category, different EAN, similar title (e.g. 55" vs 65" of one
series, 128 GB vs 256 GB). Splits are by EAN group so no product leaks from train into test.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass

import duckdb


@dataclass(frozen=True)
class Listing:
    retailer: str
    sku: str
    category: str
    brand: str
    title: str
    ean: str | None
    attrs: dict

    @property
    def key(self) -> tuple[str, str]:
        return self.retailer, self.sku

    def text(self) -> str:
        """Compact description fed to the matcher: title + the specs we extracted."""
        specs = ", ".join(f"{k}={v}" for k, v in sorted(self.attrs.items())
                          if v is not None and k != "brand")
        return f"{self.brand} | {self.title}" + (f" | {specs}" if specs else "")


def tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", s.lower()) if t}


def jaccard(a: Listing, b: Listing) -> float:
    ta, tb = tokens(a.title), tokens(b.title)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def load_listings(con: duckdb.DuckDBPyConnection) -> list[Listing]:
    has_attrs = con.execute("SELECT count(*) FROM information_schema.tables "
                            "WHERE table_name = 'product_attributes'").fetchone()[0]
    attrs_join = ("LEFT JOIN product_attributes a ON a.retailer = p.retailer "
                  "AND a.retailer_sku = p.retailer_sku AND a.method = 'hybrid'") if has_attrs else ""
    attrs_col = "a.attrs" if has_attrs else "NULL"
    rows = con.execute(f"""
        SELECT DISTINCT p.retailer, p.retailer_sku, p.category, upper(coalesce(p.brand, '')),
               p.title, p.ean, {attrs_col}
        FROM products p {attrs_join}
        WHERE (p.retailer, p.retailer_sku) IN (SELECT retailer, retailer_sku FROM v_comparable)
    """).fetchall()
    return [Listing(r, s, c, b, t, e, json.loads(a) if a else {}) for r, s, c, b, t, e, a in rows]


def candidate_pairs(listings: list[Listing], min_jaccard: float = 0.15):
    """Blocking: only compare listings from different shops, same category and brand."""
    blocks: dict[tuple[str, str], list[Listing]] = {}
    for x in listings:
        blocks.setdefault((x.category, x.brand), []).append(x)
    for group in blocks.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if a.retailer != b.retailer and jaccard(a, b) >= min_jaccard:
                    yield a, b


def labelled_pairs(listings: list[Listing], neg_per_pos: int = 3, seed: int = 0):
    """(a, b, label, group) where group = EAN used for leakage-free splitting."""
    rng = random.Random(seed)
    with_ean = [x for x in listings if x.ean]
    pos, neg = [], []
    for a, b in candidate_pairs(with_ean, min_jaccard=0.0):
        if a.ean == b.ean:
            pos.append((a, b, 1, a.ean))
        elif jaccard(a, b) >= 0.3:  # hard negative: looks similar, but different product
            neg.append((a, b, 0, min(a.ean, b.ean)))
    rng.shuffle(neg)
    return pos + neg[: len(pos) * neg_per_pos]


def split_by_group(pairs, valid: float = 0.15, test: float = 0.2, seed: int = 0):
    groups = sorted({p[3] for p in pairs})
    random.Random(seed).shuffle(groups)
    n_test, n_valid = int(len(groups) * test), int(len(groups) * valid)
    test_g, valid_g = set(groups[:n_test]), set(groups[n_test:n_test + n_valid])
    out = {"train": [], "valid": [], "test": []}
    for p in pairs:
        out["test" if p[3] in test_g else "valid" if p[3] in valid_g else "train"].append(p)
    return out
