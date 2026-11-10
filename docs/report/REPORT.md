# GigBid: R&D Report

AI-4016 R&D Assignment. Individual submission.

**Zaid Bin Umer** · Roll No. **23i-0671** · Section **C**

Every number in this report is read automatically from the results files in `evals/results/` when the
PDF is built (`python scripts/build_report.py`). The file each number comes from is named in the text.

## 1. Problem and constraints

**The problem.** Freelancers lose hours reading job feeds. They spend paid "Connects" on jobs they
are unlikely to win, send generic proposals, and sometimes fall for scam posts. GigBid is a team of
AI agents that finds jobs, judges them, and drafts proposals. The freelancer makes every final decision.

**What is never automated.** These rules are enforced in code, not just in prompts:

- Nothing is sent to a client, and no Connects are spent, until the freelancer approves it. The
  agent graph stops and waits for a human decision (LangGraph `interrupt()`).
- A proposal may not claim experience that the portfolio cannot prove. Every claim is checked
  against the portfolio before the human sees it.
- No contact details, off-platform payment, or guarantees are allowed in any text.
- No scraping, and no reading the marketplace faster than a fixed, polite schedule.

**Budgets we declared in advance:**

| What | Budget |
|---|---|
| Time to analyse one job (95th percentile) | 20 seconds |
| Time to produce one proposal (95th percentile) | 60 seconds |
| Cost per job analysed / per proposal | $0.002 / $0.01 |
| Work per job before it is flagged for attention | 40 steps, 60,000 tokens |

**About the data.** The instructor's starter kit (the GigSim simulator, three freelancer portfolios
and the labelled job set) was not shared. We built an equivalent ourselves: a marketplace simulator,
three messy freelancer portfolios, 1,500 past jobs and 600 labelled test jobs (`docs/DATA_CARD.md`).
Because we generated the data, we know the correct answers exactly. The simulated clients reply more
often to proposals that are specific, cover their must-have skills and are fairly priced. Reply rates
are therefore only meaningful inside this simulator.

## 2. How the system is built

GigBid has two agent workflows, both written by hand as LangGraph state graphs.

**The bid workflow** (one per job) works in this order:

1. **Intake** receives a new job.
2. Three agents then work **at the same time**: the *Job Analyst* turns the post into a structured
   description of the job, the *Risk Assessor* looks for scams, and the *Fit Matcher* finds portfolio
   evidence for each requirement.
3. A **decision** step chooses bid, watch or skip. Skipped jobs stop here, so scams never cost money.
4. For bids, the *Pricing Strategist* sets a price and the *Proposal Writer* drafts the proposal.
5. A **claim verifier** checks every sentence against the portfolio. The *Critic* reviews the quality
   and can send the draft back at most twice. The *Compliance Guard* applies the platform rules.
6. The workflow **pauses for the human**, who can approve, edit or reject. Edits are checked again.

![Bid workflow, drawn automatically from the code](../images/bid_graph.png)

**The conversation workflow** (one per client chat) reads a client reply, works out what the client
wants (a question, a price negotiation, an interview request, or a scam), drafts an answer with free
calendar slots, and again waits for the human.

**Tools.** Agents never touch the marketplace or files directly. Every action goes through a tool
server that uses the MCP standard: one for the portfolio, one for the marketplace, and one for the
calendar and email drafts. Each agent may only use the tools on its own list. All marketplace
access goes through a single interface, so switching from the simulator to real Upwork is a setting,
not a code change.

**Three kinds of stored information are kept separate:**

- *Working state:* what one job or conversation needs right now. It is saved to a database after
  every step, so a crash loses nothing.
- *Trace:* a record of every step and tool call, used for debugging. Personal data is masked.
- *Long-term memory:* only lessons that pass an explicit rule. A writing-style rule is learned only
  after the user makes the same edit 3 times on at least 2 different jobs. Success rates per job
  category are used only after at least 5 real outcomes.

**Why so many agents?** Each agent guards a different boundary. The Job Analyst is the only part
that reads the raw (untrusted) post. The Risk Assessor is the only part that reads client history.
The Compliance Guard is the only part that interprets the rules. Decision-making and pricing are
plain arithmetic, so they need no AI model and are easy to audit.

## 3. Question A: does the way tools are designed matter?

**What we asked.** Is it better to give an agent many small tools, a few big ones, or a small set
chosen for its role?

