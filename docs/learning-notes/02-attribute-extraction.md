# Phase 2 – Attribute extraction (LangChain structured output)

**Goal:** turn messy shop titles into structured specs, so we can compare *similar* products
(e.g. "55-inch Mini LED TVs") and give the matcher (Phase 3) better inputs.

## Design
| Piece | Why |
|---|---|
| Pydantic schemas per category (`extraction/schemas.py`) | One source of truth. Field descriptions double as LLM instructions; every field is optional ("not stated" = `None`, never a guess). |
| Regex baseline (`regex_extractor.py`) | Fast, free, deterministic. It's the bar the LLM must beat. |
| LLM extractor (`llm_extractor.py`) | `ChatOllama(...).with_structured_output(Schema, method="json_schema")`: Ollama constrains decoding to the JSON schema, so the output always parses. |
| Hybrid merge (`pipeline.py`) | Regex wins on **numbers** (inches, GB); the LLM wins on **names/codes/colour**. |
| Budgeted LLM runs | ~2.5 s/title on the local 8B model, so we prioritise (VoltMarkt assortment → EANs sold by several shops → products without EAN) and cache. Coverage grows run by run, like the EAN budget. |

## Evaluation without hand labels
**Cross-shop consistency:** the same EAN at two shops must yield the same attributes. For each
method and field we report *agreement* (both shops filled it in: do the values match?) and
*coverage* (how often is it filled in at all?).

First results: storage, panel and screen size agree 95–100% when extracted. **Coverage** is
the real limit: MEDIMAX titles are bare model codes (`Samsung GQ55QN72FATXZG`), so nothing
can be extracted from the title. Next improvement: use the spec description in MEDIMAX's
product-page JSON-LD, which we already archive.

## LLM mistakes we saw (and handled)
- `model_code: ""` instead of null → `clean()` normalises empty strings.
- Marketing names in `model_code` ("Galaxy S26 FE") → the prompt now separates part numbers
  from `product_line`.
- `product_line` agrees only ~60% across shops ("Galaxy S26" vs "Galaxy S26 5G"). That's
  exactly why matching needs a learned model, not string equality.

```bash
python scripts/extract_attributes.py               # regex all + ≤300 LLM titles
python scripts/extract_attributes.py --report      # consistency report
```
