"""Compliance Guard: policy-as-code over the sendable text (no LLM). Redacts contact details
and guarantees, blocks off-platform payment, unsupported claims, prompt leaks, free work.
A block is shown in the UI with the rule's reason; the user can still edit and re-check."""
from __future__ import annotations

from agent import policy_engine
from agent.handoffs import ComplianceVerdict, ProposalDraft
from agent.runtime import NodeCtx, node
from rag.verify import strip_citations


def check_draft(state: dict, text: str) -> ComplianceVerdict:
    ver = state.get("verification") or {"unsupported_after": 0}
    ctx = {"job": {k: state.get("job", {}).get(k) for k in ("screening_questions", "budget", "category")},
           "verification": {"unsupported_after": ver.get("unsupported_after", 0)},
           "price": state.get("price") or {}, "draft": {"screening_answers": (state.get("drafts") or [{}])[-1].get("screening_answers", [])}}
    return policy_engine.check(text, "proposal", ctx)


@node("compliance")
async def compliance(state: dict, ctx: NodeCtx) -> dict:
    d = ProposalDraft.model_validate(state["drafts"][-1])
    v = check_draft(state, strip_citations(d.text))
    ans = [policy_engine.check(a, "proposal").cleaned_text for a in d.screening_answers]
    new = d.model_copy(update={"sendable_text": v.cleaned_text, "screening_answers": ans})
    out = {"compliance": v.model_dump(), "drafts": [new.model_dump()],
           "progress": [f"Compliance: {'allowed' if v.allowed else 'BLOCKED'}"
                        + (f" ({'; '.join(i.message for i in v.issues)})" if v.issues else " (no issues)")]}
    if not v.allowed:
        out["status"] = "blocked"
    return out
