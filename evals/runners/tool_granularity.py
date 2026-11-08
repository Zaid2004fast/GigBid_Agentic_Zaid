"""R&D question A - does tool granularity change agent behaviour?

40 tasks with known correct calls. Three tool surfaces, same LLM, same tasks:
  fine     - every GigBid MCP tool exposed (19 tools, original one-line descriptions)
  coarse   - 3 tools (marketplace / portfolio / workspace) each taking {action, args}
  best     - fine-grained names, but only tools relevant to the agent role are exposed
             (allowlists) and descriptions rewritten as "use when ... / do not use for ..."
Metrics: tool-selection accuracy, argument accuracy, prompt + completion tokens per task.

    python -m evals.runners.tool_granularity --model qwen3:1.7b
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time

from evals.runners.harness import ROOT

OUT = ROOT / "evals" / "results"

# (task, correct tool, {arg: expected substring}, role)
TASKS = [
    ("Find portfolio evidence that I have built Celery background workers.", "search_evidence", {"requirement": "celery"}, "matcher"),
    ("Do I have proof of FAISS vector search work in my portfolio?", "search_evidence", {"requirement": "faiss"}, "matcher"),
    ("Look for evidence of dbt modelling experience.", "search_evidence", {"requirement": "dbt"}, "matcher"),
    ("Is there anything in my portfolio about Stripe subscription billing?", "search_evidence", {"requirement": "stripe"}, "matcher"),
    ("Search my work for Tableau dashboards.", "search_evidence", {"requirement": "tableau"}, "matcher"),
    ("Have I done RAG for a client in the legal industry?", "have_i_done", {"skill": "rag", "industry": "legal"}, "matcher"),
    ("Have I ever used Airflow for a fintech client?", "have_i_done", {"skill": "airflow", "industry": "fintech"}, "matcher"),
    ("Which skills can my portfolio actually prove?", "list_skills", {}, "matcher"),
    ("List every skill I have evidence for.", "list_skills", {}, "matcher"),
    ("Open the full case study 'docs-assistant'.", "get_case_study", {"id": "docs-assistant"}, "writer"),
    ("Load the case study with id churn-model so I can quote its result.", "get_case_study", {"id": "churn-model"}, "writer"),
    ("Show me past proposals that won for an NLP classification job.", "find_winning_proposals", {"job_summary": "nlp"}, "writer"),
    ("Get the full text of evidence items aiml:cs:docs-assistant and aiml:cv:docs-assistant.", "get_evidence", {"item_ids": "docs-assistant"}, "verifier"),
    ("Search open jobs that mention LangGraph.", "search_jobs", {"query": "langgraph"}, "scout"),
    ("Find new Data Analytics jobs.", "search_jobs", {"category": "data analytics"}, "scout"),
    ("Look for jobs asking for Next.js.", "search_jobs", {"query": "next.js"}, "scout"),
    ("Get the details of job dev_aiml_010.", "get_job", {"job_id": "dev_aiml_010"}, "scout"),
    ("What are the screening questions on job live_0042?", "get_job", {"job_id": "live_0042"}, "scout"),
    ("Check the hiring history of client cl_0012.", "get_client_history", {"client_id": "cl_0012"}, "risk"),
    ("Is client cl_0300 payment verified and do they hire?", "get_client_history", {"client_id": "cl_0300"}, "risk"),
    ("How many Connects do I have left this week?", "get_connects_balance", {}, "pricing"),
    ("What's my Connects balance?", "get_connects_balance", {}, "pricing"),
    ("What do Web Development fixed-price jobs usually pay?", "get_market_stats", {"category": "web development"}, "pricing"),
    ("Give me hourly rate percentiles for AI & Machine Learning.", "get_market_stats", {"category": "ai & machine learning", "budget_type": "hourly"}, "pricing"),
    ("What does a proposal cost in Connects under the current platform policy?", "get_policy", {}, "pricing"),
    ("Which platform rules are in force right now?", "get_policy", {}, "pricing"),
    ("List my client conversations.", "list_threads", {}, "liaison"),
    ("Read the messages in thread th_dev_web_003.", "list_messages", {"thread_id": "th_dev_web_003"}, "liaison"),
    ("What did the client say in thread th_live_0007?", "list_messages", {"thread_id": "th_live_0007"}, "liaison"),
    ("When am I free for a 30 minute interview this week?", "free_slots", {}, "liaison"),
    ("Find three free slots for a call in the next 5 days.", "free_slots", {}, "liaison"),
    ("Put a tentative hold on my calendar at 2026-11-10T11:00:00+05:00 for the client interview (key hold-abc-123).", "create_interview_hold",
     {"start": "2026-11-10"}, "liaison"),
    ("Draft an email to Sara with subject 'Kickoff' saying we start Monday (key email-xyz-987).", "create_email_draft", {"subject": "kickoff"}, "liaison"),
    ("Send the approved message 'Thanks, Tuesday works' to thread th_dev_aiml_002 (key msg-key-0001).", "send_message", {"thread_id": "th_dev_aiml_002"}, "liaison"),
    ("Create a proposal draft for job dev_web_001 at $900 with the approved cover letter (key draft-key-001).", "create_proposal_draft",
     {"job_id": "dev_web_001"}, "submitter"),
    ("Submit approved proposal prop_123abc for job dev_web_001 (key submit-key-001).", "submit_proposal", {"proposal_id": "prop_123abc"}, "submitter"),
    ("Preview what submitting proposal prop_9 for job dev_data_004 would cost, without submitting (key submit-key-002).", "submit_proposal",
     {"dry_run": "true"}, "submitter"),
    ("What events happened on my proposals since time 0?", "list_events", {}, "liaison"),
    ("Have any clients viewed or replied to my proposals?", "list_events", {}, "liaison"),
    ("Find evidence for 'background job queue with retries'.", "search_evidence", {"requirement": "queue"}, "matcher"),
]

BEST_DESCRIPTIONS = {
    "search_evidence": "Use when you need PROOF from the freelancer's own portfolio for ONE job requirement (a skill, tool or kind of work). Do not use for searching jobs.",
    "have_i_done": "Use for yes/no questions 'have I done <skill> for a client in <industry>'. Args: skill, industry.",
    "list_skills": "Use to list every skill the portfolio can prove. No arguments.",
    "get_case_study": "Use to open ONE full case study by its project id (e.g. 'docs-assistant').",
    "get_evidence": "Use to load the full text of specific evidence item ids (list).",
    "find_winning_proposals": "Use to see past proposals that won/replied for similar jobs (tone only, never proof).",
    "search_jobs": "Use to find OPEN JOBS on the marketplace by keywords (query) or category. Not for portfolio.",
    "get_job": "Use to load one job's full details by job_id (e.g. dev_aiml_010, live_0042).",
    "get_client_history": "Use to check a CLIENT's history (spend, hires, payment verified) by client_id (cl_xxxx).",
    "get_connects_balance": "Use to get this week's Connects balance. No arguments.",
    "get_market_stats": "Use for typical prices in a category: args category and budget_type (fixed|hourly).",
    "get_policy": "Use for current platform rules and the Connects cost formula. No arguments.",
    "list_threads": "Use to list client conversation threads. No arguments.",
    "list_messages": "Use to read messages of ONE thread by thread_id (th_...).",
    "list_events": "Use to see proposal events: viewed, replied, interview, hired, lost.",
    "free_slots": "Use to find free calendar slots for interviews.",
    "create_interview_hold": "Use to place a TENTATIVE calendar hold at a given ISO start time.",
    "create_email_draft": "Use to create an email DRAFT (never sends).",
    "send_message": "Use ONLY after human approval to send a message to a client thread.",
    "create_proposal_draft": "Use ONLY after human approval to create a proposal draft for a job.",
    "submit_proposal": "Use ONLY after human approval to submit a draft; dry_run=true previews cost without submitting.",
}
COARSE = {"marketplace": ["search_jobs", "get_job", "get_client_history", "get_connects_balance", "get_market_stats", "get_policy",
                          "list_threads", "list_messages", "list_events", "create_proposal_draft", "submit_proposal", "send_message"],
          "portfolio": ["search_evidence", "have_i_done", "list_skills", "get_case_study", "get_evidence", "find_winning_proposals"],
          "workspace": ["free_slots", "create_interview_hold", "create_email_draft"]}
ROLE_TOOLS = {"matcher": ["search_evidence", "have_i_done", "list_skills", "find_winning_proposals"],
              "writer": ["search_evidence", "get_case_study", "get_evidence", "find_winning_proposals"],
              "verifier": ["search_evidence", "get_evidence"], "scout": ["search_jobs", "get_job"],
              "risk": ["get_client_history", "get_job"], "pricing": ["get_market_stats", "get_connects_balance", "get_policy"],
              "liaison": ["list_threads", "list_messages", "list_events", "send_message", "free_slots", "create_interview_hold", "create_email_draft"],
              "submitter": ["create_proposal_draft", "submit_proposal"]}


async def tool_specs() -> dict[str, dict]:
    from agent.mcp_client import SERVER_MODULES, ToolHub
    hub = ToolHub()
    specs = {}
    for s in SERVER_MODULES:
        for t in await hub.list_tools(s):
            specs[t["name"]] = {"name": t["name"], "description": (t.get("description") or "").strip().split("\n")[0],
                                "parameters": t["inputSchema"]}
    return specs


def as_lc(spec: dict) -> dict:
    return {"type": "function", "function": {"name": spec["name"], "description": spec["description"], "parameters": spec["parameters"]}}


def surface(name: str, specs: dict, role: str) -> list[dict]:
    if name == "fine":
        return [as_lc(s) for s in specs.values()]
    if name == "best":
        return [as_lc({**specs[t], "description": BEST_DESCRIPTIONS[t]}) for t in ROLE_TOOLS[role]]
    return [as_lc({"name": srv, "description": f"{srv.capitalize()} operations. action is one of: {', '.join(acts)}. args holds that action's arguments.",
                   "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": acts}, "args": {"type": "object"}},
                                  "required": ["action"]}}) for srv, acts in COARSE.items()]


def normalise(name: str, call: dict) -> tuple[str, dict]:
    if name == "coarse":
        return call["args"].get("action", ""), call["args"].get("args") or {}
    return call["name"], call["args"]


def arg_ok(expected: dict, got: dict) -> bool:
    blob = json.dumps(got).lower()
    return all(str(v).lower() in blob for v in expected.values())


async def run(model: str, limit: int | None) -> dict:
    from langchain_ollama import ChatOllama

    from agent.llm import load_prompt
    specs = await tool_specs()
    chat = ChatOllama(model=model, reasoning=False, temperature=0, num_ctx=8192, num_predict=200)
    res = {}
    for sname in ("fine", "coarse", "best"):
        recs = []
        for task, tool, args, role in TASKS[:limit]:
            tools = surface(sname, specs, role)
            t0 = time.time()
            try:
                sys_msg, user_msg = load_prompt("eval_tool_agent").render(task=task)
                msg = await chat.bind_tools(tools).ainvoke([("system", sys_msg), ("user", user_msg)])
                calls = msg.tool_calls or []
                um = msg.usage_metadata or {}
                got_tool, got_args = normalise(sname, {"name": calls[0]["name"], "args": calls[0]["args"]}) if calls else ("", {})
                if sname == "coarse" and calls:
                    got_tool, got_args = calls[0]["args"].get("action", ""), calls[0]["args"].get("args") or {}
                recs.append({"task": task, "expected": tool, "got": got_tool, "tool_ok": got_tool == tool,
                             "args_ok": got_tool == tool and arg_ok(args, got_args), "tokens": um.get("total_tokens", 0),
                             "latency_s": round(time.time() - t0, 2)})
            except Exception as e:  # noqa: BLE001
                recs.append({"task": task, "expected": tool, "got": "", "tool_ok": False, "args_ok": False, "tokens": 0, "error": str(e)[:200]})
        n = len(recs)
        res[sname] = {"tool_selection_accuracy": round(sum(r["tool_ok"] for r in recs) / n, 4),
                      "argument_accuracy": round(sum(r["args_ok"] for r in recs) / n, 4),
                      "tokens_per_task": round(sum(r["tokens"] for r in recs) / n, 1), "n": n, "records": recs}
        print(sname, {k: v for k, v in res[sname].items() if k != "records"}, flush=True)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3:1.7b")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    res = asyncio.run(run(a.model, a.limit))
    out = {"meta": {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": a.model, "tasks": len(TASKS[: a.limit])}, "surfaces": res}
    (OUT / "tool_granularity.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
