"""V8 corrective / self-RAG loop as a small LangGraph graph.

For every requirement:  grade evidence -> if weak, re-query with a taxonomy-expanded
query (names, aliases, code tokens) -> if still weak, REFUSE to claim it.
The refusal list flows into the Fit Matcher and the Writer, which is how GigBid
avoids claiming experience the portfolio does not have (R5).
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from rag.pipeline import PipelineSpec
from rag.skills import SKILLS, extract_skills

SPEC = PipelineSpec("V8", decompose=True, bm25=True, rerank=True, corrective=True)
STRONG = 0.5   # requirement support needed to accept evidence


class CState(TypedDict):
    requirement: str
    hits: list
    attempts: int
    verdict: str


def _grade(hits) -> float:
    return max((h.support for h in hits), default=0.0)


def build_corrective_graph(pipe, q):
    def grade(state: CState):
        g = _grade(state["hits"])
        if g >= STRONG:
            return {"verdict": "supported"}
        if state["attempts"] >= 1:
            return {"verdict": "partial" if g > 0 else "none"}
        return {"verdict": "retry"}

    def requery(state: CState):
        sk = extract_skills(state["requirement"])
        expansion = " ".join(f"{SKILLS[s]['name']} {' '.join(SKILLS[s]['aliases'])} {SKILLS[s]['code']}" for s in sk)
        text = f"{state['requirement']} {expansion}".strip()
        cands = pipe._retrieve(text, q, [])
        if pipe.s.rerank:
            cands = pipe._rerank(state["requirement"], cands)
        new = pipe._to_items(cands, state["requirement"], k=4)
        merged = {h.item_id: h for h in state["hits"] + new}
        best = sorted(merged.values(), key=lambda h: (-h.support, -h.score))[:4]
        return {"hits": best, "attempts": state["attempts"] + 1}

    g = StateGraph(CState)
    g.add_node("grade", grade)
    g.add_node("requery", requery)
    g.add_edge(START, "grade")
    g.add_conditional_edges("grade", lambda s: "requery" if s["verdict"] == "retry" else END, {"requery": "requery", END: END})
    g.add_edge("requery", "grade")
    return g.compile()


def corrective_loop(pipe, per_req, q, trace):
    graph = build_corrective_graph(pipe, q)
    out, unsupported = {}, []
    for req, hits in per_req.items():
        res = graph.invoke({"requirement": req, "hits": hits, "attempts": 0, "verdict": ""})
        trace.append(f"corrective[{req[:40]}] -> {res['verdict']} after {res['attempts']} re-query")
        if res["verdict"] == "none":
            unsupported.append(req)
            out[req] = []
        else:
            out[req] = [h for h in res["hits"] if h.support > 0]
    return out, unsupported
