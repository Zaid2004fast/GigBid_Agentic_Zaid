"""LangGraph long-term store + checkpointer factories.

Namespaces (all scoped by user id - tenant isolation):
  ("style", user)              promoted style rules (read by Writer / Liaison)
  ("style_candidates", user)   observed edit patterns waiting for promotion (NOT read by agents)
  ("outcome", user)            promoted per-category Beta posteriors + evidence win stats
  ("outcome_events", user)     validated, de-duplicated outcome records (input to promotion)
  ("ev_history", user)         recent expected-value-per-Connect values for budget pacing
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from agent.config import ROOT


def _pg_url() -> str | None:
    url = os.getenv("DATABASE_URL", "")
    if url.startswith("postgres"):
        return url.replace("postgresql+psycopg://", "postgresql://")
    return None


@asynccontextmanager
async def open_persistence():
    """Yields (checkpointer, store). Postgres when DATABASE_URL is Postgres, else SQLite files."""
    pg = _pg_url()
    if pg:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from langgraph.store.postgres.aio import AsyncPostgresStore
        async with AsyncPostgresSaver.from_conn_string(pg) as cp, AsyncPostgresStore.from_conn_string(pg) as st:
            await cp.setup()
            await st.setup()
            yield cp, st
        return
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from langgraph.store.sqlite.aio import AsyncSqliteStore
    d = ROOT / "data" / "processed"
    d.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(d / "checkpoints.sqlite")) as cp, \
            AsyncSqliteStore.from_conn_string(str(d / "memory_store.sqlite")) as st:
        await cp.setup()
        await st.setup()
        yield cp, st


def memory_store():
    from langgraph.store.memory import InMemoryStore
    return InMemoryStore()
