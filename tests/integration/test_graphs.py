"""Graph runs against in-process GigSim + MCP servers (offline model profile)."""
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph
from agent.mcp_client import ToolHub
from agent.runner import resume, run_bid, run_conversation

SETTINGS = {"pacing": False, "floor_hourly": 45, "min_fixed": 400}


def pick(rows, **kw):
    return next(r for r in rows if all(r["gold"].get(k) == v for k, v in kw.items()))


@pytest.mark.asyncio
async def test_scam_is_skipped_with_reason(rows):
    store = InMemoryStore()
    g = build_bid_graph(InMemorySaver(), store)
    row = next(r for r in rows if r["gold"]["scam_type"] in ("off_platform_contact", "off_platform_payment"))
    res = await run_bid(g, row["job"], "it-user", "aiml", SETTINGS, store=store)
    assert res["values"]["decision"]["action"] == "skip"
    assert "scam" in res["values"]["decision"]["reasons"][0]
    assert not res["pending_approval"]


@pytest.mark.asyncio
async def test_bid_interrupts_then_submits_exactly_once(rows, tmp_dir):
    """Crash-and-resume: the approval waits in a SQLite checkpoint; a brand-new graph/saver
    (as after an API restart) resumes it; a second resume never submits twice."""
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    row = pick(rows, bid=True, scam=False)
    store = InMemoryStore()
    db = str(tmp_dir / "cp_crash.sqlite")
    async with AsyncSqliteSaver.from_conn_string(db) as saver:
        g = build_bid_graph(saver, store)
        res = await run_bid(g, row["job"], "crash-user", "aiml", SETTINGS, store=store)
    assert res["pending_approval"], res["status"]
    payload_keys = {"draft", "claims", "risk", "price", "preview", "compliance"}
    # --- "API restart": new saver, new graph object, same checkpoint file
    async with AsyncSqliteSaver.from_conn_string(db) as saver2:
        g2 = build_bid_graph(saver2, store)
        snap = await g2.aget_state({"configurable": {"thread_id": res["thread_id"]}})
        assert payload_keys <= set(snap.tasks[0].interrupts[0].value)
        bal0 = (await ToolHub(user_id="crash-user", persona="aiml").call("get_connects_balance", {}))["balance"]
        r1 = await resume(g2, res["thread_id"], {"action": "approve"}, user_id="crash-user", persona="aiml", store=store)
        r2 = await resume(g2, res["thread_id"], {"action": "approve"}, user_id="crash-user", persona="aiml", store=store)
        bal1 = (await ToolHub(user_id="crash-user", persona="aiml").call("get_connects_balance", {}))["balance"]
    assert r1["status"] == "submitted" and r2["status"] == "submitted"
    assert bal0 - bal1 == r1["values"]["submission"]["connects_cost"]


@pytest.mark.asyncio
async def test_edit_goes_back_through_compliance_and_approval(rows):
    store = InMemoryStore()
    g = build_bid_graph(InMemorySaver(), store)
    row = [r for r in rows if r["gold"]["bid"] and not r["gold"]["scam"]][1]
    res = await run_bid(g, row["job"], "edit-user", "aiml", SETTINGS, store=store)
    assert res["pending_approval"]
    text = res["values"]["drafts"][-1]["sendable_text"] + " Email me at me@example.com."
    r = await resume(g, res["thread_id"], {"action": "edit", "edited_text": text}, user_id="edit-user", persona="aiml", store=store)
    assert r["pending_approval"]                                  # back at the approval gate, not sent
    assert "me@example.com" not in r["values"]["drafts"][-1]["sendable_text"]   # compliance re-check redacted it


@pytest.mark.asyncio
async def test_critic_loop_is_bounded(rows):
    store = InMemoryStore()
    g = build_bid_graph(InMemorySaver(), store)
    for row in [r for r in rows if r["gold"]["bid"]][:6]:
        res = await run_bid(g, row["job"], "loop-user", "aiml", SETTINGS, store=store)
        assert len(res["values"].get("critiques") or []) <= 3     # first critique + at most 2 send-backs


@pytest.mark.asyncio
async def test_step_budget_moves_thread_to_needs_attention(rows, monkeypatch):
    from agent import runtime
    monkeypatch.setattr(runtime, "cfg", lambda k, d=None: 3 if k == "budgets.per_thread_steps" else d)
    store = InMemoryStore()
    g = build_bid_graph(InMemorySaver(), store)
    row = pick(rows, bid=True, scam=False)
    res = await run_bid(g, row["job"], "budget-user", "aiml", SETTINGS, store=store)
    assert res["values"]["status"] == "needs_attention"
    assert "step budget" in res["values"]["attention_reason"]


@pytest.mark.asyncio
async def test_degraded_mode_when_marketplace_down(rows, monkeypatch):
    from agent import mcp_client
    from mcp_servers.marketplace.server import ADAPTER
    monkeypatch.setattr(ADAPTER, "base", "http://127.0.0.1:9")    # nothing listens there
    monkeypatch.setattr(ADAPTER, "_client", None)
    monkeypatch.setattr(ADAPTER, "retries", 0)
    for b in mcp_client.BREAKERS.values():
        b.failures, b.opened_at = 0, None
    store = InMemoryStore()
    g = build_bid_graph(InMemorySaver(), store)
    row = pick(rows, bid=True, scam=False)
    job = {"id": row["job"]["id"]}                                 # forces a marketplace read in intake
    res = await run_bid(g, job, "deg-user", "aiml", SETTINGS, store=store)
    assert res["values"]["status"] == "queued_degraded"
    assert mcp_client.server_status()["marketplace"]["failures"] >= 1
    for b in mcp_client.BREAKERS.values():
        b.failures, b.opened_at = 0, None


@pytest.mark.asyncio
async def test_conversation_graph_drafts_reply_and_waits(rows):
    from gigsim.app import W
    row = pick(rows, bid=True, scam=False)
    hub = ToolHub(user_id="conv-user", persona="aiml")
    th = f"th_{row['job']['id']}"
    W.db.execute("INSERT INTO messages VALUES (?,?,?,?,?)", ("msg_test1", th, "aiml", W.now() - 10,
                                                              '{"from": "client", "text": "Could we schedule a short call this week?"}'))
    W.db.commit()
    store = InMemoryStore()
    g = build_conversation_graph(InMemorySaver(), store)
    res = await run_conversation(g, th, row["job"]["id"], "conv-user", "aiml", store=store)
    assert res["pending_approval"]
    assert res["values"]["intent"]["intent"] == "interview_request" and res["values"]["slots"]
    r = await resume(g, res["thread_id"], {"action": "approve"}, user_id="conv-user", persona="aiml", store=store)
    assert r["status"] == "sent" and r["values"]["sent"]["hold"]["status"] == "tentative"
    assert hub is not None
