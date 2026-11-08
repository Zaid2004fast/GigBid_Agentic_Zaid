import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.workspace.server import mcp

META = {"gigbid": {"user_id": "ws-test", "persona": "aiml", "trace_id": "t"}}


@pytest.mark.asyncio
async def test_slots_hold_is_idempotent_and_blocks_slot():
    async with create_connected_server_and_client_session(mcp) as s:
        slots = (await s.call_tool("free_slots", {"days": 7, "max_slots": 3}, meta=META)).structuredContent["slots"]
        assert len(slots) == 3
        args = {"hold": {"start": slots[0]["start"], "duration_minutes": 30, "title": "Interview", "idempotency_key": "hold-key-0001"}}
        a = (await s.call_tool("create_interview_hold", args, meta=META)).structuredContent
        b = (await s.call_tool("create_interview_hold", args, meta=META)).structuredContent
        assert a["event_id"] == b["event_id"] and a["status"] == "tentative"
        again = (await s.call_tool("free_slots", {"days": 7, "max_slots": 3}, meta=META)).structuredContent["slots"]
        assert slots[0]["start"] not in [x["start"] for x in again]


@pytest.mark.asyncio
async def test_email_draft_never_sends():
    async with create_connected_server_and_client_session(mcp) as s:
        r = (await s.call_tool("create_email_draft", {"draft": {"to_name": "Sara", "subject": "Kickoff", "body": "We start on Monday.",
                                                                 "idempotency_key": "email-key-0001"}}, meta=META)).structuredContent
        assert r["status"] == "draft"
