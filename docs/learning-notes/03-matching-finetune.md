# Phase 3 – Fine-tuning a product-matching model (LoRA, MLX)

**Goal:** decide "same product?" for listings that don't share an EAN (missing EAN,
refurbished-style variants, different colour codes), so cross-shop overlap grows beyond
exact EAN matches.

## Free labels
- **Positives:** the same EAN at two different shops.
- **Hard negatives:** same brand and category, *different* EAN, but similar titles (55" vs 65"
  of one series, 128 GB vs 256 GB, different colour). Easy negatives teach nothing.
- **Leakage guard:** train/valid/test are split **by EAN group**, so no product seen in
  training appears in the test set.

## Contenders (same held-out test set)
1. **Rule baseline:** title token overlap + "spec conflict ⇒ no match" + model-code containment.
2. **Qwen3-0.6B base, zero-shot.**
3. **Qwen3-0.6B + LoRA** fine-tuned with `mlx_lm lora` on the Mac's GPU.

The LLM is scored by **next-token probability** of `" yes"` vs `" no"` (`llm_matcher.py`),
not by generated text, which gives a confidence score we can threshold. The threshold is
tuned on **valid**, and metrics are reported on **test**.

## Why LoRA?
Only ~0.24% of parameters are trained (1.4M of 596M): small adapters on the attention
layers. Training takes minutes on an M-series GPU, and the adapter is a few MB.

## Results (full data, 2026-11-06, 300 iterations ≈ 6 min on an M5)
Held-out test set: 228 pairs (60 positive), split by EAN group.

| model | precision | recall | F1 |
|---|---|---|---|
| rule baseline | 0.84 | 0.43 | 0.57 |
| Qwen3-0.6B zero-shot | 0.46 | 0.68 | 0.55 |
| **Qwen3-0.6B + LoRA** | **0.82** | **0.82** | **0.82** |

## Lesson: test-set metrics ≠ real-world precision (distribution shift)
Applied to real candidate pairs, the first run produced **1,909** "matches", and a random
spot check showed many were wrong: 98" vs 85" TVs, `GQ48S95H` vs `GQ-83S99H`, and one vague
"MacBook Pro 14 CTO" matched to every configuration. Why: the test set was 1:3
positive/negative and built from products *with* EANs, while real candidates are mostly
negatives and often vaguer listings.

The fix was **hard rules in front of the model** (`matching/baseline.py`), for facts a model
shouldn't be trusted with:
1. Screen size from TV model codes (`GQ48S95H` → 48").
2. Model codes must agree when both are known (title fallback for TVs).
3. Variant words must agree (`Pro`/`Pro XL`/`FE`/`Plus` are different phones).
4. Ambiguous listings (no storage stated) are not matched.
5. One-to-one assignment per shop pair (best score wins).

Result: **119 model matches** (plus 191 EAN pairs). A random spot check now looks about 92%
correct, mostly listings that differ only in the colour one shop omits. Always spot-check a
model on the data you'll actually apply it to.

## Applying it
`train_matcher.py apply` scores candidate pairs (same brand + category, different shops,
some title overlap, no spec conflicts, no conflicting EANs) and writes `product_matches`
(`method = ean | model`).

```bash
python scripts/train_matcher.py all --iters 300     # data → train → eval → apply
```
