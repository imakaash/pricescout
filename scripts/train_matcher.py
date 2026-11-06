"""Phase 3: build matching data, LoRA fine-tune Qwen3-0.6B with MLX, evaluate, apply.

  python scripts/train_matcher.py data            # labelled pairs -> training/data/*.jsonl
  python scripts/train_matcher.py train           # LoRA fine-tune (MLX, Apple Silicon)
  python scripts/train_matcher.py eval            # baseline vs zero-shot vs fine-tuned
  python scripts/train_matcher.py apply           # write product_matches
  python scripts/train_matcher.py all
"""

from __future__ import annotations

import argparse
import json
import pickle
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from pricescout.config import settings
from pricescout.db import store
from pricescout.matching import baseline
from pricescout.matching.llm_matcher import BASE_MODEL, LLMMatcher, training_text
from pricescout.matching.pairs import candidate_pairs, labelled_pairs, load_listings, split_by_group

DATA = Path("training/data")
ADAPTER = Path("training/adapters/matcher")
RESULTS = Path("training/results.json")
console = Console()

MATCHES_SCHEMA = """
CREATE TABLE IF NOT EXISTS product_matches (
    retailer_a VARCHAR, sku_a VARCHAR, retailer_b VARCHAR, sku_b VARCHAR,
    method VARCHAR,            -- ean | model
    score DOUBLE,
    matched_at TIMESTAMP,
    PRIMARY KEY (retailer_a, sku_a, retailer_b, sku_b)
);
"""


def cmd_data(db: str) -> None:
    con = store.connect(db)
    listings = load_listings(con)
    pairs = labelled_pairs(listings)
    splits = split_by_group(pairs)
    DATA.mkdir(parents=True, exist_ok=True)
    for name, rows in splits.items():
        with open(DATA / f"{name}.jsonl", "w") as fh:
            fh.writelines(json.dumps({"text": training_text(a, b, y)}, ensure_ascii=False) + "\n" for a, b, y, _ in rows)
    with open(DATA / "pairs.pkl", "wb") as fh:  # keeps Listing objects for evaluation
        pickle.dump(splits, fh)
    for name, rows in splits.items():
        console.print(f"{name}: {len(rows)} pairs ({sum(r[2] for r in rows)} positive)")


def cmd_train(iters: int) -> None:
    subprocess.run([
        sys.executable, "-m", "mlx_lm", "lora", "--model", BASE_MODEL, "--train",
        "--data", str(DATA), "--adapter-path", str(ADAPTER),
        "--iters", str(iters), "--batch-size", "8", "--num-layers", "8",
        "--learning-rate", "1e-4", "--max-seq-length", "512", "--steps-per-eval", "50",
        "--val-batches", "10", "--save-every", "100", "--seed", "0",
    ], check=True)


def _metrics(scores: list[float], labels: list[int], threshold: float) -> dict:
    tp = sum(s >= threshold and y for s, y in zip(scores, labels, strict=True))
    fp = sum(s >= threshold and not y for s, y in zip(scores, labels, strict=True))
    fn = sum(s < threshold and y for s, y in zip(scores, labels, strict=True))
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3),
            "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0, "threshold": threshold}


def _best_threshold(scores, labels) -> float:
    return max((t / 100 for t in range(5, 100, 5)), key=lambda t: _metrics(scores, labels, t)["f1"])


def cmd_eval() -> None:
    with open(DATA / "pairs.pkl", "rb") as fh:
        splits = pickle.load(fh)
    contenders = {"rule baseline": lambda: baseline.score}
    contenders["Qwen3-0.6B zero-shot"] = lambda: LLMMatcher().p_match
    if (ADAPTER / "adapters.safetensors").exists():
        contenders["Qwen3-0.6B + LoRA"] = lambda: LLMMatcher(adapter_path=str(ADAPTER)).p_match

    results = {}
    for name, make in contenders.items():
        fn = make()
        val = [(fn(a, b), y) for a, b, y, _ in splits["valid"]]
        thr = _best_threshold([s for s, _ in val], [y for _, y in val])  # tuned on valid only
        test = [(fn(a, b), y) for a, b, y, _ in splits["test"]]
        results[name] = _metrics([s for s, _ in test], [y for _, y in test], thr)
        console.print(f"{name}: {results[name]}")

    t = Table(title=f"Matching on held-out test set ({len(splits['test'])} pairs)")
    for col in ["model", "precision", "recall", "F1", "threshold"]:
        t.add_column(col)
    for name, m in results.items():
        t.add_row(name, str(m["precision"]), str(m["recall"]), str(m["f1"]), str(m["threshold"]))
    console.print(t)
    RESULTS.write_text(json.dumps({"evaluated_at": datetime.now().isoformat(), **results}, indent=2))


def cmd_apply(db: str) -> None:
    con = store.connect(db)
    con.execute(MATCHES_SCHEMA)
    results = json.loads(RESULTS.read_text())
    thr = results["Qwen3-0.6B + LoRA"]["threshold"]
    matcher = LLMMatcher(adapter_path=str(ADAPTER))
    now = datetime.now()
    listings = load_listings(con)
    rows, scored, model_hits = [], 0, []
    for a, b in candidate_pairs(listings, min_jaccard=0.25):
        if a.key > b.key:
            a, b = b, a
        if a.ean and a.ean == b.ean:
            rows.append((*a.key, *b.key, "ean", 1.0, now))
            continue
        if a.ean and b.ean:
            continue  # different valid EANs: different products by definition
        if baseline.conflicts(a, b) or baseline.ambiguous(a, b):
            continue  # hard rules the model can't be trusted with
        p = matcher.p_match(a, b)
        scored += 1
        if p >= thr:
            model_hits.append((p, a, b))
    # One-to-one: each listing gets at most one partner per other shop (best score first).
    # Without this, a vague listing ('MacBook Pro 14 CTO') matched many configurations.
    taken: set[tuple] = set()
    for p, a, b in sorted(model_hits, key=lambda h: -h[0]):
        if (a.key, b.retailer) in taken or (b.key, a.retailer) in taken:
            continue
        taken |= {(a.key, b.retailer), (b.key, a.retailer)}
        rows.append((*a.key, *b.key, "model", round(p, 4), now))
    con.execute("DELETE FROM product_matches")
    if rows:
        con.executemany("INSERT INTO product_matches VALUES (?,?,?,?,?,?,?)", rows)
    n_model = sum(r[4] == "model" for r in rows)
    console.print(f"product_matches: {len(rows) - n_model} by EAN, {n_model} by model "
                  f"({scored} pairs scored)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("step", choices=["data", "train", "eval", "apply", "all"])
    ap.add_argument("--iters", type=int, default=300)
    ap.add_argument("--db", default=settings.db_path)
    args = ap.parse_args()
    if args.step in ("data", "all"):
        cmd_data(args.db)
    if args.step in ("train", "all"):
        cmd_train(args.iters)
    if args.step in ("eval", "all"):
        cmd_eval()
    if args.step in ("apply", "all"):
        cmd_apply(args.db)


if __name__ == "__main__":
    main()
