"""Conversation graph (one thread per client conversation) - Client Liaison (C1).

fetch -> guard -> intent ─┬─ interview_request -> slots ─┐
                          └─ other intents ──────────────┴─► draft -> compliance -> approval (interrupt)
approval: approve -> send -> END | edit -> edit -> approval | reject -> END
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from agent.nodes import liaison as L
from agent.state import TERMINAL_OR_ATTENTION, ConvState

RETRY = RetryPolicy(max_attempts=2, initial_interval=0.5)


def _g(nxt):
    def r(s):
        return END if s.get("status") in TERMINAL_OR_ATTENTION else nxt
    r.__name__ = f"to_{nxt}"
    return r


def after_intent(s: dict) -> str:
    if s.get("status") in TERMINAL_OR_ATTENTION:
        return END
    return "slots" if (s.get("intent") or {}).get("intent") == "interview_request" else "draft"


def after_approval(s: dict) -> str:
    return {"approved": "send", "editing": "edit", "rejected": END}.get(s.get("status"), END)


def build_conversation_graph(checkpointer=None, store=None):
    g = StateGraph(ConvState)
    g.add_node("fetch", L.fetch, retry_policy=RETRY, timeout=60)
    g.add_node("guard", L.guard, timeout=30)
    g.add_node("intent", L.intent, retry_policy=RETRY, timeout=90)
    g.add_node("slots", L.slots, retry_policy=RETRY, timeout=30)
    g.add_node("draft", L.draft, retry_policy=RETRY, timeout=150)
    g.add_node("compliance", L.compliance, timeout=30)
    g.add_node("approval", L.approval)
    g.add_node("edit", L.edit, timeout=30)
    g.add_node("send", L.send, retry_policy=RetryPolicy(max_attempts=3, initial_interval=1.0), timeout=60)
    g.add_edge(START, "fetch")
    g.add_conditional_edges("fetch", _g("guard"), ["guard", END])
    g.add_conditional_edges("guard", _g("intent"), ["intent", END])
    g.add_conditional_edges("intent", after_intent, ["slots", "draft", END])
    g.add_conditional_edges("slots", _g("draft"), ["draft", END])
    g.add_conditional_edges("draft", _g("compliance"), ["compliance", END])
    g.add_conditional_edges("compliance", _g("approval"), ["approval", END])
    g.add_conditional_edges("approval", after_approval, ["send", "edit", END])
    g.add_conditional_edges("edit", _g("approval"), ["approval", END])
    g.add_edge("send", END)
    return g.compile(checkpointer=checkpointer, store=store, name="conversation_graph")
