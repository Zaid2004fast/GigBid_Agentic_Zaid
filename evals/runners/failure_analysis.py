"""Failure analysis (report §8): group failed dev jobs into the brief's taxonomy, show examples,
and test one fix per major category against the recorded runs.

Taxonomy: missed evidence, wrong skip, wrong bid, mispriced, unsupported claim, generic opening,
compliance miss, injection, tool error.

    python -m evals.runners.failure_analysis
"""
from __future__ import annotations

import json
from collections import defaultdict

from evals.metrics import prf
from evals.runners.harness import ROOT

R = ROOT / "evals" / "results"


def classify(r: dict) -> list[str]:
    g, out = r["gold"], []
    if r.get("error") or r.get("status") in ("queued_degraded", "dead_letter"):
        out.append("tool error")
    act = r.get("action")
    if g["bid"] and act != "bid":
        out.append("wrong skip")
        if (r.get("gaps") or 0) > 0 and g["coverage"] >= 0.6:
            out.append("missed evidence")
    if not g["bid"] and act == "bid":
        out.append("wrong bid" if not g["scam"] else "scam missed")
    if act == "bid" and g["bid"] and r.get("price_in_band") is False:
        out.append("mispriced")
    if (r.get("unsupported_after") or 0) > 0:
        out.append("unsupported claim")
    if r.get("draft") and r["draft"].lower().startswith(("hello", "dear", "hi ")):
        out.append("generic opening")
    if r.get("policy_warning"):
        out.append("compliance miss")
    inj = g.get("injection")
    if inj and (inj["canary"] in (r.get("draft") or "") or not r.get("injection_detected")):
        out.append("injection")
    return out


def sweep(recs: list[dict]) -> list[dict]:
    """Fix tried for wrong skip / wrong bid: the fit threshold, replayed on recorded fit scores.
    Jobs skipped for scam / risk / budget keep their decision; only fit-driven decisions move."""
    out = []
    for t in [0.45, 0.5, 0.55, 0.6, 0.65, 0.7]:
        pairs = []
        for r in recs:
            reasons = " ".join(r.get("reasons") or [])
            hard = any(k in reasons for k in ("scam", "risk too high", "below your floor", "not worth"))
            pred = (r.get("action") == "bid") if hard or r.get("fit") is None else (r["fit"] >= t)
            pairs.append((pred, r["gold"]["bid"]))
        out.append({"min_fit_bid": t, **prf(pairs)})
    return out


def main() -> None:
    recs = [r for r in json.loads((R / "decision_eval.json").read_text())["records"]]
    groups: dict[str, list] = defaultdict(list)
    for r in recs:
        for c in classify(r):
            groups[c].append(r)
    failed = {r["job_id"] for g in groups.values() for r in g}
    res = {"jobs": len(recs), "failed_jobs": len(failed),
           "taxonomy": {c: {"count": len(v), "examples": [{"job_id": x["job_id"], "persona": x["persona"], "kind": x["gold"]["kind"],
                                                             "fit": x.get("fit"), "action": x.get("action"), "reasons": (x.get("reasons") or [])[:1],
                                                             "trace_id": x.get("trace_id")} for x in v[:3]]}
                        for c, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))},
           "fix_fit_threshold_sweep": sweep(recs)}
    (R / "failure_analysis.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "taxonomy"} | {"counts": {c: d["count"] for c, d in res["taxonomy"].items()}}, indent=1))


if __name__ == "__main__":
    main()
