"""Capture a Critic send-back with the LLM writer (open_local profile: Qwen3 via Ollama).
The deterministic writer satisfies the deterministic critic, so loops need the LLM path.

    GIGBID_PROFILE=open_local python scripts/critic_loop_trace.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GIGBID_PROFILE", "open_local")
os.environ.setdefault("GIGSIM_URL", "inprocess")
os.environ.setdefault("GIGSIM_ERROR_RATE", "0")
os.environ.setdefault("GIGSIM_DB", str(ROOT / "data" / "processed" / "gigsim_critic.sqlite"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{(ROOT / 'data' / 'processed' / 'demo_app.sqlite').as_posix()}")

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.store.memory import InMemoryStore  # noqa: E402

from agent.graphs.bid_graph import build_bid_graph  # noqa: E402
from agent.runner import run_bid  # noqa: E402
from scripts.demo import export, rows  # noqa: E402


async def main() -> None:
    store = InMemoryStore()
    g = build_bid_graph(InMemorySaver(), store)
    for r in [x for x in rows("aiml") if x["gold"]["bid"] and not x["gold"]["injection"]][:6]:
        res = await run_bid(g, r["job"], "demo-user", "aiml", {"pacing": False, "floor_hourly": 45, "min_fixed": 400}, store=store)
        crit = res["values"].get("critiques") or []
        print(r["job"]["id"], res["status"], "critic rounds:", len(crit), [c["issues"] for c in crit], flush=True)
        if len(crit) > 1:
            out = export("3_critic_loop", res, {"critic_rounds": len(crit), "issues": [c["issues"] for c in crit],
                                                "writer_models": sorted({d.get("writer_model") for d in res["values"]["drafts"]}),
                                                "profile": os.environ["GIGBID_PROFILE"]})
            p = ROOT / "evals" / "results" / "demo_traces.json"
            d = json.loads(p.read_text())
            d["scenarios"] = [s for s in d["scenarios"] if s["scenario"] != "3_critic_loop"] + [out]
            p.write_text(json.dumps(d, indent=1, default=str))
            return
    print("no critic loop in 6 jobs")


if __name__ == "__main__":
    asyncio.run(main())
