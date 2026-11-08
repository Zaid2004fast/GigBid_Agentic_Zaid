# GigBid - R&D design review

AI-4016 R&D assignment · individual · Every number below is filled at build time from
`evals/results/*.json` (`python scripts/build_report.py`); file names are cited inline.
Repository commit history and traces (`docs/traces/`) back every claim.

## 1. Problem and constraints

A freelancer's week has four expensive steps: scanning feeds, judging whether a job is worth the
Connects, writing a specific proposal, and keeping conversations moving. GigBid automates
discovery, assessment and drafting. **The freelancer makes every decision that leaves the system.**

**Never automated (enforced in code):** submitting a proposal, sending a message, spending Connects
(LangGraph `interrupt()` in both graphs; no API path resumes a thread without an approval body);
claiming experience the portfolio cannot support (claim verifier + compliance rule P2); any
off-platform contact, payment or guarantee (policy pack); any read faster than the declared
schedule (rate limiter + RUNBOOK). The per-user autonomy setting can auto-*skip* clearly low-fit
jobs, never auto-send.

**Declared budgets** (`agent/config.yaml → budgets.declared`): p95 latency 20 s per job analysed
and 60 s per proposal; USD 0.002 per job analysed and 0.01 per proposal; 40 steps and 60k tokens
per thread (exceeding either moves the thread to *needs_attention*).

**Data.** The starter kit was not distributed, so `data/generator` builds a deterministic stand-in
world with the brief's properties and exact gold labels (`docs/DATA_CARD.md`). GigSim's client model
rewards must-have coverage and specificity, penalises generic openings and over-budget bids, and
exposes fabricated experience at interview. Reply rates are comparable only within GigSim.

## 2. Architecture

Two hand-written LangGraph `StateGraph`s (rendered from code: `docs/images/bid_graph.png`,
`conversation_graph.png`). In the **bid graph**, `intake` fans out with `Send` to Job Analyst, Risk
Assessor and Fit Matcher in parallel. A `reconcile` join searches evidence for any requirement the
Analyst found that the Matcher's own decomposition missed. Then come `decide` (skip / watch / bid),
Pricing, Writer, claim Verifier, Critic (≤ 2 send-backs), Compliance, `dry_run` preview and the
`interrupt()` approval (approve → idempotent submit; edit → diff, style memory, compliance re-check,
re-approval; reject → reason). The **conversation graph** (one thread per client) runs fetch, injection
guard, intent, interview slots or negotiation (walk-away rules), reply, compliance and approval.

![Bid graph](../images/bid_graph.png)

**Marketplace port.** One interface (`agent/marketplace_port.py`) with two adapters: GigSim (our
Marketplace MCP server) and live Upwork (official MCP server via `MultiServerMCPClient`, OAuth 2.1 +
PKCE, tokens encrypted per user, tool names discovered at connect time). `marketplace.mode` switches
them; no node imports an adapter.

**MCP surface.** Portfolio (read), Marketplace (read + idempotent, `dry_run`-able writes with
annotations), Workspace (calendar slots, tentative holds, email drafts), plus Upwork and GitHub
(`docs/TOOLS.md`). There are per-agent allowlists, per-server timeouts, retries with backoff, and a
circuit breaker that drives degraded mode.

**State, trace, memory are separate.** Typed state (TypedDict + reducers on every parallel or loop key;
Pydantic hand-offs `JobSpec`, `RiskReport`, `FitReport`, `BidDecision`, `PriceQuote`, `ProposalDraft`,
`Critique`, `ComplianceVerdict`) lives in the Postgres checkpointer. The execution trace (every node,
LLM call with tokens and USD, tool call with masked args and result) lives in the spans table and
Phoenix. Long-term memory lives in the LangGraph store and is written **only** by promotion rules:
style rule S1 (≥ 3 edits across ≥ 2 jobs within 60 days; demoted on contradiction) and outcome rules
O1/O2 (Beta posteriors per category from validated marketplace events; used after ≥ 5 samples).

**Why each agent exists** (`docs/ARCHITECTURE.md`): each one owns either a trust boundary (Analyst:
the only reader of untrusted text; Compliance: the only rule interpreter), a different data source
(Risk: client history; Matcher: portfolio), or a different cost/latency class (deterministic
decide/pricing vs. strong-model writer/critic).

