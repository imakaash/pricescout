from datetime import UTC, datetime
from pathlib import Path

from pricescout.scrapers.medimax import category_url, has_next_page, parse_listing

FIXTURE = (Path(__file__).parent / "fixtures" / "medimax_listing.html").read_text()
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def test_parse_listing():
    offers = parse_listing(FIXTURE, "tv", page=0, scraped_at=NOW, rank_offset=18)
    assert [o.retailer_sku for o in offers] == ["300001", "300002"]

    acme = offers[0]
    assert acme.title == "Acme 55ABC123/12"
    assert acme.brand == "ACME"
    assert (acme.price, acme.strike_price, acme.strike_price_type) == (499.0, 1049.0, "RRP")
    assert acme.availability == "Lieferung in 1-3 Werktagen"
    assert acme.url == "https://www.medimax.de/p/300001/55abc123-12"
    assert acme.list_rank == 19  # continues numbering across category paths

    widget = offers[1]
    assert widget.price == 1299.0  # falls back to the visible price when data-et-price is empty
    assert widget.strike_price is None


def test_pagination_is_zero_indexed():
    assert category_url("/c/112/x", 0) == "https://www.medimax.de/c/112/x"
    assert category_url("/c/112/x", 1).endswith("/c/112/x?q=%3Arelevance%3AhasStock%3Atrue&page=1")
    assert has_next_page(FIXTURE, 0)
    assert not has_next_page(FIXTURE, 1)
