"""R&D question C - is the multi-agent design worth it?

(a) one ReAct agent holding all tools        (langgraph.prebuilt.create_react_agent)
(b) a prebuilt supervisor with 3 workers      (langgraph-supervisor)
(c) GigBid's hand-built graph                 (agent/graphs/bid_graph.py)
Same LLM for (a), (b) and the LLM nodes of (c); same dev jobs. Metrics: bid/skip accuracy,
unsupported claims per proposal (same verifier for all), compliance violations that would
have been SENT (policy pack run on the final text), GigSim reply rate (proposals submitted
by the harness), tokens and latency.

    python -m evals.runners.multiagent_compare --n 12 --model qwen3:1.7b
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time

from agent import policy_engine
from agent.llm import load_prompt
from agent.mcp_client import ToolHub
from evals.metrics import mean, percentile
from evals.runners.harness import ROOT, load, reset_gigsim, run_set
from rag.corpus import get_corpus
from rag.verify import corpus_resolvers, verify_draft

OUT = ROOT / "evals" / "results"
ALL_TOOLS = ["search_jobs", "get_job", "get_client_history", "search_evidence", "get_case_study", "get_market_stats", "get_policy"]


def parse_final(text: str) -> dict:
    m = re.findall(r"\{[^{}]*\"decision\"[^{}]*\}", text, re.S)
    if m:
        try:
            return json.loads(m[-1])
        except Exception:  # noqa: BLE001
            pass
    d = "skip" if re.search(r"\bskip\b", text, re.I) and not re.search(r"\"decision\"\s*:\s*\"bid\"", text) else "bid"
    return {"decision": d, "price": None, "proposal": text[-1500:]}


def tokens_of(messages) -> int:
    return sum((getattr(m, "usage_metadata", None) or {}).get("total_tokens", 0) for m in messages)


async def run_baseline(kind: str, model: str, row: dict) -> dict:
    from langchain_ollama import ChatOllama
    from langgraph.prebuilt import create_react_agent
    persona, job = row["persona"], row["job"]
    hub = ToolHub(user_id=f"cmp-{kind}", persona=persona, record_spans=False)
    llm = ChatOllama(model=model, reasoning=False, temperature=0.1, num_ctx=8192, num_predict=700)
    sys_r, user_r = load_prompt("react_baseline").render(job_id=job["id"], persona=persona)
    t0 = time.time()
    if kind == "react":
        agent = create_react_agent(llm, await hub.langchain_tools(names=ALL_TOOLS), prompt=sys_r)
    else:
        from langgraph_supervisor import create_supervisor
        research = create_react_agent(llm, await hub.langchain_tools(names=["get_job", "get_client_history", "get_market_stats"]),
                                      name="research_agent", prompt="Research the job, the client and market prices. Report facts only.")
        portfolio = create_react_agent(llm, await hub.langchain_tools(names=["search_evidence", "get_case_study"]),
                                       name="portfolio_agent", prompt="Find portfolio evidence for each requirement. Report item ids.")
        writer = create_react_agent(llm, [], name="writer_agent", prompt="Write the proposal from the facts and evidence given to you.")
        sys_s, _ = load_prompt("supervisor_baseline").render(job_id=job["id"], persona=persona)
        agent = create_supervisor([research, portfolio, writer], model=llm, prompt=sys_s).compile()
    try:
        out = await asyncio.wait_for(agent.ainvoke({"messages": [("user", user_r)]}, {"recursion_limit": 30}), 600)
        msgs = out["messages"]
        final = parse_final(str(msgs[-1].content))
        err = None
    except Exception as e:  # noqa: BLE001
        msgs, final, err = [], {"decision": "skip", "proposal": ""}, f"{type(e).__name__}: {e}"[:200]
    return {"job_id": job["id"], "persona": persona, "gold": row["gold"], "action": final.get("decision", "skip"),
            "draft": final.get("proposal") or "", "price": final.get("price"), "tokens": tokens_of(msgs),
            "latency_s": round(time.time() - t0, 2), "error": err}


async def score(recs: list[dict]) -> dict:
    """Same verifier + policy pack for every system; submit bid proposals to GigSim for reply rate."""
    from gigsim.app import W
    for r in recs:
        txt = r.get("draft") or ""
        if r["action"] == "bid" and txt:
            resolve, search = corpus_resolvers(get_corpus(r["persona"]))
            _, rep = await verify_draft(txt, {}, resolve, search, fix=False)
            r["unsupported"] = rep.unsupported_before
            r["violations"] = [i.rule_id for i in policy_engine.check(txt, "proposal").issues]
    hub = ToolHub(user_id="cmp-submit", persona="aiml", record_spans=False)
    for r in recs:
        if r["action"] == "bid" and r.get("draft") and len(r["draft"]) >= 50 and r.get("replied") is None:
            hub.persona = r["persona"]
            try:
                d = await hub.call("create_proposal_draft", {"proposal": {"job_id": r["job_id"], "cover_letter": r["draft"][:4900],
                                   "bid_amount": float(r.get("price") or 500), "idempotency_key": f"cmp-{r['job_id']}-{abs(hash(r['draft'])) % 10**8}"}})
                await hub.call("submit_proposal", {"submission": {"proposal_id": d["result"]["proposal_id"], "job_id": r["job_id"],
                                                                  "idempotency_key": f"cmps-{r['job_id']}-{abs(hash(r['draft'])) % 10**8}"}})
                r["submitted_pid"] = d["result"]["proposal_id"]
            except Exception:  # noqa: BLE001
                pass
    W.offset += 4 * 86400
    ev = {}
    for (b,) in W.db.execute("SELECT body FROM events").fetchall():
        e = json.loads(b)
        ev.setdefault(e.get("proposal_id"), set()).add(e["type"])
    for r in recs:
        if r.get("submitted_pid"):
            r["replied"] = "replied" in ev.get(r["submitted_pid"], set())
    props = [r for r in recs if r["action"] == "bid" and r.get("draft")]
    subs = [r for r in recs if r.get("replied") is not None]
    return {"n": len(recs), "bid_skip_accuracy": round(mean([1.0 if (r["action"] == "bid") == r["gold"]["bid"] else 0.0 for r in recs]), 4),
            "scams_bid_on": sum(1 for r in recs if r["gold"]["scam"] and r["action"] == "bid"),
            "unsupported_per_proposal": round(mean([r.get("unsupported", 0) for r in props]), 3),
            "compliance_violations_sent": sum(len(r.get("violations") or []) for r in props),
            "reply_rate": round(mean([1.0 if r.get("replied") else 0.0 for r in subs]), 4) if subs else None,
            "tokens_per_job": round(mean([r.get("tokens", 0) for r in recs]), 1),
            "p95_latency_s": round(percentile([r.get("latency_s", 0) for r in recs], .95), 2),
            "errors": sum(1 for r in recs if r.get("error"))}


async def main_async(n: int, model: str, systems: list[str]) -> dict:
    rows = []
    for p in ("aiml", "web", "data"):
        rs = load(p)
        rows += ([r for r in rs if r["gold"]["bid"]][: (n + 1) // 2] + [r for r in rs if not r["gold"]["bid"]][: n // 2])[:n]
    out = {}
    for s in systems:
        reset_gigsim()
        if s == "graph":
            recs = await run_set(rows, approve=False)
            recs = [{**r, "action": r.get("action") or "skip", "draft": r.get("draft") or "", "latency_s": r.get("latency_s", 0),
                     "tokens": r.get("tokens", 0)} for r in recs]
        else:
            recs = []
            for row in rows:
                recs.append(await run_baseline(s, model, row))
                print(s, recs[-1]["job_id"], recs[-1]["action"], recs[-1]["gold"]["bid"], recs[-1].get("error"), flush=True)
        out[s] = {"summary": await score(recs), "records": [{k: r.get(k) for k in ("job_id", "persona", "action", "unsupported", "violations",
                                                                                   "replied", "tokens", "latency_s", "error")} | {"gold_bid": r["gold"]["bid"]} for r in recs]}
        print(s, out[s]["summary"], flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12, help="jobs per persona")
    ap.add_argument("--model", default="qwen3:1.7b")
    ap.add_argument("--systems", nargs="+", default=["graph", "react", "supervisor"])
    a = ap.parse_args()
    from agent.config import cfg
    res = asyncio.run(main_async(a.n, a.model, a.systems))
    (OUT / "multiagent_compare.json").write_text(json.dumps({"meta": {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": a.model,
                                                                       "graph_profile": cfg("active_profile"), "jobs_per_persona": a.n},
                                                              "systems": res}, indent=1, default=str))


if __name__ == "__main__":
    main()