## 3. R&D question A - tool granularity

**Hypothesis.** Coarse tools (`marketplace(action, args)`) cut prompt tokens but cost argument
accuracy. Exposing only role-relevant fine-grained tools with "use when / do not use for"
descriptions beats both.

**Setup.** 40 tasks with known correct calls (`evals/runners/tool_granularity.py`), the same model
({{tool_granularity.json:meta.model|raw}}), and three surfaces: *fine* (all 19 tools), *coarse*
(3 tools), *best* (role allowlist + rewritten descriptions). We record one tool call per task.

| Surface | Tool selection | Argument accuracy | Tokens / task |
|---|---|---|---|
| fine | {{tool_granularity.json:surfaces.fine.tool_selection_accuracy}} | {{tool_granularity.json:surfaces.fine.argument_accuracy}} | {{tool_granularity.json:surfaces.fine.tokens_per_task|0}} |
| coarse | {{tool_granularity.json:surfaces.coarse.tool_selection_accuracy}} | {{tool_granularity.json:surfaces.coarse.argument_accuracy}} | {{tool_granularity.json:surfaces.coarse.tokens_per_task|0}} |
| best | {{tool_granularity.json:surfaces.best.tool_selection_accuracy}} | {{tool_granularity.json:surfaces.best.argument_accuracy}} | {{tool_granularity.json:surfaces.best.tokens_per_task|0}} |

**Conclusion.** <!--A-CONCLUSION-->

## 4. R&D question B - retrieval, verification, what ships

**Hypothesis (stated before running).** "Hybrid BM25 + dense raises evidence Recall@5 by ≥ 10
points over naive dense, and a cross-encoder adds ≥ 3 more at k = 5."

**Results** (`rag_retrieval.json`, every dev job with gold evidence, n = {{rag_retrieval.json:results.best.all.n|int}}):

| Variant | Recall@5 | MRR | nDCG@10 | p95 s |
|---|---|---|---|---|
| V0 naive dense (all docs) | {{rag_retrieval.json:results.V0.all.recall@5}} | {{rag_retrieval.json:results.V0.all.mrr}} | {{rag_retrieval.json:results.V0.all.ndcg@10}} | {{rag_retrieval.json:results.V0.latency_s.p95}} |
| V0e control: naive dense, evidence only | {{rag_retrieval.json:results.V0e.all.recall@5}} | {{rag_retrieval.json:results.V0e.all.mrr}} | {{rag_retrieval.json:results.V0e.all.ndcg@10}} | {{rag_retrieval.json:results.V0e.latency_s.p95}} |
| V1 requirement decomposition | {{rag_retrieval.json:results.V1.all.recall@5}} | {{rag_retrieval.json:results.V1.all.mrr}} | {{rag_retrieval.json:results.V1.all.ndcg@10}} | {{rag_retrieval.json:results.V1.latency_s.p95}} |
| V2 hybrid BM25 + dense (RRF) | {{rag_retrieval.json:results.V2.all.recall@5}} | {{rag_retrieval.json:results.V2.all.mrr}} | {{rag_retrieval.json:results.V2.all.ndcg@10}} | {{rag_retrieval.json:results.V2.latency_s.p95}} |
| V3 + cross-encoder rerank | {{rag_retrieval.json:results.V3.all.recall@5}} | {{rag_retrieval.json:results.V3.all.mrr}} | {{rag_retrieval.json:results.V3.all.ndcg@10}} | {{rag_retrieval.json:results.V3.latency_s.p95}} |
| V4 outcome-aware | {{rag_retrieval.json:results.V4.all.recall@5}} | {{rag_retrieval.json:results.V4.all.mrr}} | {{rag_retrieval.json:results.V4.all.ndcg@10}} | {{rag_retrieval.json:results.V4.latency_s.p95}} |
| V5 multi-vector | {{rag_retrieval.json:results.V5.all.recall@5}} | {{rag_retrieval.json:results.V5.all.mrr}} | {{rag_retrieval.json:results.V5.all.ndcg@10}} | {{rag_retrieval.json:results.V5.latency_s.p95}} |
| V6 contextual | {{rag_retrieval.json:results.V6.all.recall@5}} | {{rag_retrieval.json:results.V6.all.mrr}} | {{rag_retrieval.json:results.V6.all.ndcg@10}} | {{rag_retrieval.json:results.V6.latency_s.p95}} |
| V7 HyDE-lite | {{rag_retrieval.json:results.V7.all.recall@5}} | {{rag_retrieval.json:results.V7.all.mrr}} | {{rag_retrieval.json:results.V7.all.ndcg@10}} | {{rag_retrieval.json:results.V7.latency_s.p95}} |
| V8 corrective (LangGraph) | {{rag_retrieval.json:results.V8.all.recall@5}} | {{rag_retrieval.json:results.V8.all.mrr}} | {{rag_retrieval.json:results.V8.all.ndcg@10}} | {{rag_retrieval.json:results.V8.latency_s.p95}} |
| V9 skill graph | {{rag_retrieval.json:results.V9.all.recall@5}} | {{rag_retrieval.json:results.V9.all.mrr}} | {{rag_retrieval.json:results.V9.all.ndcg@10}} | {{rag_retrieval.json:results.V9.latency_s.p95}} |
| C5 = V2 + V5 + V4 + V9 (round 1 pick) | {{rag_retrieval.json:results.C5.all.recall@5}} | {{rag_retrieval.json:results.C5.all.mrr}} | {{rag_retrieval.json:results.C5.all.ndcg@10}} | {{rag_retrieval.json:results.C5.latency_s.p95}} |
| **shipped** = C5 − dense | **{{rag_retrieval.json:results.best.all.recall@5}}** | {{rag_retrieval.json:results.best.all.mrr}} | **{{rag_retrieval.json:results.best.all.ndcg@10}}** | {{rag_retrieval.json:results.best.latency_s.p95}} |

