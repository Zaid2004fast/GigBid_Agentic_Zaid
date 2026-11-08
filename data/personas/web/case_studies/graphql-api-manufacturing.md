---
project: graphql-api-manufacturing
client_industry: manufacturing
date: 2026-12
type: case_study
---
# GraphQL API consolidation for a manufacturing product

## Context
Helio Manufacturing needed one typed API replacing 2 legacy REST services. The existing process was slow and error-prone.

## What I built
I designed and delivered one typed API replacing 2 legacy REST services. The stack: GraphQL, Node, strictly typed front-end and API contracts, PostgreSQL.

A core piece of the implementation:

```
type Query { orders(userId: ID!): [Order] }
```

## Outcome
The result page payloads 78% smaller.
