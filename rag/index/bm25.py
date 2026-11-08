"""BM25 keyword index; tokenizer keeps library names such as next.js, c#, scikit-learn intact."""
from __future__ import annotations

import re
from typing import Callable

from rank_bm25 import BM25Okapi

from rag.ingest.chunkers import Chunk

_TOK = re.compile(r"[a-z0-9][a-z0-9+#._-]*[a-z0-9+#]|[a-z0-9]")
STOP = set("a an the and or of to for in on with we you our your is are be this that it as at by from i my me will can need looking".split())


def tokenize(text: str) -> list[str]:
    return [t for t in _TOK.findall(text.lower()) if t not in STOP]


class BM25Index:
    def __init__(self, chunks: list[Chunk], texts: list[str] | None = None):
        self.chunks = chunks
        self.bm = BM25Okapi([tokenize(t) or ["_"] for t in (texts or [c.text for c in chunks])]) if chunks else None

    def search(self, query: str, k: int = 10, where: Callable[[Chunk], bool] | None = None) -> list[tuple[Chunk, float]]:
        if not self.bm:
            return []
        scores = self.bm.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        out = []
        for i in order:
            if scores[i] <= 0:
                break
            c = self.chunks[i]
            if where and not where(c):
                continue
            out.append((c, float(scores[i])))
            if len(out) >= k:
                break
        return out
