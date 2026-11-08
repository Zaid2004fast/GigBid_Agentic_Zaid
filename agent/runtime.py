"""Node runtime: one decorator gives every node tracing, budgets, streaming progress and
degraded-mode handling, so node bodies stay pure business logic.

    @node("writer")
    async def writer(state, ctx) -> dict: ...

* trace span per node (masked inputs/outputs, tokens + cost per node)
* step budget and token budget per thread (C4): exceeding either moves the thread to the
  visible `needs_attention` state instead of running the node
* ToolUnavailable -> `queued_degraded` (work is re-queued by the worker when the marketplace
  recovers); other exceptions propagate so the node's RetryPolicy retries them
* custom stream events ({"node", "phase", "message"}) for the live run viewer
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer

from agent.config import cfg
from agent.llm import Usage
from agent.mcp_client import ToolHub, ToolUnavailable
from common.tracing import current_thread, current_trace, current_user, span


@dataclass
class NodeCtx:
    """What a node may use besides state: its tool allowlist, the store, user settings."""
    name: str
    hub: ToolHub
    store: Any
    config: RunnableConfig
    usages: list[Usage] = field(default_factory=list)

    def tools(self, agent: str | None = None):
        return self.hub.for_agent(agent or self.name)

    def emit(self, message: str, **data) -> None:
        try:
            get_stream_writer()({"node": self.name, "phase": "progress", "message": message, **data})
        except Exception:  # noqa: BLE001 - not streaming
            pass

    def track(self, u: Usage) -> None:
        self.usages.append(u)


def _budget_exceeded(state: dict) -> str | None:
    steps = int(state.get("steps") or 0)
    tokens = sum(u.get("tokens_in", 0) + u.get("tokens_out", 0) for u in state.get("usage") or [])
    if steps >= cfg("budgets.per_thread_steps", 40):
        return f"step budget exceeded ({steps} steps)"
    if tokens >= cfg("budgets.per_thread_tokens", 60000):
        return f"token budget exceeded ({tokens} tokens)"
    return None


def node(name: str):
    def deco(fn: Callable[[dict, NodeCtx], Awaitable[dict]]):
        # NB: no functools.wraps - LangGraph injects `config`/`store` by inspecting THIS signature
        async def wrapper(state: dict, config: RunnableConfig, *, store=None) -> dict:
            conf = (config or {}).get("configurable", {})
            hub: ToolHub = conf.get("hub") or ToolHub(user_id=state.get("user_id", "local"), persona=state.get("persona", "aiml"),
                                                     trace_id=state.get("trace_id"))
            ctx = NodeCtx(name, hub, store if store is not None else conf.get("store"), config)
            if state.get("status") in ("needs_attention", "dead_letter", "queued_degraded"):
                return {}
            reason = _budget_exceeded(state)
            if reason:
                ctx.emit(reason, phase="attention")
                return {"status": "needs_attention", "attention_reason": reason, "progress": [f"{name}: {reason}"]}
            t_tok = current_trace.set(state.get("trace_id") or conf.get("trace_id"))
            th_tok = current_thread.set(conf.get("thread_id"))
            u_tok = current_user.set(state.get("user_id"))
            t0 = time.time()
            try:
                get_stream_writer()({"node": name, "phase": "start", "ts": t0})
            except Exception:  # noqa: BLE001
                pass
            try:
                with span(f"node:{name}", "node", node=name) as sp:
                    try:
                        out = await fn(state, ctx) or {}
                    except ToolUnavailable as e:
                        out = {"status": "queued_degraded", "attention_reason": str(e),
                               "errors": [{"node": name, "error": str(e), "ts": time.time()}],
                               "progress": [f"{name}: marketplace unavailable, queued for retry"]}
                    usage = [u.as_dict() for u in ctx.usages]
                    sp["usage"] = {"tokens_in": sum(u["tokens_in"] for u in usage), "tokens_out": sum(u["tokens_out"] for u in usage),
                                   "cost_usd": sum(u["cost_usd"] for u in usage),
                                   "model": ",".join(sorted({u["model"] for u in usage})) or None}
                    sp["attrs"]["output_keys"] = sorted(out.keys())
                    if out.get("status"):
                        sp["attrs"]["status"] = out["status"]
            finally:
                current_trace.reset(t_tok)
                current_thread.reset(th_tok)
                current_user.reset(u_tok)
            out.setdefault("usage", [])
            out["usage"] = list(out["usage"]) + usage + [{"node": name, "model": "-", "provider": "-", "tokens_in": 0, "tokens_out": 0,
                                                          "cost_usd": 0.0, "latency_s": round(time.time() - t0, 3), "wall": True}]
            out["steps"] = 1
            try:
                get_stream_writer()({"node": name, "phase": "end", "latency_s": round(time.time() - t0, 3),
                                     "status": out.get("status"), "summary": (out.get("progress") or [""])[-1]})
            except Exception:  # noqa: BLE001
                pass
            return out
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        wrapper.__gigbid_node__ = name
        return wrapper
    return deco
