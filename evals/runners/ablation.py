"""Ablation of the shipped retrieval pipeline: remove one component at a time (R&D B).

Retrieval metrics come from rag_eval (best-<component> variants); end-to-end reply rate
from gigsim_outcomes on the same fixed job set.

    python -m evals.runners.ablation --limit 40 --e2e-per-persona 15
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time

from evals.runners.gigsim_outcomes import outcome_summary
from evals.runners.harness import ROOT, load, reset_gigsim, run_set
from evals.runners.rag_eval import evaluate
from rag.retriever import ABLATION_FLAGS

OUT = ROOT / "evals" / "results"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="dev jobs per persona for retrieval metrics")
    ap.add_argument("--e2e-per-persona", type=int, default=0, help="0 = skip the end-to-end reply-rate ablation")
    a = ap.parse_args()
    variants = ["best"] + [f"best-{f}" for f in ABLATION_FLAGS]
    retrieval = evaluate(variants, a.limit)
    e2e = {}
    if a.e2e_per_persona:
        rows = [r for p in ("aiml", "web", "data") for r in [x for x in load(p) if x["gold"]["bid"]][: a.e2e_per_persona]]
        for v in variants:
            reset_gigsim()
            e2e[v] = outcome_summary(asyncio.run(run_set(rows, variant=v)))
            print(v, e2e[v])
    out = {"meta": {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "limit_per_persona": a.limit, "e2e_per_persona": a.e2e_per_persona},
           "retrieval": {v: {"all": retrieval[v]["all"], "latency_s": retrieval[v]["latency_s"],
                             **{k: retrieval[v][k] for k in retrieval[v] if k.startswith("persona:") or k in ("req>=4", "vague", "implicit")}}
                         for v in variants},
           "end_to_end": e2e}
    (OUT / "ablation.json").write_text(json.dumps(out, indent=1))
    print("wrote", OUT / "ablation.json")


if __name__ == "__main__":
    main()
