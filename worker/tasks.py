"""Arq worker (Redis) - scouting and long agent runs never execute inside web requests (E1).

    arq worker.tasks.WorkerSettings

The Redis job id equals the durable queue key, so Arq itself also dedupes; the cron tick
schedules saved searches (live mode uses the conservative interval in docs/RUNBOOK.md).
"""
from __future__ import annotations

import os

from arq import cron
from arq.connections import RedisSettings

from worker.engine import Engine, claim, process, tick


async def run_item(ctx, key: str) -> str:
    items = claim(key=key)
    for it in items:
        await process(it)
    return f"processed {len(items)}"


async def drain(ctx) -> None:
    """Safety net: anything pending in the durable queue (e.g. enqueued while Redis was down)."""
    for it in claim(limit=5):
        await process(it)


async def scheduler_tick(ctx) -> None:
    await tick()


async def startup(ctx) -> None:
    await Engine.get()


async def shutdown(ctx) -> None:
    if Engine._inst:
        await Engine._inst.close()


async def enqueue_arq(key: str) -> None:
    from arq import create_pool
    pool = await create_pool(RedisSettings.from_dsn(os.environ["REDIS_URL"]))
    await pool.enqueue_job("run_item", key, _job_id=key)


class WorkerSettings:
    functions = [run_item]
    cron_jobs = [cron(scheduler_tick, second=0), cron(drain, second={15, 45})]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379"))
    max_jobs = 4
    job_timeout = 900
