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

## 7. Choosing a competitor: a reality check (2026-11-06)
We tested each candidate with our *honest* User-Agent (one or two requests each):

| Retailer | Result | Verdict |
|---|---|---|
| Saturn | Same group and platform as MediaMarkt | Skipped: prices are mostly identical |
| Cyberport, notebooksbilliger, Conrad | `403` even for `robots.txt` | Blocked |
| Euronics | `405` + CAPTCHA | Blocked |
| Otto | robots.txt permissive, but category pages serve a **Kasada** bot challenge | Blocked in practice |
| Galaxus | Products loaded client-side via an API; bot management + CAPTCHA | No clean route |
| expert | Product pages allowed, but **prices are loaded client-side from `/api/`**, which robots.txt disallows (prices vary per franchise store) | No clean route |
| Amazon.de | Conditions of Use explicitly forbid robots/data mining | Excluded |
| Kaufland, eBay, Proshop, computeruniverse, idealo, Galeria | `403` / CAPTCHA | Blocked |
| Geizhals | Reachable, but it's an aggregator of other shops' prices | Excluded (not a retailer) |
| Lidl | Allowed, but only ~45 TVs / 6 laptops / 4 phones online, mostly own-label brands | Too little overlap |
| **Alternate** | Permissive robots.txt, **publishes `/llms.txt`** (full catalogue for AI tools), server-rendered listings with prices, JSON-LD with EAN | ✅ Chosen |
| **MEDIMAX** | Electronics chain (ElectronicPartner group), robots.txt only blocks cart/account, asks for `Crawl-delay: 10`, server-rendered tiles + JSON-LD with `gtin` and `mpn` | ✅ Chosen |

**Lessons**
- robots.txt is necessary but not sufficient. A bot challenge (Kasada, Cloudflare, CAPTCHA)
  is the site saying "no" too. We **don't** work around it: no browser-UA spoofing, no
  challenge solving. That is the line between polite scraping and evasion.
- Many shops render prices **client-side**. If the only route is a robots-disallowed API,
  that retailer is out of scope.
- Signals of a bot-friendly site: permissive robots.txt, sitemaps, JSON-LD, `llms.txt`.

### Alternate design: detail pages only once
Listing pages (24/page) have price, strike price, availability, but **no EAN**. Product pages
have the EAN in JSON-LD (mislabelled as `gtin8`, though it has 13 digits). Since an EAN never
changes, we fetch a product page **only the first time we see a product**
(`store.known_eans` → `RetailerScraper.known_eans`). First run ≈ 315 requests; afterwards ≈ 15.

### MEDIMAX specifics
- Same "listing + product page once" design; the EAN logic now lives in
  `RetailerScraper.resolve_ean` and is shared by both scrapers.
- **Pagination is 0-indexed** (SAP Commerce convention). We verified this live: `page=1`
  returned 18 products with no overlap with the bare URL. Assuming 1-based pages would have
  silently skipped the top products every week.
- OLED TVs aren't under "LCD & LED", so a category can map to **several listing paths**.
- `Crawl-delay: 10` is honoured automatically: the first run takes ~65 min, weekly runs ~4 min.

### GTIN normalisation (`gtin.py`)
Every EAN passes through `normalize_gtin`: strip formatting, UPC-A (12 digits) → EAN-13,
GTIN-14 with a leading 0 → EAN-13, and **validate the check digit**. A typo can't then
create a false cross-retailer match. The tests caught that our own made-up fixture EANs were
invalid, which shows the check works.

## Commands
```bash
python scripts/scrape.py --retailer mediamarkt                    # weekly run (~3 min)
python scripts/scrape.py --retailer alternate                     # ~2 min weekly (~33 min first run)
python scripts/scrape.py --retailer medimax                       # ~4 min weekly (~65 min first run)
python scripts/scrape.py --retailer mediamarkt --category tv --max 12 --dry-run
python scripts/scrape.py --retailer mediamarkt --from-raw 2026-11-06   # re-parse, no network
pytest
```

## Next
Add competitor scrapers (same interface: `RetailerScraper.scrape_category`), then Phase 2:
LLM attribute extraction (screen size, RAM, storage…) for products where the EAN alone
can't tell us what we need.
