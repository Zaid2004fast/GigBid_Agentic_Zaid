"""Bid graph (one thread per job), hand-written StateGraph (R3, C1).

intake ──Send──► analyst ─┐
       ├─Send──► risk    ─┼─► reconcile ─► decide ─┬─ skip/watch ─► END
       └─Send──► matcher ─┘                        └─ bid ─► pricing ─► writer ─► verifier ─► critic
                                                                          ▲                      │
                                                                          └──── revise (≤2) ─────┤
                                                                                                 ▼
                     END ◄─ submit ◄─ approve ─ approval (interrupt) ◄─ preview ◄─ compliance
                                       edit ─► apply_edit ─► preview (re-approve)
                                       reject ─► reject ─► END
Every conditional edge also routes attention states (needs_attention / queued_degraded /
dead_letter) to END, so a thread that exceeds its budget stops visibly.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send

from agent.config import cfg
from agent.nodes.analyst import analyst
from agent.nodes.approval import apply_edit, approval, preview, reject, route_after_approval, submit
from agent.nodes.compliance import compliance
from agent.nodes.critic import critic, route_after_critic
from agent.nodes.decision import decide
from agent.nodes.matcher import matcher, reconcile
from agent.nodes.pricing import pricing
from agent.nodes.risk import risk
from agent.nodes.scout import intake
from agent.nodes.verifier import verifier
from agent.nodes.writer import writer
from agent.state import TERMINAL_OR_ATTENTION, BidState

RETRY = RetryPolicy(max_attempts=2, initial_interval=0.5, backoff_factor=2.0)


def _t(name: str) -> float:
    return float(cfg(f"node_timeouts_s.{name}", cfg("node_timeouts_s.default", 180)))


def fan_out(state: dict):
    if state.get("status") in TERMINAL_OR_ATTENTION:
        return END
    return [Send("analyst", state), Send("risk", state), Send("matcher", state)]


def guard(nxt: str):
    def route(state: dict) -> str:
        return END if state.get("status") in TERMINAL_OR_ATTENTION else nxt
    route.__name__ = f"to_{nxt}"
    return route


def after_decide(state: dict) -> str:
    if state.get("status") in TERMINAL_OR_ATTENTION:
        return END
    return "pricing" if (state.get("decision") or {}).get("action") == "bid" else END


def after_pricing(state: dict) -> str:
    if state.get("status") in TERMINAL_OR_ATTENTION or state.get("status") == "skipped":
        return END
    return "writer"


def build_bid_graph(checkpointer=None, store=None):
    g = StateGraph(BidState)
    g.add_node("intake", intake, retry_policy=RETRY, timeout=_t("intake"))
    g.add_node("analyst", analyst, retry_policy=RETRY, timeout=_t("analyst"))
    g.add_node("risk", risk, retry_policy=RETRY, timeout=_t("risk"))
    g.add_node("matcher", matcher, retry_policy=RETRY, timeout=_t("matcher"))
    g.add_node("reconcile", reconcile, retry_policy=RETRY, timeout=_t("reconcile"))
    g.add_node("decide", decide, retry_policy=RETRY, timeout=_t("decide"))
    g.add_node("pricing", pricing, retry_policy=RETRY, timeout=_t("pricing"))
    g.add_node("writer", writer, retry_policy=RETRY, timeout=_t("writer"))
    g.add_node("verifier", verifier, retry_policy=RETRY, timeout=_t("verifier"))
    g.add_node("critic", critic, retry_policy=RETRY, timeout=_t("critic"))
    g.add_node("compliance", compliance, timeout=_t("compliance"))
    g.add_node("preview", preview, retry_policy=RETRY, timeout=_t("preview"))
    g.add_node("approval", approval)
    g.add_node("apply_edit", apply_edit, timeout=_t("apply_edit"))
    g.add_node("submit", submit, retry_policy=RetryPolicy(max_attempts=3, initial_interval=1.0), timeout=_t("submit"))
    g.add_node("reject", reject)

    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", fan_out, ["analyst", "risk", "matcher", END])
    for n in ("analyst", "risk", "matcher"):
        g.add_edge(n, "reconcile")
    g.add_conditional_edges("reconcile", guard("decide"), ["decide", END])
    g.add_conditional_edges("decide", after_decide, ["pricing", END])
    g.add_conditional_edges("pricing", after_pricing, ["writer", END])
    g.add_conditional_edges("writer", guard("verifier"), ["verifier", END])
    g.add_conditional_edges("verifier", guard("critic"), ["critic", END])
    g.add_conditional_edges("critic", route_after_critic, {"writer": "writer", "compliance": "compliance", "end": END})
    g.add_conditional_edges("compliance", guard("preview"), ["preview", END])
    g.add_conditional_edges("preview", guard("approval"), ["approval", END])
    g.add_conditional_edges("approval", route_after_approval, {"submit": "submit", "apply_edit": "apply_edit", "reject": "reject", "end": END})
    g.add_conditional_edges("apply_edit", guard("preview"), ["preview", END])
    g.add_edge("submit", END)
    g.add_edge("reject", END)
    return g.compile(checkpointer=checkpointer, store=store, name="bid_graph")
