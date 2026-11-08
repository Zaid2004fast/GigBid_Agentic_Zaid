"""End-to-end demo + trace export (python scripts/run.py demo).

Scenarios (each exported as a trace file under docs/traces/ and listed in
evals/results/demo_traces.json):
  1. skipped scam                       4. approved proposal -> submitted
  2. injected instruction ignored        5. crash-and-resume -> submitted exactly once
  3. Critic loop (draft sent back)       6. client reply handled (conversation graph)
Also renders both graphs from code to docs/images/*.mmd (+ .png when mermaid.ink is reachable).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GIGSIM_URL", "inprocess")
os.environ.setdefault("GIGSIM_ERROR_RATE", "0")
os.environ.setdefault("GIGSIM_WEEKLY_CONNECTS", "100000")
os.environ.setdefault("GIGSIM_DB", str(ROOT / "data" / "processed" / "gigsim_demo.sqlite"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{(ROOT / 'data' / 'processed' / 'demo_app.sqlite').as_posix()}")

import logging  # noqa: E402

logging.disable(logging.WARNING)

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # noqa: E402
from langgraph.store.memory import InMemoryStore  # noqa: E402
from sqlalchemy import select  # noqa: E402

from agent.graphs.bid_graph import build_bid_graph  # noqa: E402
from agent.graphs.conversation_graph import build_conversation_graph  # noqa: E402
from agent.mcp_client import ToolHub  # noqa: E402
from agent.runner import resume, run_bid, run_conversation  # noqa: E402
from common.db import engine, spans  # noqa: E402

TRACES = ROOT / "docs" / "traces"
IMAGES = ROOT / "docs" / "images"
SET = {"pacing": False, "floor_hourly": 45, "min_fixed": 400}
UID = "demo-user"


def rows(p="aiml"):
    return [json.loads(x) for x in (ROOT / "evals" / "datasets" / f"dev_{p}.jsonl").read_text().splitlines() if x.strip()]


def export(name: str, res: dict, extra: dict | None = None) -> dict:
    with engine().connect() as c:
        sp = [dict(r) for r in c.execute(select(spans).where(spans.c.trace_id == res["trace_id"]).order_by(spans.c.start)).mappings()]
    v = res["values"]
    doc = {"scenario": name, "thread_id": res["thread_id"], "trace_id": res["trace_id"], "status": res["status"],
           "progress": v.get("progress"), "decision": v.get("decision"), "spans": sp, **(extra or {})}
    TRACES.mkdir(parents=True, exist_ok=True)
    (TRACES / f"{name}.json").write_text(json.dumps(doc, indent=1, default=str))
    print(f"\n## {name}: {res['status']}  (trace {res['trace_id']}, {len(sp)} spans)")
    for p in (v.get("progress") or [])[-8:]:
        print("   ", p)
    return {"scenario": name, "trace_id": res["trace_id"], "thread_id": res["thread_id"], "status": res["status"],
            "file": f"docs/traces/{name}.json", **(extra or {})}


async def main() -> None:
    store = InMemoryStore()
    g = build_bid_graph(InMemorySaver(), store)
    conv = build_conversation_graph(InMemorySaver(), store)
    data = rows()
    out = []

    scam = next(r for r in data if r["gold"]["scam_type"] == "off_platform_payment")
    out.append(export("1_skipped_scam", await run_bid(g, scam["job"], UID, "aiml", SET, store=store)))

    inj = next(r for r in data if r["gold"]["injection"] and r["gold"]["bid"])
    res = await run_bid(g, inj["job"], UID, "aiml", SET, store=store)
    draft = (res["values"].get("drafts") or [{}])[-1].get("sendable_text", "")
    canary = inj["gold"]["injection"]["canary"]
    out.append(export("2_injection_ignored", res, {"injection_kind": inj["gold"]["injection"]["kind"], "canary": canary,
                                                   "canary_in_draft": canary in draft,
                                                   "detected": res["values"]["risk"]["injection_detected"]}))

    loop_res = None
    for r in [x for x in data if x["gold"]["bid"]][:40]:
        cand = await run_bid(g, r["job"], UID, "aiml", SET, store=store)
        if len(cand["values"].get("critiques") or []) > 1:
            loop_res = cand
            break
    if loop_res:
        out.append(export("3_critic_loop", loop_res, {"critic_rounds": len(loop_res["values"]["critiques"]),
                                                      "issues": [c["issues"] for c in loop_res["values"]["critiques"]]}))

    ok = next(r for r in data if r["gold"]["bid"] and not r["gold"]["injection"])
    r1 = await run_bid(g, ok["job"], UID, "aiml", SET, store=store)
    r2 = await resume(g, r1["thread_id"], {"action": "approve"}, user_id=UID, persona="aiml", store=store)
    r2["trace_id"] = r1["trace_id"]
    out.append(export("4_approved_proposal", r2, {"proposal_id": (r2["values"].get("submission") or {}).get("proposal_id")}))

    # 5. crash-and-resume: approval waits in a SQLite checkpoint; the "API" (graph + saver) is torn down
    #    and rebuilt from disk; approving twice still submits exactly once
    cp = ROOT / "data" / "processed" / "demo_crash.sqlite"
    cp.unlink(missing_ok=True)
    job = [r for r in data if r["gold"]["bid"] and not r["gold"]["injection"]][3]["job"]
    async with AsyncSqliteSaver.from_conn_string(str(cp)) as s1:
        first = await run_bid(build_bid_graph(s1, store), job, UID, "aiml", SET, store=store)
    hub = ToolHub(user_id=UID, persona="aiml")
    bal0 = (await hub.call("get_connects_balance", {}))["balance"]
    async with AsyncSqliteSaver.from_conn_string(str(cp)) as s2:
        g2 = build_bid_graph(s2, store)
        a = await resume(g2, first["thread_id"], {"action": "approve"}, user_id=UID, persona="aiml", store=store)
        b = await resume(g2, first["thread_id"], {"action": "approve"}, user_id=UID, persona="aiml", store=store)
    bal1 = (await hub.call("get_connects_balance", {}))["balance"]
    a["trace_id"] = first["trace_id"]
    out.append(export("5_crash_and_resume", a, {"second_resume_status": b["status"], "connects_spent": bal0 - bal1,
                                                "connects_cost": a["values"]["submission"]["connects_cost"],
                                                "submitted_exactly_once": bal0 - bal1 == a["values"]["submission"]["connects_cost"]}))

    # 6. client reply: fast-forward GigSim until a client replies to one of our proposals
    from gigsim.app import W
    for r in [x for x in data if x["gold"]["bid"] and not x["gold"]["injection"]][5:15]:
        x = await run_bid(g, r["job"], UID, "aiml", SET, store=store)
        if x["pending_approval"]:
            await resume(g, x["thread_id"], {"action": "approve"}, user_id=UID, persona="aiml", store=store)
    W.offset += 2 * 86400
    threads = (await hub.call("list_threads", {}))["threads"]
    if threads:
        th = threads[0]
        c1 = await run_conversation(conv, th["thread_id"], th["job_id"], UID, "aiml", store=store)
        c2 = await resume(conv, c1["thread_id"], {"action": "approve"}, user_id=UID, persona="aiml", store=store)
        c2["trace_id"] = c1["trace_id"]
        out.append(export("6_client_reply", c2, {"intent": c1["values"]["intent"], "reply": c1["values"]["reply"]["text"]}))

    (ROOT / "evals" / "results" / "demo_traces.json").write_text(json.dumps({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                                                             "scenarios": out}, indent=1, default=str))
    render_graphs(g, conv)


def render_graphs(g, conv) -> None:
    IMAGES.mkdir(parents=True, exist_ok=True)
    for name, graph in (("bid_graph", g), ("conversation_graph", conv)):
        mmd = graph.get_graph().draw_mermaid()
        (IMAGES / f"{name}.mmd").write_text(mmd)
        try:
            (IMAGES / f"{name}.png").write_bytes(graph.get_graph().draw_mermaid_png())
            print(f"rendered docs/images/{name}.png")
        except Exception as e:  # noqa: BLE001 - offline: the .mmd file is still the source of truth
            print(f"rendered docs/images/{name}.mmd (png skipped: {type(e).__name__})")
        _ = re


if __name__ == "__main__":
    asyncio.run(main())
