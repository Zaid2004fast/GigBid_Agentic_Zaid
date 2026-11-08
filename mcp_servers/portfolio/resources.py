"""Resource templates so an MCP host (Claude Desktop, Cursor) can load full items."""
from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP

from rag.corpus import get_corpus


def _persona() -> str:
    return os.getenv("PORTFOLIO_PERSONA", "aiml")


def register(mcp: FastMCP) -> None:
    @mcp.resource("portfolio://case/{id}", name="case_study", mime_type="text/markdown",
                  description="A full case study by project key")
    def case(id: str) -> str:
        c = get_corpus(_persona())
        docs = c.by_item.get(f"{c.persona}:cs:{id}")
        if not docs:
            raise ValueError(f"no case study {id}")
        return docs[0].text

    @mcp.resource("portfolio://proposal/{id}", name="past_proposal", mime_type="application/json",
                  description="A past proposal with its outcome (won / replied / ignored)")
    def proposal(id: str) -> str:
        c = get_corpus(_persona())
        docs = c.by_item.get(f"{c.persona}:proposal:{id}")
        if not docs:
            raise ValueError(f"no proposal {id}")
        d = docs[0]
        return json.dumps({"id": id, "text": d.text, **{k: d.meta.get(k) for k in ("outcome", "title", "date", "client_industry", "cited_projects")}})

    @mcp.resource("portfolio://repo/{id}", name="repo", mime_type="text/plain", description="README and code of a repo")
    def repo(id: str) -> str:
        c = get_corpus(_persona())
        docs = c.by_item.get(f"{c.persona}:repo:{id}")
        if not docs:
            raise ValueError(f"no repo {id}")
        return "\n\n".join(f"# {d.meta.get('path')}\n{d.text}" for d in docs)

    @mcp.resource("portfolio://cv", name="cv", mime_type="text/plain", description="The CV as text")
    def cv() -> str:
        c = get_corpus(_persona())
        return "\n".join(d.text for i, ds in c.by_item.items() if ":cv:" in i for d in ds)
