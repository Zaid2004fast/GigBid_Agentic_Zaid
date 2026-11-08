---
version: matcher-v1
node: Fit Matcher
model_route: none (retrieval + deterministic scoring)
---
## system
(Not sent to a model in the shipped configuration.) The Fit Matcher maps each JobSpec requirement to
portfolio evidence via the Portfolio MCP server (search_evidence) using the RAG variant chosen in
config, then scores fit = weighted share of requirements with supported evidence. Requirements the
corrective loop refuses are reported as gaps and must never be claimed.

## user
Requirements: {requirements}