"""Importer for the instructor's starter-kit data format (GigBid_Student_Starter_Kit v0.1).

Converts the kit's `jobs.json`, `freelancers.json`, `portfolio_items.json` and
`client_history.json` into GigBid's internal shapes, so the instructor's data (or the real
GigSim seed, if it uses the same schema) plugs in without code changes elsewhere.

    python -m data.importers.starter_kit --kit <starter-kit>/data/sample --persona kit_ai
      -> data/personas/kit_ai/...  (portfolio folder the Portfolio MCP server can index)
      -> data/processed/kit_jobs.json (jobs in GigBid's job shape)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def convert_job(j: dict) -> dict:
    b = j.get("budget") or {}
    lo, hi = b.get("min"), b.get("max")
    budget = {"type": "fixed", "amount": float(hi or lo or 0)}
    skills = j.get("required_skills", [])
    desc = j.get("description", "")
    if skills and "What we need" not in desc:
        desc += "\n\nWhat we need:\n" + "\n".join(f"- {s}" for s in skills)
    if hi:
        desc += f"\n\nBudget: ${float(hi):,.0f} fixed. Timeline: {j.get('duration_days', '?')} days."
    return {"id": j["job_id"], "title": j.get("title", ""), "description": desc, "category": j.get("category", ""),
            "skills_tags": skills[:3], "budget": budget, "timeline": f"{j.get('duration_days')} days" if j.get("duration_days") else None,
            "screening_questions": j.get("screening_questions", []), "client_id": j.get("client_id"),
            "connects_required": j.get("connects_cost", 6), "posted_at": 0, "proposals_count": 10,
            "kit_warning_signals": j.get("warning_signals", [])}


def convert_client(c: dict) -> dict:
    return {"id": c["client_id"], "payment_verified": c.get("payment_verified"), "jobs_posted": c.get("completed_projects", 0),
            "hire_rate": 0.6 if c.get("completed_projects") else 0.0, "avg_rating": c.get("average_rating"),
            "total_spent": 1000 * (c.get("completed_projects") or 0), "freelancer_reviews": []}


def write_portfolio(items: list[dict], freelancer: dict, out: Path) -> None:
    (out / "case_studies").mkdir(parents=True, exist_ok=True)
    (out / "repos").mkdir(exist_ok=True)
    for it in items:
        key = it["evidence_id"]
        body = (f"---\nproject: {key}\ntype: case_study\ndate: \n---\n# {it['title']}\n\n## What I built\n{it['summary']}\n\n"
                f"## Skills\n{', '.join(it.get('skills', []))}\n\n## Outcome\nThe result {it.get('outcome', 'is documented')}.\n")
        (out / "case_studies" / f"{key}.md").write_text(body, encoding="utf-8")
    (out / "profile.json").write_text(json.dumps({"id": out.name, "name": freelancer.get("display_name"),
                                                   "skills": freelancer.get("skills", []),
                                                   "floor_hourly": freelancer.get("hourly_rate_usd"),
                                                   "min_fixed": freelancer.get("minimum_project_budget_usd")}, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit", required=True)
    ap.add_argument("--persona", default="kit_ai")
    a = ap.parse_args()
    kit = Path(a.kit)
    jobs = [convert_job(j) for j in json.loads((kit / "jobs.json").read_text())]
    items = json.loads((kit / "portfolio_items.json").read_text())
    fl = json.loads((kit / "freelancers.json").read_text())[0]
    write_portfolio(items, fl, ROOT / "data" / "personas" / a.persona)
    out = ROOT / "data" / "processed" / "kit_jobs.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(jobs, indent=1))
    print(f"imported {len(jobs)} jobs -> {out}; {len(items)} portfolio items -> data/personas/{a.persona}")


if __name__ == "__main__":
    main()
