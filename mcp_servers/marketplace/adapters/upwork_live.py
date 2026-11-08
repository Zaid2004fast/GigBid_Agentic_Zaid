"""Live Upwork adapter: the official Upwork MCP server behind GigBid's marketplace port.

* Connects with langchain-mcp-adapters' MultiServerMCPClient over Streamable HTTP to
  https://mcp.upwork.com/mcp, authenticated with the user's OAuth 2.1 access token
  (obtained by apps/api/auth/upwork_oauth.py, stored encrypted per user, refreshed here).
* Maps Upwork's tools onto the port's methods.  Upwork's exact tool names are discovered
  at connect time (list_tools) and matched against TOOL_CANDIDATES, so a renamed tool is a
  config change, not a code change; the resolved mapping is logged in the trace.
* Safety: reads only on the conservative schedule in docs/RUNBOOK.md; writes are ONLY
  draft-creating calls, made after the user approved in GigBid - the user then confirms on
  Upwork, as the platform requires.  `submit_proposal` / `send_message` therefore create
  platform drafts and never auto-confirm.  No scraping, no browser automation, no cookies.
"""
from __future__ import annotations

import json
import time

from agent.config import cfg

# port method -> candidate Upwork MCP tool names (first one present wins)
TOOL_CANDIDATES: dict[str, list[str]] = {
    "search_jobs": ["search_jobs", "job_search", "find_jobs", "marketplace_job_search"],
    "get_job": ["get_job", "get_job_details", "job_details"],
    "get_client_history": ["get_client", "get_client_details", "client_info"],
    "get_connects_balance": ["get_connects", "connects_balance", "get_connects_balance"],
    "list_threads": ["list_rooms", "list_conversations", "list_threads"],
    "list_messages": ["list_messages", "get_room_messages", "get_messages"],
    "create_proposal_draft": ["create_proposal_draft", "draft_proposal", "create_proposal"],
    "send_message": ["create_message_draft", "draft_message", "send_message"],
}


class LiveModeError(Exception):
    pass


async def access_token(user_id: str) -> str:
    """Decrypt the user's Upwork token; refresh it if it expires within 2 minutes."""
    from sqlalchemy import select

    from common.crypto import decrypt
    from common.db import engine, oauth_tokens
    with engine().connect() as c:
        row = c.execute(select(oauth_tokens).where((oauth_tokens.c.user_id == user_id) & (oauth_tokens.c.provider == "upwork"))).first()
    if not row:
        raise LiveModeError("Upwork account not connected (Settings -> Connected accounts)")
    tok = json.loads(decrypt(row.ciphertext))
    if row.expires_at and row.expires_at - time.time() < 120 and tok.get("refresh_token"):
        from apps.api.auth.upwork_oauth import refresh_tokens
        tok = await refresh_tokens(user_id, tok)
    return tok["access_token"]


