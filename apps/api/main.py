"""GigBid API (FastAPI).

    uvicorn apps.api.main:app --port 8000

* one trace id per UI request (X-Trace-Id in/out) flows into the graph, MCP calls and audit log
* without REDIS_URL an in-process worker drains the durable queue (local dev); with Redis
  the Arq worker does (docker / prod) - long runs never execute inside a web request
* serves the built web app (apps/web/dist) so one public URL hosts UI + API
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from agent.config import cfg
from agent.mcp_client import ToolHub, server_status
from apps.api import streaming
from apps.api.auth.users import ensure_reviewer
from apps.api.routers import analytics, auth, jobs, messages, proposals, runs, settings
from apps.api.schemas.models import Health
from common.db import engine, queue
from common.tracing import current_trace, new_trace_id
from worker.engine import Engine, local_worker

logging.basicConfig(level=logging.INFO)
for noisy in ("httpx", "mcp", "mcp.server.lowlevel.server", "fastembed"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

_stop = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine()
    ensure_reviewer()
    await Engine.get()
    task = None
    if not os.getenv("REDIS_URL") and os.getenv("GIGBID_INPROCESS_WORKER", "1") == "1":
        task = asyncio.create_task(local_worker(_stop, concurrency=int(os.getenv("WORKER_CONCURRENCY", "2"))))
    yield
    _stop.set()
    if task:
        await asyncio.wait([task], timeout=5)
    if Engine._inst:
        await Engine._inst.close()


app = FastAPI(title="GigBid API", version="1.0.0", lifespan=lifespan,
              description="Multi-agent freelancer copilot: jobs, approvals, runs, analytics. Every write needs human approval.")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Trace-Id"])


@app.middleware("http")
async def trace_mw(request: Request, call_next):
    tid = request.headers.get("x-trace-id") or new_trace_id()
    tok = current_trace.set(tid)
    try:
        resp = await call_next(request)
    finally:
        current_trace.reset(tok)
    resp.headers["X-Trace-Id"] = tid
    return resp


for r in (auth.router, jobs.router, proposals.router, messages.router, runs.router, streaming.router, analytics.router, settings.router):
    app.include_router(r)


_health_cache: dict = {"ts": 0.0, "servers": {}}


@app.get("/api/health", response_model=Health, tags=["health"])
async def health():
    import time
    if time.time() - _health_cache["ts"] > 10:
        hub = ToolHub(record_spans=False)
        ok = True
        try:
            await asyncio.wait_for(hub.call("get_policy", {}), 6)
        except Exception:  # noqa: BLE001
            ok = False
        _health_cache.update(ts=time.time(), marketplace=ok)
    with engine().connect() as c:
        counts = dict(c.execute(select(queue.c.status, func.count()).group_by(queue.c.status)).all())
    br = server_status()
    mk = _health_cache.get("marketplace", True) and not br["marketplace"]["open"]
    return Health(marketplace=mk, degraded=not mk, servers=br, queue=counts, mode=cfg("marketplace.mode", "gigsim"))


DIST = Path(__file__).resolve().parents[1] / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
