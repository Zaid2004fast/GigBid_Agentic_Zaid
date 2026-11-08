"""GigSim REST adapter used by the Marketplace MCP server.

Timeouts, bounded retries with exponential backoff + jitter, Retry-After on 429, and
typed errors so callers can tell "rate limited" from "marketplace down".
"""
from __future__ import annotations

import asyncio
import os
import random

import httpx


class MarketplaceError(Exception):
    def __init__(self, code: str, detail: str = "", status: int | None = None):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail, self.status = code, detail, status


def token_for(user_id: str, persona: str) -> str:
    """User's GigSim token from the encrypted token store, else the persona demo token."""
    try:
        from sqlalchemy import select

        from common.crypto import decrypt
        from common.db import engine, oauth_tokens
        with engine().connect() as c:
            row = c.execute(select(oauth_tokens.c.ciphertext).where(
                (oauth_tokens.c.user_id == user_id) & (oauth_tokens.c.provider == "gigsim"))).first()
        if row:
            return decrypt(row[0])
    except Exception:  # noqa: BLE001 - fall back to demo token
        pass
    return f"tok_{persona}"


class GigSimAdapter:
    def __init__(self, base_url: str | None = None, timeout: float = 10.0, retries: int = 3, backoff: float = 0.5):
        self.base = (base_url or os.getenv("GIGSIM_URL", "http://localhost:8100")).rstrip("/")
        self.timeout, self.retries, self.backoff = timeout, retries, backoff
        self._client: httpx.AsyncClient | None = None

    def client(self) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        if self._client is not None and getattr(self, "_loop", None) is not loop:
            self._client = None   # an httpx client is bound to the loop that created it
        self._loop = loop
        if self._client is None or self._client.is_closed:
            if self.base == "inprocess":   # tests / evals: GigSim app in the same process
                from gigsim.app import app as gigsim_app
                self._client = httpx.AsyncClient(transport=httpx.ASGITransport(app=gigsim_app), base_url="http://gigsim",
                                                 timeout=self.timeout)
            else:
                self._client = httpx.AsyncClient(base_url=self.base, timeout=self.timeout)
        return self._client

    async def request(self, method: str, path: str, token: str, *, params=None, json=None, idem: str | None = None) -> dict:
        headers = {"Authorization": f"Bearer {token}"}
        if idem:
            headers["Idempotency-Key"] = idem
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                r = await self.client().request(method, path, params=params, json=json, headers=headers)
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError) as e:
                last = MarketplaceError("unavailable", str(e))
            else:
                if r.status_code == 429:
                    wait = float(r.headers.get("Retry-After", "2"))
                    last = MarketplaceError("rate_limited", f"retry after {wait}s", 429)
                    if attempt < self.retries:
                        await asyncio.sleep(min(wait, 10))
                        continue
                elif r.status_code >= 500:
                    last = MarketplaceError("upstream_error", r.text[:200], r.status_code)
                elif r.status_code >= 400:
                    try:
                        detail = r.json().get("detail", r.text)
                    except Exception:  # noqa: BLE001
                        detail = r.text
                    raise MarketplaceError({401: "unauthorized", 402: "insufficient_connects", 404: "not_found",
                                            409: "conflict", 422: "policy_rejected"}.get(r.status_code, "bad_request"),
                                           str(detail)[:300], r.status_code)
                else:
                    return r.json()
            if attempt < self.retries:
                await asyncio.sleep(self.backoff * (2 ** attempt) + random.uniform(0, 0.2))
        raise last or MarketplaceError("unavailable", "unknown")

    # ---------------- reads
    async def search_jobs(self, token, **params):
        return await self.request("GET", "/v1/jobs", token, params={k: v for k, v in params.items() if v not in (None, "")})

    async def get_job(self, token, job_id):
        return await self.request("GET", f"/v1/jobs/{job_id}", token)

    async def get_client(self, token, client_id):
        return await self.request("GET", f"/v1/clients/{client_id}", token)

    async def connects(self, token):
        return await self.request("GET", "/v1/connects", token)

    async def threads(self, token):
        return await self.request("GET", "/v1/threads", token)

    async def messages(self, token, thread_id):
        return await self.request("GET", f"/v1/threads/{thread_id}/messages", token)

    async def events(self, token, since):
        return await self.request("GET", "/v1/events", token, params={"since": since})

    async def market_stats(self, token, category, budget_type):
        return await self.request("GET", "/v1/market/stats", token, params={"category": category, "budget_type": budget_type})

    async def policy(self, token):
        return await self.request("GET", "/v1/policy", token)

    # ---------------- writes
    async def create_draft(self, token, body, idem):
        return await self.request("POST", "/v1/proposals", token, json=body, idem=idem)

    async def submit(self, token, proposal_id, idem):
        return await self.request("POST", f"/v1/proposals/{proposal_id}/submit", token, idem=idem)

    async def send_message(self, token, thread_id, text, idem):
        return await self.request("POST", f"/v1/threads/{thread_id}/messages", token, json={"text": text}, idem=idem)
