"""GTIN/EAN normalisation: the join key for matching products across retailers.

Barcodes come as GTIN-8, UPC-A (12 digits), EAN-13 or GTIN-14, sometimes with lost leading
zeros or under the wrong schema.org label (Alternate puts 13-digit EANs in `gtin8`).
We normalise to EAN-13 (what German retailers display) and validate the check digit, so a
typo can never create a false cross-retailer match.
"""

from __future__ import annotations

import re


def _check_digit_ok(code: str) -> bool:
    digits = [int(c) for c in code]
    body, check = digits[:-1], digits[-1]
    # Weights alternate 3,1,3,1... starting from the digit next to the check digit.
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def normalize_gtin(raw: object) -> str | None:
    """Return a validated 13-digit EAN (or 8-digit GTIN-8), else None."""
    if raw is None:
        return None
    code = re.sub(r"\D", "", str(raw))
    if not code or set(code) == {"0"}:
        return None
    if len(code) == 14 and code.startswith("0"):
        code = code[1:]  # GTIN-14 with packaging indicator 0 == the EAN-13
    elif len(code) in (11, 12):
        code = code.zfill(13)  # UPC-A (or UPC with lost leading zero) -> EAN-13
    if len(code) not in (8, 13) or not _check_digit_ok(code):
        return None
    return code
