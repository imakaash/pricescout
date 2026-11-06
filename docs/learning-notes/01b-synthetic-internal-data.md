# Phase 1b – Synthetic internal data for our fictional retailer

**Why:** scraping shows what competitors charge. A useful *pricing recommendation* also needs
data only the company has: cost, margin floor, stock and sales. "Match the cheapest
competitor" is bad advice if it means selling at a loss or discounting a product that's
nearly sold out.

**Who "we" are:** a **fictional** retailer, `VoltMarkt` (configurable via `OWN_COMPANY_NAME`).
MediaMarkt, Alternate and MEDIMAX are all real competitors. We deliberately don't invent
"internal" numbers for a real company, especially in a public repo.

## What is real and what is synthetic
| Real (scraped) | Synthetic (`internal_*` tables) |
|---|---|
| competitor prices, strike prices, availability, ranks, EANs | our assortment selection, cost price, margin floor, strategic role, demand, stock, sales, our price |

`internal_meta` records the company name, seed and an explicit `synthetic` flag.

## How it's generated (`internal/simulate.py`)
1. **Assortment:** real EANs from the scraped market, preferring products **several
   competitors carry** (so comparisons exist), then the best-ranked. 50 per category by default.
2. **Cost:** a category-dependent share of the real cheapest competitor price
   (smartphones 84–93%, laptops 78–89%, TVs 70–84%), so margins are thin on phones and wider
   on TVs, as in the real industry.
3. **Strategic role:** `traffic_driver` (20%, priced at or below market), `standard` (50%),
   `margin` (30%, priced above market). This sets the initial price.
4. **Demand model:**
   `expected units = base_demand × (our_price / cheapest_competitor) ^ (−elasticity)`, with
   Poisson noise. `base_demand` falls with list rank (bestsellers sell more) and elasticity
   is 2–3.5 depending on category. Being 10% more expensive than the cheapest competitor
   costs roughly 20–30% of sales.
5. **Stock:** opening stock covers 3–10 weeks; the reorder rule tops up to about 6 weeks when
   cover falls below 2 weeks. Sales can't exceed stock.
6. **Guard-rail:** the price never goes below `cost × (1 + min_margin)`.

## Why a simulation, not just random numbers?
Because a **pricing decision has to have consequences**. In Phase 4 the pricing agent's
accepted recommendations are fed back through `simulate_week(..., price_overrides=...)`, so
we can measure whether its advice would have increased revenue or margin. That makes the
agent *evaluable* rather than merely plausible.

## Determinism
Same `--seed` + same scraped data → identical internal data (tested). The random generator
for each week is seeded with `(seed, week)`, so re-simulating one week doesn't change the others.

## Commands
```bash
python scripts/generate_internal_data.py              # after each weekly scrape
python scripts/generate_internal_data.py --per-category 80 --seed 7
```
