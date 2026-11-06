from pricescout.scrapers.base import RetailerScraper
from pricescout.scrapers.mediamarkt import MediaMarktScraper

SCRAPERS: dict[str, type[RetailerScraper]] = {
    MediaMarktScraper.name: MediaMarktScraper,
}

__all__ = ["SCRAPERS", "RetailerScraper"]
