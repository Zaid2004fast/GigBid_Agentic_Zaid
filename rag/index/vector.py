"""Dense vector index.

NumpyIndex  - in-process exact cosine search (dev, CI, evals; corpus is small)
PgVectorIndex - Postgres + pgvector, used by docker compose / deployment
Both expose .search(query_vec, k, where) -> [(chunk, score)].
"""
from __future__ import annotations

import json
import os
from typing import Callable

import numpy as np

from rag.ingest.chunkers import Chunk


class NumpyIndex:
    def __init__(self, chunks: list[Chunk], embedder, texts: list[str] | None = None):
        self.chunks = chunks
        self.mat = embedder.embed(texts or [c.text for c in chunks]) if chunks else np.zeros((0, embedder.dim), np.float32)

    def search(self, qvec: np.ndarray, k: int = 10, where: Callable[[Chunk], bool] | None = None) -> list[tuple[Chunk, float]]:
        if not self.chunks:
            return []
        sims = self.mat @ qvec
        order = np.argsort(-sims)
        out = []
        for i in order:
            c = self.chunks[i]
            if where and not where(c):
                continue
            out.append((c, float(sims[i])))
            if len(out) >= k:
                break
        return out


class PgVectorIndex:
    """Same interface backed by pgvector (DATABASE_URL must point to Postgres with the vector extension)."""

    def __init__(self, chunks: list[Chunk], embedder, texts: list[str] | None = None, table: str = "rag_chunks", namespace: str = ""):
        import psycopg
        self.chunks = {c.id: c for c in chunks}
        self.ns = namespace
        self.conn = psycopg.connect(os.environ["DATABASE_URL"].replace("+asyncpg", "").replace("+psycopg", ""), autocommit=True)
        dim = embedder.dim
        self.table = table
        self.conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        self.conn.execute(f"CREATE TABLE IF NOT EXISTS {table}(id TEXT, ns TEXT, item_id TEXT, meta JSONB, emb vector({dim}), PRIMARY KEY(ns, id))")
        existing = {r[0] for r in self.conn.execute(f"SELECT id FROM {table} WHERE ns=%s", (namespace,))}
        new = [c for c in chunks if c.id not in existing]
        if new:
            vecs = embedder.embed([texts[chunks.index(c)] if texts else c.text for c in new])
            with self.conn.cursor() as cur:
                for c, v in zip(new, vecs):
                    cur.execute(f"INSERT INTO {table} VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                                (c.id, namespace, c.item_id, json.dumps(c.meta), "[" + ",".join(f"{x:.6f}" for x in v) + "]"))

    def search(self, qvec: np.ndarray, k: int = 10, where=None) -> list[tuple[Chunk, float]]:
        q = "[" + ",".join(f"{x:.6f}" for x in qvec) + "]"
        rows = self.conn.execute(f"SELECT id, 1 - (emb <=> %s::vector) FROM {self.table} WHERE ns=%s ORDER BY emb <=> %s::vector LIMIT %s",
                                 (q, self.ns, q, k * 4)).fetchall()
        out = []
        for cid, s in rows:
            c = self.chunks.get(cid)
            if c and (not where or where(c)):
                out.append((c, float(s)))
            if len(out) >= k:
                break
        return out


def make_index(chunks, embedder, texts=None, namespace=""):
    from agent.config import cfg
    if cfg("rag.vector_store", os.getenv("VECTOR_STORE", "numpy")) == "pgvector" and os.getenv("DATABASE_URL", "").startswith("postgres"):
        return PgVectorIndex(chunks, embedder, texts, namespace=namespace)
    return NumpyIndex(chunks, embedder, texts)
