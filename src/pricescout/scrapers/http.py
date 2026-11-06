"""A polite HTTP fetcher: robots.txt, rate limiting, retries with backoff, raw-page archive."""

from __future__ import annotations

import gzip
import logging
import random
import time
from datetime import UTC, date, datetime
from datetime import time as dtime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from pricescout.scrapers.robots import RobotsTxt

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


class DisallowedByRobots(Exception):
    pass


class PoliteFetcher:
    def __init__(
        self,
        base_url: str,
        user_agent: str,
        min_delay: float = 5.0,
        max_retries: int = 3,
        raw_dir: Path | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.max_retries = max_retries
        self.raw_dir = raw_dir
        self.client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Language": "de-DE,de;q=0.9"},
            timeout=30,
            follow_redirects=True,
        )
        self._last_request = 0.0
        self.pages_fetched = 0

        resp = self.client.get(f"{self.base_url}/robots.txt")
        self.robots = RobotsTxt(resp.text if resp.status_code == 200 else "")
        # Use the larger of our own delay and the site's requested Crawl-delay.
        self.delay = max(min_delay, self.robots.crawl_delay(user_agent) or 0)

    def _wait(self) -> None:
        # Jitter avoids hitting the server in a perfectly regular rhythm.
        target = self._last_request + self.delay + random.uniform(0, self.delay * 0.5)
        if (pause := target - time.monotonic()) > 0:
            time.sleep(pause)
        self._last_request = time.monotonic()

    def get(self, url: str, archive_name: str | None = None) -> str:
        if not self.robots.can_fetch(self.user_agent, url):
            raise DisallowedByRobots(url)

        for attempt in range(self.max_retries + 1):
            self._wait()
            try:
                resp = self.client.get(url)
            except httpx.TransportError as exc:
                if attempt == self.max_retries:
                    raise
                log.warning("transport error %s on %s, retrying", exc, url)
                time.sleep(2**attempt * self.delay)
                continue
            if resp.status_code in RETRY_STATUS and attempt < self.max_retries:
                retry_after = resp.headers.get("Retry-After", "")
                backoff = float(retry_after) if retry_after.isdigit() else 2**attempt * self.delay
                log.warning("HTTP %s on %s, backing off %.0fs", resp.status_code, url, backoff)
                time.sleep(backoff)
                continue
            resp.raise_for_status()
            self.pages_fetched += 1
            if self.raw_dir and archive_name:
                self._archive(archive_name, resp.text)
            return resp.text
        raise RuntimeError("unreachable")

    def _archive(self, name: str, html: str) -> None:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        with gzip.open(self.raw_dir / f"{name}.html.gz", "wt", encoding="utf-8") as fh:
            fh.write(html)

    def clock(self) -> datetime:
        return datetime.now(UTC)

    def close(self) -> None:
        self.client.close()

    @property
    def host(self) -> str:
        return urlsplit(self.base_url).netloc


class ArchiveFetcher:
    """Drop-in replacement for PoliteFetcher that replays archived pages from disk.

    Lets you fix a parser bug and re-parse past scrapes without touching the website.
    The archive folder is named by date (data/raw/<retailer>/YYYY-MM-DD), which becomes the
    timestamp, so the snapshots land in the right week.
    """

    def __init__(self, raw_dir: Path):
        self.raw_dir = raw_dir
        self.delay = 0.0
        self.pages_fetched = 0
        self._when = datetime.combine(date.fromisoformat(raw_dir.name), dtime(12), tzinfo=UTC)

    def get(self, url: str, archive_name: str | None = None) -> str:
        path = self.raw_dir / f"{archive_name}.html.gz"
        if not path.exists():
            raise FileNotFoundError(f"{path} not archived (was --max larger than the original?)")
        self.pages_fetched += 1
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return fh.read()

    def clock(self) -> datetime:
        return self._when

    def close(self) -> None:
        pass
