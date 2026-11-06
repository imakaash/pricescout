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

## Smoke-test result (small snapshot data, 50 iterations)
| model | precision | recall | F1 |
|---|---|---|---|
| rule baseline | 0.35 | 1.00 | 0.52 |
| zero-shot | 0.45 | 0.81 | 0.58 |
| **LoRA** | 0.49 | 0.84 | **0.62** |
See `training/results.json` for the full-data run.

## Applying it
`train_matcher.py apply` scores candidate pairs (same brand + category, different shops,
some title overlap, no spec conflicts, no conflicting EANs) and writes `product_matches`
(`method = ean | model`).

```bash
python scripts/train_matcher.py all --iters 300     # data → train → eval → apply
```
