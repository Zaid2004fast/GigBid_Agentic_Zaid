"""Regenerates the results tables from evals/results/*.json and writes them into README.md
between <!-- RESULTS:START --> and <!-- RESULTS:END --> (and evals/results/results_tables.md).
Every number in those tables is read from a results file - CI checks this (scripts/ci_checks.py).

    python -m evals.runners.make_results_table
"""
from __future__ import annotations

import json
import re

from evals.runners.harness import ROOT

R = ROOT / "evals" / "results"


def _load(name: str) -> dict | None:
    p = R / name
    return json.loads(p.read_text()) if p.exists() else None


def f(x, nd=3) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, (int,)) and not isinstance(x, bool):
        return str(x)
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return str(x)


def rag_table() -> str:
    ret = (_load("rag_retrieval.json") or {}).get("results", {})
    out = (_load("gigsim_outcomes.json") or {}).get("variants", {})
    judge = _load("judge_scores.json")
    rows = ["| Variant | Evidence Recall@5 | MRR | nDCG@10 | Unsupported claims / proposal (before -> after verify) | Judge score | GigSim reply rate | Retrieval p95 (s/query) | Proposal p95 (s, end to end) | Cost / proposal (USD) |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    order = [v for v in ["V0", "V0e", "V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9", "C1", "C2", "C3", "C4", "best"] if v in ret or v in out]
    for v in order:
        a = ret.get(v, {}).get("all", {})
        o = out.get(v, {}).get("summary", {})
        unsup = f"{f(o.get('unsupported_before'))} -> {f(o.get('unsupported_after'))}" if o else "n/a"
        rows.append(f"| {v} | {f(a.get('recall@5'))} | {f(a.get('mrr'))} | {f(a.get('ndcg@10'))} | {unsup} | "
                    f"{'see calibration' if judge and o else 'n/a'} | {f(o.get('reply_rate')) if o else 'n/a'} | "
                    f"{f(ret.get(v, {}).get('latency_s', {}).get('p95'))} | {f(o.get('p95_latency_s')) if o else 'n/a'} | "
                    f"{f(o.get('usd_per_proposal'), 4) if o else 'n/a'} |")
    order_extra = [v for v in ["C5", "C6", "C7"] if v in ret]
    for v in order_extra:
        a = ret[v]["all"]
        rows.append(f"| {v} | {f(a.get('recall@5'))} | {f(a.get('mrr'))} | {f(a.get('ndcg@10'))} | n/a | n/a | n/a | "
                    f"{f(ret[v].get('latency_s', {}).get('p95'))} | n/a | n/a |")
    rows.append("")
    rows.append("_End-to-end columns come from `gigsim_outcomes.json` (the same fixed gold-bid job set for every variant). Cost is 0 "
                "because the evaluation ran on the deterministic offline profile; judge scores await human calibration. "
                "`best` = BM25 + skill graph + multi-vector + outcome boost (ADR 0003)._")
    return "\n".join(rows)


def decision_table() -> str:
    d = (_load("decision_eval.json") or {}).get("summary")
    if not d:
        return "_decision_eval.json not generated yet_"
    return "\n".join([
        "| Metric | Value |", "|---|---|",
        f"| Bid-or-skip F1 | {f(d['bid_skip']['f1'])} |",
        f"| Scam precision / recall | {f(d['scam']['precision'])} / {f(d['scam']['recall'])} |",
        f"| Price inside fair band | {f(d['price_in_band'])} |",
        f"| Unsupported claims / proposal (before -> after) | {f(d['unsupported_before_per_proposal'])} -> {f(d['unsupported_after_per_proposal'])} |",
        f"| Critic send-back rate | {f(d['critic_loop_rate'])} |",
        f"| GigSim reply / hire rate | {f(d['reply_rate'])} / {f(d['hire_rate'])} |",
        f"| p50 / p95 latency per job analysed (s) | {f(d['latency_job_s']['p50'])} / {f(d['latency_job_s']['p95'])} |",
        f"| p50 / p95 latency per proposal (s) | {f(d['latency_proposal_s']['p50'])} / {f(d['latency_proposal_s']['p95'])} |",
        f"| USD per job / per proposal | {f(d['usd_per_job'], 4)} / {f(d['usd_per_proposal'], 4)} |",
        f"| Injection posts detected | {d['injection']['detected']} of {d['injection']['jobs']} ({d['injection']['false_alarms']} false alarms) |",
    ])


def multiagent_table() -> str:
    m = (_load("multiagent_compare.json") or {}).get("systems")
    if not m:
        return "_multiagent_compare.json not generated yet_"
    rows = ["| System | Bid/skip accuracy | Scams bid on | Unsupported claims / proposal | Compliance violations sent | GigSim reply rate | Tokens / job | p95 latency (s) |",
            "|---|---|---|---|---|---|---|---|"]
    names = {"react": "(a) single ReAct agent", "supervisor": "(b) prebuilt supervisor", "graph": "(c) GigBid graph"}
    for k in ("react", "supervisor", "graph"):
        if k in m:
            s = m[k]["summary"]
            rows.append(f"| {names[k]} | {f(s['bid_skip_accuracy'])} | {s['scams_bid_on']} | {f(s['unsupported_per_proposal'])} | "
                        f"{s['compliance_violations_sent']} | {f(s['reply_rate'])} | {f(s['tokens_per_job'], 1)} | {f(s['p95_latency_s'], 2)} |")
    return "\n".join(rows)


def misc() -> str:
    lines = []
    t = (_load("tool_granularity.json") or {}).get("surfaces")
    if t:
        lines += ["| Tool surface | Selection accuracy | Argument accuracy | Tokens / task |", "|---|---|---|---|"]
        lines += [f"| {k} | {f(v['tool_selection_accuracy'])} | {f(v['argument_accuracy'])} | {f(v['tokens_per_task'], 1)} |" for k, v in t.items()]
        lines.append("")
    inj = _load("injection_eval.json")
    if inj:
        lines.append(f"Prompt-injection attack success rate: naive pipeline {f(inj['attack_success_rate']['naive'])} -> GigBid "
                     f"{f(inj['attack_success_rate']['defended'])} (n={inj['meta']['n']}, {inj['meta']['model']}).")
    ab = _load("ab_test.json")
    if ab:
        lines.append(f"X2 A/B: reply rate evidence_first {f(ab['reply_rate']['A'])} vs question_first {f(ab['reply_rate']['B'])}, "
                     f"McNemar p={f(ab['mcnemar_exact']['p_value'])}, P(B>A)={f(ab['bayes_p_B_better'])} ({ab['meta']['pairs']} paired jobs).")
    ce = (_load("claims_eval.json") or {}).get("summary")
    if ce:
        for w, s in ce.items():
            lines.append(f"Claims ({w} writer): unsupported per proposal {f(s['unsupported_per_proposal_before'])} before -> "
                         f"{f(s['unsupported_per_proposal_after'])} after verification.")
    return "\n\n".join(lines) if lines else ""


def build() -> str:
    return "\n\n".join(["### RAG variants (dev set, all personas)", rag_table(), "### Shipped configuration (decision + proposal + outcome)",
                        decision_table(), "### Multi-agent comparison (R&D question C)", multiagent_table(), "### Other experiments", misc()])


def main() -> None:
    md = build()
    (R / "results_tables.md").write_text(md + "\n", encoding="utf-8")
    readme = ROOT / "README.md"
    if readme.exists():
        txt = readme.read_text(encoding="utf-8")
        txt = re.sub(r"<!-- RESULTS:START -->.*?<!-- RESULTS:END -->", lambda _: f"<!-- RESULTS:START -->\n{md}\n<!-- RESULTS:END -->", txt, flags=re.S)
        readme.write_text(txt, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
