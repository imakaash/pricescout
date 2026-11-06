# Phase 1 – Polite scrapers + data model

**Goal:** collect a weekly price snapshot of TVs, laptops and smartphones from MediaMarkt and
store it in a schema the later phases (matching, agents, KPIs) can build on.

## 1. Look before you scrape
Before writing any scraper code, we explored the site by hand with `curl`:

1. **`robots.txt`**: product and category pages are allowed; `/de/list/*_*` and most internal
   APIs are disallowed. It also lists **sitemaps**.
2. **Terms of use** (`/de/legal/nutzungsbedingungen`): no clause about crawlers or scraping.
   (Not legal advice. Re-check before scraping each new retailer.)
3. **Sitemaps** list every product URL, but each file has 10,000 URLs (mostly accessories).
   Not useful for "top TVs".
4. **A product page**: contains **JSON-LD** (schema.org `Product`) with the EAN, brand,
   price and seller.
5. **A category page**: contains JSON-LD `ItemList` **and** `window.__PRELOADED_STATE__`, the
   app's GraphQL cache (Apollo), with EAN, price, strike price, shipping, seller and stock for
   all 12 products on the page.

**Lesson:** look for *structured data* first (JSON-LD, embedded state, internal JSON). It is
more stable than CSS selectors and often holds more than the visible page. Here it cut the
request count by 12×: 300 products = **27 requests per week**.

## 2. Being polite (`scrapers/http.py`, `scrapers/robots.py`)
| Technique | Why |
|---|---|
| Honest User-Agent | The site can identify and contact or block us. We don't pretend to be a browser. |
| robots.txt check on every URL | Respect the site's wishes, enforced in code rather than by memory. |
| ≥5 s delay + random jitter | Negligible load; jitter avoids a mechanical rhythm. |
| Retry only on 429/5xx with exponential backoff, honour `Retry-After` | When the server says "slow down", we slow down. |
| Archive every raw page (gzip) | Fix parser bugs by **re-parsing** (`--from-raw`) instead of re-fetching. |

**Gotcha:** Python's `urllib.robotparser` ignores `*` and `$` wildcards, so it would have
missed `Disallow: *de/list/*_*`. We wrote a small RFC 9309 parser (longest match wins,
Allow wins ties) with tests.

## 3. Parsing (`scrapers/mediamarkt.py`)
- `__PRELOADED_STATE__` is a **JavaScript** object, not JSON: it contains `undefined`.
  We replace it with `null`, then use `json.JSONDecoder().raw_decode`, which stops at the end
  of the object and ignores the JavaScript that follows.
- The Apollo cache is *normalised*: entries are keyed by type + id
  (`CofrPriceFeature:{"id":"Media:de:3047279",...}`), and we join them by SKU.
- Fallback: if the Apollo data for a product is missing, use the JSON-LD price.

## 4. Data model (`models.py`, `db/store.py`)
```
products         (retailer, retailer_sku) PK   title, brand, ean, category, first/last_seen
price_snapshots  (retailer, retailer_sku, week) PK   price, strike_price(+type), shipping,
                                                     seller, is_marketplace, availability, rank…
scrape_runs      run_id PK   pages, offers, errors, status
```
- **Grain = one row per product per ISO week.** Re-running a scrape in the same week
  *overwrites* that week's row (idempotent), so retries never create duplicates.
- `products` is upserted with `ON CONFLICT DO UPDATE`: keep `first_seen`, update `last_seen`,
  and never let a missing EAN erase a known one (`COALESCE`).
- `scrape_runs` gives the Phase 4 data-quality agent something to check ("did this week's run
  succeed? fewer offers than usual?").

## 5. Bugs the data-quality check caught
Looking at aggregates *right after* the first run found two bugs:
1. **All marketplace offers labelled "MediaMarkt".** The seller field is `sellerName`, not `name`,
   so the code fell back to the default. That would have badly skewed price comparisons. Fix:
   correct key, and a marketplace offer may never default to "MediaMarkt".
2. **99 rows from 100 offers.** Rankings shift between page requests, so a product appeared
   on two pages. Fix: de-duplicate SKUs within a run.

Both were fixed and **re-parsed from the archive with zero new requests**.

## 6. First observations (2026-11-06, 300 products)
- 100% EAN coverage, which will make cross-retailer matching (Phase 3) much easier.
- ~29% of offers are **marketplace** sellers, many of them refurbished resellers (AfB,
  cybernerds). KPIs must separate these from MediaMarkt's own prices.
- Strike prices: mostly **RRP/UVP** (manufacturer's recommended price), some **LOP** (lowest
  price in the last 30 days, required by the EU Omnibus directive). The average discount
  against UVP for TVs is ~46%, so "% off UVP" says little about real promotions. LOP is the
  more honest signal.

## Commands
```bash
python scripts/scrape.py --retailer mediamarkt                    # weekly run (~3 min)
python scripts/scrape.py --retailer mediamarkt --category tv --max 12 --dry-run
python scripts/scrape.py --retailer mediamarkt --from-raw 2026-11-06   # re-parse, no network
pytest
```

## Next
Add competitor scrapers (same interface: `RetailerScraper.scrape_category`), then Phase 2:
LLM attribute extraction (screen size, RAM, storage…) for products where the EAN alone
can't tell us what we need.
