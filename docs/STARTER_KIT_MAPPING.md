# Starter kit v0.1: checklist mapping

The instructor shared `GigBid_Student_Starter_Kit_v0.1` as an example scaffold, to be used only as a
reference. GigBid was built independently. Its folder layout already matched the kit's suggested
structure. This page maps each item of the kit's `IMPLEMENTATION_CHECKLIST.md` to where it is done.

| Kit checklist item | Where it is implemented | Evidence |
|---|---|---|
| Marketplace port and GigSim adapter | `agent/marketplace_port.py`, `mcp_servers/marketplace/adapters/gigsim.py` | `tests/integration/test_graphs.py` |
| Portfolio MCP tools, resources and prompts | `mcp_servers/portfolio/` (6 tools, 4 resources, 3 prompts) | `mcp_servers/portfolio/tests/` |
| Marketplace MCP read/write tools with schemas and idempotency | `mcp_servers/marketplace/server.py` | `test_retried_submit_spends_connects_once` |
| Workspace MCP tools or local mock | `mcp_servers/workspace/server.py` (local mock) | `mcp_servers/workspace/tests/` |
| Ingest CVs, case studies, READMEs, code, reviews, past proposals | `rag/ingest/loaders.py` | `docs/DATA_CARD.md` |
| V0 plus at least four required variants | `rag/variants/` (V0 to V9) + composites in `rag/retriever.py` | `evals/results/rag_retrieval.json` |
| Claim splitting and evidence verification | `rag/verify.py`, `agent/nodes/verifier.py` | `evals/results/claims_eval.json` |
| Bid graph with parallel analysis branches | `agent/graphs/bid_graph.py` (`Send` fan-out) | `docs/images/bid_graph.png` |
| Conversation graph | `agent/graphs/conversation_graph.py` | `docs/traces/6_client_reply.json` |
| Bounded Critic loop and Compliance Guard | `agent/nodes/critic.py`, `agent/nodes/compliance.py`, `data/policy_pack/rules.yaml` | `docs/traces/3_critic_loop.json` |
| Interrupts for all external actions and Connects spend | `agent/nodes/approval.py`, `agent/nodes/liaison.py` | Playwright approve / edit / reject tests |
| Durable checkpointing and crash/resume test | `agent/memory/store.py` | `test_bid_interrupts_then_submits_exactly_once`, `docs/traces/5_crash_and_resume.json` |
| All UI screens and approval interactions | `apps/web/src/app/*` | `apps/web/tests/e2e/gigbid.spec.ts` |
| Worker scheduling, tracing, budgets, guardrails | `worker/`, `common/tracing.py`, `agent/runtime.py`, `agent/guards.py` | `docs/RUNBOOK.md` |
| Unit, integration, contract and Playwright tests | `tests/`, `mcp_servers/*/tests`, `apps/web/tests/e2e` | 46 Python + 6 Playwright tests |
| Evaluations with reproducible results | `evals/runners/`, `scripts/run.py eval` | `evals/results/*.json` |
| Deploy and verify reviewer access | `render.yaml`, `docs/DEPLOY.md` | https://gigbid.onrender.com |
| Report, demo, write-up, AI usage | `docs/report/`, `docs/AI_USAGE.md` | `docs/report/GigBid_RnD_Report.pdf` |

## Compatibility with the kit's data format

`data/importers/starter_kit.py` converts the kit's `jobs.json`, `freelancers.json`, `portfolio_items.json`
and `client_history.json` into GigBid's shapes. `tests/unit/test_starter_kit_format.py` runs the kit's own
sample data (copied unchanged into `tests/fixtures/starter_kit_sample/`) through GigBid's real components:

- `sample-job-002` (unpaid trial + external messaging app) is flagged high risk: free work, off-platform contact.
- `sample-job-001` (churn baseline) extracts its requirements, $450 budget and screening question, with low risk.
- The kit's portfolio item `evidence-001` is retrieved first for "scikit-learn classifier evaluation".

**What this check found.** The kit's wording "contact the client on an external messaging app" was *not* caught
at first, because our patterns named specific apps (WhatsApp, Telegram, Skype). This was the overfitting to our
own data that the report warns about. The Risk Assessor and the policy pack now also match generic phrasing. On all
600 dev jobs the change blocks 0 legitimate jobs (`evals/results/scam_gate_check.json`).
