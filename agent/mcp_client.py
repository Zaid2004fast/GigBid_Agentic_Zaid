"""MCP client layer for the agents (A6 client discipline).

* Transport from config: `inprocess` (in-memory MCP sessions against the server objects;
  tests/evals - still the full MCP protocol) or `http` (MultiServerMCPClient over
  Streamable HTTP with bearer auth; docker/prod).
* Per-agent allowlists: an agent can only call tools listed for it in config.yaml.
* Timeouts, bounded retries with exponential backoff, and a per-server circuit breaker.
  When the marketplace is down the breaker opens and calls raise ToolUnavailable
  immediately; the graph moves the thread to `queued_degraded`, the UI shows a banner,
  and the worker re-queues the work when the breaker closes (degraded mode).
* Every call carries {user_id, persona, trace_id} in MCP `_meta` and is recorded as a
  tool span (masked) in the trace.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import random
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from agent.config import cfg
from common.tracing import current_trace, span

SERVER_MODULES = {
    "portfolio": "mcp_servers.portfolio.server",
    "marketplace": "mcp_servers.marketplace.server",
    "workspace": "mcp_servers.workspace.server",
}
TOOL_SERVER = {
    # portfolio
    "search_evidence": "portfolio", "get_case_study": "portfolio", "list_skills": "portfolio", "have_i_done": "portfolio",
    "get_evidence": "portfolio", "find_winning_proposals": "portfolio",
    # marketplace
    "search_jobs": "marketplace", "get_job": "marketplace", "get_client_history": "marketplace",
    "get_connects_balance": "marketplace", "list_threads": "marketplace", "list_messages": "marketplace",
    "list_events": "marketplace", "get_market_stats": "marketplace", "get_policy": "marketplace",
    "create_proposal_draft": "marketplace", "submit_proposal": "marketplace", "send_message": "marketplace",
    # workspace
    "free_slots": "workspace", "create_interview_hold": "workspace", "create_email_draft": "workspace",
}
UNAVAILABLE_MARKERS = ("unavailable", "upstream_error", "ConnectError", "connection", "timed out", "rate_limited")


class ToolError(Exception):
    """The tool ran and returned an error (bad input, not found, policy rejection...)."""


class ToolUnavailable(Exception):
    """The server (or its upstream) is unreachable: degraded mode."""

    def __init__(self, server: str, reason: str):
        super().__init__(f"{server} unavailable: {reason}")
        self.server, self.reason = server, reason


class ToolNotAllowed(Exception):
    pass


@dataclass
class Breaker:
    failures: int = 0
    opened_at: float | None = None
    last_error: str = ""

    def is_open(self) -> bool:
        cd = cfg("mcp.circuit_breaker.cooldown_s", 30)
        if self.opened_at and time.time() - self.opened_at < cd:
            return True
        return False

    def record(self, ok: bool, err: str = "") -> None:
        if ok:
            self.failures, self.opened_at, self.last_error = 0, None, ""
        else:
            self.failures += 1
            self.last_error = err
            if self.failures >= cfg("mcp.circuit_breaker.failures_to_open", 3):
                self.opened_at = time.time()


BREAKERS: dict[str, Breaker] = {s: Breaker() for s in SERVER_MODULES}


def server_status() -> dict[str, dict]:
    return {s: {"ok": not b.is_open() and b.failures == 0, "open": b.is_open(), "failures": b.failures,
                "last_error": b.last_error[:200]} for s, b in BREAKERS.items()}


@dataclass
class ToolHub:
    user_id: str = "local"
    persona: str = "aiml"
    trace_id: str | None = None
    transport: str = field(default_factory=lambda: cfg("mcp.transport", "inprocess"))
    record_spans: bool = True

    # ------------------------------------------------------------------ core call
    async def call(self, tool: str, args: dict | None = None, agent: str | None = None, timeout: float | None = None) -> Any:
        if agent is not None:
            allowed = cfg(f"mcp.allowlists.{agent}", []) or []
            if tool not in allowed:
                raise ToolNotAllowed(f"agent {agent!r} may not call {tool!r} (allowlist: {allowed})")
        server = TOOL_SERVER[tool]
        br = BREAKERS[server]
        if br.is_open():
            raise ToolUnavailable(server, f"circuit open ({br.last_error[:80]})")
        timeout = timeout or cfg(f"mcp.servers.{server}.timeout_s", cfg("mcp.timeout_s", 20))
        retries = cfg("mcp.retries", 3)
        base = cfg("mcp.backoff_base_s", 0.5)
        meta = {"gigbid": {"user_id": self.user_id, "persona": self.persona, "trace_id": self.trace_id or current_trace.get() or "untraced"}}
        last: Exception | None = None
        for attempt in range(retries + 1):
            ctx = span(f"tool:{tool}", "tool", server=server, tool=tool, args=args or {}, agent=agent, attempt=attempt) \
                if self.record_spans else _nullspan()
            with ctx as sp:
                try:
                    res = await asyncio.wait_for(self._raw_call(server, tool, args or {}, meta), timeout)
                    br.record(True)
                    if sp is not None:
                        sp["attrs"]["result"] = res
                    return res
                except ToolError as e:
                    msg = str(e)
                    if server == "marketplace" and any(m in msg for m in UNAVAILABLE_MARKERS):
                        last = ToolUnavailable(server, msg)
                        br.record(False, msg)
                    else:
                        br.record(True)
                        if sp is not None:
                            sp["attrs"]["tool_error"] = msg
                        raise
                except (asyncio.TimeoutError, OSError, ConnectionError) as e:
                    last = ToolUnavailable(server, f"{type(e).__name__}: {e}")
                    br.record(False, str(last))
                except Exception as e:  # noqa: BLE001 - transport errors (httpx, anyio, ExceptionGroup)
                    last = ToolUnavailable(server, f"{type(e).__name__}: {str(e)[:200]}")
                    br.record(False, str(last))
            if br.is_open():
                break
            if attempt < retries:
                await asyncio.sleep(base * (2 ** attempt) + random.uniform(0, 0.1))
        raise last or ToolUnavailable(server, "unknown")

    async def _raw_call(self, server: str, tool: str, args: dict, meta: dict) -> Any:
        if self.transport == "inprocess":
            from mcp.shared.memory import create_connected_server_and_client_session
            mod = importlib.import_module(SERVER_MODULES[server])
            async with create_connected_server_and_client_session(mod.mcp) as session:
                res = await session.call_tool(tool, args, read_timeout_seconds=timedelta(seconds=60), meta=meta)
        else:
            from langchain_mcp_adapters.client import MultiServerMCPClient
            client = MultiServerMCPClient(self.connections())
            async with client.session(server) as session:
                res = await session.call_tool(tool, args, read_timeout_seconds=timedelta(seconds=60), meta=meta)
        return _parse(res)

    def connections(self) -> dict:
        tok = os.getenv("MCP_SERVER_TOKEN", "")
        conns = {}
        for s in SERVER_MODULES:
            conns[s] = {"transport": "streamable_http", "url": cfg(f"mcp.servers.{s}.url"),
                        "headers": {"Authorization": f"Bearer {tok}", "X-Trace-Id": self.trace_id or ""}, "timeout": 30}
        return conns

    # ------------------------------------------------------------------ helpers
    def for_agent(self, agent: str) -> "AgentTools":
        return AgentTools(self, agent)

    async def list_tools(self, server: str) -> list[dict]:
        from mcp.shared.memory import create_connected_server_and_client_session
        if self.transport == "inprocess":
            mod = importlib.import_module(SERVER_MODULES[server])
            async with create_connected_server_and_client_session(mod.mcp) as session:
                tl = await session.list_tools()
        else:
            from langchain_mcp_adapters.client import MultiServerMCPClient
            async with MultiServerMCPClient(self.connections()).session(server) as session:
                tl = await session.list_tools()
        return [t.model_dump() for t in tl.tools]

    async def langchain_tools(self, agent: str | None = None, names: list[str] | None = None, descriptions: dict | None = None):
        """LangChain tools (for the ReAct / supervisor baselines), filtered by allowlist or names."""
        from langchain_core.tools import StructuredTool
        allowed = names or (cfg(f"mcp.allowlists.{agent}", []) if agent else list(TOOL_SERVER))
        out = []
        for server in SERVER_MODULES:
            for t in await self.list_tools(server):
                if t["name"] not in allowed:
                    continue
                name = t["name"]

                async def _run(_name=name, **kw):
                    try:
                        return json.dumps(await self.call(_name, kw), default=str)[:4000]
                    except Exception as e:  # noqa: BLE001
                        return f"ERROR: {e}"
                out.append(StructuredTool.from_function(coroutine=_run, name=name,
                                                        description=(descriptions or {}).get(name, t.get("description") or name),
                                                        args_schema=t["inputSchema"]))
        return out

    async def health(self) -> dict[str, bool]:
        out = {}
        for s in SERVER_MODULES:
            try:
                await asyncio.wait_for(self.list_tools(s), 5)
                out[s] = not BREAKERS[s].is_open()
            except Exception:  # noqa: BLE001
                out[s] = False
        return out


class AgentTools:
    def __init__(self, hub: ToolHub, agent: str):
        self.hub, self.agent = hub, agent

    async def __call__(self, tool: str, **args):
        return await self.hub.call(tool, args, agent=self.agent)


class _nullspan:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


def _parse(res) -> Any:
    if getattr(res, "isError", False):
        txt = " ".join(getattr(c, "text", "") for c in res.content)
        raise ToolError(txt or "tool error")
    if getattr(res, "structuredContent", None) is not None:
        sc = res.structuredContent
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    texts = [getattr(c, "text", "") for c in res.content]
    try:
        return json.loads(texts[0]) if len(texts) == 1 else [json.loads(t) for t in texts]
    except Exception:  # noqa: BLE001
        return "\n".join(texts)
