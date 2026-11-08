"""The single marketplace port (R1).

All marketplace access in the graph goes through `MarketplacePort`. Two adapters:
  * GigSimPort      -> our Marketplace MCP server (which wraps GigSim)
  * UpworkLivePort  -> the official Upwork MCP server (OAuth 2.1, Streamable HTTP),
                       mapped onto the same method names and normalised shapes
Switched by config: marketplace.mode = gigsim | upwork_live.  Nodes cannot tell which
marketplace they are talking to - viva Q7: switching changes config, not graph code.
"""
from __future__ import annotations

from typing import Protocol

from agent.config import cfg
from agent.mcp_client import ToolHub


class MarketplacePort(Protocol):
    name: str
    async def search_jobs(self, query: str = "", category: str = "", skills: str = "", since: float | None = None,
                          limit: int = 20, split: str = "live") -> list[dict]: ...
    async def get_job(self, job_id: str) -> dict: ...
    async def get_client_history(self, client_id: str) -> dict: ...
    async def get_connects_balance(self) -> dict: ...
    async def get_market_stats(self, category: str, budget_type: str) -> dict | None: ...
    async def get_policy(self) -> dict: ...
    async def list_threads(self) -> list[dict]: ...
    async def list_messages(self, thread_id: str) -> list[dict]: ...
    async def list_events(self, since: float) -> list[dict]: ...
    async def preview_proposal(self, job_id: str, text: str, bid: float, answers: list[str], key: str) -> dict: ...
    async def create_proposal_draft(self, job_id: str, text: str, bid: float, answers: list[str], key: str) -> dict: ...
    async def submit_proposal(self, proposal_id: str, job_id: str, key: str) -> dict: ...
    async def send_message(self, thread_id: str, text: str, key: str, dry_run: bool = False) -> dict: ...


class GigSimPort:
    name = "gigsim"

    def __init__(self, hub: ToolHub, agent: str | None = None):
        self.hub, self.agent = hub, agent

    async def _c(self, tool, args=None, agent=None):
        return await self.hub.call(tool, args or {}, agent=agent if agent is not None else self.agent)

    async def search_jobs(self, query="", category="", skills="", since=None, limit=20, split="live"):
        r = await self._c("search_jobs", {"query": query, "category": category, "skills": skills, "since": since, "limit": limit, "split": split})
        return r["jobs"]

    async def get_job(self, job_id):
        return await self._c("get_job", {"job_id": job_id})

    async def get_client_history(self, client_id):
        return await self._c("get_client_history", {"client_id": client_id})

    async def get_connects_balance(self):
        return await self._c("get_connects_balance")

    async def get_market_stats(self, category, budget_type):
        try:
            return await self._c("get_market_stats", {"category": category, "budget_type": budget_type})
        except Exception:  # noqa: BLE001 - not enough data is a normal outcome
            return None

    async def get_policy(self):
        return await self._c("get_policy")

    async def list_threads(self):
        return (await self._c("list_threads"))["threads"]

    async def list_messages(self, thread_id):
        return (await self._c("list_messages", {"thread_id": thread_id}))["messages"]

    async def list_events(self, since):
        return (await self._c("list_events", {"since": since}))["events"]

    async def preview_proposal(self, job_id, text, bid, answers, key):
        return await self._c("create_proposal_draft", {"proposal": {"job_id": job_id, "cover_letter": text, "bid_amount": bid,
                                                                    "screening_answers": answers, "idempotency_key": key, "dry_run": True}})

    async def create_proposal_draft(self, job_id, text, bid, answers, key):
        return await self._c("create_proposal_draft", {"proposal": {"job_id": job_id, "cover_letter": text, "bid_amount": bid,
                                                                    "screening_answers": answers, "idempotency_key": key}})

    async def submit_proposal(self, proposal_id, job_id, key):
        return await self._c("submit_proposal", {"submission": {"proposal_id": proposal_id, "job_id": job_id, "idempotency_key": key}})

    async def send_message(self, thread_id, text, key, dry_run=False):
        return await self._c("send_message", {"message": {"thread_id": thread_id, "text": text, "idempotency_key": key, "dry_run": dry_run}})


def get_port(hub: ToolHub, agent: str | None = None) -> MarketplacePort:
    mode = cfg("marketplace.mode", "gigsim")
    if mode == "upwork_live":
        from mcp_servers.marketplace.adapters.upwork_live import UpworkLivePort
        return UpworkLivePort(hub.user_id, trace_id=hub.trace_id)
    return GigSimPort(hub, agent)
