from datetime import UTC, datetime
from pathlib import Path

from pricescout.scrapers.alternate import has_next_page, parse_listing
from pricescout.scrapers.base import product_page_ean as parse_product_ean

FIXTURE = (Path(__file__).parent / "fixtures" / "alternate_listing.html").read_text()
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def test_parse_listing():
    offers = parse_listing(FIXTURE, "laptop", page=2, scraped_at=NOW)
    assert [o.retailer_sku for o in offers] == ["200001", "200002"]  # card without price skipped

    acme = offers[0]
    assert acme.brand == "ACME"
    assert acme.title == "Acme Laptop 15, Notebook"
    assert (acme.price, acme.strike_price, acme.strike_price_type) == (1299.0, 1499.0, "RRP")
    assert acme.availability == "Sofort verfügbar"  # whitespace collapsed
    assert acme.url == "https://www.alternate.de/ACME/Laptop-15/html/product/200001"
    assert acme.list_rank == 25  # page 2 of 24-item pages

    widget = offers[1]
    assert widget.price == 349.90
    assert widget.strike_price is None and widget.strike_price_type is None


def test_pagination():
    assert has_next_page(FIXTURE, 1)
    assert not has_next_page(FIXTURE, 2)


def test_product_ean_from_mislabelled_gtin8():
    html = """<script type="application/ld+json">
      {"@context":"https://www.schema.org","@type":"Product","sku":1,"gtin8":"4711636211802"}
    </script>"""
    assert parse_product_ean(html) == "4711636211802"


def test_product_ean_invalid_checksum_rejected():
    html = '<script type="application/ld+json">{"@type":"Product","gtin8":"4711636211803"}</script>'
    assert parse_product_ean(html) is None
