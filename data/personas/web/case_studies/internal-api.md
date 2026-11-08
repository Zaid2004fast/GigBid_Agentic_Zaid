---
project: internal-api
client_industry: SaaS
date: 2023-08
type: case_study
---
# Async internal API for a SaaS operations team

## Context
Evergreen Saas needed a typed internal API with caching and background jobs. The existing process was slow and error-prone.

## What I built
I designed and delivered a typed internal API with caching and background jobs. The stack: an async Python API with automatic OpenAPI docs, python3, Postgres, Docker, Redis, WebSocket.

A core piece of the implementation:

```
CREATE INDEX CONCURRENTLY idx_orders_user ON orders(user_id);
```

## Outcome
The result API p95 at 50 ms.
