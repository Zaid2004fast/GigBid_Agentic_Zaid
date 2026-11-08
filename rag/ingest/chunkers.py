"""Chunkers.

fixed_chunks      - V0 baseline: fixed character windows, structure ignored
structured_chunks - heading/code aware; code blocks and code files become their own chunks
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rag.ingest.loaders import Document


@dataclass
class Chunk:
    id: str
    item_id: str
    text: str
    kind: str                       # prose | code | readme | cv | review | proposal | summary
    meta: dict = field(default_factory=dict)


def fixed_chunks(doc: Document, size: int = 450, overlap: int = 60) -> list[Chunk]:
    t, out, i, n = doc.text, [], 0, 0
    while i < len(t):
        out.append(Chunk(f"{doc.item_id}#f{n}:{doc.meta.get('path', '')}", doc.item_id, t[i:i + size], "prose", doc.meta))
        i += size - overlap
        n += 1
    return out


def structured_chunks(doc: Document, size: int = 450) -> list[Chunk]:
    typ = doc.meta["type"]
    p = doc.meta.get("path", "")
    if typ in ("cv", "review", "proposal"):
        return [Chunk(f"{doc.item_id}#s0", doc.item_id, doc.text, typ, doc.meta)]
    if typ == "repo_code":
        blocks = re.split(r"\n\s*\n", doc.text)
        return [Chunk(f"{doc.item_id}#code:{p}:{i}", doc.item_id, b, "code", doc.meta) for i, b in enumerate(blocks) if b.strip()]
    if typ == "repo_readme":
        return [Chunk(f"{doc.item_id}#readme", doc.item_id, doc.text[:1500], "readme", doc.meta)]
    # markdown case study: split by "## " sections, code fences separate
    out, n = [], 0
    title = doc.meta.get("title", "")
    for sec in re.split(r"\n(?=## )", doc.text):
        parts = re.split(r"```(?:\w+)?\n(.*?)```", sec, flags=re.S)
        for j, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue
            kind = "code" if j % 2 == 1 else "prose"
            # keep the document title on prose chunks so a section is never orphaned
            text = part if kind == "code" or part.startswith("# ") else f"{title}\n{part}"
            for k in range(0, len(text), size):
                out.append(Chunk(f"{doc.item_id}#s{n}", doc.item_id, text[k:k + size], kind, doc.meta))
                n += 1
    return out