The hypothesis was **half right**. On the clean index, hybrid raised Recall@5 from
{{rag_retrieval.json:results.V0e.all.recall@5}} (V0e) to {{rag_retrieval.json:results.V2.all.recall@5}}, but the reranker added
nothing at k = 5 on this corpus while costing seconds on CPU. Two results were larger than anything hypothesised:
(1) **corpus contamination**. Naive RAG retrieved past proposals (they look like job posts) instead of
evidence; the V0 → V0e control isolates it. (2) **Structure beats similarity**: the skill graph alone
outperforms every text ranker. Caveat: gold relevance is skill-defined, which favours a skill-aware
retriever, so we also check end to end below.

**Ablation of the shipped pipeline** (`ablation.json`; round 1 in `ablation_round1.json`):
removing the graph → Recall@5 {{ablation.json:retrieval.best-graph.all.recall@5}};
removing BM25 → {{ablation.json:retrieval.best-bm25.all.recall@5}};
removing multi-vector → {{ablation.json:retrieval.best-multivector.all.recall@5}};
removing outcome boost → {{ablation.json:retrieval.best-outcome.all.recall@5}};
adding the dense ranking back → {{ablation.json:retrieval.best+dense.all.recall@5}}.
By persona (shipped): aiml {{ablation.json:retrieval.best.persona:aiml.recall@5}}, web
{{ablation.json:retrieval.best.persona:web.recall@5}}, data {{ablation.json:retrieval.best.persona:data.recall@5}}.
By job type: vague posts {{ablation.json:retrieval.best.vague.recall@5}}, implied skills
{{ablation.json:retrieval.best.implicit.recall@5}}, ≥ 4 requirements {{ablation.json:retrieval.best.req>=4.recall@5}}.
Removing BM25 (graph-only) scores slightly *higher* on the skill-defined gold, but we keep BM25:
{{requirement_coverage.json:all.share|pct}} of real requirements contain no taxonomy skill
(`requirement_coverage.json`), so a graph-only retriever returns nothing for them in the
requirement-to-evidence matrix, and graph-only is worse on vague posts
({{ablation.json:retrieval.best-bm25.vague.recall@5}} vs {{ablation.json:retrieval.best.vague.recall@5}}). This is the metric
bias made visible.

