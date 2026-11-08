---
project: internal-api-logistics
client_industry: logistics
date: 2023-09
type: case_study
---
# Async internal API for a logistics operations team

## Context
Tessellate Logistics needed a typed internal API with caching and background jobs. The existing process was slow and error-prone.

## What I built
I designed and delivered a typed internal API with caching and background jobs. The stack: an async Python API with automatic OpenAPI docs, python3, a relational database with migrations and indexes tuned for slow queries, Docker, Redis, server-rendered pages with file-based routing for SEO.

A core piece of the implementation:

```
import redis
r = redis.Redis()
```

## Outcome
The result API p95 at 70 ms.
