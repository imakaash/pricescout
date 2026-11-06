from pricescout.scrapers.alternate import AlternateScraper
from pricescout.scrapers.base import RetailerScraper
from pricescout.scrapers.mediamarkt import MediaMarktScraper
from pricescout.scrapers.medimax import MedimaxScraper

SCRAPERS: dict[str, type[RetailerScraper]] = {
    s.name: s for s in (MediaMarktScraper, AlternateScraper, MedimaxScraper)
}

__all__ = ["SCRAPERS", "RetailerScraper"]
