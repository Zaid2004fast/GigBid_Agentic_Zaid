"""Part A deliverable: a single agent drafts ONE grounded proposal for a GigSim job using only
MCP tools (marketplace read + portfolio). Saves the full tool-call transcript, the proposal and
the claim-verification verdict to docs/traces/single_agent_proposal.json.

    python scripts/single_agent_proposal.py [--job dev_aiml_002] [--model qwen3:1.7b]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GIGSIM_URL", "inprocess")
os.environ.setdefault("GIGSIM_ERROR_RATE", "0")

from agent.llm import load_prompt  # noqa: E402
from agent.mcp_client import ToolHub  # noqa: E402
from rag.corpus import get_corpus  # noqa: E402
from rag.verify import corpus_resolvers, verify_draft  # noqa: E402

TOOLS = ["get_job", "get_client_history", "search_evidence", "get_case_study", "get_market_stats"]


async def main(job_id: str, model: str) -> None:
    from langchain_ollama import ChatOllama
    from langgraph.prebuilt import create_react_agent
    hub = ToolHub(user_id="single-agent", persona="aiml")
    llm = ChatOllama(model=model, reasoning=False, temperature=0.1, num_ctx=8192, num_predict=800)
    sys_msg, user_msg = load_prompt("react_baseline").render(job_id=job_id, persona="aiml")
    agent = create_react_agent(llm, await hub.langchain_tools(names=TOOLS), prompt=sys_msg)
    out = await agent.ainvoke({"messages": [("user", user_msg)]}, {"recursion_limit": 24})
    transcript = []
    for m in out["messages"]:
        entry = {"role": m.type, "content": str(m.content)[:1500]}
        if getattr(m, "tool_calls", None):
            entry["tool_calls"] = [{"name": t["name"], "args": t["args"]} for t in m.tool_calls]
        transcript.append(entry)
    final = str(out["messages"][-1].content)
    resolve, search = corpus_resolvers(get_corpus("aiml"))
    _, rep = await verify_draft(final, {}, resolve, search, fix=False)
    doc = {"job_id": job_id, "model": model, "tools_exposed": TOOLS, "transcript": transcript, "final": final,
           "verification": rep.model_dump()}
    p = ROOT / "docs" / "traces" / "single_agent_proposal.json"
    p.write_text(json.dumps(doc, indent=1, default=str))
    calls = [c["name"] for t in transcript for c in t.get("tool_calls", [])]
    print(f"tool calls: {calls}\nclaims: {len(rep.claims)}, unsupported: {rep.unsupported_before}\nwrote {p}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", default="dev_aiml_002")
    ap.add_argument("--model", default="qwen3:1.7b")
    a = ap.parse_args()
    asyncio.run(main(a.job, a.model))
