"""Small-LLM matcher (Qwen3-0.6B base) scored by next-token probability, optionally with LoRA.

Prompt -> the model continues with " yes" or " no". Instead of generating text we read the
logits for those two tokens and turn them into P(match), which gives a threshold-able score.
"""

from __future__ import annotations

import math

from pricescout.matching.pairs import Listing

BASE_MODEL = "Qwen/Qwen3-0.6B-Base"

PROMPT = (
    "Decide whether two shop listings are the exact same product "
    "(same model, size, storage and colour).\n"
    "A: {a}\nB: {b}\nSame product?"
)


def prompt(a: Listing, b: Listing) -> str:
    return PROMPT.format(a=a.text()[:400], b=b.text()[:400])


def training_text(a: Listing, b: Listing, label: int) -> str:
    return prompt(a, b) + (" yes" if label else " no")


class LLMMatcher:
    def __init__(self, model: str = BASE_MODEL, adapter_path: str | None = None):
        import mlx.core as mx
        from mlx_lm import load

        self.mx = mx
        self.model, self.tok = load(model, adapter_path=adapter_path)
        self.yes = self.tok.encode(" yes")[0]
        self.no = self.tok.encode(" no")[0]

    def p_match(self, a: Listing, b: Listing) -> float:
        ids = self.mx.array([self.tok.encode(prompt(a, b))])
        logits = self.model(ids)[0, -1]
        y, n = logits[self.yes].item(), logits[self.no].item()
        return 1 / (1 + math.exp(n - y))  # softmax over {yes, no}
