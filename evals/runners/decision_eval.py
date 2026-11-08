"""Decision + proposal + outcome evaluation of the shipped configuration (B4).

    python -m evals.runners.decision_eval --per-persona 200            # full dev set
    python -m evals.runners.decision_eval --per-persona 10 --out smoke.json --thresholds   # CI smoke

Writes bid/skip F1, scam precision/recall, price-in-band, unsupported claims before/after
verification, critic loops, compliance hits, GigSim reply/hire rate, latency p50/p95, tokens
and USD per job analysed and per proposal, broken down by persona and job kind.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

from agent.config import cfg
from evals.metrics import mean, percentile, prf
from evals.runners.harness import ROOT, load, reset_gigsim, run_set

OUT = ROOT / "evals" / "results"
THRESHOLDS = {"bid_f1_min": 0.70, "unsupported_after_max": 0.10, "scam_recall_min": 0.70}


def summarise(recs: list[dict]) -> dict:
    ok = [r for r in recs if not r.get("error")]
    bids = [r for r in ok if r.get("action") == "bid"]
    props = [r for r in ok if r.get("draft")]
    subs = [r for r in ok if r.get("submission")]
    gold_bid_and_bid = [r for r in bids if r["gold"]["bid"]]
    s = {
        "n": len(recs), "errors": len(recs) - len(ok),
        "bid_skip": prf([(r.get("action") == "bid", r["gold"]["bid"]) for r in ok]),
        "scam": prf([((r.get("scam_p") or 0) >= cfg("decision.scam_block", 0.6), r["gold"]["scam"]) for r in ok]),
        "price_in_band": round(mean([1.0 if r.get("price_in_band") else 0.0 for r in gold_bid_and_bid]), 4),
        "unsupported_before_per_proposal": round(mean([r.get("unsupported_before") or 0 for r in props]), 4),
        "unsupported_after_per_proposal": round(mean([r.get("unsupported_after") or 0 for r in props]), 4),
        "claims_per_proposal": round(mean([r.get("claims") or 0 for r in props]), 3),
        "critic_rounds_mean": round(mean([r.get("critic_rounds") or 0 for r in props]), 3),
        "critic_loop_rate": round(mean([1.0 if (r.get("critic_rounds") or 0) > 1 else 0.0 for r in props]), 4),
        "compliance_hits": sum(len(r.get("compliance_issues") or []) for r in props),
        "reply_rate": round(mean([1.0 if r.get("replied") else 0.0 for r in subs]), 4),
        "hire_rate": round(mean([1.0 if r.get("hired") else 0.0 for r in subs]), 4),
        "submitted": len(subs),
        "latency_job_s": {"p50": round(percentile([r["latency_s"] for r in ok], .5), 3), "p95": round(percentile([r["latency_s"] for r in ok], .95), 3)},
        "latency_proposal_s": {"p50": round(percentile([r["proposal_latency_s"] for r in subs if r.get("proposal_latency_s")], .5), 3),
                               "p95": round(percentile([r["proposal_latency_s"] for r in subs if r.get("proposal_latency_s")], .95), 3)},
        "tokens_per_job": round(mean([r.get("tokens", 0) for r in ok]), 1),
        "usd_per_job": round(mean([r.get("cost_usd", 0) for r in ok]), 6),
        "usd_per_proposal": round(mean([r.get("cost_usd", 0) for r in props]), 6),
        "injection": {"jobs": sum(1 for r in ok if r["gold"].get("injection")),
                      "detected": sum(1 for r in ok if r["gold"].get("injection") and r.get("injection_detected")),
                      "false_alarms": sum(1 for r in ok if not r["gold"].get("injection") and r.get("injection_detected"))},
    }
    return s


def breakdown(recs: list[dict]) -> dict:
    out = {}
    for key, fn in (("persona", lambda r: r["persona"]), ("kind", lambda r: r["gold"]["kind"])):
        groups: dict[str, list] = {}
        for r in recs:
            groups.setdefault(fn(r), []).append(r)
        out[key] = {k: summarise(v) for k, v in groups.items()}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=200)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--variant", default=None)
    ap.add_argument("--strategy", default="evidence_first")
    ap.add_argument("--out", default="decision_eval.json")
    ap.add_argument("--thresholds", action="store_true", help="exit 1 if CI gates fail")
    ap.add_argument("--concurrency", type=int, default=4)
    a = ap.parse_args()
    rows = [r for p in ("aiml", "web", "data") for r in load(p, a.per_persona, a.offset)]
    reset_gigsim()
    t0 = time.time()
    recs = asyncio.run(run_set(rows, variant=a.variant, strategy=a.strategy, concurrency=a.concurrency))
    res = {"meta": {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": cfg("active_profile"), "variant": a.variant or cfg("rag.variant"),
                    "strategy": a.strategy, "jobs": len(rows), "wall_s": round(time.time() - t0, 1)},
           "summary": summarise(recs), "breakdown": breakdown(recs), "records": recs}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / a.out).write_text(json.dumps(res, indent=1, default=str))
    s = res["summary"]
    print(f"jobs={s['n']} errors={s['errors']} bidF1={s['bid_skip']['f1']} scamP/R={s['scam']['precision']}/{s['scam']['recall']} "
          f"inBand={s['price_in_band']} unsup {s['unsupported_before_per_proposal']}->{s['unsupported_after_per_proposal']} "
          f"reply={s['reply_rate']} hire={s['hire_rate']} p95job={s['latency_job_s']['p95']}s")
    if a.thresholds:
        fails = []
        if s["bid_skip"]["f1"] < THRESHOLDS["bid_f1_min"]:
            fails.append(f"bid/skip F1 {s['bid_skip']['f1']} < {THRESHOLDS['bid_f1_min']}")
        if s["unsupported_after_per_proposal"] > THRESHOLDS["unsupported_after_max"]:
            fails.append(f"unsupported claims {s['unsupported_after_per_proposal']} > {THRESHOLDS['unsupported_after_max']}")
        if s["scam"]["recall"] < THRESHOLDS["scam_recall_min"]:
            fails.append(f"scam recall {s['scam']['recall']} < {THRESHOLDS['scam_recall_min']}")
        if fails:
            print("EVAL GATE FAILED: " + "; ".join(fails))
            sys.exit(1)
        print("eval gates passed")


if __name__ == "__main__":
    main()
