# ADR 0003 - Shipped retrieval design is chosen by measurement

**Decision.** `rag.variant` ships the variant with the best evidence Recall@5 / nDCG@10 on the dev
set at acceptable latency, as recorded in `evals/results/rag_retrieval.json` and the ablation in
`evals/results/ablation.json`. See `docs/report/REPORT.md` §4 for the decision paragraph.

**Notable negative results.** Cross-encoder reranking (MiniLM) and HyDE-lite did not beat plain
hybrid retrieval on this corpus, and contextual chunk headers hurt recall slightly, so they are not
in the shipped pipeline even though they are implemented.