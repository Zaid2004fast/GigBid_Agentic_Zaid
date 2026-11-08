"""Shared plumbing for GigBid's MCP servers.

* call context  - user_id / persona / trace_id travel in the MCP request `_meta`
                  (works the same over in-memory, stdio and Streamable HTTP)
* bearer auth   - ASGI middleware for the HTTP endpoint (MCP_SERVER_TOKEN)
* rate limiter  - per-user token bucket that stays under the upstream's limits
* audit log     - append-only JSONL, hash-chained (each line stores the hash of the
                  previous line) so tampering is detectable; PII and secrets masked
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import threading
import time
from pathlib import Path

from agent.guards import mask_obj

ROOT = Path(__file__).resolve().parents[1]


def call_context(ctx) -> dict:
    """Extract {user_id, persona, trace_id} from the MCP request meta (or env defaults)."""
    meta = {}
    try:
        m = ctx.request_context.meta
        if m is not None:
            meta = m.model_dump() if hasattr(m, "model_dump") else dict(m)
    except Exception:  # noqa: BLE001 - no active request (direct function call in tests)
        pass
    extra = meta.get("gigbid") or meta
    return {
        "user_id": extra.get("user_id") or os.getenv("DEFAULT_USER_ID", "local"),
        "persona": extra.get("persona") or os.getenv("PORTFOLIO_PERSONA", "aiml"),
        "trace_id": extra.get("trace_id") or "untraced",
    }


class BearerAuth:
    """ASGI middleware: rejects requests without the shared bearer token."""

    def __init__(self, app, token: str | None):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and self.token and scope.get("path", "") != "/health":
            hdrs = dict(scope.get("headers") or [])
            got = hdrs.get(b"authorization", b"").decode()
            if got != f"Bearer {self.token}":
                body = b'{"error":"unauthorized"}'
                await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


class RateLimiter:
    """Per-user token bucket. Default 1 request/s burst 10 = 60/min, half of GigSim's 120/min."""

    def __init__(self, rate_per_s: float = 1.0, burst: int = 10):
        self.rate, self.burst = rate_per_s, burst
        self.state: dict[str, tuple[float, float]] = {}
        self.lock = asyncio.Lock()

    async def acquire(self, key: str) -> float:
        async with self.lock:
            tokens, last = self.state.get(key, (self.burst, time.monotonic()))
            now = time.monotonic()
            tokens = min(self.burst, tokens + (now - last) * self.rate)
            wait = 0.0 if tokens >= 1 else (1 - tokens) / self.rate
            self.state[key] = (tokens - 1 + wait * self.rate, now + wait)
        if wait:
            await asyncio.sleep(wait)
        return wait


class AuditLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def _last_hash(self) -> str:
        if not self.path.exists():
            return "genesis"
        with self.path.open("rb") as f:
            try:
                f.seek(-4096, os.SEEK_END)
            except OSError:
                f.seek(0)
            lines = f.read().decode(errors="ignore").strip().splitlines()
        return json.loads(lines[-1])["hash"] if lines else "genesis"

    def append(self, *, user: str, tool: str, args: dict, result, trace_id: str, status: str = "ok") -> None:
        with self.lock:
            rec = {"ts": time.time(), "user": user, "tool": tool, "args": mask_obj(args), "result": mask_obj(result),
                   "trace_id": trace_id, "status": status, "prev": self._last_hash()}
            rec["hash"] = hashlib.sha256(json.dumps(rec, sort_keys=True, default=str).encode()).hexdigest()
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, default=str) + "\n")

    def verify(self) -> bool:
        prev = "genesis"
        if not self.path.exists():
            return True
        for line in self.path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            h = rec.pop("hash")
            if rec["prev"] != prev or hashlib.sha256(json.dumps(rec, sort_keys=True, default=str).encode()).hexdigest() != h:
                return False
            prev = h
        return True


def http_app(mcp, token_env: str = "MCP_SERVER_TOKEN"):
    """Streamable-HTTP ASGI app with bearer auth + /health."""
    from starlette.responses import JSONResponse

    @mcp.custom_route("/health", methods=["GET"])
    async def _health(request):  # noqa: ARG001
        return JSONResponse({"ok": True, "server": mcp.name})

    return BearerAuth(mcp.streamable_http_app(), os.getenv(token_env))
