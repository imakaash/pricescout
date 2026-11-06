# Phase 4 – LangGraph multi-agent weekly analysis

```
START → data_quality ─┬→ promotions → pricing → human_review → report_writer → END
                      └──────── (no data this week) ──────────→ report_writer
```

## The core rule: code decides, the LLM explains
| Node | Deterministic part | LLM part |
|---|---|---|
| data_quality | run status, EAN coverage, offer-count drops, competitor coverage | – |
| promotions | LOP promos, big UVP discounts, week-over-week changes | – |
| pricing | rules + demand model → new price, expected profit Δ, margin floor | one-sentence rationale per recommendation |
| human_review | `interrupt()` pauses the graph; decisions are written to the DB | – |
| report_writer | all tables, the 3 summary bullets, verified fact sentences | 1–2 sentences of commentary per section |

## What went wrong first (worth remembering)
1. **"Write the whole report" prompt:** the 8B model ignored the structure, fixated on one
   section, and told the reader to "approve all changes". Fix: **code renders the
   structure and numbers**; the LLM fills a Pydantic `Narrative` schema.
2. **Misreading tables:** it claimed VoltMarkt was "cheapest everywhere" while it ranked
   last. Fix: `key_facts()` turns tables into **verified sentences** ("voltmarkt is cheapest
   on 38 of 150… rank 4 of 4"), and the LLM only rephrases.
3. **Combining facts wrongly in the summary:** the summary is now chosen by code.
4. **Guardrail:** `grounded()` drops any LLM sentence containing a number not present in the
   facts. It's cheap and catches invented numbers (not every wrong claim, which is why the
   prompt also bans unstated superlatives).

## Pricing rules (`agents/pricing.py`)
- `traffic_driver_not_cheapest`: key products must match the cheapest competitor (may cost
  profit, by design).
- `low_stock_raise`: <2 weeks of cover → earn more per unit.
- `overstock_close_gap` / `far_above_market`: only if the demand model says profit improves.
- Never below `cost × (1 + min_margin)`.

**Modelling insight:** with elasticities of 2–3 the model said price cuts never pay off, since
the profit-optimal margin ≈ 1/elasticity ≈ 40%. For *identical* products across shops,
shoppers switch easily, so elasticity is high (5–14), consistent with real 5–20% margins.

## Human in the loop, two ways
- `python scripts/weekly_analysis.py --review` → terminal approve/reject via `interrupt()` +
  `Command(resume=...)` (needs a checkpointer, here `MemorySaver`).
- Batch (scheduled) runs leave recommendations `pending` → approve in the dashboard.
- Approved prices feed the next week's simulation (`price_overrides`), so impact is measurable.
