import pytest

from pricescout.gtin import normalize_gtin
from pricescout.scrapers.common import parse_euro


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("4711636211802", "4711636211802"),  # valid EAN-13
        ("195950691474", "0195950691474"),  # UPC-A -> EAN-13
        ("00195950691474", "0195950691474"),  # GTIN-14 with leading 0
        (4711636211802, "4711636211802"),  # int input
        ("4711-6362-1180-2", "4711636211802"),  # formatting stripped
        ("4711636211803", None),  # bad check digit
        ("96385074", "96385074"),  # valid GTIN-8
        ("0000000000000", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_gtin(raw, expected):
    assert normalize_gtin(raw) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("€ 1.299,00", 1299.0), ("349,90 €", 349.9), ("1.299,-", 1299.0), ("1299.0", 1299.0),
     ("", None), (None, None), ("gratis", None)],
)
def test_parse_euro(text, expected):
    assert parse_euro(text) == expected
