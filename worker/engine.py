"""Execution engine shared by the Arq worker and the API's local in-process worker.

Durable work queue = the `work_queue` table. Every item has a natural idempotency key
(e.g. analyse:<user>:<job>), so double-enqueueing is a no-op and a worker restart never
double-analyses. Items are claimed with a lease; a crashed worker's lease expires and the
item is retried. Graph threads are durable in the checkpointer, and marketplace writes are
idempotent, so a retried `resume` submits exactly once.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import traceback
from contextlib import AsyncExitStack

from sqlalchemy import and_, case, or_, select, update

from agent.config import cfg
from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph
from agent.mcp_client import BREAKERS, ToolHub
from agent.memory.store import open_persistence
from common.db import engine, jobs, pipeline, queue, runs, saved_searches, settings, users

log = logging.getLogger("gigbid.worker")
LEASE_S = 300


class Engine:
    _inst: "Engine | None" = None

    def __init__(self) -> None:
        self.stack = AsyncExitStack()
        self.checkpointer = self.store = None
        self.bid = self.conv = None
        self.ready = asyncio.Event()

    @classmethod
    async def get(cls) -> "Engine":
        if cls._inst is None:
            cls._inst = Engine()
            await cls._inst.start()
        await cls._inst.ready.wait()
        return cls._inst

    async def start(self) -> None:
        self.checkpointer, self.store = await self.stack.enter_async_context(open_persistence())
        self.bid = build_bid_graph(self.checkpointer, self.store)
        self.conv = build_conversation_graph(self.checkpointer, self.store)
        self.ready.set()
        if os.getenv("GIGBID_WARM", "1") == "1" and cfg("mcp.transport", "inprocess") == "inprocess":
            from rag.retriever import warm
            asyncio.get_running_loop().run_in_executor(None, warm)

    async def close(self) -> None:
        await self.stack.aclose()
        Engine._inst = None


# ---------------------------------------------------------------- queue
def enqueue(key: str, user_id: str, kind: str, payload: dict) -> bool:
    """Returns False if an item with this key already exists (idempotent enqueue)."""
    with engine().begin() as c:
        row = c.execute(select(queue.c.status).where(queue.c.key == key)).first()
        if row and row[0] in ("pending", "running", "done"):
            return False
        if row:
            c.execute(update(queue).where(queue.c.key == key).values(status="pending", payload=payload, updated_at=time.time()))
        else:
            c.execute(queue.insert().values(key=key, user_id=user_id, kind=kind, payload=payload, status="pending", attempts=0,
                                            created_at=time.time(), updated_at=time.time()))
    _notify_arq(key, kind)
    return True


def _notify_arq(key: str, kind: str) -> None:
    if not os.getenv("REDIS_URL"):
        return
    try:
        import asyncio as _a

        from worker.tasks import enqueue_arq
        loop = _a.get_event_loop()
        loop.create_task(enqueue_arq(key))
    except Exception:  # noqa: BLE001 - the poller will still pick it up
        pass


def claim(key: str | None = None, limit: int = 1) -> list[dict]:
    now = time.time()
    with engine().begin() as c:
        cond = or_(queue.c.status == "pending", and_(queue.c.status == "running", queue.c.updated_at < now - LEASE_S))
        if key:
            cond = and_(cond, queue.c.key == key)
        # a human is waiting on approvals: resume items jump the queue ahead of background analysis
        prio = case((queue.c.kind == "resume", 0), (queue.c.kind == "conversation", 1), else_=2)
        rows = c.execute(select(queue).where(cond).order_by(prio, queue.c.created_at).limit(limit)).mappings().all()
        out = []
        for r in rows:
            res = c.execute(update(queue).where(and_(queue.c.key == r["key"], queue.c.updated_at == r["updated_at"]))
                            .values(status="running", attempts=r["attempts"] + 1, updated_at=now))
            if res.rowcount:
                out.append(dict(r))
        return out


def finish(key: str, status: str, error: str | None = None) -> None:
    with engine().begin() as c:
        c.execute(update(queue).where(queue.c.key == key).values(status=status, last_error=error, updated_at=time.time()))


def user_settings(user_id: str) -> dict:
    with engine().connect() as c:
        row = c.execute(select(settings.c.data).where(settings.c.user_id == user_id)).first()
    return dict(row[0]) if row else {}


def user_persona(user_id: str) -> str:
    with engine().connect() as c:
        row = c.execute(select(users.c.persona).where(users.c.id == user_id)).first()
    return (row[0] if row else None) or "aiml"


# ---------------------------------------------------------------- tasks
async def process(item: dict) -> None:
    from agent.runner import resume, run_bid, run_conversation
    eng = await Engine.get()
    p, uid = item["payload"], item["user_id"]
    persona = user_persona(uid)
    st = user_settings(uid)
    kind = item["kind"]
    try:
        if kind == "scout":
            await scout_user(uid, persona, st)
        elif kind == "analyse":
            job = p.get("job") or {"id": p["job_id"]}
            res = await run_bid(eng.bid, job, uid, persona, st, trace_id=p.get("trace_id"), store=eng.store,
                                thread_id=p.get("thread_id"))
            _after_run(uid, job["id"], res)
        elif kind == "resume":
            graph = eng.bid if p["thread_id"].startswith("bid:") else eng.conv
            if os.getenv("GIGBID_FAULT") == "crash_before_resume" and item["attempts"] <= 1:
                os._exit(1)   # fault injection for the exactly-once demo
            res = await resume(graph, p["thread_id"], p["decision"], user_id=uid, persona=persona, trace_id=p.get("trace_id"),
                               store=eng.store)
            if p["thread_id"].startswith("bid:"):
                _after_run(uid, p["job_id"], res)
        elif kind == "conversation":
            res = await run_conversation(eng.conv, p["market_thread_id"], p.get("job_id", ""), uid, persona,
                                         job_spec=p.get("job_spec"), price=p.get("price"), settings=st, store=eng.store)
        elif kind == "poll_events":
            await poll_events(uid, persona)
        finish(item["key"], "done")
    except Exception as e:  # noqa: BLE001
        log.error("task %s failed: %s", item["key"], traceback.format_exc())
        attempts = item.get("attempts", 1)
        finish(item["key"], "dead_letter" if attempts >= 3 else "pending", f"{type(e).__name__}: {e}"[:500])


def _after_run(uid: str, job_id: str, res: dict) -> None:
    v = res["values"]
    status = res["status"]
    with engine().begin() as c:
        c.execute(update(jobs).where(and_(jobs.c.user_id == uid, jobs.c.job_id == job_id)).values(
            status=status, fit=(v.get("fit") or {}).get("fit_score"), risk=(v.get("risk") or {}).get("risk_score"),
            action=(v.get("decision") or {}).get("action"), price=(v.get("price") or {}).get("amount"),
            connects=(v.get("decision") or {}).get("connects_cost"), thread_id=res["thread_id"], updated_at=time.time()))
        if status in ("awaiting_approval", "submitted"):
            stage = "submitted" if status == "submitted" else "drafted"
            _set_stage(c, uid, job_id, stage, v)
        if status == "queued_degraded":
            pass


def _set_stage(c, uid: str, job_id: str, stage: str, v: dict | None = None) -> None:
    row = c.execute(select(pipeline).where(and_(pipeline.c.user_id == uid, pipeline.c.job_id == job_id))).mappings().first()
    hist = list(row["history"] or []) if row else []
    hist.append({"stage": stage, "ts": time.time()})
    vals = {"stage": stage, "updated_at": time.time(), "history": hist}
    if v:
        vals.update(title=(v.get("job") or {}).get("title"), category=(v.get("job") or {}).get("category"),
                    connects=(v.get("decision") or {}).get("connects_cost"), price=(v.get("price") or {}).get("amount"),
                    proposal_id=(v.get("submission") or {}).get("proposal_id"))
    if row:
        c.execute(update(pipeline).where(and_(pipeline.c.user_id == uid, pipeline.c.job_id == job_id)).values(**vals))
    else:
        c.execute(pipeline.insert().values(user_id=uid, job_id=job_id, **vals))


async def scout_user(uid: str, persona: str, st: dict) -> int:
    """Run the user's due saved searches; insert new jobs; enqueue analysis for each."""
    from agent.nodes.scout import scout_search
    hub = ToolHub(user_id=uid, persona=persona)
    now = time.time()
    with engine().connect() as c:
        searches = c.execute(select(saved_searches).where(and_(saved_searches.c.user_id == uid, saved_searches.c.enabled.is_(True)))).mappings().all()
        seen = {r[0] for r in c.execute(select(jobs.c.job_id).where(jobs.c.user_id == uid))}
        fps = {r[0]: r[1] for r in c.execute(select(jobs.c.fingerprint, jobs.c.job_id).where(jobs.c.user_id == uid)) if r[0]}
    total = 0
    for s in searches:
        new, dups = await scout_search(hub, {"query": s["query"] or "", "category": s["category"] or "", "skills": s["skills"] or "",
                                             "since": s["last_seen_posted_at"], "limit": 30}, seen, fps)
        with engine().begin() as c:
            for j in new + dups:
                c.execute(jobs.insert().values(user_id=uid, job_id=j["id"], fingerprint=j.get("fingerprint"), data=j,
                                               status="duplicate" if j.get("duplicate_of") else "queued", duplicate_of=j.get("duplicate_of"),
                                               created_at=now, updated_at=now))
            mx = max([j.get("posted_at", 0) for j in new + dups] + [s["last_seen_posted_at"] or -1e18])
            interval = s["interval_minutes"] or cfg("marketplace.gigsim_scout_interval_minutes", 30)
            c.execute(update(saved_searches).where(saved_searches.c.id == s["id"]).values(last_seen_posted_at=mx, next_run_at=now + interval * 60))
        for j in new:
            enqueue(f"analyse:{uid}:{j['id']}", uid, "analyse", {"job": j})
        total += len(new)
    return total


