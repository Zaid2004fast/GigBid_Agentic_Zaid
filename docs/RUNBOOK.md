# Runbook

## Start

| Mode | Command | Notes |
|---|---|---|
| Local, no Docker | `python scripts/run.py dev` | API on :8000 with in-process GigSim, MCP sessions and worker; web dev server on :5173 |
| Everything | `docker compose -f infra/docker-compose.yml up --build` | web :8080, API :8000, Phoenix :6006 |
| Single container (free host) | `infra/docker/allinone.Dockerfile` | see `docs/DEPLOY.md` |

## Schedules (E1)

| Job | GigSim | Live Upwork | Why |
|---|---|---|---|
| Saved-search scout | every 30 min (per search, configurable 15–1440) | **every 240 min**, plus manual "Scout now" | A freelancer reviews new jobs a few times a day, and Upwork's guidance forbids scraping-like polling. Four hours means at most 6 read bursts a day per search, each a single `search_jobs` call, which is indistinguishable from a person checking their feed. |
| Event poll (pipeline) | every 2 min | every 240 min | Replies are not urgent to the minute. Live mode reads threads only on the same conservative cadence. |
| Degraded-work retry | every scheduler tick (60 s) once the breaker closes | same | |

Per-user rate limiter on the marketplace server: 1 request/s with a burst of 10, which is
half of GigSim's 120 requests/min. `GigSimAdapter` honours `Retry-After` on 429 and backs
off exponentially on 5xx.

## Idempotency (no double analysis, no double submit)

- Queue keys: `scout:<user>:<minute>`, `analyse:<user>:<job>`, `resume:<thread>:<checkpoint>`.
  Re-enqueueing an existing key is a no-op, and a crashed worker's lease (300 s) expires so
  the item is retried.
- Approvals have priority: `resume` items are claimed before background analysis.
- The submit key is `<thread>:v<draft version>:<sha(text+bid)>:submit`. If the worker dies
  after the marketplace call but before the checkpoint write, LangGraph re-runs `submit`
  with the same key and both servers replay the stored result.

## Viva drills

1. **Kill the marketplace MCP server**: `docker compose stop mcp-marketplace`. Within one
   call the breaker records failures; threads go to `queued_degraded`; `/api/health` returns
   `degraded: true`; the UI banner appears. Restart it and the next tick re-queues.
   Code: `agent/mcp_client.py::ToolHub.call`, `agent/runtime.py` (`ToolUnavailable` →
   `queued_degraded`), `worker/engine.py::tick`, `apps/web/src/components/DegradedBanner.tsx`.
2. **Crash before submit**: approve, then `docker compose kill worker` (or set
   `GIGBID_FAULT=crash_before_resume`). Restart. The lease expires, `resume` runs again, and
   `submit` replays, so Connects are spent once. Proof: `tests/integration/test_graphs.py::test_bid_interrupts_then_submits_exactly_once`
   and `docs/traces/5_crash_and_resume.json`.
3. **Delete evidence and regenerate**: remove the case study and refresh the corpus
   (upload or restart). On regeneration, the verifier finds no support and removes or
   rewrites the claim.
4. **Replay a wrongly skipped job**: Runs → the thread → Checkpoint history → "Replay from here".
5. **Switch to live mode**: set `MARKETPLACE_MODE=upwork_live` and connect Upwork in
   Settings. Only `agent/marketplace_port.get_port` picks a different adapter; no node changes.

## Change request (2 Nov policy update)

GigSim v2 (`POST /admin/policy/2`) tiers Connects by budget and rejects proposals with
unanswered screening questions. See `docs/EXTENSION.md#change-request` for the diff.

## Budgets (declared; measured values in `evals/results/decision_eval.json`)

| Budget | Declared |
|---|---|
| p95 latency per job analysed | 20 s |
| p95 latency per proposal | 60 s |
| USD per job analysed | 0.002 |
| USD per proposal | 0.01 |

## Secrets

Secrets come only from environment variables. `TOKEN_ENC_KEY` (Fernet) encrypts OAuth and
marketplace tokens at rest. Tokens are never logged: `mask_obj` redacts token, secret,
password and authorization keys, and `mask_pii` masks emails, phones, cards, IBANs,
wallets and handles in every span and audit record.
