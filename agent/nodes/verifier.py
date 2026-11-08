"""Claim verification node (B3): every claim checked against portfolio evidence fetched via
the Portfolio MCP server; unsupported claims removed / repaired BEFORE the Critic sees it."""
from __future__ import annotations

from agent.handoffs import ProposalDraft
from agent.runtime import NodeCtx, node
from rag.verify import strip_citations, verify_draft


def mcp_resolvers(ctx: NodeCtx):
    tools = ctx.tools("verifier")
    cache: dict[str, dict] = {}

    async def resolve(item_ids: list[str]) -> list[dict]:
        need = [i for i in item_ids if i not in cache]
        if need:
            for d in (await tools("get_evidence", item_ids=need[:10]))["items"]:
                cache[d["item_id"]] = d
        return [cache[i] for i in item_ids if i in cache]

    async def search(text: str) -> list[str]:
        r = await tools("search_evidence", requirement=text[:380], k=2)
        return [i["item_id"] for i in r["items"] if i.get("support", 0) > 0][:2]
    return resolve, search


@node("verifier")
async def verifier(state: dict, ctx: NodeCtx) -> dict:
    d = ProposalDraft.model_validate(state["drafts"][-1])
    labels = {k: {"item_id": v} for k, v in d.evidence_labels.items()}
    resolve, search = mcp_resolvers(ctx)
    fixed, rep = await verify_draft(d.text, labels, resolve, search, fix=True)
    new = d.model_copy(update={"text": fixed, "sendable_text": strip_citations(fixed), "word_count": len(strip_citations(fixed).split()),
                               "claims": rep.claims})
    ctx.emit(f"claims: {len(rep.claims)}, unsupported {rep.unsupported_before} -> {rep.unsupported_after}")
    return {"drafts": [new.model_dump()], "verification": rep.model_dump(),
            "progress": [f"Verifier: {len(rep.claims)} claims, unsupported {rep.unsupported_before}->{rep.unsupported_after}, "
                         f"{len(rep.rewritten)} rewritten, {len(rep.removed)} removed"]}
