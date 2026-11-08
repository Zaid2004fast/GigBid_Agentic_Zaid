"""Human approval (R4, C5) - LangGraph interrupt() before anything leaves the system.

preview  -> dry_run through the marketplace port: exact payload + Connects cost
approval -> interrupt(payload): draft, evidence behind every claim, risk report, price
            rationale, dry_run preview, compliance verdict. Resumed by the web UI with
            {"action": "approve" | "edit" | "reject", ...}. The node has no side effects
            before interrupt(), so re-execution on resume is safe.
apply_edit -> diff saved (edits table + style-memory candidates), compliance re-checked,
            back to preview/approval (an edit is never sent without being approved again)
submit   -> idempotency key derived from (thread, draft version, text hash): a crash between
            the marketplace call and the checkpoint re-runs submit with the SAME key, and both
            our MCP server and GigSim replay the stored result -> submitted exactly once.
"""
from __future__ import annotations

import difflib
import hashlib
import time
import uuid

from langgraph.types import interrupt

from agent.handoffs import ApprovalDecision, ProposalDraft
from agent.marketplace_port import get_port
from agent.memory.promotion_rules import observe_edit
from agent.nodes.compliance import check_draft
from agent.runtime import NodeCtx, node


def idem_key(state: dict, kind: str) -> str:
    d = (state.get("drafts") or [{}])[-1]
    h = hashlib.sha256((d.get("sendable_text", "") + str(d.get("bid_amount"))).encode()).hexdigest()[:12]
    return f"{state['thread_id']}:v{d.get('version', 0)}:{h}:{kind}"


@node("preview")
async def preview(state: dict, ctx: NodeCtx) -> dict:
    d = ProposalDraft.model_validate(state["drafts"][-1])
    port = get_port(ctx.hub, agent="submitter")
    pv = await port.preview_proposal(d.job_id, d.sendable_text, d.bid_amount, d.screening_answers, idem_key(state, "draft"))
    return {"preview": pv, "status": "awaiting_approval" if (state.get("compliance") or {}).get("allowed", True) else "blocked",
            "progress": [f"Dry run: {pv.get('connects_cost')} Connects, balance after {pv.get('connects_balance_after')}"]}


def approval_payload(state: dict) -> dict:
    d = state["drafts"][-1]
    ev = state.get("evidence") or {}
    claims = [{**c, "evidence": [ev.get(i) or {"item_id": i} for i in c.get("evidence_ids", [])]} for c in d.get("claims", [])]
    cited = [ev.get(i) or {"item_id": i} for i in d.get("evidence_labels", {}).values()]   # every cited item, for hover fallback
    if cited:
        claims.append({"id": "cited", "text": "", "status": "supported", "evidence_ids": [], "evidence": cited})
    return {"kind": "proposal", "thread_id": state["thread_id"], "job_id": state["job_id"], "job_title": state["job"].get("title"),
            "draft": d, "claims": claims, "evidence_labels": d.get("evidence_labels", {}), "risk": state.get("risk"),
            "price": state.get("price"), "decision": state.get("decision"), "preview": state.get("preview"),
            "compliance": state.get("compliance"), "critique": (state.get("critiques") or [None])[-1],
            "verification": state.get("verification"), "blocked": not (state.get("compliance") or {}).get("allowed", True)}


async def approval(state: dict, config) -> dict:
    """Plain (undecorated) node so nothing runs before interrupt() except building the payload."""
    raw = interrupt(approval_payload(state))
    dec = ApprovalDecision.model_validate(raw)
    blocked = not (state.get("compliance") or {}).get("allowed", True)
    if dec.action == "approve" and blocked:
        dec = ApprovalDecision(action="edit", edited_text=state["drafts"][-1].get("sendable_text"), reason="blocked: edit required",
                               user_id=dec.user_id)
    return {"approvals": [{**dec.model_dump(), "ts": time.time()}],
            "status": {"approve": "approved", "edit": "editing", "reject": "rejected"}[dec.action],
            "progress": [f"Human: {dec.action}" + (f" ({dec.reason})" if dec.reason else "")]}


