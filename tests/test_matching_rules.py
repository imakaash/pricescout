import pytest

from pricescout.matching.baseline import ambiguous, conflicts, tv_inches
from pricescout.matching.pairs import Listing


def L(title, category="tv", attrs=None):
    return Listing("r", title, category, "X", title, None, attrs or {})


@pytest.mark.parametrize(("title", "inches"), [
    ("SAMSUNG GQ48S95H OLED 4K", 48), ("TCL 98P8L QD-Mini LED", 98), ("LG OLED65C4 OLED TV", 65),
    ("Philips 55PQS8611/12", 55), ("Samsung GU-98U9079H", 98), ("TV 100Hz Ambilight", None),
])
def test_tv_inches_from_model_code(title, inches):
    assert tv_inches(L(title)) == inches


@pytest.mark.parametrize(("a", "b", "category"), [
    ("TCL 98P8L QD-Mini LED", "TCL 85P8L QD-Mini LED", "tv"),  # size in the code
    ("Panasonic TV-65W80CEZS VIVID", "Panasonic TV-65Z90BE7A", "tv"),  # different code
    ("Samsung Galaxy S26 FE 256GB", "Samsung Galaxy S26 256GB", "smartphone"),  # variant
    ("Google Pixel 11 Pro XL 256GB", "Google Pixel 11 Pro 256GB", "smartphone"),
])
def test_conflicts_block_wrong_matches(a, b, category):
    assert conflicts(L(a, category), L(b, category))


@pytest.mark.parametrize(("a", "b", "category"), [
    ("Philips 55OLED811/12, OLED-Fernseher", "Philips 55OLED811/12", "tv"),
    ("Apple iPhone 18 Pro Max 256GB DEP, Handy", "Apple iPhone 18 Pro Max 256GB", "smartphone"),
    ("Xiaomi Redmi Note 15 Pro+ 5G 256GB", "XIAOMI REDMI Note 15 Pro+ 5G 256 GB Black", "smartphone"),
])
def test_no_conflict_for_true_matches(a, b, category):
    assert not conflicts(L(a, category), L(b, category))


def test_build_to_order_laptop_is_ambiguous():
    cto = L("Apple MacBook Pro (14\") 2026 CTO", "laptop")
    spec = L("APPLE MacBook Pro 14 M6 16 GB 1 TB", "laptop", {"storage_gb": 1024})
    assert ambiguous(cto, spec)
