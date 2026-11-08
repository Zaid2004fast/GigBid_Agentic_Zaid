"""GigBid Portfolio MCP server (read-only).

Run it for your own portfolio folder (cv.pdf, case_studies/*.md, repos/*, reviews.jsonl,
proposals.jsonl):
    PORTFOLIO_DIR=~/my-portfolio PORTFOLIO_PERSONA=me python -m mcp_servers.portfolio.server          # stdio
    python -m mcp_servers.portfolio.server --http --port 8201                                         # streamable HTTP
"""
from __future__ import annotations

import argparse
import os

from mcp.server.fastmcp import FastMCP

from mcp_servers.portfolio import prompts, resources, tools

mcp = FastMCP(
    "gigbid-portfolio",
    instructions=("Read-only access to a freelancer's portfolio: evidence search per requirement, case studies, skills, "
                  "and 'have I done X' questions. Every item has a stable id you can cite."),
    stateless_http=True, json_response=True,
)
tools.register(mcp)
resources.register(mcp)
prompts.register(mcp)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", action="store_true")
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", "8201")))
    a = ap.parse_args()
    if a.http:
        import uvicorn
        from mcp_servers.common import http_app
        uvicorn.run(http_app(mcp), host="0.0.0.0", port=a.port)
    else:
        mcp.run("stdio")


if __name__ == "__main__":
    main()
