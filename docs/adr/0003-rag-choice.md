# ADR 0003 - Shipped retrieval design is chosen by measurement

**Status:** accepted · **Date:** 2026-11-08 · **Evidence:** `evals/results/rag_retrieval.json`, `evals/results/ablation.json`

**Context.** We implemented V0 to V9, a control V0e (naive dense over evidence only) and composites
C1 to C7, and evaluated them all on every dev job with gold evidence (about 470 jobs, three
personas), using Recall@5, MRR, nDCG@10 and p95 latency.

**Decision (two rounds).**

1. Round 1 picked **C5 = hybrid BM25+dense with RRF (V2) + multi-vector project aggregation (V5) +
   outcome-aware boost (V4) + skill-graph fusion (V9)**, the best of all variants and composites.
2. Its one-at-a-time ablation (`ablation_round1.json`) showed that **removing the dense ranking
   improved Recall@5 and nDCG@10 on every persona and every hard slice** (vague posts,
   implied skills, ≥4 requirements). The embeddings still matter, but they already do their
   semantic work inside the skill extractor that maps requirements and documents onto the
   graph. A separate dense ranking only adds near-duplicate noise to the fusion.

Shipped as `rag.variant: best`: **BM25 + skill graph + multi-vector + outcome boost, no dense
ranking**. The round-2 ablation of this pipeline is `ablation.json`.

**Why.**

- The skill graph was the largest single gain (V9 ≫ every similarity-only variant). Portfolio
  questions are structured ("which project proves skill X?"), and the graph answers them with an
  explicit path: project → skill confirmed by case study / CV / code.
- Multi-vector aggregation rescues repos whose README is vague but whose code is specific.
- C5 is also fast (no cross-encoder), well inside the 20 s per-job budget on a CPU-only host.

**Negative results (implemented, measured, not shipped).**

- Cross-encoder reranking (MiniLM-L6) did not beat plain hybrid and cost ~5 s p95 per job on CPU.
- HyDE-lite (taxonomy pseudo-proposal) and contextual chunk headers lowered recall.
- Requirement decomposition lowered Recall@5 versus whole-post hybrid (C2 < C1). Per-requirement
  lists fused with RRF over-weight generic requirements such as "Python". We still decompose for
  the requirement-to-evidence *matrix* (one search per requirement), which is a UI and grounding
  need, not a recall need.
- V0 (naive dense over everything) retrieved past proposals instead of evidence (Recall@5 ≈ 0).
  The V0e control shows corpus contamination, not chunking, caused most of that failure.

**Caveat.** Gold relevance is defined by skill overlap with a project's true skills, which
structurally favours a skill-aware retriever. The end-to-end reply-rate and unsupported-claim
comparison (`gigsim_outcomes.json`) is the check that the retrieval gain matters downstream.

**Default vs measured.** The provisional composite written before any measurement (C7: contextual chunks + decomposition + reranking + outcome + corrective) scored Recall@5 0.781 at 5.5 s p95; the measured choice scores 0.949 at 0.02 s (`rag_retrieval.json`).
