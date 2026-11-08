"""Change request (2 Nov "platform policy update") - how cheaply GigBid absorbs it.

GigSim policy v2: (1) Connects cost is tiered by job budget; (2) proposals with any
unanswered screening question are rejected.

Measured on dev jobs with screening questions, BEFORE and AFTER our config change:
  * Connects-cost prediction errors (what the approval screen promised vs what GigSim charges)
  * proposals with a missing screening answer (simulated: an edit blanked one answer) that
    reach GigSim and get rejected there, vs blocked by Compliance before approval
plus the size of the diff (lines changed, files touched, code files touched).

    python -m evals.runners.change_request --n 60
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time

import yaml

from agent import policy_engine
from agent.config import ROOT, cfg
from agent.nodes.decision import connects_cost
from evals.runners.harness import load

OUT = ROOT / "evals" / "results"
P7 = "P7-screening"


def rules_without_p7() -> dict:
    r = yaml.safe_load((ROOT / "data" / "policy_pack" / "rules.yaml").read_text())
    return {**r, "rules": [x for x in r["rules"] if x["id"] != P7]}


def diff_stats(commit: str | None) -> dict:
    if not commit:
        return {}
    try:
        out = subprocess.run(["git", "show", "--numstat", "--format=", commit], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except Exception:  # noqa: BLE001
        return {}
    files = [line.split("\t") for line in out.splitlines() if line.strip()]
    return {"commit": commit, "files": [f[2] for f in files], "lines_added": sum(int(f[0]) for f in files),
            "lines_removed": sum(int(f[1]) for f in files), "code_files_touched": [f[2] for f in files if f[2].endswith(".py")]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--commit", default=None, help="the change-request commit, for diff stats")
    a = ap.parse_args()
    from gigsim.app import POLICIES, W, connects_cost as gigsim_cost
    W.policy_version = 2
    policy_v2 = POLICIES[2]
    jobs = [r["job"] for p in ("aiml", "web", "data") for r in load(p) if r["job"]["screening_questions"]][: a.n]
    flat_cfg = {"connects": {"formula": "flat", "flat": cfg("pricing.connects.flat", 6)}}
    before_cost_err = sum(connects_cost(j, flat_cfg) != gigsim_cost(W.jobs[j["id"]]) for j in jobs)
    after_cost_err = sum(connects_cost(j, policy_v2) != gigsim_cost(W.jobs[j["id"]]) for j in jobs)
    text = "For your project you need a reliable data pipeline. I built a similar pipeline for a logistics client [E1]."
    v1, v2 = rules_without_p7(), policy_engine.load_rules()
    blocked_before = blocked_after = 0
    for j in jobs:
        answers = ["A concrete answer that is long enough."] * len(j["screening_questions"])
        answers[0] = ""                                   # one answer missing
        ctx = {"draft": {"screening_answers": answers}, "job": {"screening_questions": j["screening_questions"]}}
        blocked_before += not policy_engine.check(text, "proposal", ctx, rules=v1).allowed
        blocked_after += not policy_engine.check(text, "proposal", ctx, rules=v2).allowed
    res = {"meta": {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "jobs": len(jobs), "gigsim_policy": 2,
                    "p7_rule_present": any(r["id"] == P7 for r in v2["rules"])},
           "connects_cost_prediction_errors": {"before_config_only": before_cost_err, "after_synced_from_get_policy": after_cost_err},
           "missing_answer_proposals": {"n": len(jobs), "blocked_by_compliance_before": blocked_before,
                                        "rejected_by_gigsim_before": len(jobs) - blocked_before,
                                        "blocked_by_compliance_after": blocked_after, "rejected_by_gigsim_after": len(jobs) - blocked_after},
           "diff": diff_stats(a.commit)}
    (OUT / "change_request.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
