"""Parsing helpers shared by retailer scrapers."""

from __future__ import annotations

import json
import re

_JSONLD_RE = re.compile(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", re.DOTALL)


def extract_jsonld(html: str) -> list[dict]:
    """All schema.org JSON-LD objects on a page, with @graph containers flattened."""
    out: list[dict] = []
    for block in _JSONLD_RE.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for obj in data if isinstance(data, list) else [data]:
            if isinstance(obj, dict):
                out.extend(obj.get("@graph", [obj]))
    return out


def jsonld_of_type(html: str, type_: str) -> dict | None:
    return next((o for o in extract_jsonld(html) if o.get("@type") == type_), None)


def parse_euro(text: str | None) -> float | None:
    """'€ 1.299,00' / '1.299,-' / '1299.0' -> 1299.0"""
    if not text:
        return None
    s = re.sub(r"[^\d,.\-]", "", text).rstrip("-").rstrip(",")
    if not s:
        return None
    if "," in s:  # German format: '.' thousands, ',' decimals
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):  # '1.299' after stripping ',-' is thousands
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None
