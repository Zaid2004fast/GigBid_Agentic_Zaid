"""Audit of past proposals as "evidence": how many claim skills the persona's portfolio cannot
support? (Supports the finding that past proposals must not be used as evidence.)

    python -m evals.runners.proposal_audit
"""
from __future__ import annotations

import json

from evals.runners.harness import ROOT
from rag.corpus import get_corpus
from rag.skills import explicit_skills


def main() -> None:
    out = {}
    for p in ("aiml", "web", "data"):
        c = get_corpus(p)
        proven = set().union(*c.project_skills.values())
        props = [d for d in c.docs if d.meta["type"] == "proposal"]
        unsupported = [d for d in props if explicit_skills(d.text) - proven]
        generic = [d for d in props if "extensive experience" in d.text]
        out[p] = {"proposals": len(props), "with_unsupported_skill_claim": len(unsupported),
                  "share_unsupported": round(len(unsupported) / len(props), 4),
                  "share_generic_experience_claims": round(len(generic) / len(props), 4),
                  "outcomes": {o: sum(1 for d in props if d.meta["outcome"] == o) for o in ("won", "replied", "ignored")}}
    tot = sum(v["proposals"] for v in out.values())
    out["all"] = {"proposals": tot, "share_unsupported": round(sum(v["with_unsupported_skill_claim"] for v in out.values()) / tot, 4),
                  "share_generic_experience_claims": round(sum(v["share_generic_experience_claims"] * v["proposals"] for k, v in out.items()) / tot, 4)}
    (ROOT / "evals" / "results" / "proposal_audit.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
