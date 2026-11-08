# ADR 0001 - Build our own GigSim and synthetic world

**Status:** accepted · **Date:** 2026-11-08

**Context.** The starter kit (GigSim, personas, policy pack, dev set) was never shared, but every
part of the brief (evaluation, hidden-test readiness, demo) assumes a marketplace with clients.

**Decision.** Write a deterministic generator (seed 4016) and a GigSim REST stand-in with the same
contract the brief describes: jobs, clients with histories, Connects, proposals, messages, rate
limits, 5xx errors, hidden client preferences, a switchable policy version, and a simulated clock.

**Consequences.** Exact gold labels and reproducible reply rates. Risk: results are only as
realistic as the client model; we document its scoring in `docs/DATA_CARD.md`. The marketplace
port means the instructor's GigSim (or live Upwork) replaces ours with no graph changes.