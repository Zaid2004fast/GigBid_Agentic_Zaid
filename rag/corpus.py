"""Per-persona corpus: documents -> chunk sets -> dense / BM25 / graph indexes.

Chunk sets
  fixed_all   fixed windows over *every* document, past proposals included (V0 baseline)
  struct      structure-aware chunks over evidence documents only
  ctx         struct chunks with a context line prepended (V6 contextual retrieval)
  proposals   past proposals with outcomes (outcome-aware ranking, phrasing exemplars)

Design decision: past proposals are NOT evidence of experience (a past proposal may
itself have over-claimed), so they are excluded from evidence indexes and only used
as outcome signals.  V0 includes them, which is one reason naive RAG over-claims.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from functools import cached_property
from pathlib import Path

from agent.config import ROOT, cfg
from rag.embeddings import get_embedder
from rag.index.bm25 import BM25Index
from rag.index.graph import SkillGraph
from rag.index.vector import make_index
from rag.ingest.chunkers import Chunk, fixed_chunks, structured_chunks
from rag.ingest.loaders import Document, load_persona
from rag.skills import skill_name

EVIDENCE_TYPES = {"case_study", "cv", "repo_readme", "repo_code", "review"}
PERSONA_DIR = ROOT / "data" / "personas"


class Corpus:
    def __init__(self, persona: str, docs: list[Document]):
        self.persona = persona
        self.docs = docs
        self.embedder = get_embedder()
        self.by_item: dict[str, list[Document]] = defaultdict(list)
        for d in docs:
            self.by_item[d.item_id].append(d)
        self.project_skills: dict[str, set[str]] = defaultdict(set)
        from rag.skills import semantic_skills
        for d in docs:
            if d.meta["type"] in EVIDENCE_TYPES and d.meta.get("project"):
                self.project_skills[d.meta["project"]].update(d.meta.get("skills", []))
                if d.meta["type"] == "case_study":   # implied skills count too (semantic match)
                    self.project_skills[d.meta["project"]].update(semantic_skills(d.text))

    # ---------------------------------------------------------------- chunk sets
    @cached_property
    def fixed_all(self) -> list[Chunk]:
        size, ov = cfg("rag.chunk_size", 450), cfg("rag.chunk_overlap", 60)
        return [c for d in self.docs for c in fixed_chunks(d, size, ov)]

    @cached_property
    def struct(self) -> list[Chunk]:
        return [c for d in self.docs if d.meta["type"] in EVIDENCE_TYPES for c in structured_chunks(d)]

    @cached_property
    def proposals(self) -> list[Chunk]:
        return [c for d in self.docs if d.meta["type"] == "proposal" for c in structured_chunks(d)]

    def context_line(self, c: Chunk) -> str:
        m = c.meta
        proj = m.get("project", "")
        title = next((d.meta.get("title") for d in self.by_item.get(f"{self.persona}:cs:{proj}", [])), m.get("title", ""))
        skills = sorted(self.project_skills.get(proj, set()))[:8]
        return (f"[{m['type'].replace('_', ' ')} | project: {title} | industry: {m.get('client_industry') or self.industry_of(proj)} "
                f"| skills: {', '.join(skill_name(s) for s in skills)}]")

    def industry_of(self, project: str) -> str:
        for d in self.by_item.get(f"{self.persona}:cs:{project}", []):
            return d.meta.get("client_industry", "")
        return ""

    # ---------------------------------------------------------------- indexes (lazy, thread-safe)
    _lock = threading.Lock()

    def _get(self, name: str, factory):
        with self._lock:
            if name not in self.__dict__:
                self.__dict__[name] = factory()
            return self.__dict__[name]

    def dense(self, chunkset: str):
        def f():
            chunks = getattr(self, chunkset if chunkset != "ctx" else "struct")
            texts = [f"{self.context_line(c)}\n{c.text}" for c in chunks] if chunkset == "ctx" else None
            return make_index(chunks, self.embedder, texts, namespace=f"{self.persona}:{chunkset}")
        return self._get(f"_dense_{chunkset}", f)

    def bm25(self, chunkset: str) -> BM25Index:
        def f():
            chunks = getattr(self, chunkset if chunkset != "ctx" else "struct")
            texts = [f"{self.context_line(c)}\n{c.text}" for c in chunks] if chunkset == "ctx" else None
            return BM25Index(chunks, texts)
        return self._get(f"_bm25_{chunkset}", f)

    @property
    def graph(self) -> SkillGraph:
        return self._get("_graph", lambda: SkillGraph.build(self.docs))

    def item_text(self, item_id: str, limit: int = 1200) -> str:
        return "\n".join(d.text for d in self.by_item.get(item_id, []))[:limit]

    def item_meta(self, item_id: str) -> dict:
        ds = self.by_item.get(item_id)
        return dict(ds[0].meta) if ds else {}

    def items_of_project(self, project: str) -> list[str]:
        order = {"cs": 0, "repo": 1, "cv": 2}
        ids = [i for i in self.by_item if i.split(":")[1] in order and i.split(":", 2)[2] == project]
        return sorted(ids, key=lambda i: order[i.split(":")[1]])


_CACHE: dict[str, Corpus] = {}
_CLOCK = threading.Lock()


def get_corpus(persona: str, refresh: bool = False) -> Corpus:
    """Incremental re-indexing: embeddings are cached by content hash, so a refresh after an
    upload only embeds the new / changed chunks."""
    with _CLOCK:
        if refresh or persona not in _CACHE:
            _CACHE[persona] = Corpus(persona, load_persona(persona_dir(persona)))
        return _CACHE[persona]


def persona_dir(persona: str) -> Path:
    """`me` (or any persona when PORTFOLIO_DIR is set) points at a user's own portfolio folder,
    so the published Portfolio MCP server works for any freelancer."""
    import os
    custom = os.getenv("PORTFOLIO_DIR")
    if custom and persona in ("me", os.getenv("PORTFOLIO_PERSONA", "me")):
        return Path(custom)
    return PERSONA_DIR / persona
