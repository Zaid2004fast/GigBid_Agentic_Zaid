"""Job Analyst: raw post -> JobSpec.  The ONLY node (with Risk) that sees post text, and it
sees it neutralised + spotlighted.  Pattern: "LLM proposes, deterministic disposes" - LLM
requirements/skills are kept only if the taxonomy and the post text support them."""
from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from agent.extract import heuristic_jobspec
from agent.guards import sanitize_field, spotlight
from agent.handoffs import JobSpec, Requirement
from agent.llm import structured, uses_llm
from agent.runtime import NodeCtx, node
from rag.skills import extract_skills


class JobSpecLLM(BaseModel):
    summary: str = Field(description="neutral one-sentence summary of the work")
    deliverables: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list, description="atomic requirements")
    hidden_needs: list[str] = Field(default_factory=list)
    client_industry: str | None = None
    vague: bool = False


def merge(base: JobSpec, llm: JobSpecLLM, post_text: str) -> JobSpec:
    supported = set(extract_skills(post_text)) | set(base.skills)
    reqs = list(base.requirements)
    seen = {r.text.lower() for r in reqs}
    for r in llm.requirements[:10]:
        r = sanitize_field(r, 200)
        if not r or r.lower() in seen:
            continue
        sk = set(extract_skills(r))
        if sk and not sk <= supported:      # LLM invented a technology the post never asks for
            continue
        reqs.append(Requirement(text=r, skills=sorted(sk), must_have=True))
        seen.add(r.lower())
    return base.model_copy(update={
        "summary": sanitize_field(llm.summary, 240) or base.summary,
        "deliverables": [d for d in (sanitize_field(x, 160) for x in llm.deliverables[:5]) if d] or base.deliverables,
        "requirements": reqs[:12],
        "hidden_needs": list(dict.fromkeys(base.hidden_needs + [h for h in (sanitize_field(x, 160) for x in llm.hidden_needs[:4]) if h])),
        "client_industry": base.client_industry or (sanitize_field(llm.client_industry or "", 40) or None),
        "vague": base.vague or llm.vague,
        "extraction": "llm",
    })


@node("analyst")
async def analyst(state: dict, ctx: NodeCtx) -> dict:
    job = state["job"]
    base = await asyncio.to_thread(heuristic_jobspec, job)
    spec = base
    if uses_llm("analyst"):
        b = job.get("budget", {})
        llm_out, u = await structured(
            "analyst", "analyst", JobSpecLLM, heuristic=lambda: None, job_id=job["id"], title=job.get("title", ""),
            category=job.get("category", ""), tags=", ".join(job.get("skills_tags", [])), budget=b, timeline=job.get("timeline"),
            questions=job.get("screening_questions", []), spotlighted=spotlight(job.get("description", "")))
        ctx.track(u)
        if llm_out is not None:
            spec = merge(base, llm_out, job.get("description", ""))
    ctx.emit(f"{len(spec.requirements)} requirements extracted ({spec.extraction})")
    return {"job_spec": spec.model_dump(),
            "progress": [f"Job Analyst: {len(spec.requirements)} requirements, budget {spec.budget_type} {spec.budget_max}"]}