async def poll_events(uid: str, persona: str) -> None:
    """Marketplace events -> pipeline board + outcome memory (promotion rule O1) + conversations."""
    from agent.marketplace_port import get_port
    from agent.memory.promotion_rules import observe_outcome
    eng = await Engine.get()
    hub = ToolHub(user_id=uid, persona=persona)
    st = user_settings(uid)
    since = st.get("_events_since", -1e18)
    evs = await get_port(hub).list_events(since)
    stage_of = {"viewed": "viewed", "replied": "replied", "interview": "interview", "hired": "hired", "lost": "lost"}
    with engine().begin() as c:
        for e in evs:
            jid = e.get("job_id")
            if e["type"] in stage_of and jid:
                row = c.execute(select(pipeline).where(and_(pipeline.c.user_id == uid, pipeline.c.job_id == jid))).mappings().first()
                order = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"]
                if row and (order.index(stage_of[e["type"]]) > order.index(row["stage"]) if row["stage"] in order else True):
                    _set_stage(c, uid, jid, stage_of[e["type"]])
    for e in evs:
        jid = e.get("job_id")
        if not jid:
            continue
        with engine().connect() as c:
            jrow = c.execute(select(jobs).where(and_(jobs.c.user_id == uid, jobs.c.job_id == jid))).mappings().first()
        cat = ((jrow or {}).get("data") or {}).get("category", "Other") if jrow else "Other"
        if e.get("proposal_id"):
            await observe_outcome(eng.store, uid, proposal_id=e["proposal_id"], event=e["type"], category=cat,
                                  strategy=st.get("strategy", "evidence_first"))
        if e["type"] == "replied" and e.get("thread_id"):
            spec = price = None
            if jrow and jrow.get("thread_id"):
                snap = await eng.bid.aget_state({"configurable": {"thread_id": jrow["thread_id"]}})
                spec, price = snap.values.get("job_spec"), snap.values.get("price")
            enqueue(f"conversation:{uid}:{e['id']}", uid, "conversation",
                    {"market_thread_id": e["thread_id"], "job_id": jid, "job_spec": spec, "price": price})
    if evs:
        st["_events_since"] = max(e["at"] for e in evs)
        from common.db import settings as settings_t
        with engine().begin() as c:
            c.execute(update(settings_t).where(settings_t.c.user_id == uid).values(data=st))


