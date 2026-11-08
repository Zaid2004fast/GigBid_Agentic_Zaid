---
project: graphql-api
client_industry: SaaS
date: 2022-07
type: case_study
---
# GraphQL API consolidation for a SaaS product

## Context
Granite Saas needed one typed API replacing 6 legacy REST services. The existing process was slow and error-prone.

## What I built
I designed and delivered one typed API replacing 6 legacy REST services. The stack: GraphQL, a JavaScript runtime on the server handling the API, strictly typed front-end and API contracts, a relational database with migrations and indexes tuned for slow queries, REST routes with middleware for auth and validation.

A core piece of the implementation:

```
type Query { orders(userId: ID!): [Order] }
```

## Outcome
The result page payloads 86% smaller.