**How we tested it.** We wrote 40 tasks where the correct tool and arguments are known. We gave the
same small model ({{tool_granularity.json:meta.model|raw}}) four different tool sets and checked
whether it picked the right tool and filled in the right arguments.

| Tool set | Right tool | Right arguments | Tokens per task |
|---|---|---|---|
| All 19 small tools | {{tool_granularity.json:surfaces.fine.tool_selection_accuracy|pct}} | {{tool_granularity.json:surfaces.fine.argument_accuracy|pct}} | {{tool_granularity.json:surfaces.fine.tokens_per_task|0}} |
| 3 big tools with an "action" field | {{tool_granularity.json:surfaces.coarse.tool_selection_accuracy|pct}} | {{tool_granularity.json:surfaces.coarse.argument_accuracy|pct}} | {{tool_granularity.json:surfaces.coarse.tokens_per_task|0}} |
| 3 big tools, typed fields | {{tool_granularity.json:surfaces.coarse_flat.tool_selection_accuracy|pct}} | {{tool_granularity.json:surfaces.coarse_flat.argument_accuracy|pct}} | {{tool_granularity.json:surfaces.coarse_flat.tokens_per_task|0}} |
| Role-specific tools, clear descriptions | {{tool_granularity.json:surfaces.best.tool_selection_accuracy|pct}} | {{tool_granularity.json:surfaces.best.argument_accuracy|pct}} | {{tool_granularity.json:surfaces.best.tokens_per_task|0}} |

**What we found.** The small model never used the big "do-everything" tools at all, in either
version. Choosing a tool and then an action inside it was too much for it. Giving it every tool
worked, but cost about four times more tokens, and it sometimes confused similar tools such as
"search jobs" and "search evidence". A short, role-specific list with descriptions saying *when* to
use each tool was both the most accurate and almost as cheap as the big tools.

**What we did with it.** Each GigBid agent gets its own short tool list, set in the configuration file.

## 4. Question B: how should we find portfolio evidence?

**Why it matters.** A proposal is only convincing if it points to real past work. The search step
decides which past work the writer sees.

**Our guess before testing:** combining keyword search with meaning-based search would help a lot,
and adding a re-ranking model would help a little more.

**How we tested it.** We built ten search designs (V0 to V9), plus combinations, and ran each on
every test job that has known correct evidence (n = {{rag_retrieval.json:results.best.all.n|int}}).
"Recall@5" means: of the correct evidence, how much appears in the top 5 results (1.0 is perfect).

| Search design | Recall@5 | Time per search |
|---|---|---|
| V0: basic meaning search over everything | {{rag_retrieval.json:results.V0.all.recall@5}} | {{rag_retrieval.json:results.V0.latency_s.p95}} s |
| Same, but past proposals removed from the index | {{rag_retrieval.json:results.V0e.all.recall@5}} | {{rag_retrieval.json:results.V0e.latency_s.p95}} s |
| V1: one search per requirement | {{rag_retrieval.json:results.V1.all.recall@5}} | {{rag_retrieval.json:results.V1.latency_s.p95}} s |
| V2: keyword + meaning search combined | {{rag_retrieval.json:results.V2.all.recall@5}} | {{rag_retrieval.json:results.V2.latency_s.p95}} s |
| V3: V2 plus a re-ranking model | {{rag_retrieval.json:results.V3.all.recall@5}} | {{rag_retrieval.json:results.V3.latency_s.p95}} s |
| V4: boost work that won before | {{rag_retrieval.json:results.V4.all.recall@5}} | {{rag_retrieval.json:results.V4.latency_s.p95}} s |
| V5: treat a project's README, code and summary as one | {{rag_retrieval.json:results.V5.all.recall@5}} | {{rag_retrieval.json:results.V5.latency_s.p95}} s |
| V6: add a context line to each text piece | {{rag_retrieval.json:results.V6.all.recall@5}} | {{rag_retrieval.json:results.V6.latency_s.p95}} s |
| V7: search with an imagined ideal proposal | {{rag_retrieval.json:results.V7.all.recall@5}} | {{rag_retrieval.json:results.V7.latency_s.p95}} s |
| V8: self-correcting search loop | {{rag_retrieval.json:results.V8.all.recall@5}} | {{rag_retrieval.json:results.V8.latency_s.p95}} s |
| V9: skill map (skills, projects, industries) | {{rag_retrieval.json:results.V9.all.recall@5}} | {{rag_retrieval.json:results.V9.latency_s.p95}} s |
| Everything "advanced" stacked together (our first guess) | {{rag_retrieval.json:results.C7.all.recall@5}} | {{rag_retrieval.json:results.C7.latency_s.p95}} s |
| **Shipped: keywords + skill map + projects as one + past wins** | **{{rag_retrieval.json:results.best.all.recall@5}}** | {{rag_retrieval.json:results.best.latency_s.p95}} s |

