"""Portfolio server through an in-memory MCP client (real protocol, no network)."""
import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.portfolio.server import mcp

META = {"gigbid": {"user_id": "t", "persona": "aiml", "trace_id": "test"}}


@pytest.mark.asyncio
async def test_tools_resources_prompts_listed():
    async with create_connected_server_and_client_session(mcp) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
        assert {"search_evidence", "get_case_study", "list_skills", "get_evidence", "have_i_done", "find_winning_proposals"} <= set(tools)
        assert all(t.annotations.readOnlyHint for t in tools.values())
        templates = {t.uriTemplate for t in (await s.list_resource_templates()).resourceTemplates}
        assert {"portfolio://case/{id}", "portfolio://proposal/{id}"} <= templates
        prompts = {p.name for p in (await s.list_prompts()).prompts}
        assert "answer_screening_question" in prompts


@pytest.mark.asyncio
async def test_search_evidence_returns_typed_items():
    async with create_connected_server_and_client_session(mcp) as s:
        r = await s.call_tool("search_evidence", {"requirement": "LangChain retrieval assistant", "k": 3}, meta=META)
        assert not r.isError
        data = r.structuredContent
        assert data["items"] and {"item_id", "type", "source", "date", "outcome", "support"} <= set(data["items"][0])
        assert all(i["item_id"].startswith("aiml:") for i in data["items"])


@pytest.mark.asyncio
async def test_search_evidence_validates_input():
    async with create_connected_server_and_client_session(mcp) as s:
        r = await s.call_tool("search_evidence", {"requirement": "x", "k": 500}, meta=META)
        assert r.isError


@pytest.mark.asyncio
async def test_case_study_and_resource():
    async with create_connected_server_and_client_session(mcp) as s:
        r = await s.call_tool("get_case_study", {"id": "aiml:cs:docs-assistant"}, meta=META)
        assert r.structuredContent["project"] == "docs-assistant"
        res = await s.read_resource("portfolio://case/docs-assistant")
        assert "docs-assistant" in res.contents[0].text or "assistant" in res.contents[0].text
        p = await s.read_resource("portfolio://proposal/aiml-prop-000")
        assert json.loads(p.contents[0].text)["outcome"] in ("won", "replied", "ignored")
