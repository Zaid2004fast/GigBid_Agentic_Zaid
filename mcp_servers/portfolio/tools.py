"""Portfolio tools (read-only). Owner: GigBid portfolio team. Tests: mcp_servers/portfolio/tests."""
from __future__ import annotations

import asyncio
from typing import Literal

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from mcp_servers.common import call_context
from rag.corpus import get_corpus
from rag.pipeline import Query
from rag.retriever import get_retriever
from rag.skills import skill_name

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

EvidenceType = Literal["case_study", "cv", "repo_readme", "repo_code", "review", "proposal"]


class EvidenceFilters(BaseModel):
    persona: str | None = Field(None, description="Portfolio owner id; defaults to the caller's persona")
    types: list[EvidenceType] | None = Field(None, description="Restrict to these evidence types")
    since: str | None = Field(None, pattern=r"^\d{4}(-\d{2})?$", description="Only evidence dated on/after YYYY or YYYY-MM")
    industry: str | None = Field(None, max_length=40)
    outcome: Literal["won", "replied", "ignored"] | None = None


class EvidenceItem(BaseModel):
    item_id: str = Field(description="Stable id, e.g. aiml:cs:docs-assistant; use with get_case_study or resources")
    type: str
    source: str | None
    date: str | None
    outcome: str | None = Field(None, description="For past proposals: won | replied | ignored")
    project: str | None
    title: str | None
    client_industry: str | None = None
    snippet: str
    score: float
    support: float = Field(description="0-1: share of the requirement's skills this project is proven to have")


class SearchEvidenceResult(BaseModel):
    requirement: str
    variant: str
    status: Literal["supported", "partial", "none"]
    items: list[EvidenceItem]


class CaseStudy(BaseModel):
    id: str
    title: str
    project: str
    client_industry: str | None
    date: str | None
    skills: list[str]
    markdown: str
    related_items: list[str]


class SkillEntry(BaseModel):
    skill: str
    name: str
    projects: list[str]
    strength: float = Field(description="Sum of independent sources confirming the skill")


class SkillList(BaseModel):
    persona: str
    skills: list[SkillEntry]


class EvidenceDetail(BaseModel):
    item_id: str
    type: str
    project: str
    title: str | None
    text: str
    project_skills: list[str]
    industry: str | None


class EvidenceBundle(BaseModel):
    items: list[EvidenceDetail]


class WinningProposals(BaseModel):
    items: list[dict]


class HaveIDone(BaseModel):
    skill: str
    industry: str | None
    answer: bool
    projects: list[dict]


