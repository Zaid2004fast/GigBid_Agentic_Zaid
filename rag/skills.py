"""GigBid's skill taxonomy + extractor.

Important fairness rule: GigBid only knows each skill's *name, aliases and typical code
tokens*.  It deliberately does NOT use the generator's `implicit` phrases, so implied
skills ("background workers that process uploads" -> Celery) must be recovered by
semantic similarity, exactly as on a real corpus.
"""
from __future__ import annotations

import re
from functools import lru_cache

import numpy as np

from data.generator.ontology import SKILLS

GENERIC = {"python", "sql", "docker", "pandas", "typescript", "excel"}


@lru_cache(maxsize=1)
def alias_patterns() -> dict[str, re.Pattern]:
    pats = {}
    for sid, s in SKILLS.items():
        names = sorted({a for a in s["aliases"] + [s["name"]] if len(a) > 1}, key=len, reverse=True)
        pats[sid] = re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in names) + r")(?![\w-])", re.I)
    return pats


@lru_cache(maxsize=1)
def code_patterns() -> dict[str, re.Pattern]:
    """Library tokens that reveal a skill inside code (import celery, from peft ...)."""
    pats = {}
    for sid, s in SKILLS.items():
        toks = set(re.findall(r"(?:import|from)\s+([a-zA-Z_][\w.]*)", s["code"]))
        toks |= set(re.findall(r"\b(cv2|torch|boto3|stripe|mlflow|faiss|airflow|gtag|bigquery|snowflake|redis|celery)\b", s["code"]))
        if toks:
            pats[sid] = re.compile(r"\b(" + "|".join(re.escape(t.split(".")[0]) for t in toks) + r")\b")
    return pats


def explicit_skills(text: str) -> set[str]:
    found = {sid for sid, p in alias_patterns().items() if p.search(text)}
    found |= {sid for sid, p in code_patterns().items() if p.search(text)}
    # "Node" alone is too ambiguous to count as Node.js
    return found


def skill_card(sid: str) -> str:
    s = SKILLS[sid]
    return f"{s['name']} ({', '.join(s['aliases'])}). {s['code']}"


@lru_cache(maxsize=1)
def _card_matrix():
    from rag.embeddings import get_embedder
    ids = [s for s in SKILLS]
    emb = get_embedder()
    return ids, emb.embed([skill_card(s) for s in ids])


def semantic_skills(text: str, threshold: float = 0.72, top: int = 2) -> dict[str, float]:
    """Skills implied by `text` (sentence-level), with similarity scores."""
    from rag.embeddings import get_embedder
    ids, mat = _card_matrix()
    sents = [s for s in re.split(r"(?<=[.!?\n])\s+|\n-\s*", text) if len(s.split()) >= 3][:40]
    if not sents:
        return {}
    v = get_embedder().embed(sents)
    sims = v @ mat.T
    out: dict[str, float] = {}
    for row in sims:
        for j in np.argsort(-row)[:top]:
            if row[j] >= threshold:
                out[ids[j]] = max(out.get(ids[j], 0.0), float(row[j]))
    return out


def extract_skills(text: str, semantic: bool = True, threshold: float = 0.72) -> dict[str, float]:
    """Union of explicit (score 1.0) and semantic matches (memoised: called per hit)."""
    return dict(_extract_cached(text, semantic, threshold))


@lru_cache(maxsize=50_000)
def _extract_cached(text: str, semantic: bool, threshold: float) -> tuple:
    out = {s: 1.0 for s in explicit_skills(text)}
    if semantic:
        for s, sc in semantic_skills(text, threshold).items():
            out.setdefault(s, sc)
    return tuple(out.items())


def skill_name(sid: str) -> str:
    return SKILLS[sid]["name"] if sid in SKILLS else sid


def domain_of(sid: str) -> str:
    return SKILLS.get(sid, {}).get("domain", "off")
