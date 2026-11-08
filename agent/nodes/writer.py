"""Proposal Writer - claim-plan-then-write.

1. CLAIM PLAN: choose 2-3 projects that cover the most requirements (from the FitReport
   matrix) and label their evidence E1..En. Gaps are listed as "do not claim".
2. WRITE: the LLM (or the deterministic writer) produces prose that cites [E#] labels.
3. The draft keeps the label -> evidence id map, so verification and the UI's
   evidence-on-hover work from the same ledger.

The writer never sees the raw job post - only typed JobSpec fields (injection quarantine).
Two strategies exist for the X2 A/B experiment: evidence_first (default) and question_first.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from agent.config import cfg
from agent.handoffs import Critique, FitReport, JobSpec, PriceQuote, ProposalDraft
from agent.llm import structured, uses_llm
from agent.memory.promotion_rules import apply_style, style_rules
from agent.runtime import NodeCtx, node
from rag.skills import skill_name
from rag.verify import strip_citations


class WriterOut(BaseModel):
    cover_letter: str = Field(description="proposal text with [E#] citations")
    screening_answers: list[str] = Field(default_factory=list)


def _facts(ev_text: str) -> dict:
    deliv = re.search(r"I designed and delivered ([^.]+)\.", ev_text) or re.search(r"\(\d{4}\): ([^;]+);", ev_text) or \
        re.search(r"^# [\w-]+\s*\n\s*\n([A-Z][^.\n]{10,160})\.", ev_text, re.M)
    metric = re.search(r"The result ([^.]+)\.", ev_text) or re.search(r"\(\d{4}\): [^;]+; ([^.]+)\.", ev_text) or \
        re.search(r"## Results\n([^\n]+)", ev_text)
    d = deliv.group(1).strip() if deliv else ""
    m = metric.group(1).strip().rstrip(".") if metric else ""
    return {"deliverable": d[:1].lower() + d[1:] if d else "", "metric": m[:1].lower() + m[1:] if m else ""}


def claim_plan(fit: FitReport, max_projects: int = 3) -> tuple[list[dict], dict[str, str]]:
    """Greedy set cover: projects that evidence the most (supported first) requirements."""
    by_proj: dict[str, dict] = {}
    for m in fit.matrix:
        if m.status == "none":
            continue
        for e in m.evidence:
            key = e.project or e.item_id
            p = by_proj.setdefault(key, {"project": key, "evidence": [], "reqs": [], "skills": set(), "partial_skills": set(), "score": 0.0})
            if e.item_id not in [x.item_id for x in p["evidence"]]:
                p["evidence"].append(e)
            if m.requirement not in p["reqs"]:
                p["reqs"].append(m.requirement)
                p["score"] += 1.0 if m.status == "supported" else 0.5
            (p["skills"] if m.status == "supported" else p["partial_skills"]).update(m.skills)
    chosen, covered = [], set()
    for _ in range(max_projects):
        best = max(by_proj.values(), key=lambda p: (len(set(p["reqs"]) - covered), p["score"]), default=None)
        if not best or not (set(best["reqs"]) - covered):
            break
        chosen.append(best)
        covered |= set(best["reqs"])
        by_proj.pop(best["project"])
    labels: dict[str, str] = {}
    for i, p in enumerate(chosen, 1):
        p["label"] = f"E{i}"
        best = sorted(p["evidence"], key=lambda e: {"case_study": 0, "repo_readme": 1, "repo_code": 1, "cv": 2}.get(e.type or "", 3))[0]
        persona = best.item_id.split(":")[0]
        # cite the project's case study (richest, most specific) when the project has one
        labels[p["label"]] = f"{persona}:cs:{p['project']}" if best.type != "case_study" and best.project else best.item_id
    return chosen, labels


def deterministic_letter(spec: JobSpec, fit: FitReport, price: PriceQuote, plan: list[dict], facts: dict[str, dict],
                         strategy: str, critiques: list[Critique], settings: dict) -> tuple[str, list[str]]:
    issues = " ".join(i for c in critiques[-1:] for i in c.instructions).lower()
    ind = spec.client_industry or ""
    need = (spec.deliverables[0] if spec.deliverables else spec.summary).rstrip(".")
    need = re.sub(r"^(a|an|the)\s+", "", need, flags=re.I)
    top_sk = [s for m in fit.matrix if m.status == "supported" for s in m.skills][:3]
    core = ", ".join(dict.fromkeys(skill_name(s) for s in top_sk)).strip() or \
        (spec.requirements[0].text.strip() if spec.requirements else "") or "the stack you listed"
    where = f"your {ind} project" if ind else "your project"
    title = re.sub(r"\s*\((reposted)\)", "", spec.title).strip().rstrip(".")
    # the opening states the CLIENT's need only; experience claims come next, each with a citation
    if strategy == "question_first":
        opening = f"For {where} (\"{title}\"), is the risky part getting {core} right in production, not just in a demo?"
    else:
        opening = f"For {where} (\"{title}\") you need {need} built on {core}, delivered in reviewable steps."
    body = []
    for p in plan:
        f = facts.get(p["label"], {})
        skills = sorted(p["skills"] | p["partial_skills"])   # NB: partial skills are over-claimed; verification repairs them
        named = ", ".join(skill_name(s) for s in skills[:3])
        what = f.get("deliverable") or p["reqs"][0]
        ind_p = f" for a {f['industry']} client" if f.get("industry") else ""
        s = f"I built {what}{ind_p}"
        if named:
            s += f" using {named}"
        if f.get("metric"):
            s += f" (result: {f['metric']})"
        body.append(s + f" [{p['label']}].")
    if "shorter" in issues or "too long" in issues:
        body = body[:2]
    gaps = [g for g in fit.gaps][:1]
    gap_line = ""
    if gaps and "gap" not in issues:
        gap_line = (f"One honest note: I have not done \"{gaps[0][:60].rstrip('.')}\" in production yet, so I would budget a short spike "
                    f"for it in the first milestone.")
    first = spec.hidden_needs[0] if spec.hidden_needs else (spec.deliverables[0] if spec.deliverables else "a scoped first milestone")
    plan_line = f"My plan: start with {first.rstrip('.')} as a paid first milestone, then ship in small weekly increments you can review."
    price_line = (f"My rate for this is ${price.amount:.0f}/hr." if price.budget_type == "hourly" else f"I can deliver this for ${price.amount:,.0f}.")
    q = "What does your current setup look like, and what would make the first milestone a clear win for you?"
    if spec.vague:
        q = "What is the one outcome that would make this project a success for you in the first month?"
    text = " ".join([opening, *body, gap_line, plan_line, price_line, q]).replace("  ", " ").strip()
    answers = []
    first_claim = body[0] if body else ""
    for sq in spec.screening_questions:
        ql = sq.lower()
        if "similar project" in ql or "example" in ql or "link" in ql:
            answers.append(first_claim or "The closest work in my portfolio is described above; I can walk you through it on a call.")
        elif "tools" in ql:
            sk = sorted({s for p in plan for s in p["skills"]})
            answers.append(f"I would use {', '.join(skill_name(s) for s in sk[:4]) or 'the stack already in place'}, because that is what I have shipped with and it fits your requirements.")
        elif "changing requirements" in ql:
            answers.append("I work in short milestones with a written scope per milestone, so changes are agreed, priced and reviewed weekly instead of piling up.")
        elif "availability" in ql:
            answers.append(f"About {settings.get('hours_per_week', 30)} hours per week, with overlap in your working hours for calls.")
        else:
            answers.append(f"Short answer: {first_claim or 'see the plan above'}")
    return text, answers


def evidence_block(plan: list[dict], facts: dict[str, dict]) -> str:
    lines = []
    for p in plan:
        f = facts.get(p["label"], {})
        lines.append(f"[{p['label']}] project {p['project']}: {f.get('deliverable', '')}; result: {f.get('metric', '')}; "
                     f"proven skills: {', '.join(skill_name(s) for s in sorted(p['skills']))}")
    return "\n".join(lines) or "(no evidence - do not claim experience)"


@node("writer")
async def writer(state: dict, ctx: NodeCtx) -> dict:
    spec = JobSpec.model_validate(state["job_spec"])
    fit = FitReport.model_validate(state["fit"])
    price = PriceQuote.model_validate(state["price"])
    crit = [Critique.model_validate(c) for c in state.get("critiques") or []]
    settings = state.get("settings") or {}
    strategy = settings.get("strategy", "evidence_first")
    plan, labels = claim_plan(fit)
    tools = ctx.tools("writer")
    facts: dict[str, dict] = {}
    if labels:
        # facts come from the exact evidence item each label cites, so claim and citation always agree
        try:
            details = {d["item_id"]: d for d in (await tools("get_evidence", item_ids=list(labels.values())))["items"]}
        except Exception:  # noqa: BLE001
            details = {}
        for p in plan:
            if labels[p["label"]] not in details:   # project has no case study: cite the retrieved item itself
                labels[p["label"]] = p["evidence"][0].item_id
                if labels[p["label"]] not in details:
                    try:
                        details.update({d["item_id"]: d for d in (await tools("get_evidence", item_ids=[labels[p["label"]]]))["items"]})
                    except Exception:  # noqa: BLE001
                        pass
            d = details.get(labels[p["label"]])
            facts[p["label"]] = {**_facts(d["text"] if d else " ".join(e.snippet for e in p["evidence"])),
                                 "industry": (d or {}).get("industry")}
    rules = await style_rules(ctx.store, state["user_id"])
    revision = int(state.get("revision") or 0)
    model = "rules-v1"
    if uses_llm("writer"):
        lo, hi = cfg("writer.target_words", [120, 230])
        rev = ""
        if crit:
            rev = "REVISION REQUIRED. Fix these issues: " + "; ".join(crit[-1].instructions or crit[-1].issues)
        out, u = await structured(
            "writer", "writer", WriterOut, heuristic=lambda: None, timeout_s=150, min_words=lo, max_words=hi,
            style_rules="; ".join(r["text"] for r in rules) or "none yet",
            exemplars=" || ".join(e.get("text", "")[:300] for e in fit.exemplars[:2]) or "none",
            revision_instructions=rev, title=spec.title, summary=spec.summary, deliverables=spec.deliverables,
            requirements=[r.text for r in spec.requirements], industry=spec.client_industry or "unknown",
            questions=spec.screening_questions, price=f"{price.budget_type} {price.amount}", evidence=evidence_block(plan, facts),
            gaps=fit.gaps or "none")
        ctx.track(u)
        if out is not None:
            text, answers, model = out.cover_letter, out.screening_answers, u.model
        else:
            text, answers = deterministic_letter(spec, fit, price, plan, facts, strategy, crit, settings)
    else:
        text, answers = deterministic_letter(spec, fit, price, plan, facts, strategy, crit, settings)
    text = apply_style(text, rules)
    answers = [strip_citations(a) for a in (answers + [""] * len(spec.screening_questions))[: len(spec.screening_questions)]]
    draft = ProposalDraft(job_id=spec.job_id, version=revision + 1, text=text, screening_answers=answers, bid_amount=price.amount,
                          strategy=strategy, writer_model=model, word_count=len(strip_citations(text).split()),
                          evidence_labels=labels, sendable_text=strip_citations(text))
    ctx.emit(f"draft v{draft.version}: {draft.word_count} words")
    return {"drafts": [draft.model_dump()], "revision": revision + 1,
            "progress": [f"Writer: draft v{draft.version} ({draft.word_count} words, {len(labels)} evidence items, {model})"]}
