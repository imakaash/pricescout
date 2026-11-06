import pytest

from pricescout.extraction.pipeline import clean, merge
from pricescout.extraction.regex_extractor import extract


@pytest.mark.parametrize(
    ("title", "category", "expected"),
    [
        ("PHILIPS 77OLED811/12 OLED TV (Flat, 77 Zoll / 194 cm, UHD 4K, SMART TV)", "tv",
         {"screen_inches": 77, "panel": "OLED", "resolution": "4K"}),
        ("Samsung GQ55Q80C QLED-Fernseher 138 cm (55\"), 100Hz", "tv",
         {"screen_inches": 55, "panel": "QLED", "refresh_hz": 100}),
        ("LG OLED65C4 QD-OLED", "tv", {"panel": "QD-OLED"}),
        ("HP 17,3\" Intel Core 3 100U, 8 GB RAM, 512 GB SSD", "laptop",
         {"screen_inches": 17.3, "ram_gb": 8, "storage_gb": 512, "cpu": "Intel Core 3 100U"}),
        ("ASUS TUF A18, AMD Ryzen 7 260, NVIDIA GeForce RTX 5060, 16 GB DDR5, 1 TB (1 TB SSD)",
         "laptop", {"ram_gb": 16, "storage_gb": 1024, "gpu": "RTX 5060"}),
        ("SAMSUNG Galaxy A55 5G 8 GB 128 GB Awesome Navy", "smartphone",
         {"storage_gb": 128, "ram_gb": 8, "is_5g": True}),
        ("Apple iPhone 18 Pro 1TB", "smartphone", {"storage_gb": 1024}),
    ],
)
def test_regex_extract(title, category, expected):
    got = extract(title, category).model_dump()
    for k, v in expected.items():
        assert got[k] == v, (k, got[k], v)


def test_regex_does_not_invent():
    got = extract("Samsung GQ55QN72FATXZG", "tv").model_dump()
    assert got["screen_inches"] is None and got["panel"] is None


def test_clean_and_merge():
    assert clean({"model_code": "  ", "brand": "Samsung"}) == {"model_code": None, "brand": "SAMSUNG"}
    regex = {"storage_gb": 256, "model_code": None, "screen_inches": None}
    llm = {"storage_gb": 512, "model_code": "SM-S731B", "screen_inches": 6.4}
    m = merge(regex, llm)
    assert m["storage_gb"] == 256  # numbers: regex wins when it has a value
    assert m["model_code"] == "SM-S731B"  # names/codes: LLM wins
    assert m["screen_inches"] == 6.4  # regex empty -> LLM fills in
