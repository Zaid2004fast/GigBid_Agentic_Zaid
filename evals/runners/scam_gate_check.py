"""Measures the hard-stop fix for missed scams (failure analysis round 2) with the Risk
Assessor's deterministic signals on ALL dev jobs: how many scams the policy gate adds, and how
many legitimate jobs it would wrongly skip.

    python -m evals.runners.scam_gate_check
"""
from __future__ import annotations

import json

from agent.config import cfg
from agent.nodes.risk import assess
from evals.runners.harness import ROOT, load


def main() -> None:
    clients = {c["id"]: c for c in json.loads((ROOT / "gigsim" / "seed" / "clients.json").read_text())}
    hard = set(cfg("decision.hard_skip_flags", []))
    out = {"scams": 0, "caught_before": 0, "caught_after": 0, "legit": 0, "legit_blocked_before": 0, "legit_blocked_after": 0}
    for p in ("aiml", "web", "data"):
        for r in load(p):
            rep = assess(r["job"], clients.get(r["job"]["client_id"], {}))
            before = rep.scam_probability >= cfg("decision.scam_block", 0.6)
            after = before or any(f.severity == "high" and f.code in hard for f in rep.flags)
            if r["gold"]["scam"]:
                out["scams"] += 1
                out["caught_before"] += before
                out["caught_after"] += after
            else:
                out["legit"] += 1
                out["legit_blocked_before"] += before
                out["legit_blocked_after"] += after
    out["recall_before"] = round(out["caught_before"] / out["scams"], 4)
    out["recall_after"] = round(out["caught_after"] / out["scams"], 4)
    (ROOT / "evals" / "results" / "scam_gate_check.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