**Claim verification** (`claims_eval.json`, same jobs and evidence). The naive "experience list"
writer averages {{claims_eval.json:summary.naive.unsupported_per_proposal_before}} unsupported claims per proposal
before verification and {{claims_eval.json:summary.naive.unsupported_per_proposal_after}} after. The shipped
claim-plan writer averages {{claims_eval.json:summary.shipped.unsupported_per_proposal_before}} →
{{claims_eval.json:summary.shipped.unsupported_per_proposal_after}}, with a partial-claim rate of
{{claims_eval.json:summary.shipped.partial_claim_rate}} (partials are repaired by deleting the unsupported
skill, number or industry). On the full dev run (`decision_eval.json`) the rate is
{{decision_eval.json:summary.unsupported_before_per_proposal}} → {{decision_eval.json:summary.unsupported_after_per_proposal}}.

**Retrieval vs reply rate** (`gigsim_outcomes.json`, the same {{gigsim_outcomes.json:meta.jobs|int}} gold-bid jobs per variant):

| Variant | Reply rate | Hire rate | Unsupported / proposal (before → after) | p95 s |
|---|---|---|---|---|
| V0 | {{gigsim_outcomes.json:variants.V0.summary.reply_rate}} | {{gigsim_outcomes.json:variants.V0.summary.hire_rate}} | {{gigsim_outcomes.json:variants.V0.summary.unsupported_before}} → {{gigsim_outcomes.json:variants.V0.summary.unsupported_after}} | {{gigsim_outcomes.json:variants.V0.summary.p95_latency_s|1}} |
| V2 | {{gigsim_outcomes.json:variants.V2.summary.reply_rate}} | {{gigsim_outcomes.json:variants.V2.summary.hire_rate}} | {{gigsim_outcomes.json:variants.V2.summary.unsupported_before}} → {{gigsim_outcomes.json:variants.V2.summary.unsupported_after}} | {{gigsim_outcomes.json:variants.V2.summary.p95_latency_s|1}} |
| C1 | {{gigsim_outcomes.json:variants.C1.summary.reply_rate}} | {{gigsim_outcomes.json:variants.C1.summary.hire_rate}} | {{gigsim_outcomes.json:variants.C1.summary.unsupported_before}} → {{gigsim_outcomes.json:variants.C1.summary.unsupported_after}} | {{gigsim_outcomes.json:variants.C1.summary.p95_latency_s|1}} |
| shipped | {{gigsim_outcomes.json:variants.best.summary.reply_rate}} | {{gigsim_outcomes.json:variants.best.summary.hire_rate}} | {{gigsim_outcomes.json:variants.best.summary.unsupported_before}} → {{gigsim_outcomes.json:variants.best.summary.unsupported_after}} | {{gigsim_outcomes.json:variants.best.summary.p95_latency_s|1}} |

<!--B-OUTCOME-->

**Judge calibration.** The rubric judge (`agent/prompts/judge.md`) is used only after calibration
against 30 human labels (`evals/runners/judge_calibration.py`). Cohen's κ =
{{judge_calibration.json:cohen_kappa}} (n = {{judge_calibration.json:n|int}}). Judge scores are not used
for any decision until κ ≥ 0.4.

**What ships.** BM25 + skill graph + multi-vector + outcome boost (no dense ranking, no reranker),
plus claim verification on every draft. It is the best recall at the lowest latency, and the
components we dropped were measured, not assumed, to be neutral or harmful here (ADR 0003).

## 5. R&D question C - single agent vs supervisor vs graph

Same jobs ({{multiagent_compare.json:meta.jobs_per_persona|int}} per persona, half gold-bid), same LLM
({{multiagent_compare.json:meta.model|raw}}) for (a), (b) and the LLM nodes of (c); same verifier and policy pack
applied to every final proposal (`multiagent_compare.json`).

