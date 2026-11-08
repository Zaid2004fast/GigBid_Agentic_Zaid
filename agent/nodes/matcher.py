"""Fit Matcher: requirement -> portfolio evidence matrix and fit score (via Portfolio MCP).

Runs in PARALLEL with the Job Analyst, so it cannot wait for the JobSpec. It performs its
own deterministic decomposition of the neutralised post ("speculative matching"); the
`reconcile` node afterwards searches evidence for any requirement the Analyst found that
the matcher's decomposition missed. No raw post text ever reaches an LLM here.
"""
from __future__ import annotations

import asyncio

from agent.config import cfg
from agent.extract import heuristic_jobspec
from agent.handoffs import EvidenceRef, FitReport, JobSpec, RequirementMatch
from agent.runtime import NodeCtx, node
from rag.skills import GENERIC

STATUS_SCORE = {"supported": 1.0, "partial": 0.5, "none": 0.0}


async def match_requirements(ctx: NodeCtx, reqs: list[tuple[str, list[str]]]) -> list[RequirementMatch]:
    tools = ctx.tools("matcher")

    async def one(text, skills):
        r = await tools("search_evidence", requirement=text, k=4)
        ev = [EvidenceRef(**{k: i.get(k) for k in EvidenceRef.model_fields if k in i}) for i in r["items"] if i.get("support", 0) > 0]
        return RequirementMatch(requirement=text, skills=skills, status=r["status"] if ev or r["status"] == "none" else "none",
                                evidence=ev[:3])
    return list(await asyncio.gather(*(one(t, s) for t, s in reqs)))


def score(matrix: list[RequirementMatch]) -> tuple[float, list[str], list[str]]:
    if not matrix:
        return 0.0, [], ["no concrete requirements found"]
    tot = num = 0.0
    gaps, reasons = [], []
    for m in matrix:
        w = 0.5 if m.skills and set(m.skills) <= GENERIC else 1.0
        tot += w
        num += w * STATUS_SCORE[m.status]
        if m.status == "none":
            gaps.append(m.requirement)
        elif m.evidence:
            reasons.append(f"'{m.requirement[:50]}' proven by {m.evidence[0].title or m.evidence[0].item_id}")
    return round(num / tot, 3), gaps, reasons


@node("matcher")
async def matcher(state: dict, ctx: NodeCtx) -> dict:
    spec = await asyncio.to_thread(heuristic_jobspec, state["job"])
    reqs = [(r.text, r.skills) for r in spec.requirements] or [(spec.title, spec.skills)]
    matrix = await match_requirements(ctx, reqs)
    fit, gaps, reasons = score(matrix)
    try:
        ex = (await ctx.tools("matcher")("find_winning_proposals", job_summary=f"{spec.title} {' '.join(spec.skills)}", k=2))["items"]
    except Exception:  # noqa: BLE001 - exemplars are optional
        ex = []
    rep = FitReport(job_id=state["job"]["id"], fit_score=fit, matrix=matrix, gaps=gaps, reasons=reasons[:5], exemplars=ex,
                    variant=cfg("rag.variant", "best"))
    evidence = {e.item_id: e.model_dump() for m in matrix for e in m.evidence}
    ctx.emit(f"fit {fit:.2f}, {len(gaps)} gaps")
    return {"fit": rep.model_dump(), "evidence": evidence,
            "progress": [f"Fit Matcher: fit {fit:.2f} ({len(matrix) - len(gaps)}/{len(matrix)} requirements evidenced)"]}


@node("reconcile")
async def reconcile(state: dict, ctx: NodeCtx) -> dict:
    """Join step after the parallel branches: align the Analyst's requirements with the matcher's."""
    if not state.get("fit") or not state.get("job_spec"):
        return {}
    spec = JobSpec.model_validate(state["job_spec"])
    fit = FitReport.model_validate(state["fit"])
    covered_sk = {s for m in fit.matrix for s in m.skills}
    covered_txt = {m.requirement.lower() for m in fit.matrix}
    missing = [(r.text, r.skills) for r in spec.requirements
               if r.text.lower() not in covered_txt and (not r.skills or not set(r.skills) <= covered_sk)]
    if not missing:
        return {"progress": ["Reconcile: analyst and matcher agree on requirements"]}
    extra = await match_requirements(ctx, missing[:5])
    matrix = fit.matrix + extra
    f, gaps, reasons = score(matrix)
    rep = fit.model_copy(update={"matrix": matrix, "fit_score": f, "gaps": gaps, "reasons": reasons[:5]})
    return {"fit": rep.model_dump(), "evidence": {e.item_id: e.model_dump() for m in extra for e in m.evidence},
            "progress": [f"Reconcile: +{len(extra)} requirements from the Analyst, fit now {f:.2f}"]}
