"""Claim verification evaluation (B3 / R5): unsupported-claim rate before and after
verification, for three writers on the same jobs and the same retrieved evidence:

  naive    - "experience list" writer: claims every requirement, citing the top retrieved
             item (how a naive RAG + LLM prompt over-claims)
  shipped  - claim-plan-then-write (agent/nodes/writer.py deterministic path)
  llm      - the configured LLM writer (only when a model is reachable; --llm)

    python -m evals.runners.claims_eval --per-persona 40 [--llm]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time

from agent.extract import heuristic_jobspec
from agent.handoffs import EvidenceRef, FitReport, PriceQuote, RequirementMatch
from agent.nodes.matcher import score
from agent.nodes.writer import _facts, claim_plan, deterministic_letter
from evals.metrics import mean
from evals.runners.harness import ROOT, load
from rag.corpus import get_corpus
from rag.pipeline import Query
from rag.retriever import get_retriever
from rag.skills import skill_name
from rag.verify import corpus_resolvers, verify_draft

OUT = ROOT / "evals" / "results"


def fit_for(persona: str, job: dict) -> FitReport:
    spec = heuristic_jobspec(job)
    ret = get_retriever(persona)
    matrix = []
    for r in spec.requirements:
        res = ret.run(Query(job_text=r.text, title=r.text, requirements=[r.text]), k=8)
        hits = res.per_requirement.get(r.text) or []
        ev = [EvidenceRef(**{k: h.to_evidence().get(k) for k in EvidenceRef.model_fields if k in h.to_evidence()}) for h in hits if h.support > 0]
        best = max((e.support for e in ev), default=0)
        st = "none" if r.text in res.unsupported or best == 0 else "supported" if best >= 0.5 else "partial"
        matrix.append(RequirementMatch(requirement=r.text, skills=r.skills, status=st, evidence=ev[:3]))
    f, gaps, reasons = score(matrix)
    return FitReport(job_id=job["id"], fit_score=f, matrix=matrix, gaps=gaps, reasons=reasons)


def naive_letter(spec, fit: FitReport, persona: str) -> tuple[str, dict]:
    """Claims EVERY requirement (gaps included) - the over-claiming baseline."""
    c = get_corpus(persona)
    labels, sents = {}, [f"Hello, I am an experienced freelancer for {spec.title}."]
    for i, m in enumerate(fit.matrix, 1):
        sk = ", ".join(skill_name(s) for s in m.skills) or m.requirement
        top = (m.evidence[0].item_id if m.evidence else next(iter(c.by_item)))
        labels[f"E{i}"] = top
        sents.append(f"I have extensive experience with {sk} and built similar systems [E{i}].")
    sents.append("Let me know when we can start.")
    return " ".join(sents), labels


async def run(per_persona: int, use_llm: bool) -> dict:
    out: dict = {"naive": [], "shipped": [], "llm": []}
    for persona in ("aiml", "web", "data"):
        resolve, search = corpus_resolvers(get_corpus(persona))
        rows = [r for r in load(persona) if r["gold"]["bid"] or r["gold"]["kind"] == "partial"][:per_persona]
        for row in rows:
            job = row["job"]
            spec = heuristic_jobspec(job)
            fit = await asyncio.to_thread(fit_for, persona, job)
            price = PriceQuote(job_id=job["id"], amount=500, budget_type="fixed", connects_cost=6, floor=100, rationale="eval")
            # naive
            text, labels = naive_letter(spec, fit, persona)
            _, rep = await verify_draft(text, {k: {"item_id": v} for k, v in labels.items()}, resolve, search)
            out["naive"].append({"job_id": job["id"], "claims": len(rep.claims), "unsupported_before": rep.unsupported_before,
                                 "unsupported_after": rep.unsupported_after, "partial": rep.partial})
            # shipped
            plan, labels = claim_plan(fit)
            facts = {}
            for p in plan:
                d = (await resolve([labels[p["label"]]]) or [{"text": ""}])[0]
                facts[p["label"]] = {**_facts(d["text"]), "industry": d.get("industry")}
            text, _ = deterministic_letter(spec, fit, price, plan, facts, "evidence_first", [], {})
            _, rep = await verify_draft(text, {k: {"item_id": v} for k, v in labels.items()}, resolve, search)
            out["shipped"].append({"job_id": job["id"], "claims": len(rep.claims), "unsupported_before": rep.unsupported_before,
                                   "unsupported_after": rep.unsupported_after, "partial": rep.partial})
            if use_llm:
                from agent.llm import structured
                from agent.nodes.writer import WriterOut, evidence_block
                o, u = await structured("writer", "writer", WriterOut, heuristic=lambda: None, min_words=120, max_words=230,
                                        style_rules="none", exemplars="none", revision_instructions="", title=spec.title,
                                        summary=spec.summary, deliverables=spec.deliverables, requirements=[r.text for r in spec.requirements],
                                        industry=spec.client_industry or "unknown", questions=spec.screening_questions, price="fixed 500",
                                        evidence=evidence_block(plan, facts), gaps=fit.gaps or "none")
                if o is not None:
                    _, rep = await verify_draft(o.cover_letter, {k: {"item_id": v} for k, v in labels.items()}, resolve, search)
                    out["llm"].append({"job_id": job["id"], "model": u.model, "claims": len(rep.claims), "unsupported_before": rep.unsupported_before,
                                       "unsupported_after": rep.unsupported_after, "partial": rep.partial, "tokens": u.tokens_in + u.tokens_out,
                                       "latency_s": u.latency_s})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=40)
    ap.add_argument("--llm", action="store_true")
    a = ap.parse_args()
    recs = asyncio.run(run(a.per_persona, a.llm))
    summ = {}
    for w, rs in recs.items():
        if not rs:
            continue
        n_claims = sum(r["claims"] for r in rs) or 1
        summ[w] = {"proposals": len(rs), "claims_per_proposal": round(mean([r["claims"] for r in rs]), 3),
                   "unsupported_per_proposal_before": round(mean([r["unsupported_before"] for r in rs]), 4),
                   "unsupported_per_proposal_after": round(mean([r["unsupported_after"] for r in rs]), 4),
                   "unsupported_claim_rate_before": round(sum(r["unsupported_before"] for r in rs) / n_claims, 4),
                   "partial_claim_rate": round(sum(r["partial"] for r in rs) / n_claims, 4)}
    res = {"meta": {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "per_persona": a.per_persona}, "summary": summ, "records": recs}
    (OUT / "claims_eval.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
