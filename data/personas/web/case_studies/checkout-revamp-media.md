---
project: checkout-revamp-media
client_industry: media
date: 2025-10
type: case_study
---
# Checkout and subscription billing for an media store

## Context
Atlas Media needed a new checkout with subscriptions and dunning emails. The existing process was slow and error-prone.

## What I built
I designed and delivered a new checkout with subscriptions and dunning emails. The stack: a component-based single-page front end with hooks, subscription billing with webhooks for failed payments, a JavaScript runtime on the server handling the API, Express.js, a relational database with migrations and indexes tuned for slow queries, strictly typed front-end and API contracts.

A core piece of the implementation:

```
const http = require('http')
```

## Outcome
The result checkout conversion up 65%.
