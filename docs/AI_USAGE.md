# AI usage log

AI coding assistants are allowed (as in industry); the author is accountable for every line.

| Tool | Used for | Files |
|---|---|---|
| Claude Code (Claude Opus) | scaffolding and first drafts of most modules, the synthetic data generator, tests, docs; debugging sessions | whole repository - every file was reviewed, run and tested locally |
| Qwen3 1.7B (local, Ollama) | the system's own open-model path, LLM-dependent evaluations (injection, tool granularity, baselines, judge) | runtime only |

## Things the assistant got wrong that were caught

1. **Event-loop starvation.** The first in-process worker ran CPU-heavy retrieval (ONNX
   embeddings and reranking) directly in the API's event loop, and HTTP requests timed out.
   Caught by an end-to-end API test, and fixed by moving portfolio tool work to threads
   (`asyncio.to_thread`) and serialising the shared ONNX reranker with a lock. The concurrent
   rerank calls were also crashing the process natively, with no Python traceback.
2. **Approvals stuck behind background work.** The local worker claimed every queued item as
   "running" while only executing two at a time, so an approval waited 3 minutes behind job
   analyses. Caught by the Playwright "approve" test, and fixed by claiming only up to free
   capacity, with `resume` items prioritised (`worker/engine.py::claim`).
3. **Stale auth state after login.** The SPA redirected back to `/login` because the "not
   signed in" result from before login was still in state. Caught by Playwright screenshots,
   and fixed with a full navigation after sign-in and onboarding.
4. **Status reducer made "blocked" sticky,** so an edit could never un-block a draft. Caught in
   review of `agent/state.py`; only attention states are sticky now.
5. **`functools.wraps` hid the node signature from LangGraph,** which injects `config`/`store`
   by inspecting the signature. Caught in review and removed.
6. **Writer cited one project but quoted another project's metric.** The claim verifier
   flagged the number, which showed the verifier works; the writer was fixed to take facts
   from the exact evidence item it cites.
7. **Using our own canary format in the injection defence** would have overfit the defence
   to our test data. It was removed, and canaries are used only for measurement.
8. **A YAML syntax error** (a block list inside a flow mapping) made `rules.yaml` fail to parse. Caught by the first graph run.
