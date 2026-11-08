"""Marketplace server via in-memory MCP client: annotations, dry_run, idempotency, audit."""
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.marketplace.server import AUDIT, mcp

META = {"gigbid": {"user_id": "mk-test", "persona": "web", "trace_id": "trace-mk"}}
LETTER = "For your project you need a reliable API. I built a similar Django backend with background workers last year."


@pytest.mark.asyncio
async def test_write_tools_have_correct_annotations():
    async with create_connected_server_and_client_session(mcp) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
    assert tools["get_job"].annotations.readOnlyHint is True
    for name in ("create_proposal_draft", "submit_proposal", "send_message"):
        a = tools[name].annotations
        assert a.readOnlyHint is False and a.idempotentHint is True
    assert tools["submit_proposal"].annotations.destructiveHint is True
    assert tools["create_proposal_draft"].annotations.destructiveHint is False
    assert tools["submit_proposal"].outputSchema is not None


@pytest.mark.asyncio
async def test_dry_run_previews_without_side_effects():
    async with create_connected_server_and_client_session(mcp) as s:
        bal0 = (await s.call_tool("get_connects_balance", {}, meta=META)).structuredContent["balance"]
        r = await s.call_tool("create_proposal_draft", {"proposal": {"job_id": "dev_web_000", "cover_letter": LETTER, "bid_amount": 900,
                                                                     "idempotency_key": "dry-run-key-1", "dry_run": True}}, meta=META)
        out = r.structuredContent
        assert out["status"] == "dry_run" and out["preview"]["cover_letter"] == LETTER and out["connects_cost"] > 0
        assert (await s.call_tool("get_connects_balance", {}, meta=META)).structuredContent["balance"] == bal0


@pytest.mark.asyncio
async def test_retried_submit_spends_connects_once():
    async with create_connected_server_and_client_session(mcp) as s:
        d = (await s.call_tool("create_proposal_draft", {"proposal": {"job_id": "dev_web_002", "cover_letter": LETTER, "bid_amount": 800,
                                                                      "idempotency_key": "idem-draft-002"}}, meta=META)).structuredContent
        pid = d["result"]["proposal_id"]
        bal0 = (await s.call_tool("get_connects_balance", {}, meta=META)).structuredContent["balance"]
        sub = {"submission": {"proposal_id": pid, "job_id": "dev_web_002", "idempotency_key": "idem-submit-002"}}
        first = (await s.call_tool("submit_proposal", sub, meta=META)).structuredContent
        second = (await s.call_tool("submit_proposal", sub, meta=META)).structuredContent
        bal1 = (await s.call_tool("get_connects_balance", {}, meta=META)).structuredContent["balance"]
        assert first["status"] == "submitted" and second["status"] == "replayed"
        assert bal0 - bal1 == first["connects_cost"]
    assert AUDIT.verify()


@pytest.mark.asyncio
async def test_input_constraints_enforced():
    async with create_connected_server_and_client_session(mcp) as s:
        r = await s.call_tool("create_proposal_draft", {"proposal": {"job_id": "dev_web_000", "cover_letter": "too short", "bid_amount": -1,
                                                                     "idempotency_key": "k"}}, meta=META)
        assert r.isError
