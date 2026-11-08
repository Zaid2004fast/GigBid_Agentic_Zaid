# Signature extension: X2 proposal experiments

**What.** Two proposal strategies run as an A/B test in GigSim, with a significance test on reply rate.

| Arm | Strategy | Opening |
|---|---|---|
| A | `evidence_first` (default) | states the client's need with their deliverable and core stack, then evidence |
| B | `question_first` | opens with a pointed question about the riskiest requirement, then evidence |

Everything else is identical: the same jobs, retrieval, claim plan, verifier, critic, compliance and price.

**Design choices that make the test honest**

- **Paired design.** Every job gets *both* proposals, each submitted into a fresh GigSim state, so
  client-level noise (hidden preferences, budget ceilings) is matched across arms.
- **The right test for paired binary outcomes**: McNemar's exact test on discordant pairs, reported
  next to the (unpaired) two-proportion z-test and a Bayesian P(B > A) under Beta(1,1) priors.
- **Fixed job set chosen before running**: the first N gold-bid dev jobs per persona.
- **Strategy is a user setting** (Settings → Proposal strategy), and outcome memory records the
  strategy of every submitted proposal, so the experiment can keep running on a user's real traffic
  and the posterior per strategy is visible in the memory viewer.

**Result.** See `evals/results/ab_test.json` and the README results block. Interpretation is in the
R&D report §7. GigSim's client model scores coverage, specificity, length, price and generic
openings, but not *question vs statement* openings. A null result is therefore the expected and
honest outcome here, and it tells us the next lever is content (coverage and specificity), not
opening style.

Run: `python -m evals.runners.ab_test --per-persona 40`

---

## Change request

**What changed (GigSim policy v2, 2 Nov).** (1) Connects cost is tiered by job budget
(≤ $500: 4, ≤ $2,000: 8, above: 12; previously a flat 6). (2) Proposals with any unanswered
screening question are rejected by the platform.

**What we edited.** Commit `3080b70`, *"Absorb 2 Nov platform policy update (config only)"*:

| File | Change |
|---|---|
| `data/policy_pack/rules.yaml` | +1 rule `P7-screening` (`len(nonempty(draft.screening_answers)) >= len(job.screening_questions)`, action block), version 1 → 2 |
| `agent/config.yaml` | `pricing.connects.formula: flat → tiered` |
| `data/policy_pack/policy.md` | human-readable P-7 |

That is 3 files, +16 / −3 lines, and **no Python** in that commit. A follow-up two-line fix
(`cfdb3e4`) gave the policy engine empty defaults, after the unit suite showed the new rule
failing *closed* when a caller had no job context. We count it as part of the change: one code
file, two lines.

**How long.** About 10 minutes including running the tests (see the commit message).

**Why it was cheap.**

- The decision node and the marketplace server's `dry_run` already read the Connects formula from
  `get_policy()` (`pricing.connects.sync_from_marketplace: true`). The approval screen's cost was
  therefore correct on GigSim v2 **even before** the config edit; the config change only fixes the
  offline fallback.
- The Compliance Guard evaluates whatever is in `rules.yaml` through a whitelisted-AST expression
  evaluator, so a new platform rule is data.

**Measured** (`evals/results/change_request.json`, 60 dev jobs with screening questions, GigSim v2):

| | Before | After |
|---|---|---|
| Connects-cost prediction errors with config-only pricing | 60 / 60 | 0 / 60 (synced from `get_policy`) |
| Missing-answer proposals that reach GigSim and get rejected | 60 / 60 | 0 / 60 |
| Missing-answer proposals blocked by Compliance *before* approval, with a reason in the UI | 0 / 60 | 60 / 60 |

**What it says about the design.** Platform rules belong in data the Compliance Guard
interprets, and prices belong to the platform (read via the port), not hard-coded. The one code
change was a robustness gap, not a feature: rule evaluation needs defaults for every field a rule
may reference.
