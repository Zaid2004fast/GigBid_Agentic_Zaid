"""Approvals (proposal studio + message approvals). Pending approvals are read from the
graph checkpoint (interrupt payload), so a page refresh - or an API restart - never loses
one. Approving enqueues a `resume` work item; the worker resumes the interrupted thread."""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from sqlalchemy import and_, select

from agent import policy_engine
from agent.handoffs import ProposalDraft
from apps.api.auth.users import CurrentUser
from apps.api.schemas.models import Accepted, ApprovalIn, ApprovalOut, RegenerateIn
from common.db import engine, runs
from common.tracing import current_trace
from rag.verify import split_sentences, strip_citations
from worker.engine import Engine, enqueue

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


async def _pending(thread_id: str) -> dict | None:
    eng = await Engine.get()
    graph = eng.bid if thread_id.startswith("bid:") else eng.conv
    snap = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    for t in snap.tasks or []:
        for it in t.interrupts or []:
            return it.value
    return None


@router.get("", response_model=list[ApprovalOut])
async def list_pending(user=CurrentUser):
    with engine().connect() as c:
        rows = c.execute(select(runs).where(and_(runs.c.user_id == user["id"], runs.c.status.in_(["awaiting_approval", "blocked"])))
                         .order_by(runs.c.started_at.desc())).mappings().all()
    out = []
    for r in rows:
        p = await _pending(r["thread_id"])
        if p:
            out.append(ApprovalOut(thread_id=r["thread_id"], kind=p["kind"], job_id=p.get("job_id"),
                                   title=p.get("job_title") or (p.get("client_message") or "")[:80], payload=p, created_at=r["started_at"]))
    return out


def _owned(thread_id: str, uid: str) -> dict:
    with engine().connect() as c:
        r = c.execute(select(runs).where(and_(runs.c.thread_id == thread_id, runs.c.user_id == uid))).mappings().first()
    if not r:
        raise HTTPException(404, "no such thread")
    return dict(r)


@router.get("/{thread_id}", response_model=ApprovalOut)
async def get_one(thread_id: str, user=CurrentUser):
    r = _owned(thread_id, user["id"])
    p = await _pending(thread_id)
    if not p:
        raise HTTPException(409, f"thread is not waiting for approval (status {r['status']})")
    return ApprovalOut(thread_id=thread_id, kind=p["kind"], job_id=p.get("job_id"), title=p.get("job_title"), payload=p,
                       created_at=r["started_at"])


@router.post("/{thread_id}", response_model=Accepted)
async def decide(thread_id: str, body: ApprovalIn, user=CurrentUser):
    r = _owned(thread_id, user["id"])
    if not await _pending(thread_id):
        raise HTTPException(409, "already decided")
    if body.action == "edit" and not (body.edited_text or "").strip():
        raise HTTPException(422, "edited_text required for edit")
    if body.action == "reject" and not (body.reason or "").strip():
        raise HTTPException(422, "a reason is required to reject")
    # the key includes the interrupt's checkpoint so each approval round is its own work item
    eng = await Engine.get()
    graph = eng.bid if thread_id.startswith("bid:") else eng.conv
    snap = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    cp = snap.config["configurable"].get("checkpoint_id", str(time.time()))
    key = f"resume:{thread_id}:{cp}"
    enqueue(key, user["id"], "resume", {"thread_id": thread_id, "job_id": r["job_id"], "decision": body.model_dump(),
                                         "trace_id": current_trace.get() or r["trace_id"]})
    return Accepted(key=key, message=f"{body.action} queued")


@router.post("/{thread_id}/regenerate", response_model=ApprovalOut)
async def regenerate_sentence(thread_id: str, body: RegenerateIn, user=CurrentUser):
    """Regenerate one sentence: replace it with the next-best evidence claim (or drop it),
    re-check compliance, and re-enter the approval step. Not counted as a user edit."""
    _owned(thread_id, user["id"])
    eng = await Engine.get()
    cfg_ = {"configurable": {"thread_id": thread_id}}
    snap = await eng.bid.aget_state(cfg_)
    v = snap.values
    d = ProposalDraft.model_validate(v["drafts"][-1])
    sents = split_sentences(d.text)
    if body.sentence_index >= len(sents):
        raise HTTPException(422, "no such sentence")
    used = set(d.evidence_labels.values())
    alt = None
    for m in (v.get("fit") or {}).get("matrix", []):
        for e in m.get("evidence", []):
            if e["item_id"] not in used and m["status"] == "supported":
                label = f"E{len(d.evidence_labels) + 1}"
                alt = (f"I also delivered {(e.get('title') or e['item_id']).split(' (')[0].lower()} [{label}].", label, e["item_id"])
                break
        if alt:
            break
    labels = dict(d.evidence_labels)
    if alt:
        sents[body.sentence_index] = alt[0]
        labels[alt[1]] = alt[2]
    else:
        sents.pop(body.sentence_index)
    text = " ".join(sents)
    verdict = policy_engine.check(strip_citations(text), "proposal", {"verification": {"unsupported_after": 0}})
    new = d.model_copy(update={"version": d.version + 1, "text": text, "sendable_text": verdict.cleaned_text, "evidence_labels": labels,
                               "word_count": len(verdict.cleaned_text.split())})
    await eng.bid.aupdate_state(cfg_, {"drafts": [new.model_dump()], "compliance": verdict.model_dump()}, as_node="compliance")
    from agent.mcp_client import ToolHub
    from agent.runner import _drive
    hub = ToolHub(user_id=user["id"], persona=user["persona"] or "aiml", trace_id=current_trace.get())
    await _drive(eng.bid, None, {"configurable": {"thread_id": thread_id, "hub": hub, "store": eng.store}}, thread_id, user["id"], None)
    p = await _pending(thread_id)
    return ApprovalOut(thread_id=thread_id, kind="proposal", job_id=v.get("job_id"), title=(v.get("job") or {}).get("title"), payload=p or {})
