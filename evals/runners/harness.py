"""End-to-end evaluation harness: runs the REAL bid graph (MCP servers + GigSim in-process)
over dev jobs, auto-approves drafts (approval is simulated ONLY here, never in the product),
submits to GigSim, fast-forwards the simulated clock and collects outcomes.

Every record keeps: decision, gold labels, price-in-band, claim verification before/after,
critic rounds, compliance hits, latency, tokens and USD - so every metric in the report
is recomputable from evals/results/*.json.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "evals" / "datasets"
os.environ.setdefault("GIGSIM_URL", "inprocess")
os.environ.setdefault("GIGSIM_ERROR_RATE", "0")
os.environ.setdefault("GIGSIM_RATE_PER_MIN", "100000")
os.environ.setdefault("MARKETPLACE_RATE_PER_S", "1000")
os.environ.setdefault("GIGSIM_WEEKLY_CONNECTS", "100000")
os.environ.setdefault("GIGSIM_DB", str(ROOT / "data" / "processed" / f"gigsim_eval_{os.getpid()}.sqlite"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{(ROOT / 'data' / 'processed' / 'eval_app.sqlite').as_posix()}")
logging.disable(logging.WARNING)

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.store.memory import InMemoryStore  # noqa: E402

from agent.graphs.bid_graph import build_bid_graph  # noqa: E402
from agent.runner import resume, run_bid  # noqa: E402
from rag.retriever import set_variant_override  # noqa: E402

PERSONA_SETTINGS = {"aiml": {"floor_hourly": 45, "min_fixed": 400}, "web": {"floor_hourly": 35, "min_fixed": 300},
                    "data": {"floor_hourly": 30, "min_fixed": 250}}


def load(persona: str, n: int | None = None, offset: int = 0) -> list[dict]:
    rows = [json.loads(line) for line in (DS / f"dev_{persona}.jsonl").read_text().splitlines() if line.strip()]
    return rows[offset: offset + n] if n else rows[offset:]


async def run_one(graph, store, row: dict, *, approve: bool, strategy: str = "evidence_first", extra_settings: dict | None = None) -> dict:
    job, gold, persona = row["job"], row["gold"], row["persona"]
    settings = {**PERSONA_SETTINGS[persona], "pacing": False, "strategy": strategy, **(extra_settings or {})}
    uid = f"eval-{persona}"
    t0 = time.time()
    err = None
    try:
        res = await run_bid(graph, job, uid, persona, settings, store=store, thread_id=f"bid:{uid}:{job['id']}:{uuid.uuid4().hex[:6]}")
    except Exception as e:  # noqa: BLE001
        return {"job_id": job["id"], "persona": persona, "gold": gold, "error": f"{type(e).__name__}: {e}"[:300]}
    t_analyse = time.time() - t0
    v = res["values"]
    dec = (v.get("decision") or {}).get("action")
    drafts = v.get("drafts") or []
    ver = v.get("verification") or {}
    rec = {
        "job_id": job["id"], "persona": persona, "gold": gold, "action": dec, "status": res["status"],
        "scam_p": (v.get("risk") or {}).get("scam_probability"), "risk": (v.get("risk") or {}).get("risk_score"),
        "injection_detected": (v.get("risk") or {}).get("injection_detected"), "fit": (v.get("fit") or {}).get("fit_score"),
        "gaps": len((v.get("fit") or {}).get("gaps") or []), "price": (v.get("price") or {}).get("amount"),
        "connects": (v.get("decision") or {}).get("connects_cost"), "latency_s": round(t_analyse, 3),
        "tokens": res.get("tokens", 0), "cost_usd": res.get("cost_usd", 0.0), "error": err,
        "usage_by_node": _by_node(v.get("usage") or []),
    }
    if drafts:
        d = drafts[-1]
        rec.update({"draft": d.get("sendable_text"), "draft_raw": d.get("text"), "answers": d.get("screening_answers"),
                    "writer_versions": sum(1 for x in drafts if x.get("writer_model") is not None and x.get("claims") == []) or len({x["version"] for x in drafts}),
                    "unsupported_before": ver.get("unsupported_before"), "unsupported_after": ver.get("unsupported_after"),
                    "claims": len(ver.get("claims") or []), "partial": ver.get("partial"),
                    "critic_rounds": len(v.get("critiques") or []), "critic_passed": (v.get("critiques") or [{}])[-1].get("passed"),
                    "compliance_issues": [i["rule_id"] for i in (v.get("compliance") or {}).get("issues", [])],
                    "compliance_allowed": (v.get("compliance") or {}).get("allowed")})
        band = gold.get("price_band") or [0, 1e12]
        rec["price_in_band"] = band[0] <= (rec["price"] or 0) <= band[1]
        if approve and res["pending_approval"]:
            t1 = time.time()
            r2 = await resume(graph, res["thread_id"], {"action": "approve"}, user_id=uid, persona=persona, store=store)
            rec["proposal_latency_s"] = round(t_analyse + time.time() - t1, 3)
            rec["submission"] = (r2["values"].get("submission") or {}).get("proposal_id")
            rec["submit_status"] = r2["status"]
    return rec


def _by_node(usage: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for u in usage:
        n = out.setdefault(u["node"], {"tokens": 0, "cost_usd": 0.0, "latency_s": 0.0})
        n["tokens"] += u.get("tokens_in", 0) + u.get("tokens_out", 0)
        n["cost_usd"] += u.get("cost_usd", 0.0)
        if u.get("wall"):
            n["latency_s"] += u.get("latency_s", 0.0)
    return out


async def collect_outcomes(records: list[dict]) -> None:
    """Advance GigSim by 4 simulated days and attach viewed/replied/interview/hired to each submission."""
    from gigsim.app import W
    W.offset += 4 * 86400
    rows = W.db.execute("SELECT body FROM events").fetchall()
    by_prop: dict[str, set] = {}
    for (b,) in rows:
        e = json.loads(b)
        if e.get("proposal_id"):
            by_prop.setdefault(e["proposal_id"], set()).add(e["type"])
    for r in records:
        if r.get("submission"):
            ev = by_prop.get(r["submission"], set())
            r["viewed"], r["replied"] = "viewed" in ev, "replied" in ev
            r["interview"], r["hired"] = "interview" in ev, "hired" in ev
            r["policy_warning"] = "policy_warning" in ev


async def run_set(rows: list[dict], *, variant: str | None = None, approve: bool = True, strategy: str = "evidence_first",
                  concurrency: int = 4, extra_settings: dict | None = None) -> list[dict]:
    set_variant_override(variant)
    from rag.retriever import warm
    await asyncio.to_thread(warm, tuple(sorted({r["persona"] for r in rows})))
    store = InMemoryStore()
    graph = build_bid_graph(InMemorySaver(), store)
    sem = asyncio.Semaphore(concurrency)

    async def one(r):
        async with sem:
            return await run_one(graph, store, r, approve=approve, strategy=strategy, extra_settings=extra_settings)
    recs = await asyncio.gather(*(one(r) for r in rows))
    if approve:
        await collect_outcomes(recs)
    set_variant_override(None)
    return list(recs)


def reset_gigsim() -> None:
    from gigsim.app import W
    for t in ("proposals", "idem", "ledger", "events", "messages"):
        W.db.execute(f"DELETE FROM {t}")
    W.db.commit()
