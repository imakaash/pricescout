"""Rule-based baseline. Fast, free, transparent, and the bar the LLM has to beat."""

from __future__ import annotations

import re

from pricescout.extraction.schemas import SCHEMAS, Common

_INCH = re.compile(r"(\d{2,3}(?:[.,]\d)?)\s*(?:zoll|\"|''|”|-inch| inch)", re.IGNORECASE)
_INCH_PAREN = re.compile(r"\((\d{2,3}(?:[.,]\d)?)\s*\"?\)")
_CM_INCH = re.compile(r"\d{2,3}(?:[.,]\d)?\s*cm\s*\((\d{2,3}(?:[.,]\d)?)", re.IGNORECASE)
_GB = re.compile(r"(\d{1,4})\s*(GB|TB)\b", re.IGNORECASE)
_RAM = re.compile(r"(\d{1,3})\s*GB\s*(?:LP)?(?:DDR\d\w*|RAM|Arbeitsspeicher)", re.IGNORECASE)
_STORAGE_SSD = re.compile(r"(\d{1,4})\s*(GB|TB)\s*(?:\(\d+\s*(?:GB|TB)\s*SSD\)|SSD|M\.2|PCIe)", re.IGNORECASE)
_HZ = re.compile(r"(\d{2,3})\s*Hz", re.IGNORECASE)
_GPU = re.compile(r"((?:GeForce\s+)?RTX\s*\d{4}\s*(?:Ti)?|Radeon\s+RX\s*\d{4}\w*)", re.IGNORECASE)
_CPU = re.compile(
    r"(Intel\s*®?\s*Core\s*™?\s*(?:Ultra\s*)?[ i]?\d[\w\- ]*?\d{3,5}\w*|AMD\s*Ryzen\s*™?\s*(?:AI\s*)?"
    r"\d\s*\w*\s*\d{3,4}\w*|Apple\s*M\d(?:\s*(?:Pro|Max))?|Snapdragon\s*®?\s*X\s*\w*(?:\s*\w+)?)",
    re.IGNORECASE)
_PANELS = [("QD-OLED", r"qd-?oled"), ("Micro LED", r"micro[- ]?(?:rgb|led)"),
           ("Mini LED", r"mini[- ]?led"), ("OLED", r"\boled"), ("QNED", r"qned"),
           ("NanoCell", r"nanocell"), ("QLED", r"\bqled"), ("LED", r"\bled\b")]
_RES = [("8K", r"\b8k\b"), ("4K", r"\b4k\b|uhd|ultra hd|3840"), ("Full HD", r"full ?hd|fhd|1080"),
        ("HD", r"\bhd\b|hd ready|720")]


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _gb(value: str, unit: str) -> int:
    return int(value) * (1024 if unit.upper() == "TB" else 1)


def extract(title: str, category: str, brand: str | None = None) -> Common:
    t = title
    low = t.lower()
    data: dict = {"brand": brand.title() if brand else None}

    inch = _INCH.search(t) or _CM_INCH.search(t) or _INCH_PAREN.search(t)
    if category == "tv":
        if inch:
            data["screen_inches"] = round(_num(inch.group(1)))
        data["panel"] = next((p for p, rx in _PANELS if re.search(rx, low)), None)
        data["resolution"] = next((r for r, rx in _RES if re.search(rx, low)), None)
        if hz := _HZ.search(t):
            data["refresh_hz"] = int(hz.group(1))
    elif category == "laptop":
        if inch:
            data["screen_inches"] = _num(inch.group(1))
        if ram := _RAM.search(t):
            data["ram_gb"] = int(ram.group(1))
        if ssd := _STORAGE_SSD.search(t):
            data["storage_gb"] = _gb(ssd.group(1), ssd.group(2))
        if cpu := _CPU.search(t):
            data["cpu"] = re.sub(r"\s+", " ", cpu.group(1).replace("®", "").replace("™", "")).strip()
        if gpu := _GPU.search(t):
            data["gpu"] = re.sub(r"\s+", " ", gpu.group(1)).replace("GeForce ", "")
    elif category == "smartphone":
        sizes = [_gb(v, u) for v, u in _GB.findall(t)]
        if sizes:
            data["storage_gb"] = max(sizes)  # "8 GB RAM 256 GB" -> storage is the larger
            if len(sizes) > 1:
                data["ram_gb"] = min(sizes)
        data["is_5g"] = True if re.search(r"\b5g\b", low) else None
    return SCHEMAS[category].model_validate(data)
