# Data card

## Why synthetic

The starter kit (GigSim, three persona corpora, policy pack, dev set) was not distributed.
`data/generator/generate.py` therefore builds a deterministic equivalent (seed 4016) that
matches every property the brief specifies. It also gives **exact** gold labels, because we
know which projects truly cover which skill. If the instructor's kit arrives, it plugs into
the same adapter and loaders.

## Contents

| Asset | Size | Notes |
|---|---|---|
| Skill ontology | 60 skills (AI/ML, web, data, off-domain) | names, aliases, *implicit phrases*, code tokens |
| Personas | `aiml` (20 projects), `web` (18), `data` (16) | CV as **PDF** + Markdown, case studies, repos (README + code), client reviews |
| Past proposals | 150 per persona | labelled `won` / `replied` / `ignored` by the GigSim client model |
| Clients | 420 | history (spend, hires, hire rate, verification, rating); 1 in 9 scam-prone |
| Historical jobs | 1,500 | awarded prices, used for market statistics |
| Live stream | 322 jobs | includes duplicates (reposts), scams and planted prompt injections |
| Dev set | 200 jobs × 3 personas | gold: bid/skip, scam, scam type, injection goal + canary, graded evidence items, fair price band, job kind |
| Policy pack | `data/policy_pack/policy.md` + `rules.yaml` | instructor-style rules in machine-readable form |

## Deliberate messiness (built to defeat naive RAG)

- **The same project is described three ways**: case study, terse CV bullet, and repo README + code.
- **Skills are implied rather than named** in about 45% of case-study mentions ("background
  workers that process uploads" means Celery). GigBid's extractor never sees these
  phrases; it has to recover them semantically.
- **30% of READMEs are vague** ("Internal tooling for an ops team") while their code
  imports the real libraries. This is the target of V5 multi-vector retrieval.
- **Code is mixed with prose** inside case studies.
- **Past proposals look like job posts** and sometimes over-claim, so naive RAG retrieves
  them instead of evidence. This is a finding (V0 vs V0e).
- **Job posts** mix aliases ("data build tool"), implicit phrasing (dial 0.1–0.7) and vague
  goal-only posts (18% of fit jobs).

## Gold labels

- **Evidence**: every case study, CV entry and repo of a project that shares a required
  skill. Graded relevance = number of shared skills, with generic skills (Python, SQL,
  Docker, pandas, TypeScript, Excel) weighted 0.25. Items below 0.5 are not gold.
  Recall@5 is capped by `min(5, |gold|)`.
- **Bid**: not a scam, AND at least 60% of required skills in the persona's true skills,
  AND budget ≥ floor (hourly max ≥ 0.75 × floor, or fixed ≥ minimum project).
- **Fair price band**: 0.75–1.25 × the simulated fair point (hourly: floored at the persona's rate).
- **Label balance**: about 50% bid, about 20% scam, about 10% injection per persona.

## Known biases and limits

- The client model is a hand-written scoring function, not real clients. Reply rates are
  only comparable *within* GigSim. It rewards must-have skill coverage, concrete numbers
  and specificity, and penalises generic openings, over-budget bids and length. It catches
  fabricated experience at the interview stage, so lies can still earn replies but rarely hires.
- Templates make posts more regular than real ones, which flatters the heuristic extractor.
  The LLM analyst path exists for real posts.
- No hidden set is committed. The instructor's hidden run is the real test.
- All persons, clients and companies are fictional.
