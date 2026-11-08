"""How many job requirements contain no taxonomy skill at all? A graph-only retriever returns
nothing for those, which a skill-defined Recall@5 cannot reveal.

    python -m evals.runners.requirement_coverage
"""
from __future__ import annotations

import json

from agent.extract import heuristic_jobspec
from evals.runners.harness import ROOT, load


def main() -> None:
    out, tot, empty = {}, 0, 0
    for p in ("aiml", "web", "data"):
        n = e = 0
        jobs_any_empty = 0
        rows = load(p)
        for r in rows:
            spec = heuristic_jobspec(r["job"])
            reqs = spec.requirements
            n += len(reqs)
            k = sum(1 for q in reqs if not q.skills)
            e += k
            jobs_any_empty += k > 0
        out[p] = {"requirements": n, "without_taxonomy_skill": e, "share": round(e / max(1, n), 4),
                  "jobs_with_such_a_requirement": jobs_any_empty, "jobs": len(rows)}
        tot += n
        empty += e
    out["all"] = {"requirements": tot, "without_taxonomy_skill": empty, "share": round(empty / max(1, tot), 4)}
    (ROOT / "evals" / "results" / "requirement_coverage.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
