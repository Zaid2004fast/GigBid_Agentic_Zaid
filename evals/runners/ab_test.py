"""Signature extension X2 - proposal experiments: two proposal strategies as an A/B test in
GigSim with a significance test on reply rate.

A = evidence_first (opening states the client's need, evidence follows)
B = question_first (opening is a pointed question about the client's riskiest requirement)

Design: paired - every job gets BOTH proposals, each in a fresh GigSim state, so client
noise is matched. Reported: reply rates, two-proportion z-test, McNemar's exact test on the
discordant pairs (the right test for paired data), and the Bayesian P(B > A) under Beta(1,1).

    python -m evals.runners.ab_test --per-persona 60
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import time

from evals.runners.harness import ROOT, load, reset_gigsim, run_set

OUT = ROOT / "evals" / "results"


def two_prop_z(s1: int, n1: int, s2: int, n2: int) -> tuple[float, float]:
    p1, p2 = s1 / n1, s2 / n2
    p = (s1 + s2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2)) or 1e-9
    z = (p2 - p1) / se
    pval = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return round(z, 4), round(pval, 5)


def mcnemar_exact(b: int, c: int) -> float:
    """b = A replied & B not, c = B replied & A not. Two-sided exact binomial p-value."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return round(min(1.0, 2 * tail), 5)


def p_b_better(sa: int, na: int, sb: int, nb: int, draws: int = 20000, seed: int = 7) -> float:
    rng = random.Random(seed)
    wins = sum(rng.betavariate(1 + sb, 1 + nb - sb) > rng.betavariate(1 + sa, 1 + na - sa) for _ in range(draws))
    return round(wins / draws, 4)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=60)
    a = ap.parse_args()
    rows = [r for p in ("aiml", "web", "data") for r in [x for x in load(p) if x["gold"]["bid"]][: a.per_persona]]
    results = {}
    for arm, strat in (("A", "evidence_first"), ("B", "question_first")):
        reset_gigsim()
        recs = asyncio.run(run_set(rows, strategy=strat))
        results[arm] = {r["job_id"]: bool(r.get("replied")) for r in recs if r.get("submission")}
    common = sorted(set(results["A"]) & set(results["B"]))
    sa = sum(results["A"][j] for j in common)
    sb = sum(results["B"][j] for j in common)
    n = len(common)
    b = sum(1 for j in common if results["A"][j] and not results["B"][j])
    c = sum(1 for j in common if results["B"][j] and not results["A"][j])
    z, p = two_prop_z(sa, n, sb, n)
    out = {"meta": {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "pairs": n, "A": "evidence_first", "B": "question_first"},
           "reply_rate": {"A": round(sa / n, 4) if n else 0, "B": round(sb / n, 4) if n else 0},
           "two_proportion_z": {"z": z, "p_value": p}, "mcnemar_exact": {"A_only": b, "B_only": c, "p_value": mcnemar_exact(b, c)},
           "bayes_p_B_better": p_b_better(sa, n, sb, n),
           "decision": "", "pairs_detail": {j: [results["A"][j], results["B"][j]] for j in common}}
    pm = out["mcnemar_exact"]["p_value"]
    out["decision"] = (f"B {'beats' if sb > sa else 'does not beat'} A; McNemar p={pm} "
                       f"({'significant' if pm < 0.05 else 'not significant'} at 0.05)")
    (OUT / "ab_test.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "pairs_detail"}, indent=1))


if __name__ == "__main__":
    main()