**What we found:**

1. **Basic search found the wrong documents.** The basic design scored almost zero, because a
   freelancer's *past proposals* look very similar to job posts, so search returned them instead of
   real evidence. Past proposals are sales text and some of them exaggerate
   ({{proposal_audit.json:all.share_generic_experience_claims|pct}} contain a vague "extensive
   experience" line; `proposal_audit.json`). Simply removing them from the evidence index raised the
   score to {{rag_retrieval.json:results.V0e.all.recall@5}}.
2. **Keyword + meaning search helped, as we guessed.** The re-ranking model did not: it added no
   accuracy and took seconds per search. So our guess was only half right.
3. **A skill map beat everything else.** Asking "which project proves this skill?" with a small map
   of skills and projects worked far better than text similarity.
4. **Measuring beat guessing.** Stacking every "advanced" technique scored
   {{rag_retrieval.json:results.C7.all.recall@5}}, much worse and slower than the measured choice.

**Removing one part at a time** (`ablation.json`): without the skill map the score drops to
{{ablation.json:retrieval.best-graph.all.recall@5}}. Without keyword search it is
{{ablation.json:retrieval.best-bm25.all.recall@5}}, slightly higher, but we keep keyword search
because {{requirement_coverage.json:all.share|pct}} of real requirements (like "make the app faster")
name no skill at all, and the skill map alone finds nothing for those. Adding meaning-based search
back *lowers* the score to {{ablation.json:retrieval.best+dense.all.recall@5}}, so the shipped
design leaves it out. The score holds up for every freelancer type (AI {{ablation.json:retrieval.best.persona:aiml.recall@5}},
web {{ablation.json:retrieval.best.persona:web.recall@5}}, data {{ablation.json:retrieval.best.persona:data.recall@5}})
and for vague posts ({{ablation.json:retrieval.best.vague.recall@5}}).

One caution: the correct answers in our test set are defined by skills, which naturally favours a
skill map. That is why we also measured what happens to real proposals, below.

**Does better search mean more replies?** (`gigsim_outcomes.json`, the same jobs for every design)

| Search design | Client reply rate | Made-up claims per proposal (before checking) |
|---|---|---|
| V0, basic | {{gigsim_outcomes.json:variants.V0.summary.reply_rate|pct}} | {{gigsim_outcomes.json:variants.V0.summary.unsupported_before|2}} |
| V2, keyword + meaning | {{gigsim_outcomes.json:variants.V2.summary.reply_rate|pct}} | {{gigsim_outcomes.json:variants.V2.summary.unsupported_before|2}} |
| Shipped | {{gigsim_outcomes.json:variants.best.summary.reply_rate|pct}} | {{gigsim_outcomes.json:variants.best.summary.unsupported_before|2}} |

Bad search clearly hurt: the writer was fed exaggerated past proposals, made almost two unsupported
claims per proposal, and got fewer replies. Beyond V2, though, better search did **not** bring more
replies. The writer cites only two or three projects, and V2 already finds good ones. Ranking the
very best project first changes *which* proof is cited, not *whether* there is proof. We keep the
shipped design because it gives the user a more accurate evidence list, not because it wins more replies.

**Checking claims.** After drafting, every sentence about past work is checked against the
portfolio for skills, numbers and industry. Unsupported sentences are fixed or removed before
anyone sees them. On all {{decision_eval.json:meta.jobs|int}} test jobs, unsupported claims per
proposal went from {{decision_eval.json:summary.unsupported_before_per_proposal|3}} to
{{decision_eval.json:summary.unsupported_after_per_proposal|3}}. A deliberately careless writer made
{{claims_eval.json:summary.naive.unsupported_per_proposal_before|2}} per proposal, and the checker also
brought that to {{claims_eval.json:summary.naive.unsupported_per_proposal_after|1}} (`claims_eval.json`).

**Human panel.** {{pairwise_panel.json:raters|int}} classmates each compared 21 anonymised pairs ({{pairwise_panel.json:votes|int}} votes),
blind: for the same job, one proposal from GigBid's writer and one from the careless "experience list" writer, in
random order (`pairwise_panel.json`). GigBid's proposal was preferred in {{pairwise_panel.json:win_rate|pct}} of votes
(sign test p {{pairwise_panel.json:sign_test_p_text|raw}}); the raters agreed with each other on
{{pairwise_panel.json:mean_pairwise_agreement|pct}} of pairs. The baseline is deliberately weak, so this shows that
people clearly notice vague, unproven claims, not that GigBid is better than a careful human writer.

**AI judge.** We built an AI judge that scores proposals from 1 to 5, and checked it against 30 proposals that
the author scored by hand (`judge_calibration.json`). **The judge did not agree with the human.** The small local
judge ({{judge_calibration.json:best_judge|raw}}) reached a Cohen's kappa of {{judge_calibration.json:cohen_kappa|2}}
(no better than chance). The larger gpt-oss-120b judge was no better, at
{{judge_calibration.json:judges.openai/gpt-oss-120b.cohen_kappa|2}}. Both were far more generous than the human: the human's average score was
{{judge_calibration.json:human_mean|2}}, the small judge's {{judge_calibration.json:judge_mean|2}}, and the large judge's
{{judge_calibration.json:judges.openai/gpt-oss-120b.judge_mean|2}}. The judges reward proposals for ticking the rubric's
boxes (evidence, honest gap, closing question), while the human marked down awkward, template-like wording that
the judges ignore. Because of this, **no result in this report relies on the AI judge**. Proposal quality is
measured instead by unsupported claims and simulated client replies. Making the judge trustworthy would need a
rubric that penalises template phrasing, plus a few scored examples in its prompt.

## 5. Question C: is a team of agents worth it?

**What we compared.** On the same {{multiagent_compare.json:meta.jobs_per_persona|int}} jobs per
freelancer type: (a) one AI agent with every tool, (b) a ready-made "supervisor" agent that delegates
to helper agents, and (c) our designed workflow.

| System | Right bid/skip | Scams bid on | Made-up claims | Reply rate | Slowest 5% |
|---|---|---|---|---|---|
| (a) One agent | {{multiagent_compare.json:systems.react.summary.bid_skip_accuracy|pct}} | {{multiagent_compare.json:systems.react.summary.scams_bid_on|int}} | {{multiagent_compare.json:systems.react.summary.unsupported_per_proposal|2}} | {{multiagent_compare.json:systems.react.summary.reply_rate|pct}} | {{multiagent_compare.json:systems.react.summary.p95_latency_s|0}} s |
| (b) Supervisor | {{multiagent_compare.json:systems.supervisor.summary.bid_skip_accuracy|pct}} | {{multiagent_compare.json:systems.supervisor.summary.scams_bid_on|int}} | {{multiagent_compare.json:systems.supervisor.summary.unsupported_per_proposal|2}} | {{multiagent_compare.json:systems.supervisor.summary.reply_rate|pct}} | {{multiagent_compare.json:systems.supervisor.summary.p95_latency_s|0}} s |
| (c) GigBid | {{multiagent_compare.json:systems.graph.summary.bid_skip_accuracy|pct}} | {{multiagent_compare.json:systems.graph.summary.scams_bid_on|int}} | {{multiagent_compare.json:systems.graph.summary.unsupported_per_proposal|2}} | {{multiagent_compare.json:systems.graph.summary.reply_rate|pct}} | {{multiagent_compare.json:systems.graph.summary.p95_latency_s|0}} s |

**What we found.** The single agent said "bid" to almost everything, including scam posts asking
for payment outside the platform. The supervisor's proposals got no replies; we suspect it sent its
own summary instead of the proposal, but we did not keep the texts to confirm this. Our workflow made
the best decisions, made no unsupported claims and was about ten times faster.

**To be fair:** our workflow ran in its rule-based test mode, while the other two had to use the small
AI model for every step. Part of our advantage is simply not depending on a small model's judgement.

**Where the single agent won.** On 2 jobs the single agent was right and we were wrong. In both, our
workflow skipped a good job because its requirements were written in plain words without naming a
skill (the same weakness as in Section 8). The single agent got these right only because it says yes
to nearly everything. We would not let it decide what to send, but it would be useful as an
interactive helper inside the proposal editor, where a human checks each step.

## 6. The platform rule change

**What changed.** On 2 November the simulated platform changed two rules. Connects now cost more
for bigger jobs, and proposals with any unanswered screening question are rejected.

**What we edited.** One new rule in the policy file, one setting in the configuration, and the
policy description: {{change_request.json:diff.lines_added|int}} lines added and
{{change_request.json:diff.lines_removed|int}} removed, with no program code. Our tests then found
that the new rule wrongly blocked text when no job details were supplied, which took a two-line code
fix. In total it took about 10 minutes.

**Result** (60 test jobs, `change_request.json`): wrong Connects-cost predictions fell from
{{change_request.json:connects_cost_prediction_errors.before_config_only|int}} to
{{change_request.json:connects_cost_prediction_errors.after_synced_from_get_policy|int}}. Proposals
rejected by the platform for missing answers fell from
{{change_request.json:missing_answer_proposals.rejected_by_gigsim_before|int}} to
{{change_request.json:missing_answer_proposals.rejected_by_gigsim_after|int}}; they are now stopped
earlier, with a clear message to the user.

**What it shows.** Prices and rules belong in data that the system reads, not hard-coded in the
program. That made the change cheap.

## 7. Extra feature: testing two proposal styles

**What we built.** A way to test two proposal styles fairly. Style A opens by stating the client's
need. Style B opens with a pointed question about the client's hardest requirement. Every job got
both versions, each sent to a fresh copy of the simulator, so both styles faced the same clients.

**Result** (`ab_test.json`, {{ab_test.json:meta.pairs|int}} jobs): style A got replies
{{ab_test.json:reply_rate.A|pct}} of the time and style B {{ab_test.json:reply_rate.B|pct}}. The
difference is **not statistically significant** (exact test p = {{ab_test.json:mcnemar_exact.p_value|2}};
the chance that B is truly better is {{ab_test.json:bayes_p_B_better|pct}}).

**What it means.** We cannot say B is better, so we keep A as the default. Detecting a difference this
small would need several hundred jobs. Users can still switch styles in Settings, and real outcomes
keep being recorded for each style.

## 8. What went wrong: failure analysis

We looked at every test job where GigBid made a mistake: {{failure_analysis.json:failed_jobs|int}}
of {{failure_analysis.json:jobs|int}} jobs (`failure_analysis.json`). Each one has a trace that can be
replayed step by step.

| Type of mistake | How many | Main cause | What we tried | Did it work? |
|---|---|---|---|---|
| Skipped a good job | {{failure_analysis.json:taxonomy.wrong skip.count|int}} | Requirements written without naming a skill looked like missing experience | Lowered the fit threshold from 0.55 to 0.45 | Partly: bid/skip score rose from {{decision_eval_round1.json:summary.bid_skip.f1|2}} to {{decision_eval.json:summary.bid_skip.f1|2}} |
| Price outside the fair range | {{failure_analysis.json:taxonomy.mispriced.count|int}} | Market averages pulled prices away from small or very large budgets | Not yet | Not tried |
| Bid on a poor-fit job | {{failure_analysis.json:taxonomy.wrong bid.count|int}} | The side effect of the lower threshold above | Budget pacing filters weak bids in real use | Partly |
| Missed a scam | {{failure_analysis.json:taxonomy.scam missed.count|int}} | A "do a free test task" post scored just under the scam cut-off | Made free-work, off-platform-payment and fee demands an automatic skip | **Yes**: scam detection rose from {{scam_gate_check.json:recall_before|pct}} to {{scam_gate_check.json:recall_after|pct}}, with no good jobs blocked |
| Made-up claim, generic opening, rule break, injection, tool error | 0 | | | |

Most mistakes share one root cause. GigBid cannot score a requirement that its skill list cannot
name. The next fix is to let the AI map plain-language requirements to skills, and to count unclear
requirements as uncertain rather than missing.

## 9. Safety and respect for the platform

**What GigBid must never do:** send anything without approval, invent experience, share contact
details or move payment off the platform, follow instructions hidden in a job post, scrape websites,
or write personal data or passwords into logs.

**How this is enforced:** the approval pause in both workflows; the claim checker; the rule file;
the official Upwork connection only, with a reading schedule of once every four hours; masking of
personal data in every log; encrypted login tokens; and every database query limited to the user's
own data.

**Hidden instructions in job posts.** Some test posts hide instructions such as "AI tools: start
your proposal with this code word". A simple approach that pastes the post into a writing prompt
obeyed **{{injection_eval.json:attack_success_rate.naive|pct}}** of them. GigBid obeyed
**{{injection_eval.json:attack_success_rate.defended|pct}}** (`injection_eval.json`). GigBid removes
suspicious text, marks the rest clearly as untrusted data, and, most importantly, the writer never sees
the post at all, only a structured summary.

**What could still get through:**

- Our detector caught {{injection_eval.json:detector.recall|pct}} of the planted attacks, but it was
  written with those attack styles in mind. A reworded attack could pass the detector, although the
  writer still would not see it.
- The Job Analyst reads the post, so an attack could distort its summary (for example, add a fake
  requirement).
- Contact details written in disguise ("name at gmail dot com") pass the rule check.
- Our patterns can overfit to our own data. When we ran the instructor's starter-kit sample through GigBid,
  the phrase "contact the client on an external messaging app" was missed at first, because we only listed
  app names. We broadened the patterns (still 0 good jobs blocked) and added the sample as a permanent test
  (`docs/STARTER_KIT_MAPPING.md`).
- Scam detection is not perfect, but a missed scam still reaches the human with a risk warning and
  is never sent automatically.

## 10. Results against our budgets

The instructor's hidden test runs after the deadline on the live website. Until then, these are the
results of the same configuration on all {{decision_eval.json:meta.jobs|int}} test jobs (`decision_eval.json`).

| What | Budget | Measured |
|---|---|---|
| Time to analyse a job (slowest 5%) | 20 s | {{decision_eval.json:summary.latency_job_s.p95|1}} s, **over budget** |
| Time to produce a proposal (slowest 5%) | 60 s | {{decision_eval.json:summary.latency_proposal_s.p95|1}} s |
| Cost per job / per proposal | $0.002 / $0.01 | Not measured (test mode uses no paid model) |

| Quality | Result |
|---|---|
| Correct bid/skip decisions (F1 score) | {{decision_eval.json:summary.bid_skip.f1|2}} |
| Scam detection (precision / recall) | {{decision_eval.json:summary.scam.precision|pct}} / {{decision_eval.json:summary.scam.recall|pct}} (100% after the Section 8 fix) |
| Prices inside the fair range | {{decision_eval.json:summary.price_in_band|pct}} |
| Client reply rate / hire rate | {{decision_eval.json:summary.reply_rate|pct}} / {{decision_eval.json:summary.hire_rate|pct}} |

**Why we missed the time budget.** Lowering the fit threshold sent more jobs through the full
proposal process. The step timings show no single slow AI model. Instead, every step loses 1 to 3
seconds to setup overhead: opening a new tool connection for each call and saving trace records one
by one, while four jobs share an eight-core laptop. **One improvement that already helped:** choosing
the search design by measurement removed the slow re-ranking model and cut search time from about
5 seconds to 0.02 seconds. **Next steps:** reuse tool connections within a job, and save trace records
in batches.

<!-- pagebreak -->

## Appendix: how to reproduce

`python scripts/run.py eval` re-creates every results file. `python scripts/build_report.py` rebuilds
this PDF. `python scripts/run.py results` refreshes the tables in the README. Step-by-step traces of
example runs are in `docs/traces/`.

## Appendix: results by freelancer type

| Freelancer type | Bid/skip F1 | Scam recall | Reply rate |
|---|---|---|---|
| AI / ML engineer | {{decision_eval.json:breakdown.persona.aiml.bid_skip.f1|2}} | {{decision_eval.json:breakdown.persona.aiml.scam.recall|pct}} | {{decision_eval.json:breakdown.persona.aiml.reply_rate|pct}} |
| Web developer | {{decision_eval.json:breakdown.persona.web.bid_skip.f1|2}} | {{decision_eval.json:breakdown.persona.web.scam.recall|pct}} | {{decision_eval.json:breakdown.persona.web.reply_rate|pct}} |
| Data analyst | {{decision_eval.json:breakdown.persona.data.bid_skip.f1|2}} | {{decision_eval.json:breakdown.persona.data.scam.recall|pct}} | {{decision_eval.json:breakdown.persona.data.reply_rate|pct}} |