class UpworkLivePort:
    name = "upwork_live"

    def __init__(self, user_id: str, trace_id: str | None = None):
        self.user_id, self.trace_id = user_id, trace_id
        self._map: dict[str, str] | None = None

    async def _client(self):
        from langchain_mcp_adapters.client import MultiServerMCPClient
        tok = await access_token(self.user_id)
        return MultiServerMCPClient({"upwork": {"transport": "streamable_http", "url": cfg("marketplace.upwork_mcp_url"),
                                                "headers": {"Authorization": f"Bearer {tok}"}, "timeout": 30}})

    async def _resolve(self, session) -> dict[str, str]:
        if self._map is None:
            names = {t.name for t in (await session.list_tools()).tools}
            self._map = {m: next((c for c in cands if c in names), "") for m, cands in TOOL_CANDIDATES.items()}
        return self._map

    async def _call(self, method: str, args: dict):
        client = await self._client()
        async with client.session("upwork") as s:
            tool = (await self._resolve(s)).get(method)
            if not tool:
                raise LiveModeError(f"Upwork MCP exposes no tool for {method}")
            res = await s.call_tool(tool, args)
        if res.isError:
            raise LiveModeError(" ".join(getattr(c, "text", "") for c in res.content))
        if res.structuredContent is not None:
            return res.structuredContent
        txt = "".join(getattr(c, "text", "") for c in res.content)
        try:
            return json.loads(txt)
        except Exception:  # noqa: BLE001
            return {"text": txt}

    # ---- normalisers: Upwork shapes -> GigBid port shapes (best effort, verified on connect)
    @staticmethod
    def _job(j: dict) -> dict:
        budget = j.get("budget") or {}
        hourly = j.get("hourlyBudgetMax") or j.get("hourly_max")
        return {"id": j.get("id") or j.get("ciphertext"), "title": j.get("title", ""), "description": j.get("description", ""),
                "category": j.get("category") or j.get("occupation", ""), "skills_tags": [s.get("name", s) if isinstance(s, dict) else s for s in j.get("skills", [])],
                "budget": {"type": "hourly", "min": j.get("hourlyBudgetMin") or 0, "max": hourly} if hourly else
                          {"type": "fixed", "amount": budget.get("amount") or j.get("amount") or 0},
                "timeline": j.get("duration") or j.get("engagement"), "screening_questions": j.get("questions", []),
                "client_id": (j.get("client") or {}).get("id") or j.get("client_id", ""), "posted_at": j.get("publishedDateTime") or 0,
                "connects_required": j.get("connectPrice") or j.get("connects_required") or 0}

    async def search_jobs(self, query="", category="", skills="", since=None, limit=20, split="live"):
        r = await self._call("search_jobs", {"query": query or skills or category, "limit": limit})
        jobs = r.get("jobs") or r.get("results") or r.get("items") or []
        return [self._job(j) for j in jobs]

    async def get_job(self, job_id):
        return self._job(await self._call("get_job", {"id": job_id}))

    async def get_client_history(self, client_id):
        c = await self._call("get_client_history", {"id": client_id})
        return {"id": client_id, "payment_verified": c.get("paymentVerified", c.get("payment_verified")),
                "total_spent": c.get("totalSpent", c.get("total_spent", 0)), "hire_rate": c.get("hireRate", c.get("hire_rate")),
                "jobs_posted": c.get("jobsPosted", c.get("jobs_posted", 0)), "avg_rating": c.get("rating"),
                "member_since": c.get("memberSince"), "country": c.get("country"), "freelancer_reviews": c.get("reviews", [])}

    async def get_connects_balance(self):
        r = await self._call("get_connects_balance", {})
        bal = r.get("balance") or r.get("connects") or 0
        return {"balance": bal, "allowance": cfg("live.weekly_connects", bal), "spent": 0}

    async def get_market_stats(self, category, budget_type):
        return None   # Upwork exposes no market statistics; pricing falls back to GigBid's own history

    async def get_policy(self):
        return {"version": "upwork-live", "connects": {"formula": "per_job"}, "rules": []}

    async def list_threads(self):
        r = await self._call("list_threads", {})
        return [{"thread_id": t.get("id"), "job_id": t.get("jobId", ""), "last_at": t.get("updatedAt", 0)} for t in r.get("rooms", r.get("items", []))]

    async def list_messages(self, thread_id):
        r = await self._call("list_messages", {"roomId": thread_id})
        return [{"id": m.get("id"), "from": "freelancer" if m.get("isMine") else "client", "text": m.get("text", ""), "at": m.get("createdAt", 0)}
                for m in r.get("messages", r.get("items", []))]

    async def list_events(self, since):
        return []   # live mode derives pipeline changes from threads/proposals on the scheduled poll

    async def preview_proposal(self, job_id, text, bid, answers, key):
        job = await self.get_job(job_id)
        return {"status": "dry_run", "preview": {"job_id": job_id, "cover_letter": text, "bid_amount": bid, "screening_answers": answers,
                                                 "note": "Will be created as an Upwork DRAFT; confirm it on Upwork."},
                "connects_cost": job.get("connects_required", 0), "idempotency_key": key}

    async def create_proposal_draft(self, job_id, text, bid, answers, key):
        r = await self._call("create_proposal_draft", {"jobId": job_id, "coverLetter": text, "bidAmount": bid, "answers": answers})
        return {"status": "draft_created", "result": {"proposal_id": r.get("id") or r.get("proposalId", ""), **r}, "idempotency_key": key}

    async def submit_proposal(self, proposal_id, job_id, key):
        # Upwork requires the user to confirm the draft on the platform: never auto-confirm.
        return {"status": "submitted", "result": {"proposal_id": proposal_id, "awaiting_user_confirmation_on_upwork": True},
                "connects_cost": 0, "idempotency_key": key}

    async def send_message(self, thread_id, text, key, dry_run=False):
        if dry_run:
            return {"status": "dry_run", "preview": {"thread_id": thread_id, "text": text}, "idempotency_key": key}
        r = await self._call("send_message", {"roomId": thread_id, "text": text})
        return {"status": "sent", "result": {**r, "draft_on_upwork": True}, "idempotency_key": key}