async def tick() -> None:
    """Scheduler tick: due saved searches -> scout; every user -> poll events; degraded work -> retry."""
    now = time.time()
    with engine().connect() as c:
        due = c.execute(select(saved_searches.c.user_id).where(and_(saved_searches.c.enabled.is_(True),
                                                                     or_(saved_searches.c.next_run_at.is_(None),
                                                                         saved_searches.c.next_run_at <= now)))).all()
        users_ = {r[0] for r in c.execute(select(users.c.id))}
    for (uid,) in {tuple(r) for r in due}:
        enqueue(f"scout:{uid}:{int(now // 60)}", uid, "scout", {})
    for uid in users_:
        enqueue(f"poll:{uid}:{int(now // 120)}", uid, "poll_events", {})
    if not any(b.is_open() for b in BREAKERS.values()):
        with engine().begin() as c:
            for r in c.execute(select(runs).where(runs.c.status == "queued_degraded")).mappings().all():
                if r["job_id"]:
                    c.execute(update(runs).where(runs.c.thread_id == r["thread_id"]).values(status="requeued"))
                    enqueue(f"analyse:{r['user_id']}:{r['job_id']}:retry:{int(now)}", r["user_id"], "analyse", {"job_id": r["job_id"]})


async def local_worker(stop: asyncio.Event, concurrency: int = 2) -> None:
    """In-process worker for local dev (no Redis): polls the durable queue + ticks the scheduler."""
    last_tick = 0.0
    active: set[asyncio.Task] = set()
    while not stop.is_set():
        if time.time() - last_tick > 60:
            last_tick = time.time()
            try:
                await tick()
            except Exception:  # noqa: BLE001
                log.exception("tick failed")
        # claim only what we can run now, so the priority order (approvals first) is respected
        free = concurrency - len(active)
        items = claim(limit=free) if free > 0 else []
        for it in items:
            t = asyncio.create_task(process(it))
            active.add(t)
            t.add_done_callback(active.discard)
        try:
            await asyncio.wait_for(stop.wait(), timeout=1.0 if not items else 0.1)
        except asyncio.TimeoutError:
            pass
