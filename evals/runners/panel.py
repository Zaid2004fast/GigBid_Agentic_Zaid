"""Blind pairwise human panel (B4): classmates compare anonymised proposals.

    python -m evals.runners.panel make --n 20     # -> evals/datasets/pairwise_panel.csv (+ hidden key)
    # raters fill a copy with a 'vote' column (A or B) -> evals/datasets/pairwise_panel_votes.csv
    python -m evals.runners.panel score           # win rate of the shipped writer + exact sign test

Pairs: the shipped claim-plan writer vs the naive experience-list writer, same job, same
evidence, order randomised per row. Raters never see which system wrote which.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random

from evals.runners.harness import ROOT

DS = ROOT / "evals" / "datasets"


def make(n: int) -> None:
    import asyncio

    from agent.extract import heuristic_jobspec
    from agent.handoffs import PriceQuote
    from agent.nodes.writer import _facts, claim_plan, deterministic_letter
    from evals.runners.claims_eval import fit_for, naive_letter
    from rag.corpus import get_corpus
    from rag.verify import corpus_resolvers, strip_citations

    rng = random.Random(4016)
    rows, key = [], {}

    async def build():
        for p in ("aiml", "web", "data"):
            resolve, _ = corpus_resolvers(get_corpus(p))
            for r in [x for x in __import__("evals.runners.harness", fromlist=["load"]).load(p) if x["gold"]["bid"]][: (n + 2) // 3]:
                job = r["job"]
                spec = heuristic_jobspec(job)
                fit = fit_for(p, job)
                plan, labels = claim_plan(fit)
                facts = {}
                for pl in plan:
                    d = (await resolve([labels[pl["label"]]]) or [{"text": ""}])[0]
                    facts[pl["label"]] = {**_facts(d["text"]), "industry": d.get("industry")}
                price = PriceQuote(job_id=job["id"], amount=500, budget_type="fixed", connects_cost=6, floor=100, rationale="panel")
                shipped, _ = deterministic_letter(spec, fit, price, plan, facts, "evidence_first", [], {})
                naive, _ = naive_letter(spec, fit, p)
                a_is_shipped = rng.random() < 0.5
                rid = f"p{len(rows):02d}"
                key[rid] = "A" if a_is_shipped else "B"
                pa, pb = (shipped, naive) if a_is_shipped else (naive, shipped)
                rows.append({"id": rid, "job": f"{job['title']} - {job['description'][:400]}", "proposal_A": strip_citations(pa),
                             "proposal_B": strip_citations(pb), "vote": ""})
    asyncio.run(build())
    with (DS / "pairwise_panel.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (DS / "pairwise_panel_key.json").write_text(json.dumps(key, indent=1))
    print(f"wrote {len(rows)} pairs -> {DS / 'pairwise_panel.csv'}")


def score() -> None:
    key = json.loads((DS / "pairwise_panel_key.json").read_text())
    votes = list(csv.DictReader((DS / "pairwise_panel_votes.csv").open(encoding="utf-8")))
    wins = sum(1 for v in votes if v["vote"].strip().upper() == key[v["id"]])
    n = sum(1 for v in votes if v["vote"].strip().upper() in ("A", "B"))
    k = min(wins, n - wins)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n) if n else 1.0
    from collections import defaultdict
    by = defaultdict(dict)
    for v in votes:
        by[v.get("rater", "r")][v["id"]] = v["vote"].strip().upper()
    raters = list(by)
    pairs = [(a, b) for i, a in enumerate(raters) for b in raters[i + 1:]]
    agree = [sum(by[a][k] == by[b].get(k) for k in by[a]) / len(by[a]) for a, b in pairs]
    res = {"votes": n, "raters": len(raters), "shipped_wins": wins, "win_rate": round(wins / n, 4) if n else None,
           "sign_test_p": p, "sign_test_p_text": "< 0.001" if p < 0.001 else f"{p:.3f}",
           "per_rater_win_rate": [round(sum(key[k] == x for k, x in by[r].items()) / len(by[r]), 4) for r in raters],
           "mean_pairwise_agreement": round(sum(agree) / len(agree), 4) if agree else None}
    (ROOT / "evals" / "results" / "pairwise_panel.json").write_text(json.dumps(res, indent=1))
    print(res)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["make", "score"])
    ap.add_argument("--n", type=int, default=21)
    a = ap.parse_args()
    make(a.n) if a.cmd == "make" else score()
