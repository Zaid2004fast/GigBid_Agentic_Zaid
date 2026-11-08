"""Scout: run saved searches via the marketplace port, deduplicate, queue new jobs.

Dedup is two-level: exact job id, and a content fingerprint (normalised title + first 300
chars of the description + client id) that catches reposts with a new id.
`intake` is the first node of the bid graph: it validates the job and snapshots settings.
"""
from __future__ import annotations

import hashlib
import re

from agent.marketplace_port import get_port
from agent.mcp_client import ToolHub
from agent.runtime import NodeCtx, node


def fingerprint(job: dict) -> str:
    title = re.sub(r"\(reposted\)|[^a-z0-9 ]", "", job.get("title", "").lower()).strip()
    desc = re.sub(r"\s+", " ", job.get("description", "").lower())[:300]
    return hashlib.sha256(f"{job.get('client_id')}|{title}|{desc}".encode()).hexdigest()[:20]


async def scout_search(hub: ToolHub, search: dict, seen_ids: set[str], seen_fps: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """Returns (new_jobs, duplicates). `seen_fps` maps fingerprint -> original job id."""
    port = get_port(hub, agent="scout")
    jobs = await port.search_jobs(query=search.get("query", ""), category=search.get("category", ""), skills=search.get("skills", ""),
                                  since=search.get("since"), limit=search.get("limit", 30), split=search.get("split", "live"))
    new, dups = [], []
    for j in sorted(jobs, key=lambda x: x.get("posted_at", 0)):
        if j["id"] in seen_ids:
            continue
        fp = fingerprint(j)
        if fp in seen_fps and seen_fps[fp] != j["id"]:
            dups.append({**j, "duplicate_of": seen_fps[fp], "fingerprint": fp})
            seen_ids.add(j["id"])
            continue
        seen_ids.add(j["id"])
        seen_fps[fp] = j["id"]
        new.append({**j, "fingerprint": fp})
    return new, dups


DEFAULT_SETTINGS = {"floor_hourly": 30, "min_fixed": 250, "weekly_connects": 120, "autonomy": "suggest", "pacing": True,
                    "strategy": "evidence_first", "hours_per_week": 30, "timezone": "Asia/Karachi"}


@node("intake")
async def intake(state: dict, ctx: NodeCtx) -> dict:
    job = state.get("job")
    if not job or not job.get("description"):
        job = await get_port(ctx.hub, agent="scout").get_job(state["job_id"])
    settings = {**DEFAULT_SETTINGS, **(state.get("settings") or {})}
    return {"job": job, "job_id": job["id"], "settings": settings, "status": "analysing", "revision": 0,
            "progress": [f"Scout: job {job['id']} '{job.get('title', '')[:60]}' taken in"]}
