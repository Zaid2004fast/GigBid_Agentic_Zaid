"""Client threads + pipeline board."""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from sqlalchemy import and_, select, update

from agent.marketplace_port import get_port
from agent.mcp_client import ToolHub, ToolUnavailable
from apps.api.auth.users import CurrentUser
from apps.api.schemas.models import Accepted, PipelineCard, ThreadOut
from common.db import engine, jobs, pipeline, runs
from worker.engine import Engine, enqueue

router = APIRouter(prefix="/api", tags=["messages"])
STAGES = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"]


@router.get("/messages/threads", response_model=list[ThreadOut])
async def threads(user=CurrentUser):
    hub = ToolHub(user_id=user["id"], persona=user["persona"] or "aiml")
    try:
        ts = await get_port(hub, agent="liaison").list_threads()
    except ToolUnavailable as e:
        raise HTTPException(503, f"marketplace unavailable: {e.reason}") from e
    with engine().connect() as c:
        pend = {r["thread_id"] for r in c.execute(select(runs.c.thread_id).where(and_(runs.c.user_id == user["id"], runs.c.graph == "conversation",
                                                                                       runs.c.status.in_(["awaiting_approval", "blocked"])))).mappings()}
    return [ThreadOut(thread_id=t["thread_id"], job_id=t.get("job_id"), last_at=t.get("last_at"), count=t.get("count", 0),
                      pending_approval=any(t["thread_id"] in p for p in pend)) for t in ts]


@router.get("/messages/threads/{thread_id}", response_model=dict)
async def thread(thread_id: str, user=CurrentUser):
    hub = ToolHub(user_id=user["id"], persona=user["persona"] or "aiml")
    try:
        msgs = await get_port(hub, agent="liaison").list_messages(thread_id)
    except ToolUnavailable as e:
        raise HTTPException(503, f"marketplace unavailable: {e.reason}") from e
    with engine().connect() as c:
        r = c.execute(select(runs).where(and_(runs.c.user_id == user["id"], runs.c.graph == "conversation",
                                              runs.c.thread_id.like(f"conv:{user['id']}:{thread_id}:%"))).order_by(runs.c.started_at.desc())).mappings().first()
    return {"thread_id": thread_id, "messages": msgs, "conversation_run": dict(r) if r else None}


@router.post("/messages/threads/{thread_id}/draft", response_model=Accepted)
async def draft_reply(thread_id: str, user=CurrentUser):
    job_id = thread_id.removeprefix("th_")
    spec = price = None
    with engine().connect() as c:
        j = c.execute(select(jobs).where(and_(jobs.c.user_id == user["id"], jobs.c.job_id == job_id))).mappings().first()
    if j and j["thread_id"]:
        snap = await (await Engine.get()).bid.aget_state({"configurable": {"thread_id": j["thread_id"]}})
        spec, price = snap.values.get("job_spec"), snap.values.get("price")
    key = f"conversation:{user['id']}:{thread_id}:{int(time.time())}"
    enqueue(key, user["id"], "conversation", {"market_thread_id": thread_id, "job_id": job_id, "job_spec": spec, "price": price})
    return Accepted(key=key, message="drafting a reply")


@router.get("/pipeline", response_model=list[PipelineCard])
def board(user=CurrentUser):
    with engine().connect() as c:
        rows = c.execute(select(pipeline).where(pipeline.c.user_id == user["id"])).mappings().all()
    return [PipelineCard(**{k: r[k] for k in PipelineCard.model_fields}) for r in rows]


@router.post("/pipeline/{job_id}/move", response_model=Accepted)
def move(job_id: str, stage: str, user=CurrentUser):
    if stage not in STAGES:
        raise HTTPException(422, f"stage must be one of {STAGES}")
    with engine().begin() as c:
        res = c.execute(update(pipeline).where(and_(pipeline.c.user_id == user["id"], pipeline.c.job_id == job_id))
                        .values(stage=stage, updated_at=time.time()))
    if not res.rowcount:
        raise HTTPException(404, "no such card")
    return Accepted(queued=False, message=f"moved to {stage}")


@router.post("/pipeline/refresh", response_model=Accepted)
def refresh(user=CurrentUser):
    key = f"poll:{user['id']}:manual:{int(time.time() // 10)}"
    enqueue(key, user["id"], "poll_events", {})
    return Accepted(key=key, message="checking marketplace events")
