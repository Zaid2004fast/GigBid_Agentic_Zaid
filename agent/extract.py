"""Deterministic JobSpec extraction (the Job Analyst's always-available path, and the
validator for the LLM path).  Works on the *neutralised* post: injection spans removed."""
from __future__ import annotations

import re

from agent.guards import neutralise, sanitize_field
from agent.handoffs import JobSpec, Requirement
from data.generator.ontology import INDUSTRIES
from rag.skills import extract_skills

_BULLET = re.compile(r"^\s*[-*•]\s+(.+)$", re.M)
_NEED_CUES = re.compile(r"\b(need|needs|know|experience|must|should|ideally|require|looking for|familiar)\b", re.I)
_DELIV = re.compile(r"\bdeliver(?:ing)?\s+([^.\n]{5,90})", re.I)
_NICE = re.compile(r"nice to have:?\s*([^.\n]+)", re.I)


def _budget(job: dict) -> tuple[str, float | None, float | None]:
    b = job.get("budget") or {}
    if b.get("type") == "fixed":
        return "fixed", b.get("amount"), b.get("amount")
    if b.get("type") == "hourly":
        return "hourly", b.get("min"), b.get("max")
    m = re.search(r"\$?\s?([\d,]+(?:\.\d+)?)\s*(?:usd|\$)?\s*(fixed|/hr|per hour)?", job.get("description", ""), re.I)
    if m:
        v = float(m.group(1).replace(",", ""))
        return ("hourly" if m.group(2) and "h" in m.group(2).lower() else "fixed"), v, v
    return "unknown", None, None


def heuristic_jobspec(job: dict) -> JobSpec:
    desc = neutralise(job.get("description", ""))
    body = desc.split("Budget:")[0].split("Fixed price")[0]
    reqs: list[str] = [b.strip() for b in _BULLET.findall(body)]
    vague = False
    if not reqs:
        vague = True
        sents = re.split(r"(?<=[.!?])\s+", body)
        reqs = [s.strip() for s in sents if _NEED_CUES.search(s) and len(s.split()) > 3][:6]
    nice = [n.strip() for n in _NICE.findall(desc)]
    tags = job.get("skills_tags", [])
    req_objs: list[Requirement] = []
    all_sk: dict[str, float] = {}
    for r in reqs:
        r_clean = sanitize_field(r, 200)
        if not r_clean or r_clean.lower().startswith("nice to have"):
            continue
        sk = extract_skills(r_clean)
        all_sk.update(sk)
        req_objs.append(Requirement(text=r_clean, skills=sorted(sk), must_have=True))
    for t in tags:   # structured tags the bullets did not cover become requirements too
        sk = extract_skills(t, semantic=False)
        if sk and not set(sk) & set(all_sk):
            all_sk.update(sk)
            req_objs.append(Requirement(text=t, skills=sorted(sk), must_have=True))
    ind = next((i for i in INDUSTRIES if re.search(rf"\b{re.escape(i)}\b", job.get("title", "") + " " + desc, re.I)), None)
    btype, bmin, bmax = _budget(job)
    deliv = [sanitize_field(d.strip().rstrip(".")) for d in _DELIV.findall(body)][:3]
    hidden = []
    if vague:
        hidden.append("client is unsure of the approach; propose a concrete plan and first milestone")
    if any(k in desc.lower() for k in ("existing system", "upgrade", "legacy")):
        hidden.append("must integrate with an existing codebase")
    if "messy" in desc.lower() or "spreadsheets" in desc.lower():
        hidden.append("data cleaning before analysis")
    title = sanitize_field(job.get("title", ""), 160)
    first = sanitize_field(re.split(r"(?<=[.!?])\s+", body.strip())[0] if body.strip() else title, 240)
    return JobSpec(
        job_id=job["id"], title=title, summary=first or title, deliverables=[d for d in deliv if d],
        requirements=req_objs, skills=sorted(all_sk), nice_to_have=nice[:3], budget_type=btype, budget_min=bmin,
        budget_max=bmax, timeline=job.get("timeline"), screening_questions=job.get("screening_questions", []),
        hidden_needs=hidden, client_industry=ind, category=job.get("category", ""), vague=vague, extraction="heuristic")
