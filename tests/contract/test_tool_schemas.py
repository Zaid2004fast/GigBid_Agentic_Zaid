"""Schema snapshot test (A7): fails CI when a tool signature changes unintentionally.

Regenerate deliberately with:  UPDATE_SNAPSHOTS=1 pytest tests/contract
"""
import json
import os
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

SNAP = Path(__file__).parent / "snapshots"
SERVERS = ["portfolio", "marketplace", "workspace"]


async def _schema(server: str) -> dict:
    import importlib
    mod = importlib.import_module(f"mcp_servers.{server}.server")
    async with create_connected_server_and_client_session(mod.mcp) as s:
        tools = (await s.list_tools()).tools
    return {t.name: {"input": t.inputSchema, "output": t.outputSchema,
                     "annotations": t.annotations.model_dump(exclude_none=True) if t.annotations else None} for t in sorted(tools, key=lambda x: x.name)}


@pytest.mark.asyncio
@pytest.mark.parametrize("server", SERVERS)
async def test_tool_schema_snapshot(server):
    current = await _schema(server)
    path = SNAP / f"{server}.json"
    if os.getenv("UPDATE_SNAPSHOTS") == "1" or not path.exists():
        SNAP.mkdir(exist_ok=True)
        path.write_text(json.dumps(current, indent=1, sort_keys=True) + "\n")
        pytest.skip(f"snapshot written for {server}")
    expected = json.loads(path.read_text())
    assert set(current) == set(expected), f"tools added/removed on {server}: {set(current) ^ set(expected)}"
    for name in expected:
        assert current[name] == expected[name], f"{server}.{name} signature changed - update the snapshot only if intended"