def route_after_approval(state: dict) -> str:
    return {"approved": "submit", "editing": "apply_edit", "rejected": "reject"}.get(state.get("status"), "end")


@node("apply_edit")
async def apply_edit(state: dict, ctx: NodeCtx) -> dict:
    d = ProposalDraft.model_validate(state["drafts"][-1])
    dec = state["approvals"][-1]
    after = (dec.get("edited_text") or "").strip() or d.sendable_text
    before = d.sendable_text
    diff = list(difflib.unified_diff(before.split(". "), after.split(". "), lineterm="", n=0))
    v = check_draft(state, after)
    new = d.model_copy(update={"version": d.version + 1, "text": after, "sendable_text": v.cleaned_text,
                               "word_count": len(v.cleaned_text.split())})
    promoted: list[str] = []
    if ctx.store is not None and before != after:
        promoted = await observe_edit(ctx.store, state["user_id"], state["job_id"], before, after)
    try:
        from common.db import edits, engine
        with engine().begin() as c:
            c.execute(edits.insert().values(id="ed_" + uuid.uuid4().hex[:10], user_id=state["user_id"], job_id=state["job_id"],
                                            kind="proposal", before=before, after=after, diff=diff, ts=time.time()))
    except Exception:  # noqa: BLE001
        pass
    return {"drafts": [new.model_dump()], "compliance": v.model_dump(), "status": "awaiting_approval" if v.allowed else "blocked",
            "progress": [f"Edit applied (v{new.version}); compliance {'ok' if v.allowed else 'BLOCKED'}"
                         + (f"; style memory promoted: {', '.join(promoted)}" if promoted else "")]}


@node("submit")
async def submit(state: dict, ctx: NodeCtx) -> dict:
    d = ProposalDraft.model_validate(state["drafts"][-1])
    from agent.mcp_client import ToolError
    port = get_port(ctx.hub, agent="submitter")
    try:
        draft = await port.create_proposal_draft(d.job_id, d.sendable_text, d.bid_amount, d.screening_answers, idem_key(state, "draft"))
        pid = draft["result"]["proposal_id"]
        res = await port.submit_proposal(pid, d.job_id, idem_key(state, "submit"))
    except ToolError as e:
        # business rejection (not enough Connects, platform policy, job closed): visible, not a crash
        reason = str(e).split("submit_proposal:")[-1].split("create_proposal_draft:")[-1].strip()[:300]
        return {"status": "needs_attention", "attention_reason": f"marketplace rejected the submission: {reason}",
                "progress": [f"Submit rejected by marketplace: {reason}"]}
    try:
        from common.db import engine, submissions
        with engine().begin() as c:
            c.execute(submissions.insert().prefix_with("OR IGNORE") if engine().dialect.name == "sqlite" else submissions.insert(),
                      {"idempotency_key": idem_key(state, "submit"), "user_id": state["user_id"], "job_id": d.job_id,
                       "kind": "proposal", "result": res, "ts": time.time()})
    except Exception:  # noqa: BLE001 - duplicate key = already recorded
        pass
    return {"submission": {"proposal_id": pid, **res}, "status": "submitted",
            "progress": [f"Submitted proposal {pid} ({res.get('status')}, {res.get('connects_cost')} Connects)"]}


@node("reject")
async def reject(state: dict, ctx: NodeCtx) -> dict:
    dec = state["approvals"][-1]
    try:
        from common.db import engine, rejections
        with engine().begin() as c:
            c.execute(rejections.insert().values(user_id=state["user_id"], job_id=state["job_id"], reason=dec.get("reason") or "", ts=time.time()))
    except Exception:  # noqa: BLE001
        pass
    return {"status": "rejected", "progress": [f"Rejected by user: {dec.get('reason') or 'no reason'}"]}
