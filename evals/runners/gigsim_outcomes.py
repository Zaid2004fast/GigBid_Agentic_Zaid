"""End-to-end RAG variant comparison on a FIXED GigSim job set (B4 outcome + B5 table).

For each variant the full bid graph runs (retrieval through the Portfolio MCP server uses
that variant), drafts are auto-approved by the harness, submitted to GigSim, and replies
/ hires are read back after fast-forwarding the simulated clock.

    python -m evals.runners.gigsim_outcomes --variants V0 V2 best --per-persona 30
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time

from agent.config import cfg
from evals.metrics import mean, percentile
from evals.runners.harness import ROOT, load, reset_gigsim, run_set

OUT = ROOT / "evals" / "results"


def outcome_summary(recs: list[dict]) -> dict:
    props = [r for r in recs if r.get("draft")]
    subs = [r for r in recs if r.get("submission")]
    return {
        "jobs": len(recs), "proposals": len(props), "submitted": len(subs),
        "unsupported_before": round(mean([r.get("unsupported_before") or 0 for r in props]), 4),
        "unsupported_after": round(mean([r.get("unsupported_after") or 0 for r in props]), 4),
        "partial_claims": round(mean([r.get("partial") or 0 for r in props]), 4),
        "reply_rate": round(mean([1.0 if r.get("replied") else 0.0 for r in subs]), 4),
        "hire_rate": round(mean([1.0 if r.get("hired") else 0.0 for r in subs]), 4),
        "p95_latency_s": round(percentile([r["proposal_latency_s"] for r in subs if r.get("proposal_latency_s")], .95), 3),
        "usd_per_proposal": round(mean([r.get("cost_usd", 0) for r in props]), 6),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", nargs="+", default=["V0", "V2", "V3", "V8", "best"])
    ap.add_argument("--per-persona", type=int, default=30)
    ap.add_argument("--out", default="gigsim_outcomes.json")
    a = ap.parse_args()
    # fixed set: only jobs the persona SHOULD bid on, so reply rate compares proposal quality, not decisions
    rows = []
    for p in ("aiml", "web", "data"):
        rows += [r for r in load(p) if r["gold"]["bid"]][: a.per_persona]
    res = {"meta": {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": cfg("active_profile"), "jobs": len(rows),
                    "note": "fixed set = first N gold-bid dev jobs per persona; same jobs for every variant"}, "variants": {}}
    for v in a.variants:
        reset_gigsim()
        t0 = time.time()
        recs = asyncio.run(run_set(rows, variant=v))
        s = outcome_summary(recs)
        s["wall_s"] = round(time.time() - t0, 1)
        res["variants"][v] = {"summary": s, "records": [{k: r.get(k) for k in ("job_id", "persona", "action", "replied", "hired",
                                                                                   "unsupported_before", "unsupported_after", "proposal_latency_s")} for r in recs]}
        print(f"{v:>14} reply={s['reply_rate']} hire={s['hire_rate']} unsup={s['unsupported_before']}->{s['unsupported_after']} "
              f"p95={s['p95_latency_s']}s n={s['submitted']}")
        (OUT / a.out).write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
