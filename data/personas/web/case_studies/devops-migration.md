---
project: devops-migration
client_industry: fintech
date: 2026-08
type: case_study
---
# Containerised cloud migration for a fintech company

## Context
Brightpath Fintech needed moved a monolith to containers on AWS with CI/CD. The existing process was slow and error-prone.

## What I built
I designed and delivered moved a monolith to containers on AWS with CI/CD. The stack: docker-compose, hosted on Amazon's cloud with object storage and serverless functions, a relational database with migrations and indexes tuned for slow queries, NodeJS, server-rendered pages with file-based routing for SEO.

A core piece of the implementation:

```
CREATE INDEX CONCURRENTLY idx_orders_user ON orders(user_id);
```

## Outcome
The result hosting cost down 69%.
