"""Metric helpers shared by every runner."""
from __future__ import annotations

import math


def recall_at_k(ranked: list[str], gold: dict[str, float], k: int = 5) -> float | None:
    if not gold:
        return None
    hit = sum(1 for i in ranked[:k] if i in gold)
    return hit / min(k, len(gold))


def mrr(ranked: list[str], gold: dict[str, float]) -> float | None:
    if not gold:
        return None
    for i, it in enumerate(ranked, 1):
        if it in gold:
            return 1 / i
    return 0.0


def ndcg_at_k(ranked: list[str], gold: dict[str, float], k: int = 10) -> float | None:
    if not gold:
        return None
    dcg = sum((2 ** gold.get(it, 0) - 1) / math.log2(i + 2) for i, it in enumerate(ranked[:k]))
    ideal = sorted(gold.values(), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def f1(tp: int, fp: int, fn: int) -> float:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


def prf(pairs: list[tuple[bool, bool]]) -> dict:
    """pairs of (predicted, gold)."""
    tp = sum(1 for p, g in pairs if p and g)
    fp = sum(1 for p, g in pairs if p and not g)
    fn = sum(1 for p, g in pairs if not p and g)
    tn = sum(1 for p, g in pairs if not p and not g)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1(tp, fp, fn), 4),
            "accuracy": round((tp + tn) / max(1, len(pairs)), 4), "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    i = (len(s) - 1) * p
    lo, hi = math.floor(i), math.ceil(i)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def cohen_kappa(a: list, b: list) -> float:
    labels = sorted(set(a) | set(b))
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pe = sum((a.count(lab) / n) * (b.count(lab) / n) for lab in labels)
    return (po - pe) / (1 - pe) if pe != 1 else 1.0


def mean(xs) -> float:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else 0.0
