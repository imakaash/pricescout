"""Rule-based matcher: the bar the fine-tuned model has to beat."""

from __future__ import annotations

from pricescout.matching.pairs import Listing, jaccard

CONFLICT_FIELDS = ("screen_inches", "storage_gb", "ram_gb", "panel", "resolution")


def conflicts(a: Listing, b: Listing) -> list[str]:
    """Spec fields both listings state, with different values: a strong 'no match' signal."""
    out = []
    for f in CONFLICT_FIELDS:
        x, y = a.attrs.get(f), b.attrs.get(f)
        if x is not None and y is not None and (
            abs(x - y) > 0.15 if isinstance(x, (int, float)) else str(x).lower() != str(y).lower()
        ):
            out.append(f)
    return out


def _code(listing: Listing) -> str:
    c = listing.attrs.get("model_code") or ""
    return "".join(ch for ch in c.lower() if ch.isalnum())


def score(a: Listing, b: Listing) -> float:
    if conflicts(a, b):
        return 0.0
    s = jaccard(a, b)
    ca, cb = _code(a), _code(b)
    if len(ca) >= 6 and len(cb) >= 6 and (ca in cb or cb in ca):
        s = max(s, 0.9)  # same manufacturer part number (ignoring suffixes like 'XZG')
    return s