| System | Bid/skip acc. | Scams bid on | Unsupported / proposal | Violations sent | Reply rate | Tokens / job | p95 s |
|---|---|---|---|---|---|---|---|
| (a) one ReAct agent, all tools | {{multiagent_compare.json:systems.react.summary.bid_skip_accuracy}} | {{multiagent_compare.json:systems.react.summary.scams_bid_on|int}} | {{multiagent_compare.json:systems.react.summary.unsupported_per_proposal}} | {{multiagent_compare.json:systems.react.summary.compliance_violations_sent|int}} | {{multiagent_compare.json:systems.react.summary.reply_rate}} | {{multiagent_compare.json:systems.react.summary.tokens_per_job|0}} | {{multiagent_compare.json:systems.react.summary.p95_latency_s|1}} |
| (b) langgraph-supervisor | {{multiagent_compare.json:systems.supervisor.summary.bid_skip_accuracy}} | {{multiagent_compare.json:systems.supervisor.summary.scams_bid_on|int}} | {{multiagent_compare.json:systems.supervisor.summary.unsupported_per_proposal}} | {{multiagent_compare.json:systems.supervisor.summary.compliance_violations_sent|int}} | {{multiagent_compare.json:systems.supervisor.summary.reply_rate}} | {{multiagent_compare.json:systems.supervisor.summary.tokens_per_job|0}} | {{multiagent_compare.json:systems.supervisor.summary.p95_latency_s|1}} |
| (c) GigBid graph | {{multiagent_compare.json:systems.graph.summary.bid_skip_accuracy}} | {{multiagent_compare.json:systems.graph.summary.scams_bid_on|int}} | {{multiagent_compare.json:systems.graph.summary.unsupported_per_proposal}} | {{multiagent_compare.json:systems.graph.summary.compliance_violations_sent|int}} | {{multiagent_compare.json:systems.graph.summary.reply_rate}} | {{multiagent_compare.json:systems.graph.summary.tokens_per_job|0}} | {{multiagent_compare.json:systems.graph.summary.p95_latency_s|1}} |

<!--C-CONCLUSION-->

## 6. The change request

GigSim policy v2 (2 Nov) tiers Connects by budget and rejects proposals with unanswered screening
questions. **Edited:** `rules.yaml` (+1 rule P7), `config.yaml` (Connects formula), `policy.md`; that is
{{change_request.json:diff.lines_added|int}} lines added and {{change_request.json:diff.lines_removed|int}} removed in commit
`{{change_request.json:diff.commit|raw}}`, with no Python. The unit suite then caught that the new rule failed
*closed* without job context, which needed a two-line default fix in `policy_engine.py` (`cfdb3e4`). Time: ~10
minutes. **Effect** (60 jobs, GigSim v2): Connects-cost prediction errors
{{change_request.json:connects_cost_prediction_errors.before_config_only|int}} → {{change_request.json:connects_cost_prediction_errors.after_synced_from_get_policy|int}};
missing-answer proposals rejected by the platform {{change_request.json:missing_answer_proposals.rejected_by_gigsim_before|int}} →
{{change_request.json:missing_answer_proposals.rejected_by_gigsim_after|int}} (blocked with a reason before approval instead).
**What it says:** prices and rules belong to data the system reads (`get_policy`, `rules.yaml`), not to prompts or code.

## 7. Signature extension - X2 proposal experiments

Paired A/B in GigSim: *evidence-first* vs *question-first* openings, every job receiving both in fresh
GigSim states (`ab_test.json`, {{ab_test.json:meta.pairs|int}} pairs). Reply rate A {{ab_test.json:reply_rate.A}} vs B
{{ab_test.json:reply_rate.B}}; McNemar exact p = {{ab_test.json:mcnemar_exact.p_value}}; two-proportion z p =
{{ab_test.json:two_proportion_z.p_value}}; P(B > A) = {{ab_test.json:bayes_p_B_better}}. <!--X2-CONCLUSION-->
The strategy is a user setting, and outcome memory records the strategy of every real submission, so the
experiment keeps running on live traffic (`docs/EXTENSION.md`).

## 8. Failure analysis

{{failure_analysis.json:failed_jobs|int}} of {{failure_analysis.json:jobs|int}} dev jobs failed at least one check
(`failure_analysis.json`; each example carries a trace id for replay).

<!--FAILURE-TABLE-->

## 9. Safety and platform respect