def _keep(it: dict, f: EvidenceFilters | None) -> bool:
    if not f:
        return True
    if f.types and it.get("type") not in f.types:
        return False
    if f.since and (it.get("date") or "0000") < f.since:
        return False
    if f.industry and (it.get("client_industry") or "").lower() != f.industry.lower():
        return False
    if f.outcome and it.get("outcome") != f.outcome:
        return False
    return True


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=READ_ONLY, title="Search portfolio evidence")
    async def search_evidence(requirement: str = Field(min_length=2, max_length=400, description="One job requirement, e.g. 'Celery background workers'"),
                        k: int = Field(5, ge=1, le=20), filters: EvidenceFilters | None = None,
                        ctx: Context | None = None) -> SearchEvidenceResult:
        """Find portfolio evidence (case studies, CV entries, repos, reviews) proving ONE requirement.
        Returns items with type, source, date and outcome; status 'none' means the portfolio cannot
        support this requirement and it must not be claimed."""
        persona = (filters.persona if filters and filters.persona else None) or call_context(ctx)["persona"]
        ret = await asyncio.to_thread(get_retriever, persona)
        res = await asyncio.to_thread(ret.run, Query(job_text=requirement, title=requirement, requirements=[requirement]), max(k, 8))
        hits = res.per_requirement.get(requirement) or res.items
        items = [EvidenceItem(**{kk: h.to_evidence().get(kk) for kk in EvidenceItem.model_fields}) for h in hits]
        items = [i for i in items if _keep(i.model_dump(), filters)][:k]
        best = max((i.support for i in items), default=0.0)
        status = "none" if requirement in res.unsupported or best == 0 else "supported" if best >= 0.5 else "partial"
        return SearchEvidenceResult(requirement=requirement, variant=ret.s.name, status=status, items=items)

    @mcp.tool(annotations=READ_ONLY, title="Get case study")
    async def get_case_study(id: str = Field(min_length=1, max_length=120, description="Project key or item id (persona:cs:key)"),
                       ctx: Context | None = None) -> CaseStudy:
        """Full case study markdown with metadata and the ids of related CV / repo items."""
        persona = id.split(":")[0] if ":" in id else call_context(ctx)["persona"]
        key = id.split(":")[-1]
        c = await asyncio.to_thread(get_corpus, persona)
        docs = c.by_item.get(f"{persona}:cs:{key}")
        if not docs:
            raise ValueError(f"case study {id!r} not found")
        m = docs[0].meta
        return CaseStudy(id=f"{persona}:cs:{key}", title=m["title"], project=key, client_industry=m.get("client_industry"),
                         date=m.get("date"), skills=sorted(c.project_skills.get(key, set())), markdown=docs[0].text,
                         related_items=c.items_of_project(key))

    @mcp.tool(annotations=READ_ONLY, title="List skills")
    async def list_skills(ctx: Context | None = None) -> SkillList:
        """Every skill the portfolio can prove, with the projects that prove it and a strength score."""
        persona = call_context(ctx)["persona"]
        g = await asyncio.to_thread(lambda: get_corpus(persona).graph)
        out = [SkillEntry(skill=s, name=skill_name(s), projects=sorted(ps), strength=round(sum(ps.values()), 2))
               for s, ps in g.skill_projects.items()]
        return SkillList(persona=persona, skills=sorted(out, key=lambda e: -e.strength))

    @mcp.tool(annotations=READ_ONLY, title="Get evidence items")
    async def get_evidence(item_ids: list[str] = Field(min_length=1, max_length=10, description="Evidence item ids to load"),
                     ctx: Context | None = None) -> EvidenceBundle:
        """Full text of evidence items plus the skills and industry proven for their projects (used for claim checks)."""
        persona = call_context(ctx)["persona"]
        c = await asyncio.to_thread(get_corpus, persona)
        out = []
        for iid in item_ids:
            if not iid.startswith(f"{persona}:") or iid not in c.by_item:
                continue
            m = c.item_meta(iid)
            p = m.get("project", "")
            out.append(EvidenceDetail(item_id=iid, type=m.get("type", ""), project=p, title=m.get("title"),
                                      text=c.item_text(iid, 2500), project_skills=sorted(c.project_skills.get(p, set())),
                                      industry=(m.get("client_industry") or c.industry_of(p) or None)))
        return EvidenceBundle(items=out)

    @mcp.tool(annotations=READ_ONLY, title="Find winning past proposals")
    async def find_winning_proposals(job_summary: str = Field(min_length=3, max_length=600), k: int = Field(2, ge=1, le=5),
                               ctx: Context | None = None) -> WinningProposals:
        """Past proposals for similar jobs that WON or got a REPLY - for tone and structure only.
        They are not evidence of experience and must never be cited as proof."""
        persona = call_context(ctx)["persona"]
        c = await asyncio.to_thread(get_corpus, persona)
        hits = await asyncio.to_thread(lambda: c.bm25("proposals").search(job_summary, 25))
        good = [h for h, _ in hits if h.meta.get("outcome") in ("won", "replied")][:k]
        return WinningProposals(items=[{"id": h.item_id, "outcome": h.meta["outcome"], "text": h.text[:600]} for h in good])

    @mcp.tool(annotations=READ_ONLY, title="Have I done X (for an industry)?")
    async def have_i_done(skill: str = Field(min_length=1, max_length=60), industry: str | None = Field(None, max_length=40),
                    ctx: Context | None = None) -> HaveIDone:
        """Answer 'have I done <skill> for a client in <industry>?' from the skill graph, with the projects as proof."""
        from rag.skills import extract_skills
        persona = call_context(ctx)["persona"]
        sk = list(await asyncio.to_thread(extract_skills, skill, True)) or [skill.lower()]
        g = await asyncio.to_thread(lambda: get_corpus(persona).graph)
        projects = [p for s in sk for p in g.have_i_done(s, industry)]
        return HaveIDone(skill=skill, industry=industry, answer=bool(projects), projects=projects[:10])
