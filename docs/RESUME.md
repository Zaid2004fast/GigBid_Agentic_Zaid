# Résumé bullet (two lines, numbers from evals/results/)

- Built **GigBid**, a LangGraph multi-agent freelancer copilot (3 custom MCP servers, human-approval interrupts, Postgres
  checkpoints, exactly-once submits). It raised portfolio-evidence Recall@5 from 0.001 (naive RAG) to 0.949 with a
  skill-graph + BM25 retriever chosen by ablation (`rag_retrieval.json`, `ablation.json`).
- Cut prompt-injection success from 30/30 to 0/30 with a typed-field quarantine, and verified every proposal claim against
  the portfolio (0 unsupported claims after verification on 600 jobs; `injection_eval.json`, `decision_eval.json`).
