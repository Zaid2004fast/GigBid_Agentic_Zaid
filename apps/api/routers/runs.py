"""Agent run viewer: runs, events, trace spans, checkpoint history and replay-from-any-node."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import and_, select

from apps.api.auth.users import CurrentUser
from apps.api.schemas.models import Accepted, RunDetail, RunOut
from common.db import engine, run_events, runs, spans
from common.tracing import trace_url
from worker.engine import Engine

router = APIRouter(prefix="/api/runs", tags=["runs"])


def _run_out(r) -> RunOut:
    return RunOut(**{k: r[k] for k in RunOut.model_fields})


@router.get("", response_model=list[RunOut])
def list_runs(user=CurrentUser, limit: int = 50):
    with engine().connect() as c:
        rows = c.execute(select(runs).where(runs.c.user_id == user["id"]).order_by(runs.c.started_at.desc()).limit(limit)).mappings().all()
    return [_run_out(r) for r in rows]


@router.get("/{thread_id}", response_model=RunDetail)
async def get_run(thread_id: str, user=CurrentUser):
    with engine().connect() as c:
        r = c.execute(select(runs).where(and_(runs.c.thread_id == thread_id, runs.c.user_id == user["id"]))).mappings().first()
        if not r:
            raise HTTPException(404, "no such run")
        evs = [dict(e) for e in c.execute(select(run_events).where(run_events.c.thread_id == thread_id).order_by(run_events.c.id)).mappings()]
        sp = [dict(s) for s in c.execute(select(spans).where(spans.c.trace_id == r["trace_id"]).order_by(spans.c.start)).mappings()]
    eng = await Engine.get()
    graph = eng.bid if thread_id.startswith("bid:") else eng.conv
    v = (await graph.aget_state({"configurable": {"thread_id": thread_id}})).values
    slim = {k: v.get(k) for k in ("status", "decision", "price", "risk", "fit", "verification", "critiques", "compliance", "submission",
                                  "progress", "usage", "attention_reason", "intent", "reply", "sent")}
    return RunDetail(run=_run_out(r), events=[{"id": e["id"], "ts": e["ts"], **e["event"]} for e in evs], spans=sp,
                     trace_url=trace_url(r["trace_id"] or ""), values=slim)


@router.get("/trace/{trace_id}", response_model=list[dict])
def trace(trace_id: str, user=CurrentUser):
    with engine().connect() as c:
        return [dict(s) for s in c.execute(select(spans).where(and_(spans.c.trace_id == trace_id, spans.c.user_id == user["id"]))
                                           .order_by(spans.c.start)).mappings()]


@router.get("/{thread_id}/history", response_model=list[dict])
async def history(thread_id: str, user=CurrentUser):
    with engine().connect() as c:
        if not c.execute(select(runs.c.thread_id).where(and_(runs.c.thread_id == thread_id, runs.c.user_id == user["id"]))).first():
            raise HTTPException(404, "no such run")
    eng = await Engine.get()
    graph = eng.bid if thread_id.startswith("bid:") else eng.conv
    out = []
    async for s in graph.aget_state_history({"configurable": {"thread_id": thread_id}}):
        out.append({"checkpoint_id": s.config["configurable"]["checkpoint_id"], "next": list(s.next), "step": s.metadata.get("step"),
                    "status": s.values.get("status"), "created_at": s.created_at})
    return out


@router.post("/{thread_id}/replay", response_model=Accepted)
async def replay(thread_id: str, checkpoint_id: str, user=CurrentUser):
    """Fork the thread at any checkpoint and re-run from that node (C6 replay)."""
    import uuid

    from agent.mcp_client import ToolHub
    from agent.runner import _drive, _upsert_run
    with engine().connect() as c:
        r = c.execute(select(runs).where(and_(runs.c.thread_id == thread_id, runs.c.user_id == user["id"]))).mappings().first()
    if not r:
        raise HTTPException(404, "no such run")
    eng = await Engine.get()
    graph = eng.bid if thread_id.startswith("bid:") else eng.conv
    src = await graph.aget_state({"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}})
    new_tid = f"{thread_id.rsplit(':', 1)[0]}:replay{uuid.uuid4().hex[:4]}"
    hub = ToolHub(user_id=user["id"], persona=user["persona"] or "aiml", trace_id=r["trace_id"])
    cfg_new = {"configurable": {"thread_id": new_tid, "hub": hub, "store": eng.store}}
    await graph.aupdate_state(cfg_new, src.values, as_node=(src.metadata.get("writes") and list(src.metadata["writes"])[0]) or None)
    _upsert_run(new_tid, user_id=user["id"], graph=r["graph"], job_id=r["job_id"], status="running", trace_id=r["trace_id"],
                started_at=__import__("time").time())
    snap = await _drive(graph, None, cfg_new, new_tid, user["id"], None)
    _upsert_run(new_tid, status=snap.values.get("status") if not snap.next else "awaiting_approval")
    return Accepted(queued=False, key=new_tid, message=f"replayed from {checkpoint_id}")
