"""Risk Assessor: client quality from marketplace history + scam / injection signals.
Deterministic signals first; the LLM is asked only in the grey zone (cheap model)."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from agent.guards import detect_injection, mask_pii, spotlight
from agent.handoffs import RiskFlag, RiskReport
from agent.llm import structured, uses_llm
from agent.marketplace_port import get_port
from agent.runtime import NodeCtx, node

SIGNALS = {
    "free_work": (r"\b(for free|unpaid|free (test|sample)|test task[^.]{0,60}free|complete a (small )?test (task|project)|"
                  r"best free submission|free sample)\b", 0.55, "high"),
    "off_platform_contact": (r"\b(telegram|whatsapp|whats app|skype|wa\.me|t\.me|message me directly|contact me (directly|on))\b|"
                             r"\b(external|outside|another|third[- ]party|private|personal)\s+(messaging|chat|messenger)\s*(app|platform|channel)?\b|"
                             r"\bcontact (me|us|the client)\b[^.]{0,30}\b(off[- ]platform|outside|externally|elsewhere)\b|\boff[- ]platform\b|"
                             r"[\w.+-]+@[\w-]+\.[\w.]+", 0.6, "high"),
    "off_platform_payment": (r"\b(crypto|usdt|bitcoin|btc|gift ?cards?|western union|outside the platform|avoid (the )?fees|"
                             r"bank details)\b", 0.7, "high"),
    "upfront_fee": (r"\b(buy|purchase|pay)\b[^.]{0,40}\b(kit|training|materials|fee|onboarding)\b[^.]{0,40}\b(before|first|start)", 0.75, "high"),
}
CLIENT_W = {"unverified_payment": 0.18, "new_client": 0.08, "low_hire_rate": 0.12, "bad_reviews": 0.3}


class RiskLLM(BaseModel):
    scam_probability: float = Field(ge=0, le=1)
    rationale: str


def client_signals(c: dict) -> tuple[list[RiskFlag], float]:
    flags: list[RiskFlag] = []
    if c.get("payment_verified") is False:
        flags.append(RiskFlag(code="unverified_payment", severity="medium", evidence="payment method not verified"))
    if (c.get("total_spent") or 0) == 0 and (c.get("jobs_posted") or 0) <= 3:
        flags.append(RiskFlag(code="new_client", severity="low", evidence=f"spent $0, {c.get('jobs_posted')} jobs posted"))
    if (c.get("jobs_posted") or 0) >= 5 and (c.get("hire_rate") or 0) < 0.2:
        flags.append(RiskFlag(code="low_hire_rate", severity="medium", evidence=f"hire rate {c.get('hire_rate')}"))
    revs = [r.get("rating", 5) for r in c.get("freelancer_reviews", [])]
    if revs and sum(revs) / len(revs) < 3.2:
        flags.append(RiskFlag(code="bad_reviews", severity="high", evidence=f"avg freelancer rating {sum(revs) / len(revs):.1f}"))
    spend = c.get("total_spent") or 0
    q = 0.25 * bool(c.get("payment_verified")) + 0.25 * min(1.0, spend / 20000) + 0.25 * float(c.get("hire_rate") or 0) \
        + 0.25 * (((c.get("avg_rating") or 4.0) - 1) / 4)
    if revs:
        q = 0.8 * q + 0.2 * ((sum(revs) / len(revs) - 1) / 4)
    return flags, max(0.0, min(1.0, q))


def assess(job: dict, client: dict) -> RiskReport:
    text = job.get("description", "")
    flags, quality = client_signals(client or {})
    for code, (pat, _, sev) in SIGNALS.items():
        m = re.search(pat, text, re.I)
        if m:
            flags.append(RiskFlag(code=code, severity=sev, evidence=mask_pii(text[max(0, m.start() - 40): m.end() + 40])))
    inj_score, spans = detect_injection(text)
    if inj_score >= 0.5:
        flags.append(RiskFlag(code="prompt_injection", severity="high", evidence=mask_pii(spans[0][:160]) if spans else "instruction-like text"))
    p_not = 1.0
    for f in flags:
        w = SIGNALS[f.code][1] if f.code in SIGNALS else CLIENT_W.get(f.code, 0.0)
        p_not *= (1 - w)
    scam = 1 - p_not
    risk = min(1.0, 0.7 * scam + 0.3 * (1 - quality) + (0.1 if inj_score >= 0.5 else 0))
    level = "high" if risk >= 0.55 or scam >= 0.6 else "medium" if risk >= 0.3 else "low"
    return RiskReport(job_id=job["id"], client_quality=round(quality, 3), scam_probability=round(scam, 3), risk_score=round(risk, 3),
                      level=level, flags=flags, injection_detected=inj_score >= 0.5, injection_spans=[mask_pii(s[:200]) for s in spans[:3]],
                      rationale="; ".join(f"{f.code} ({f.severity})" for f in flags) or "no risk signals")


@node("risk")
async def risk(state: dict, ctx: NodeCtx) -> dict:
    job = state["job"]
    client = state.get("client") or {}
    if not client and job.get("client_id"):
        client = await get_port(ctx.hub, agent="risk").get_client_history(job["client_id"])
    rep = assess(job, client)
    if uses_llm("risk") and 0.25 <= rep.scam_probability <= 0.6:   # grey zone: ask the small model
        llm, u = await structured("risk", "risk", RiskLLM, heuristic=lambda: None,
                                  client={k: client.get(k) for k in ("payment_verified", "total_spent", "hire_rate", "jobs_posted", "avg_rating")},
                                  findings=rep.rationale, spotlighted=spotlight(job.get("description", "")))
        ctx.track(u)
        if llm is not None:
            p = round((rep.scam_probability + llm.scam_probability) / 2, 3)
            rep = rep.model_copy(update={"scam_probability": p, "rationale": rep.rationale + f" | LLM: {llm.rationale[:160]}"})
    ctx.emit(f"risk {rep.level} (scam p={rep.scam_probability})")
    return {"risk": rep.model_dump(), "client": client,
            "progress": [f"Risk Assessor: {rep.level} risk, scam p={rep.scam_probability:.2f}" + (", injection neutralised" if rep.injection_detected else "")]}
