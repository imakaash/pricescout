"""Rule-based matcher (the bar the fine-tuned model has to beat) + hard guard rules.

The guard rules (`conflicts`, `ambiguous`) are also applied in front of the LLM matcher: they
encode facts a model can't be trusted to get right every time (98" is not 85").
"""

from __future__ import annotations

import re

from pricescout.matching.pairs import Listing, jaccard

CONFLICT_FIELDS = ("screen_inches", "storage_gb", "ram_gb", "panel", "resolution")

# TV model codes start with the size: GQ48S95H, 55PQS8611/12, 98P8L, OLED65C4, GU-98U9079H.
_TV_CODE_SIZE = re.compile(r"^(?:[A-Z]{1,4}-?)?(\d{2,3})(?=[A-Z])", re.IGNORECASE)
_TOKEN_WITH_SIZE = re.compile(r"\b(?:[A-Z]{1,4}-?)?(\d{2,3})[A-Z][A-Z0-9]+\b")


def tv_inches(listing: Listing) -> int | None:
    """Screen size from extracted attrs, else from the model code in attrs or title."""
    if listing.category != "tv":
        return None
    if (v := listing.attrs.get("screen_inches")) is not None:
        return round(v)
    candidates = [listing.attrs.get("model_code") or ""]
    candidates += [m.group(0) for m in _TOKEN_WITH_SIZE.finditer(listing.title)]
    for code in candidates:
        if (m := _TV_CODE_SIZE.match(code.replace(" ", ""))) and 24 <= int(m.group(1)) <= 120:
            return int(m.group(1))
    return None


def conflicts(a: Listing, b: Listing) -> list[str]:
    """Spec fields both listings state, with different values: a strong 'no match' signal."""
    out = []
    for f in CONFLICT_FIELDS:
        x, y = a.attrs.get(f), b.attrs.get(f)
        if x is not None and y is not None and (
            abs(x - y) > 0.15 if isinstance(x, (int, float)) else str(x).lower() != str(y).lower()
        ):
            out.append(f)
    ia, ib = tv_inches(a), tv_inches(b)
    if ia and ib and ia != ib and "screen_inches" not in out:
        out.append("screen_inches(model code)")
    ca, cb = _code(a), _code(b)
    if len(ca) >= 5 and len(cb) >= 5 and ca not in cb and cb not in ca:
        out.append("model_code")  # TV-50W80CEZS vs TV-50W83AE7C, 65C6K vs 65C69K
    va, vb = _variants(a), _variants(b)
    if va != vb:
        out.append("variant")  # 'S26 FE' vs 'S26', 'Pixel 11 Pro XL' vs 'Pixel 11 Pro'
    return out


# Words that make a different model in the same product line.
VARIANT_WORDS = {"pro", "max", "plus", "ultra", "fe", "xl", "mini", "lite", "fold", "flip",
                 "air", "neo", "edge", "slim"}


def _variants(listing: Listing) -> frozenset[str]:
    if listing.category not in ("smartphone", "laptop"):
        return frozenset()
    toks = re.split(r"[^a-z0-9+]+", listing.title.lower())
    found = {t for t in toks if t in VARIANT_WORDS}
    found |= {"plus"} if any(t.endswith("+") for t in toks) else set()
    return frozenset(found)


def ambiguous(a: Listing, b: Listing) -> bool:
    """Not decidable from the titles: e.g. 'MacBook Pro 14 CTO' (build-to-order, no specs)
    can't be matched to one specific configuration. Laptops/phones need storage on both sides."""
    if a.category in ("laptop", "smartphone"):
        return a.attrs.get("storage_gb") is None or b.attrs.get("storage_gb") is None
    return False


_TV_CODE_IN_TITLE = re.compile(r"\b[A-Z]{0,4}-?\d{2,3}[A-Z][A-Z0-9]{2,}(?:/\d{2})?\b")


def _code(listing: Listing) -> str:
    """Model code from extracted attrs; for TVs fall back to the code in the title, since
    LLM extraction is budgeted and many products don't have it yet."""
    c = listing.attrs.get("model_code") or ""
    if not c and listing.category == "tv" and (m := _TV_CODE_IN_TITLE.search(listing.title)):
        c = m.group(0)
    return "".join(ch for ch in c.lower() if ch.isalnum())


def score(a: Listing, b: Listing) -> float:
    if conflicts(a, b):
        return 0.0
    s = jaccard(a, b)
    ca, cb = _code(a), _code(b)
    if len(ca) >= 6 and len(cb) >= 6 and (ca in cb or cb in ca):
        s = max(s, 0.9)  # same manufacturer part number (ignoring suffixes like 'XZG')
    return s
