"""Retriever factory: the deployed variant is chosen in config (rag.variant), and that
choice is justified by evals/results/rag_variants.json (see docs/adr/0003-rag-choice.md)."""
from __future__ import annotations

import importlib
from dataclasses import replace

from agent.config import cfg
from rag.corpus import get_corpus
from rag.pipeline import Pipeline, PipelineSpec, Query, Result

VARIANT_MODULES = {
    "V0": "v0_naive", "V1": "v1_decompose", "V2": "v2_hybrid", "V3": "v3_rerank", "V4": "v4_outcome",
    "V5": "v5_multivector", "V6": "v6_contextual", "V7": "v7_hyde", "V8": "v8_corrective", "V9": "v9_skill_graph",
}

# "best" = the shipped composite; components listed so ablation can drop one at a time.
BEST = PipelineSpec("best", chunks="ctx", decompose=True, bm25=True, rerank=True, multivector=False,
                    outcome=True, corrective=True)
ABLATION_FLAGS = {"decompose": False, "bm25": False, "rerank": False, "outcome": False, "corrective": False,
                  "chunks": "struct"}


# Composite candidates assembled from components that helped individually (see rag_retrieval.json).
CANDIDATES = {
    "C1": PipelineSpec("C1", bm25=True, multivector=True, outcome=True),                       # V2 + V5 + V4
    "C2": PipelineSpec("C2", bm25=True, multivector=True, outcome=True, decompose=True),       # + V1
    "C3": PipelineSpec("C3", bm25=True, multivector=True, outcome=True, decompose=True, corrective=True),  # + V8 (no rerank)
    "C4": PipelineSpec("C4", bm25=True, multivector=True, outcome=True, rerank=True),          # C1 + V3
}


def spec_for(name: str) -> PipelineSpec:
    if name in CANDIDATES:
        return CANDIDATES[name]
    if name == "best":
        return BEST
    if name == "V0e":   # control: V0 but over evidence documents only (isolates corpus contamination)
        return PipelineSpec("V0e", chunks="fixed_all", evidence_only=True)
    if name.startswith("best-"):
        flag = name.removeprefix("best-")
        return replace(BEST, name=name, **{flag: ABLATION_FLAGS[flag]})
    mod = importlib.import_module(f"rag.variants.{VARIANT_MODULES[name]}")
    return mod.SPEC


_OVERRIDE: dict[str, str | None] = {"variant": None}   # evaluation harness switches variants per run


def set_variant_override(name: str | None) -> None:
    _OVERRIDE["variant"] = name


def get_retriever(persona: str, variant: str | None = None, llm_hyde=None) -> Pipeline:
    return Pipeline(spec_for(variant or _OVERRIDE["variant"] or cfg("rag.variant", "best")), get_corpus(persona), llm_hyde)


def warm(personas: tuple[str, ...] = ("aiml", "web", "data")) -> None:
    """Build corpora, indexes and model sessions up front so the first job is not slow."""
    for p in personas:
        try:
            get_retriever(p).run(Query(job_text="warm up python api", title="warm", requirements=["python api"]), k=3)
            get_corpus(p).bm25("proposals")
        except Exception:  # noqa: BLE001 - a missing persona folder is fine
            pass


def retrieve(persona: str, query: Query, k: int = 10, variant: str | None = None) -> Result:
    return get_retriever(persona, variant).run(query, k)
