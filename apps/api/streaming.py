"""SSE bridge from LangGraph streams to the browser.

The worker drives graph.astream(stream_mode=["updates", "custom"]) and persists every event
to run_events. This endpoint replays the backlog (so a refresh shows the whole run) and then
tails new events - it works no matter which process (API or worker) runs the graph.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import and_, select
from sse_starlette.sse import EventSourceResponse

from apps.api.auth.users import CurrentUser
from common.db import engine, run_events, runs

router = APIRouter(prefix="/api/runs", tags=["runs"])
TERMINAL = {"skipped", "watch", "submitted", "rejected", "sent", "needs_attention", "dead_letter", "queued_degraded", "awaiting_approval", "blocked"}


@router.get("/{thread_id}/stream")
async def stream(thread_id: str, request: Request, user=CurrentUser, after: int = 0):
    with engine().connect() as c:
        if not c.execute(select(runs.c.thread_id).where(and_(runs.c.thread_id == thread_id, runs.c.user_id == user["id"]))).first():
            raise HTTPException(404, "no such run")

    async def gen():
        last = after
        idle = 0
        while not await request.is_disconnected():
            with engine().connect() as c:
                rows = c.execute(select(run_events).where(and_(run_events.c.thread_id == thread_id, run_events.c.id > last))
                                 .order_by(run_events.c.id)).mappings().all()
                status = c.execute(select(runs.c.status).where(runs.c.thread_id == thread_id)).scalar()
            for r in rows:
                last = r["id"]
                yield {"event": "progress", "id": str(r["id"]), "data": json.dumps({**r["event"], "ts": r["ts"]})}
            yield {"event": "status", "data": json.dumps({"status": status})}
            idle = 0 if rows else idle + 1
            if status in TERMINAL and not rows and idle > 2:
                yield {"event": "done", "data": json.dumps({"status": status})}
                return
            await asyncio.sleep(0.5)
    return EventSourceResponse(gen(), ping=15)
