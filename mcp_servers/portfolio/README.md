# gigbid-portfolio-mcp

A read-only **MCP server for your freelance portfolio**. Plug it into Claude Desktop, Cursor
or any MCP host and ask "what proof do I have for *Celery background workers*?", "have I done
RAG for a legal client?", or "answer this screening question from my portfolio".

Part of [GigBid](../../README.md). Retrieval is hybrid (BM25 + `bge-small` embeddings with
reciprocal rank fusion) with requirement decomposition and a corrective loop that **refuses**
to return evidence it cannot support.

## Tools

| Tool | What it does |
|---|---|
| `search_evidence(requirement, k, filters)` | evidence items (case study, CV, repo, review) proving ONE requirement, with type, source, date, outcome and a support score; `status: none` means *do not claim it* |
| `get_case_study(id)` | full case study markdown + related CV/repo ids |
| `get_evidence(item_ids)` | full text + skills proven for the project |
| `list_skills()` | every provable skill with the projects behind it |
| `have_i_done(skill, industry)` | skill-graph answer with the projects as proof |
| `find_winning_proposals(job_summary, k)` | your past proposals that won or got replies (for tone only) |

Resources: `portfolio://case/{id}`, `portfolio://proposal/{id}`, `portfolio://repo/{id}`, `portfolio://cv`.
Prompts: *Answer a screening question from my portfolio*, *Which requirements of this job can I prove?*,
*Draft a cover letter where every claim cites my portfolio*.

## Your portfolio folder

```
my-portfolio/
├── cv.pdf                    # bullets ending in [github.com/<you>/<project>] or [portfolio/<project>]
├── case_studies/<project>.md # optional front-matter: project, client_industry, date
├── repos/<project>/README.md (+ code files)
├── reviews.jsonl             # optional {"id","project","rating","text","date","client_industry"}
└── proposals.jsonl           # optional past proposals with "outcome": won|replied|ignored
```

## Install

```bash
# uvx (no install)
uvx --from "git+https://github.com/<you>/gigbid" gigbid-portfolio-mcp

# Docker
docker run -i --rm -v ~/my-portfolio:/portfolio -e PORTFOLIO_DIR=/portfolio -e PORTFOLIO_PERSONA=me \
  ghcr.io/<you>/gigbid-portfolio-mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{"mcpServers": {"portfolio": {"command": "uvx",
  "args": ["--from", "git+https://github.com/<you>/gigbid", "gigbid-portfolio-mcp"],
  "env": {"PORTFOLIO_DIR": "/Users/me/my-portfolio", "PORTFOLIO_PERSONA": "me"}}}}
```

Streamable HTTP instead of stdio: `gigbid-portfolio-mcp --http --port 8201` (set `MCP_SERVER_TOKEN` for bearer auth).

The first run downloads two small open models (~150 MB, CPU only). Read-only: the server never writes to your portfolio.