**Must never happen:** sending without approval; fabricated experience; off-platform contact or payment;
following instructions inside a post or message; scraping or browser automation; PII or tokens in logs.
**Enforcement:** `interrupt()` + idempotent writes; claim verifier + rule P2; policy pack; injection
quarantine (detect → neutralise → datamark → typed fields only → output guard); the official Upwork MCP
only, writes as platform drafts, a 4-hour live schedule, and a per-user rate limiter at 50% of GigSim's
limit; PII/secret masking on every span and the hash-chained audit log; Fernet-encrypted tokens; every
query scoped by user id.
**Measured:** injection attack success {{injection_eval.json:attack_success_rate.naive}} for a naive
pipeline vs {{injection_eval.json:attack_success_rate.defended}} for GigBid's path on
{{injection_eval.json:meta.n|int}} planted posts ({{injection_eval.json:meta.model|raw}}). The detector catches
{{injection_eval.json:detector.recall}} of planted injections with {{injection_eval.json:detector.false_alarm_rate}}
false alarms on all 600 dev posts. Scam recall on the dev set is {{decision_eval.json:summary.scam.recall}} at
precision {{decision_eval.json:summary.scam.precision}}.
**What still gets through:** <!--SAFETY-GAPS-->

## 10. Hidden test results against declared budgets

The hidden run happens after the deadline against the live URL, so this section reports the dev-set run
of the deployed configuration and will be re-run on the hidden set (`decision_eval.json`,
{{decision_eval.json:meta.jobs|int}} jobs, profile {{decision_eval.json:meta.profile|raw}}).

| Budget | Declared | Measured (dev) |
|---|---|---|
| p95 latency / job analysed | 20 s | {{decision_eval.json:summary.latency_job_s.p95|1}} s |
| p95 latency / proposal | 60 s | {{decision_eval.json:summary.latency_proposal_s.p95|1}} s |
| USD / job analysed | 0.002 | {{decision_eval.json:summary.usd_per_job|4}} |
| USD / proposal | 0.01 | {{decision_eval.json:summary.usd_per_proposal|4}} |

Decision quality: bid/skip F1 {{decision_eval.json:summary.bid_skip.f1}}; price inside the fair band
{{decision_eval.json:summary.price_in_band}}; GigSim reply rate {{decision_eval.json:summary.reply_rate}} and hire
rate {{decision_eval.json:summary.hire_rate}} on {{decision_eval.json:summary.submitted|int}} submitted proposals.
<!--BUDGET-NOTE-->

<!-- pagebreak -->

## Appendix A - reproduce

`python scripts/run.py eval` regenerates every results file; `python scripts/build_report.py` rebuilds this
PDF; `python scripts/run.py results` regenerates the README tables. Traces: `docs/traces/*.json`.

## Appendix B - per-persona and per-kind decision results

| Slice | Bid/skip F1 | Scam recall | Unsupported after | Reply rate |
|---|---|---|---|---|
| aiml | {{decision_eval.json:breakdown.persona.aiml.bid_skip.f1}} | {{decision_eval.json:breakdown.persona.aiml.scam.recall}} | {{decision_eval.json:breakdown.persona.aiml.unsupported_after_per_proposal}} | {{decision_eval.json:breakdown.persona.aiml.reply_rate}} |
| web | {{decision_eval.json:breakdown.persona.web.bid_skip.f1}} | {{decision_eval.json:breakdown.persona.web.scam.recall}} | {{decision_eval.json:breakdown.persona.web.unsupported_after_per_proposal}} | {{decision_eval.json:breakdown.persona.web.reply_rate}} |
| data | {{decision_eval.json:breakdown.persona.data.bid_skip.f1}} | {{decision_eval.json:breakdown.persona.data.scam.recall}} | {{decision_eval.json:breakdown.persona.data.unsupported_after_per_proposal}} | {{decision_eval.json:breakdown.persona.data.reply_rate}} |
| kind: fit | {{decision_eval.json:breakdown.kind.fit.bid_skip.accuracy}} (acc.) | - | {{decision_eval.json:breakdown.kind.fit.unsupported_after_per_proposal}} | {{decision_eval.json:breakdown.kind.fit.reply_rate}} |
| kind: partial | {{decision_eval.json:breakdown.kind.partial.bid_skip.accuracy}} (acc.) | - | {{decision_eval.json:breakdown.kind.partial.unsupported_after_per_proposal}} | {{decision_eval.json:breakdown.kind.partial.reply_rate}} |
| kind: off-domain | {{decision_eval.json:breakdown.kind.off.bid_skip.accuracy}} (acc.) | - | - | - |
| kind: scam | {{decision_eval.json:breakdown.kind.scam.bid_skip.accuracy}} (acc.) | {{decision_eval.json:breakdown.kind.scam.scam.recall}} | - | - |
