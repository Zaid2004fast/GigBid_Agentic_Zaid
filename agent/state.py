"""Typed graph state + reducers (C2).

Three things are kept apart:
  * State (this file)      - what this job / conversation needs right now. Hand-off objects
                             are stored as their Pydantic `.model_dump()` and re-validated
                             when read, so every boundary is typed.
  * Execution trace        - every tool name, argument, result and observation lives in the
                             spans table / Phoenix (common/tracing.py), NOT in state.
  * Long-term memory       - only promoted knowledge, in the LangGraph store
                             (agent/memory), written by explicit promotion rules.
Reducers exist wherever parallel branches (analyst / risk / matcher) or loops write.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_dict(a: dict | None, b: dict | None) -> dict:
    out = dict(a or {})
    out.update(b or {})
    return out


def append(a: list | None, b: list | None) -> list:
    return list(a or []) + list(b or [])


def last_status(a: str | None, b: str | None) -> str | None:
    """Terminal / attention statuses win over progress statuses when branches race."""
    rank = {"dead_letter": 3, "needs_attention": 2, "queued_degraded": 1}
    if a in rank and rank.get(a, 0) >= rank.get(b or "", 0):
        return a   # attention states are sticky: the thread stops there
    return b if b is not None else a


class BidState(TypedDict, total=False):
    # identity
    thread_id: str
    user_id: str
    persona: str
    job_id: str
    trace_id: str
    # input (raw post is untrusted; only analyst + risk read it)
    job: dict
    client: dict
    # parallel analyses
    job_spec: dict
    risk: dict
    fit: dict
    evidence: Annotated[dict[str, dict], merge_dict]          # item_id -> EvidenceRef
    # decision path
    decision: dict
    price: dict
    drafts: Annotated[list[dict], append]                      # ProposalDraft history
    verification: dict
    critiques: Annotated[list[dict], append]
    compliance: dict
    preview: dict                                              # dry_run preview for the approval screen
    approvals: Annotated[list[dict], append]
    submission: dict
    outcome: dict
    # control
    revision: int
    status: Annotated[str, last_status]
    attention_reason: str
    progress: Annotated[list[str], append]                     # human-readable timeline for the UI
    usage: Annotated[list[dict], append]                       # per-node tokens / cost / latency
    steps: Annotated[int, operator.add]
    errors: Annotated[list[dict], append]
    settings: dict                                             # user settings snapshot (rates, autonomy, budget)


class ConvState(TypedDict, total=False):
    thread_id: str              # graph thread id
    market_thread_id: str       # marketplace conversation id
    user_id: str
    persona: str
    job_id: str
    trace_id: str
    job_spec: dict
    price: dict
    messages: list[dict]
    last_client_message: str
    injection: dict
    intent: dict
    slots: list[dict]
    reply: dict
    compliance: dict
    approvals: Annotated[list[dict], append]
    sent: dict
    status: Annotated[str, last_status]
    attention_reason: str
    progress: Annotated[list[str], append]
    usage: Annotated[list[dict], append]
    steps: Annotated[int, operator.add]
    errors: Annotated[list[dict], append]
    settings: dict


TERMINAL_OR_ATTENTION = {"needs_attention", "dead_letter", "queued_degraded"}


def get(state: dict, key: str, default: Any = None) -> Any:
    v = state.get(key)
    return default if v is None else v
