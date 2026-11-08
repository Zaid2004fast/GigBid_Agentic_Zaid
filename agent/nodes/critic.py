"""Critic: grounding, personalisation, length, screening answers, generic openings.
Deterministic checks always run (they are cheap and calibrated); the LLM critic adds
issues when a model is configured. Sends the draft back at most `critic.max_revisions`."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from agent.config import cfg
from agent.handoffs import Critique, JobSpec, ProposalDraft, VerificationReport
from agent.llm import structured, uses_llm
from agent.runtime import NodeCtx, node

GENERIC = [r"^\s*(dear|hello|hi)\b", r"\bi am (a )?(very )?(passionate|hardworking|dedicated)\b", r"\bi have (carefully )?read\b",
           r"\b(perfect|best) (fit|candidate)\b", r"\bi am interested in your\b", r"^\s*greetings\b"]
_W = re.compile(r"[a-z0-9]+")


class CriticLLM(BaseModel):
    score: float = Field(ge=0, le=1)
    issues: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)


def deterministic_checks(d: ProposalDraft, spec: JobSpec, ver: VerificationReport | None) -> Critique:
    text = d.sendable_text or d.text
    issues, instr = [], []
    lo, hi = cfg("writer.target_words", [120, 230])
    wc = len(text.split())
    if wc > hi:
        issues.append(f"too long ({wc} words)")
        instr.append(f"Cut to under {hi} words: keep the two strongest evidence sentences (shorter).")
    elif wc < lo * 0.7:
        issues.append(f"too short ({wc} words)")
        instr.append("Add one more evidence-backed sentence about the closest past project.")
    first = re.split(r"(?<=[.!?])\s+", text.strip())[0] if text.strip() else ""
    if any(re.search(p, first, re.I) for p in GENERIC):
        issues.append("generic opening")
        instr.append("Open with the client's problem in one sentence, not with yourself.")
    job_words = set(_W.findall(" ".join([spec.title, spec.summary, *spec.deliverables, spec.client_industry or ""]).lower())) - \
        {"the", "a", "and", "for", "to", "of", "we", "our", "with", "is", "company", "looking", "freelancer", "deliver"}
    head = set(_W.findall(" ".join(re.split(r"(?<=[.!?])\s+", text)[:2]).lower()))
    pers = len(job_words & head) / max(1, min(6, len(job_words)))
    pers = min(1.0, pers)
    if pers < cfg("critic.min_personalisation", 0.5):
        issues.append(f"weak personalisation ({pers:.2f})")
        instr.append("Mention the client's specific deliverable and industry in the first two sentences.")
    n_claims = len(ver.claims) if ver else 0
    grounded = (sum(1 for c in ver.claims if c.status == "supported") / n_claims) if ver and n_claims else 0.0
    if ver and n_claims == 0:
        issues.append("no evidence-backed claims")
        instr.append("Include at least one past project from the evidence list.")
    missing = [q for q, a in zip(spec.screening_questions, d.screening_answers + [""] * 10) if len(a.split()) < 5]
    if missing:
        issues.append(f"{len(missing)} screening question(s) unanswered")
        instr.append("Answer every screening question in 1-3 sentences.")
    if not text.strip().endswith("?"):
        issues.append("no question back to the client")
        instr.append("End with one specific question for the client.")
    score = max(0.0, 1 - 0.18 * len(issues)) * (0.6 + 0.4 * grounded if n_claims else 0.6)
    return Critique(passed=not issues and score >= 0.6, score=round(score, 3), issues=issues, instructions=instr[:3],
                    personalisation=round(pers, 3), grounding=round(grounded, 3))


@node("critic")
async def critic(state: dict, ctx: NodeCtx) -> dict:
    d = ProposalDraft.model_validate(state["drafts"][-1])
    spec = JobSpec.model_validate(state["job_spec"])
    ver = VerificationReport.model_validate(state["verification"]) if state.get("verification") else None
    c = deterministic_checks(d, spec, ver)
    if uses_llm("critic"):
        llm, u = await structured("critic", "critic", CriticLLM, heuristic=lambda: None, summary=spec.summary,
                                  deliverables=spec.deliverables, questions=spec.screening_questions,
                                  checks="; ".join(c.issues) or "all deterministic checks passed", draft=d.sendable_text)
        ctx.track(u)
        if llm is not None:
            extra = [i for i in llm.issues if i not in c.issues][:2]
            c = c.model_copy(update={"issues": c.issues + extra, "instructions": (c.instructions + llm.instructions)[:3],
                                     "score": round((c.score + llm.score) / 2, 3),
                                     "passed": c.passed and llm.score >= 0.55})
    rev = int(state.get("revision") or 0)
    verdict = "pass" if c.passed else ("revise" if rev <= cfg("critic.max_revisions", 2) else "accept with issues")
    ctx.emit(f"critic {verdict}: {', '.join(c.issues) or 'ok'}")
    return {"critiques": [c.model_dump()], "progress": [f"Critic: {verdict} (score {c.score:.2f}){': ' + '; '.join(c.issues) if c.issues else ''}"]}


def route_after_critic(state: dict) -> str:
    if state.get("status") in ("needs_attention", "dead_letter", "queued_degraded"):
        return "end"
    c = (state.get("critiques") or [{}])[-1]
    # revision counts drafts written; the first draft is revision 1, so <= max_revisions allows two send-backs
    if not c.get("passed") and int(state.get("revision") or 0) <= cfg("critic.max_revisions", 2):
        return "writer"
    return "compliance"
