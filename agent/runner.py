"""Runs graph threads and records them (runs + run_events tables) so the UI can stream,
refresh without losing anything, and replay.  Used by the worker, the evals and tests.

    events = await run_bid(graph, job, user_id, persona, settings, on_event=cb)
    await resume(graph, thread_id, {"action": "approve"}, on_event=cb)
"""
from __future__ import annotations

import time
import uuid
from typing import Awaitable, Callable

from langgraph.types import Command
from sqlalchemy import select, update

from agent.mcp_client import ToolHub
from common.db import engine, run_events, runs
from common.tracing import new_trace_id

EventCb = Callable[[dict], Awaitable[None]] | None


def _persist_event(thread_id: str, user_id: str, ev: dict) -> None:
    try:
        with engine().begin() as c:
            c.execute(run_events.insert().values(thread_id=thread_id, user_id=user_id, ts=time.time(), event=ev))
    except Exception:  # noqa: BLE001
        pass


def _upsert_run(thread_id: str, **vals) -> None:
    with engine().begin() as c:
        if c.execute(select(runs.c.thread_id).where(runs.c.thread_id == thread_id)).first():
            c.execute(update(runs).where(runs.c.thread_id == thread_id).values(**vals))
        else:
            c.execute(runs.insert().values(thread_id=thread_id, **vals))


async def _drive(graph, inp, config: dict, thread_id: str, user_id: str, on_event: EventCb) -> dict:
    """Stream updates + custom events; persist each one; return the final state values."""
    async for mode, chunk in graph.astream(inp, config, stream_mode=["updates", "custom"]):
        if mode == "custom":
            ev = {"type": "node", **chunk}
        else:
            for node_name, upd in (chunk or {}).items():
                if node_name == "__interrupt__":
                    ev = {"type": "interrupt", "node": "approval"}
                else:
                    upd = upd or {}
                    ev = {"type": "update", "node": node_name, "status": upd.get("status") if isinstance(upd, dict) else None,
                          "progress": (upd.get("progress") or [None])[-1] if isinstance(upd, dict) else None}
                _persist_event(thread_id, user_id, ev)
                if on_event:
                    await on_event(ev)
            continue
        _persist_event(thread_id, user_id, ev)
        if on_event:
            await on_event(ev)
    snap = await graph.aget_state(config)
    return snap


def _summarise(values: dict, snap) -> dict:
    usage = values.get("usage") or []
    return {"tokens": sum(u.get("tokens_in", 0) + u.get("tokens_out", 0) for u in usage),
            "cost_usd": round(sum(u.get("cost_usd", 0.0) for u in usage), 6),
            "pending_approval": bool(snap.tasks and any(t.interrupts for t in snap.tasks))}


async def run_bid(graph, job: dict, user_id: str, persona: str, settings: dict | None = None, *, thread_id: str | None = None,
                  trace_id: str | None = None, on_event: EventCb = None, store=None, transport: str | None = None) -> dict:
    thread_id = thread_id or f"bid:{user_id}:{job['id']}:{uuid.uuid4().hex[:6]}"
    trace_id = trace_id or new_trace_id()
    hub = ToolHub(user_id=user_id, persona=persona, trace_id=trace_id, **({"transport": transport} if transport else {}))
    config = {"configurable": {"thread_id": thread_id, "hub": hub, "trace_id": trace_id, "store": store}, "recursion_limit": 80}
    t0 = time.time()
    _upsert_run(thread_id, user_id=user_id, graph="bid", job_id=job["id"], status="running", trace_id=trace_id, started_at=t0)
    inp = {"thread_id": thread_id, "user_id": user_id, "persona": persona, "job_id": job["id"], "job": job, "trace_id": trace_id,
           "settings": settings or {}}
    try:
        snap = await _drive(graph, inp, config, thread_id, user_id, on_event)
    except Exception as e:
        _upsert_run(thread_id, status="dead_letter", ended_at=time.time(), attention_reason=f"{type(e).__name__}: {e}"[:500])
        raise
    v = snap.values
    s = _summarise(v, snap)
    status = "awaiting_approval" if s["pending_approval"] else v.get("status")
    _upsert_run(thread_id, status=status, ended_at=time.time(), latency_s=round(time.time() - t0, 3), tokens=s["tokens"],
                cost_usd=s["cost_usd"], attention_reason=v.get("attention_reason"),
                summary={"action": (v.get("decision") or {}).get("action"), "fit": (v.get("fit") or {}).get("fit_score"),
                         "risk": (v.get("risk") or {}).get("risk_score")})
    return {"thread_id": thread_id, "trace_id": trace_id, "status": status, "values": v, **s}


async def resume(graph, thread_id: str, decision: dict, *, user_id: str, persona: str, trace_id: str | None = None,
                 on_event: EventCb = None, store=None, transport: str | None = None) -> dict:
    hub = ToolHub(user_id=user_id, persona=persona, trace_id=trace_id, **({"transport": transport} if transport else {}))
    config = {"configurable": {"thread_id": thread_id, "hub": hub, "trace_id": trace_id, "store": store}, "recursion_limit": 80}
    t0 = time.time()
    snap = await _drive(graph, Command(resume={**decision, "user_id": user_id}), config, thread_id, user_id, on_event)
    v = snap.values
    s = _summarise(v, snap)
    status = "awaiting_approval" if s["pending_approval"] else v.get("status")
    _upsert_run(thread_id, status=status, ended_at=time.time(), tokens=s["tokens"], cost_usd=s["cost_usd"])
    return {"thread_id": thread_id, "status": status, "values": v, "latency_s": round(time.time() - t0, 3), **s}


async def run_conversation(graph, market_thread_id: str, job_id: str, user_id: str, persona: str, *, job_spec: dict | None = None,
                           price: dict | None = None, settings: dict | None = None, on_event: EventCb = None, store=None,
                           transport: str | None = None) -> dict:
    thread_id = f"conv:{user_id}:{market_thread_id}:{uuid.uuid4().hex[:6]}"
    trace_id = new_trace_id()
    hub = ToolHub(user_id=user_id, persona=persona, trace_id=trace_id, **({"transport": transport} if transport else {}))
    config = {"configurable": {"thread_id": thread_id, "hub": hub, "trace_id": trace_id, "store": store}, "recursion_limit": 60}
    _upsert_run(thread_id, user_id=user_id, graph="conversation", job_id=job_id, status="running", trace_id=trace_id, started_at=time.time())
    snap = await _drive(graph, {"thread_id": thread_id, "market_thread_id": market_thread_id, "user_id": user_id, "persona": persona,
                                "job_id": job_id, "trace_id": trace_id, "job_spec": job_spec or {}, "price": price or {},
                                "settings": settings or {}}, config, thread_id, user_id, on_event)
    v = snap.values
    s = _summarise(v, snap)
    status = "awaiting_approval" if s["pending_approval"] else v.get("status")
    _upsert_run(thread_id, status=status, ended_at=time.time(), tokens=s["tokens"], cost_usd=s["cost_usd"])
    return {"thread_id": thread_id, "trace_id": trace_id, "status": status, "values": v, **s}
