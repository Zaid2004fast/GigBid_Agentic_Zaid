"""Job inbox and job detail. Analysis always runs in the worker, never in the request."""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_, select, update

from apps.api.auth.users import CurrentUser
from apps.api.schemas.models import Accepted, JobCard, JobDetail
from common.db import engine, jobs, runs
from common.tracing import current_trace
from worker.engine import Engine, enqueue

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _card(r: dict, risk_level: str | None = None, flags: list[str] | None = None) -> JobCard:
    d = r["data"] or {}
    return JobCard(job_id=r["job_id"], title=d.get("title", r["job_id"]), category=d.get("category"), status=r["status"] or "queued",
                   action=r["action"], fit=r["fit"], risk=r["risk"], risk_level=risk_level, price=r["price"],
                   connects=r["connects"] or d.get("connects_required"), budget=d.get("budget"), posted_at=d.get("posted_at"),
                   duplicate_of=r["duplicate_of"], thread_id=r["thread_id"], flags=flags or [])


@router.get("", response_model=list[JobCard])
async def inbox(user=CurrentUser, status: str | None = None, sort: str = Query("fit", pattern="^(fit|recent|risk)$"), limit: int = 100):
    with engine().connect() as c:
        q = select(jobs).where(jobs.c.user_id == user["id"])
        if status:
            q = q.where(jobs.c.status == status)
        rows = [dict(r) for r in c.execute(q).mappings().all()]
    eng = await Engine.get()
    cards = []
    for r in rows:
        level, flags = None, []
        if r["thread_id"]:
            snap = await eng.bid.aget_state({"configurable": {"thread_id": r["thread_id"]}})
            rk = snap.values.get("risk") or {}
            level, flags = rk.get("level"), [f["code"] for f in rk.get("flags", [])]
        cards.append(_card(r, level, flags))
    key = {"fit": lambda x: -(x.fit or -1), "recent": lambda x: -(x.posted_at or 0), "risk": lambda x: -(x.risk or 0)}[sort]
    return sorted(cards, key=key)[:limit]


@router.post("/scout", response_model=Accepted)
def scout_now(user=CurrentUser):
    key = f"scout:{user['id']}:manual:{int(time.time() // 30)}"
    enqueue(key, user["id"], "scout", {})
    return Accepted(key=key, message="scouting your saved searches")


@router.get("/{job_id}", response_model=JobDetail)
async def detail(job_id: str, user=CurrentUser):
    with engine().connect() as c:
        r = c.execute(select(jobs).where(and_(jobs.c.user_id == user["id"], jobs.c.job_id == job_id))).mappings().first()
        run = c.execute(select(runs).where(runs.c.thread_id == (r or {}).get("thread_id"))).mappings().first() if r else None
    if not r:
        raise HTTPException(404, "job not in your inbox")
    v = {}
    if r["thread_id"]:
        v = (await (await Engine.get()).bid.aget_state({"configurable": {"thread_id": r["thread_id"]}})).values
    return JobDetail(job=r["data"], status=r["status"], thread_id=r["thread_id"], trace_id=(run or {}).get("trace_id"),
                     job_spec=v.get("job_spec"), risk=v.get("risk"), fit=v.get("fit"), decision=v.get("decision"),
                     price=v.get("price"), progress=v.get("progress") or [])


@router.post("/{job_id}/analyse", response_model=Accepted)
def analyse(job_id: str, user=CurrentUser):
    with engine().connect() as c:
        r = c.execute(select(jobs).where(and_(jobs.c.user_id == user["id"], jobs.c.job_id == job_id))).mappings().first()
    if not r:
        raise HTTPException(404, "job not in your inbox")
    key = f"analyse:{user['id']}:{job_id}:manual:{int(time.time())}"
    enqueue(key, user["id"], "analyse", {"job": r["data"], "trace_id": current_trace.get()})
    with engine().begin() as c:
        c.execute(update(jobs).where(and_(jobs.c.user_id == user["id"], jobs.c.job_id == job_id)).values(status="queued"))
    return Accepted(key=key, message="analysis queued")


@router.post("/{job_id}/skip", response_model=Accepted)
def skip(job_id: str, user=CurrentUser):
    with engine().begin() as c:
        res = c.execute(update(jobs).where(and_(jobs.c.user_id == user["id"], jobs.c.job_id == job_id)).values(status="skipped_by_user",
                                                                                                                  updated_at=time.time()))
    if not res.rowcount:
        raise HTTPException(404, "job not in your inbox")
    return Accepted(queued=False, message="skipped")
