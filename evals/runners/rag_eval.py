"""Retrieval evaluation of every RAG variant on the dev set (B4 retrieval metrics).

    python -m evals.runners.rag_eval                      # all variants, all personas
    python -m evals.runners.rag_eval --variants V0 V2 best --limit 50

Writes evals/results/rag_retrieval.json with Recall@5, MRR, nDCG@10 overall, per persona
and per job type (>=4 requirements, vague, implicit-heavy), plus p50/p95 retrieval latency.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

from agent.extract import heuristic_jobspec
from evals.metrics import mean, mrr, ndcg_at_k, percentile, recall_at_k
from rag.pipeline import Query
from rag.retriever import VARIANT_MODULES, get_retriever

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "evals" / "datasets"
OUT = ROOT / "evals" / "results"
PERSONAS = ["aiml", "web", "data"]


def load_dev(persona: str, limit: int | None = None, with_gold_only: bool = True) -> list[dict]:
    rows = [json.loads(l) for l in (DS / f"dev_{persona}.jsonl").read_text().splitlines() if l.strip()]
    if with_gold_only:
        rows = [r for r in rows if r["gold"]["evidence"]]
    return rows[:limit] if limit else rows


def query_for(job: dict) -> Query:
    spec = heuristic_jobspec(job)
    return Query(job_text=job["description"], title=job["title"], requirements=[r.text for r in spec.requirements],
                 industry=spec.client_industry, category=job["category"])


def job_types(g: dict) -> list[str]:
    t = ["all"]
    if g["n_requirements"] >= 4:
        t.append("req>=4")
    if g["vague"]:
        t.append("vague")
    if g["implicit_heavy"]:
        t.append("implicit")
    t.append(f"kind:{g['kind']}")
    return t


def evaluate(variants: list[str], limit: int | None) -> dict:
    results: dict = {}
    for v in variants:
        per: dict = defaultdict(lambda: defaultdict(list))
        lat: list[float] = []
        for p in PERSONAS:
            ret = get_retriever(p, v)
            for row in load_dev(p, limit):
                q = query_for(row["job"])
                t0 = time.time()
                res = ret.run(q, k=10)
                lat.append(time.time() - t0)
                ranked = [h.item_id for h in res.items]
                gold = row["gold"]["evidence"]
                m = {"recall@5": recall_at_k(ranked, gold, 5), "mrr": mrr(ranked, gold), "ndcg@10": ndcg_at_k(ranked, gold, 10)}
                for key in [f"persona:{p}", *job_types(row["gold"])]:
                    for mk, mv in m.items():
                        per[key][mk].append(mv)
        results[v] = {k: {mk: round(mean(mv), 4) for mk, mv in d.items()} | {"n": len(d["mrr"])} for k, d in per.items()}
        results[v]["latency_s"] = {"p50": round(percentile(lat, 0.5), 4), "p95": round(percentile(lat, 0.95), 4)}
        a = results[v]["all"]
        print(f"{v:>16}  R@5={a['recall@5']:.3f}  MRR={a['mrr']:.3f}  nDCG@10={a['ndcg@10']:.3f}  p95={results[v]['latency_s']['p95']:.3f}s")
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", nargs="*", default=["V0", "V0e", *[v for v in VARIANT_MODULES if v != "V0"], "C1", "C2", "C3", "C4", "best"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default="rag_retrieval.json")
    ap.add_argument("--fresh", action="store_true", help="overwrite instead of merging")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    res: dict = {}
    if (OUT / a.out).exists() and not a.fresh:   # merge: rerunning a subset keeps the other variants
        old = json.loads((OUT / a.out).read_text())
        if old.get("meta", {}).get("limit_per_persona") == a.limit:
            res = old["results"]
    meta = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "limit_per_persona": a.limit, "embedding": "BAAI/bge-small-en-v1.5",
            "reranker": "Xenova/ms-marco-MiniLM-L-6-v2"}
    for v in a.variants:   # write after every variant so a crash never loses finished work
        res.update(evaluate([v], a.limit))
        (OUT / a.out).write_text(json.dumps({"meta": meta, "results": res}, indent=1))
    print(f"wrote {OUT / a.out}")


if __name__ == "__main__":
    main()
