from datetime import UTC, datetime
from pathlib import Path

from pricescout.scrapers.mediamarkt import category_url, parse_listing

FIXTURE = (Path(__file__).parent / "fixtures" / "mediamarkt_listing.html").read_text()
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def test_parse_listing_basic_fields():
    offers, max_page = parse_listing(FIXTURE, "tv", page=2, scraped_at=NOW)
    assert max_page == 2
    assert [o.retailer_sku for o in offers] == ["1000001", "1000002", "1000003"]

    acme = offers[0]
    assert acme.title == "ACME 55 Zoll 4K Smart TV"  # apollo title preferred over JSON-LD name
    assert acme.brand == "ACME"
    assert acme.ean == "4000000000006"
    assert acme.price == 449
    assert (acme.strike_price, acme.strike_price_type) == (849, "RRP")
    assert acme.shipping_cost == 39.9
    assert acme.seller == "MediaMarkt" and not acme.is_marketplace
    assert acme.availability == "AVAILABLE"
    assert (acme.rating, acme.review_count) == (4.5, 10)
    assert acme.list_rank == 13  # page 2, position 1


def test_marketplace_offer_uses_apollo_price():
    widget = parse_listing(FIXTURE, "tv", 1, NOW)[0][1]
    assert widget.is_marketplace
    assert widget.seller == "Some Seller GmbH"  # read from "sellerName"
    assert widget.price == 189.99  # apollo price wins over JSON-LD price
    assert widget.strike_price is None


def test_falls_back_to_jsonld_when_apollo_missing():
    fallback = parse_listing(FIXTURE, "tv", 1, NOW)[0][2]
    assert fallback.price == 99.5
    assert fallback.ean is None
    assert fallback.title == "No Apollo Data TV"


def test_week_is_monday():
    offer = parse_listing(FIXTURE, "tv", 1, NOW)[0][0]
    assert offer.week.isoformat() == "2026-11-02"


def test_category_url():
    assert category_url("fernseher-203", 1).endswith("/de/category/fernseher-203.html")
    assert category_url("fernseher-203", 3).endswith("fernseher-203.html?page=3")
