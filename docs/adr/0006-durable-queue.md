# ADR 0006 - Durable DB queue with idempotent keys, Arq as the transport

**Decision.** Every unit of work is a row in `work_queue` with a natural key and a lease. Arq
(Redis) delivers work in docker/prod; an in-process poller does the same locally. Approvals are
prioritised over background analysis.

**Why.** Redis alone loses work on restarts, and a DB key makes double-enqueue a no-op. Both the
"worker restart never double-analyses" and the "exactly once" demos rely on it.