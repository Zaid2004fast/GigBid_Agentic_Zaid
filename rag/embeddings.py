"""Open embedding + reranker models (CPU friendly) with an on-disk cache.

Providers
  fastembed : BAAI/bge-small-en-v1.5 embeddings, ms-marco MiniLM cross-encoder (ONNX, CPU)
  hash      : deterministic feature-hashing embedder, used only in unit tests / CI
"""
from __future__ import annotations

import hashlib
import math
import re
import sqlite3
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np

from agent.config import ROOT, cfg

CACHE = ROOT / "data" / "processed" / "emb_cache.sqlite"
MODELS_DIR = ROOT / ".models"
_TOK = re.compile(r"[a-z0-9][a-z0-9+#.-]*")


class HashEmbedder:
    dim = 512
    name = "hash-512"

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            toks = _TOK.findall(t.lower())
            feats = toks + [a + "_" + b for a, b in zip(toks, toks[1:])]
            for f in feats:
                h = int(hashlib.md5(f.encode()).hexdigest(), 16)
                out[i, h % self.dim] += 1.0 if (h >> 9) & 1 else -1.0
            n = np.linalg.norm(out[i])
            if n:
                out[i] /= n
        return out


class FastEmbedder:
    def __init__(self, model: str):
        from fastembed import TextEmbedding
        self.name = model
        self.m = TextEmbedding(model, cache_dir=str(MODELS_DIR))
        self.dim = len(next(iter(self.m.embed(["x"]))))

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray(list(self.m.embed(texts, batch_size=64)), dtype=np.float32)


class CachedEmbedder:
    """Wraps an embedder with a sqlite cache keyed by (model, sha1(text))."""

    def __init__(self, inner):
        self.inner, self.name, self.dim = inner, inner.name, inner.dim
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(CACHE, check_same_thread=False, timeout=60)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS emb(k TEXT PRIMARY KEY, v BLOB)")
        self.lock = threading.Lock()

    def embed(self, texts: list[str]) -> np.ndarray:
        keys = [hashlib.sha1(f"{self.name}|{t}".encode()).hexdigest() for t in texts]
        out: list[np.ndarray | None] = [None] * len(texts)
        with self.lock:
            for i, k in enumerate(keys):
                row = self.db.execute("SELECT v FROM emb WHERE k=?", (k,)).fetchone()
                if row:
                    out[i] = np.frombuffer(row[0], dtype=np.float32)
            missing = [i for i, v in enumerate(out) if v is None]
            if missing:
                vecs = self.inner.embed([texts[i] for i in missing])
                try:   # the cache is best-effort: another process holding the write lock must not fail retrieval
                    for i, v in zip(missing, vecs):
                        out[i] = v
                        self.db.execute("INSERT OR REPLACE INTO emb VALUES (?,?)", (keys[i], v.astype(np.float32).tobytes()))
                    self.db.commit()
                except sqlite3.OperationalError:
                    self.db.rollback()
                    for i, v in zip(missing, vecs):
                        out[i] = v
        mat = np.vstack(out) if out else np.zeros((0, self.dim), dtype=np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        return mat / np.where(norms == 0, 1, norms)


@lru_cache(maxsize=2)
def get_embedder(provider: str | None = None):
    provider = provider or cfg("embeddings.provider", "fastembed")
    if provider == "hash":
        return CachedEmbedder(HashEmbedder())
    return CachedEmbedder(FastEmbedder(cfg("embeddings.model", "BAAI/bge-small-en-v1.5")))


# ------------------------------------------------------------------ reranker
class LexicalReranker:
    name = "lexical"

    def score(self, query: str, docs: list[str]) -> list[float]:
        q = set(_TOK.findall(query.lower()))
        return [len(q & set(_TOK.findall(d.lower()))) / math.sqrt(len(q) + 1) for d in docs]


class CrossEncoderReranker:
    def __init__(self, model: str):
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        self.name = model
        self.m = TextCrossEncoder(model, cache_dir=str(MODELS_DIR))

    _lock = threading.Lock()   # ONNX sessions are shared; serialise calls from worker threads

    def score(self, query: str, docs: list[str]) -> list[float]:
        if not docs:
            return []
        with self._lock:
            return [float(s) for s in self.m.rerank(query, docs, batch_size=32)]


@lru_cache(maxsize=2)
def get_reranker(provider: str | None = None):
    provider = provider or cfg("reranker.provider", "fastembed")
    if provider in ("hash", "lexical"):
        return LexicalReranker()
    return CrossEncoderReranker(cfg("reranker.model", "Xenova/ms-marco-MiniLM-L-6-v2"))
