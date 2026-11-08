"""Composable retrieval pipeline. Every RAG variant (rag/variants/v*.py) is a preset of
these stages, so ablation = flip one flag, and one command reruns every variant.

Stages (in order)
  query     : whole post | requirement decomposition (V1) | + HyDE pseudo-document (V7)
  chunks    : fixed_all (V0) | struct | ctx (V6 contextual)
  retrieve  : dense | bm25 | hybrid via reciprocal rank fusion (V2)
  rerank    : cross-encoder on (requirement, chunk) pairs (V3)
  aggregate : chunk -> item, or multi-vector project aggregation (V5)
  boost     : outcome-aware boost from won / replied proposals (V4)
  graph     : skill-graph candidates fused in (V9)
  correct   : grade per requirement, re-query when weak, refuse when none (V8, LangGraph)
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from agent.config import cfg
from rag.corpus import Corpus
from rag.ingest.chunkers import Chunk
from rag.skills import SKILLS, extract_skills, skill_name


@dataclass
class Query:
    job_text: str
    title: str = ""
    requirements: list[str] = field(default_factory=list)
    industry: str | None = None
    category: str = ""


@dataclass
class Hit:
    item_id: str
    score: float
    text: str
    meta: dict
    chunk_id: str = ""
    requirements: list[str] = field(default_factory=list)
    support: float = 0.0          # 0..1 strength for the requirement(s) it was retrieved for

    def to_evidence(self) -> dict:
        return {"item_id": self.item_id, "type": self.meta.get("type"), "project": self.meta.get("project"),
                "title": self.meta.get("title"), "date": self.meta.get("date"), "source": self.meta.get("source"),
                "client_industry": self.meta.get("client_industry"), "outcome": self.meta.get("outcome"),
                "snippet": self.text[:400], "score": round(self.score, 4), "support": round(self.support, 3),
                "requirements": self.requirements}


@dataclass
class Result:
    items: list[Hit]
    per_requirement: dict[str, list[Hit]]
    unsupported: list[str]
    exemplars: list[dict] = field(default_factory=list)   # winning past proposals (phrasing)
    trace: list[str] = field(default_factory=list)


@dataclass
class PipelineSpec:
    name: str
    chunks: str = "struct"
    decompose: bool = False
    dense: bool = True
    bm25: bool = False
    rerank: bool = False
    multivector: bool = False
    outcome: bool = False
    hyde: bool = False
    graph: bool = False
    corrective: bool = False
    evidence_only: bool = True
    candidates: int = 30


def rrf(lists: list[list[tuple[Chunk, float]]], k: int = 60) -> list[tuple[Chunk, float]]:
    score: dict[str, float] = defaultdict(float)
    keep: dict[str, Chunk] = {}
    for lst in lists:
        for rank, (c, _) in enumerate(lst):
            score[c.id] += 1.0 / (k + rank + 1)
            keep[c.id] = c
    return sorted(((keep[i], s) for i, s in score.items()), key=lambda x: -x[1])


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


class Pipeline:
    def __init__(self, spec: PipelineSpec, corpus: Corpus, llm_hyde=None):
        self.s, self.c = spec, corpus
        self.llm_hyde = llm_hyde

    # ------------------------------------------------------------------ public
    def run(self, q: Query, k: int = 10) -> Result:
        trace: list[str] = [f"variant={self.s.name}"]
        reqs = q.requirements if (self.s.decompose or self.s.corrective) and q.requirements else []
        queries = reqs or [f"{q.title}\n{q.job_text}"]
        per_req: dict[str, list[Hit]] = {}
        all_lists: list[list[tuple[Chunk, float]]] = []
        for rq in queries:
            cands = self._retrieve(rq, q, trace)
            if self.s.rerank:
                cands = self._rerank(rq, cands)
            all_lists.append(cands)
            if reqs:
                per_req[rq] = self._to_items(cands, rq, k=4)
        fused = rrf(all_lists, cfg("rag.rrf_k", 60)) if len(all_lists) > 1 else all_lists[0]
        items = self._to_items(fused, None, k=max(k * 3, 30))
        if self.s.graph:
            items = self._fuse_graph(items, q)
        if self.s.outcome:
            items = self._outcome_boost(items, q)
        unsupported: list[str] = []
        if self.s.corrective and reqs:
            per_req, unsupported = self._corrective(per_req, q, trace)
            # corrective re-queries may surface new items; merge them in
            seen = {h.item_id for h in items}
            for hs in per_req.values():
                for h in hs:
                    if h.item_id not in seen:
                        items.append(h)
                        seen.add(h.item_id)
        if not reqs and q.requirements:
            per_req = self._assign(items, q.requirements)
        items = sorted(items, key=lambda h: -h.score)[:k]
        ex = self._exemplars(q) if self.s.outcome else []
        return Result(items, per_req, unsupported, ex, trace)

    # ------------------------------------------------------------------ stages
    def _where(self):
        if not self.s.evidence_only:
            return None
        return lambda c: c.meta.get("type") != "proposal"

    def _retrieve(self, text: str, q: Query, trace: list[str]) -> list[tuple[Chunk, float]]:
        n = self.s.candidates
        lists = []
        texts = [text]
        if self.s.hyde:
            texts.append(self._hyde(text, q))
        for t in texts:
            if self.s.dense:
                qv = self.c.embedder.embed([t])[0]
                lists.append(self.c.dense(self.s.chunks).search(qv, n, self._where()))
            if self.s.bm25:
                lists.append(self.c.bm25(self.s.chunks).search(t, n, self._where()))
        if self.s.multivector:
            lists = [self._multivector(lst) for lst in lists]
        return rrf(lists, cfg("rag.rrf_k", 60)) if len(lists) > 1 else lists[0]

    def _multivector(self, lst: list[tuple[Chunk, float]]) -> list[tuple[Chunk, float]]:
        """Summary / README / code chunks are separate vectors; a project's score is its best
        vector plus a bonus per distinct vector kind that matched, and every item of the
        project is surfaced (so a repo with a vague README still wins on its code)."""
        by_proj: dict[str, list[tuple[Chunk, float]]] = defaultdict(list)
        for c, s in lst:
            by_proj[c.meta.get("project") or c.item_id].append((c, s))
        out = []
        for proj, cs in by_proj.items():
            best = max(s for _, s in cs)
            kinds = {c.kind for c, _ in cs}
            bonus = 0.04 * (len(kinds) - 1) * abs(best)
            rep = max(cs, key=lambda x: x[1])[0]
            out.append((rep, best + bonus))
            for item in self.c.items_of_project(proj):
                if item != rep.item_id:
                    ghost = Chunk(f"{item}#mv", item, self.c.item_text(item, 600), "summary", self.c.item_meta(item))
                    out.append((ghost, best + bonus - 1e-4))
        return sorted(out, key=lambda x: -x[1])

    def _rerank(self, query: str, cands: list[tuple[Chunk, float]]) -> list[tuple[Chunk, float]]:
        from rag.embeddings import get_reranker
        cands = cands[: self.s.candidates]
        scores = get_reranker().score(query, [c.text for c, _ in cands])
        return sorted(zip([c for c, _ in cands], scores), key=lambda x: -x[1])

    def _to_items(self, ranked: list[tuple[Chunk, float]], req: str | None, k: int) -> list[Hit]:
        out: dict[str, Hit] = {}
        for c, s in ranked:
            if c.item_id in out:
                continue
            out[c.item_id] = Hit(c.item_id, s, c.text, dict(c.meta), c.id, [req] if req else [],
                                 support=self._support(req, c) if req else 0.0)
            if len(out) >= k:
                break
        return list(out.values())

    def _support(self, req: str, c: Chunk) -> float:
        """Requirement support = skill overlap between requirement and the *project's*
        confirmed skills (from every source), so an implied skill counts if the code proves it."""
        rs = set(extract_skills(req, semantic=True))
        if not rs:
            return 0.3
        ps = self.c.project_skills.get(c.meta.get("project", ""), set()) | set(c.meta.get("skills", []))
        return len(rs & ps) / len(rs)

    def _assign(self, items: list[Hit], reqs: list[str]) -> dict[str, list[Hit]]:
        out: dict[str, list[Hit]] = {}
        for r in reqs:
            hs = []
            for h in items:
                sup = self._support(r, Chunk(h.chunk_id, h.item_id, h.text, "x", h.meta))
                if sup > 0.34:
                    hs.append(Hit(h.item_id, h.score, h.text, h.meta, h.chunk_id, [r], sup))
            out[r] = hs[:4]
        return out

    def _fuse_graph(self, items: list[Hit], q: Query) -> list[Hit]:
        skills = set()
        for r in (q.requirements or [q.job_text]):
            skills |= set(extract_skills(r))
        ranked = self.c.graph.projects_for(sorted(skills), q.industry)
        g_hits = []
        for p, sc, matched in ranked[:10]:
            for it in self.c.items_of_project(p):
                g_hits.append(Hit(it, sc, self.c.item_text(it, 400), self.c.item_meta(it), f"{it}#graph",
                                  support=len(matched) / max(1, len(skills))))
        # reciprocal-rank fuse the graph list with the retrieval list
        score: dict[str, float] = defaultdict(float)
        keep: dict[str, Hit] = {}
        for lst in (items, g_hits):
            for rank, h in enumerate(lst):
                score[h.item_id] += 1 / (60 + rank + 1)
                keep.setdefault(h.item_id, h)
        for i, h in keep.items():
            h.score = score[i]
        return sorted(keep.values(), key=lambda h: -h.score)

    def _outcome_boost(self, items: list[Hit], q: Query) -> list[Hit]:
        """Boost projects that were cited in proposals which won or got replies for jobs
        that share skills with this job. Weighted by outcome, normalised by exposure."""
        job_sk = set()
        for r in (q.requirements or [q.job_text]):
            job_sk |= set(extract_skills(r, semantic=False))
        stat: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for d in self.c.docs:
            if d.meta["type"] != "proposal":
                continue
            js = {s for s in SKILLS if skill_name(s) in d.meta.get("job_skills", [])}
            if job_sk and not (js & job_sk):
                continue
            v = {"won": 1.0, "replied": 0.5, "ignored": -0.2}[d.meta["outcome"]]
            for p in d.meta.get("cited_projects", []):
                stat[p][0] += v
                stat[p][1] += 1
        w = cfg("rag.outcome_boost", 0.15)
        top = max((abs(h.score) for h in items), default=1.0) or 1.0
        for h in items:
            s, n = stat.get(h.meta.get("project", ""), (0.0, 0.0))
            if n:
                h.score += w * top * (s / (n + 2))
        return sorted(items, key=lambda h: -h.score)

    def _exemplars(self, q: Query, n: int = 2) -> list[dict]:
        hits = self.c.bm25("proposals").search(f"{q.title} {' '.join(q.requirements)}", 20)
        good = [c for c, _ in hits if c.meta.get("outcome") in ("won", "replied")]
        return [{"id": c.item_id, "outcome": c.meta["outcome"], "text": c.text[:500]} for c in good[:n]]

    def _hyde(self, text: str, q: Query) -> str:
        if self.llm_hyde:
            try:
                return self.llm_hyde(text, q)
            except Exception:
                pass
        # offline HyDE-lite: a hypothetical ideal proposal assembled from the taxonomy
        sk = extract_skills(text)
        names = [skill_name(s) for s in sk]
        return (f"I recently delivered a similar project: {q.title}. I built it with {', '.join(names) or 'the requested stack'}, "
                f"shipped to production and measured the result. Relevant work: {text[:200]}")

    def _corrective(self, per_req: dict[str, list[Hit]], q: Query, trace: list[str]):
        from rag.variants.v8_corrective import corrective_loop
        return corrective_loop(self, per_req, q, trace)
