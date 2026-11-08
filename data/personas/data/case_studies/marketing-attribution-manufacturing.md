---
project: marketing-attribution-manufacturing
client_industry: manufacturing
date: 2023-07
type: case_study
---
# Marketing funnel and attribution analysis (manufacturing)

## Context
Tessellate Manufacturing needed a funnel model from GA4 exports in BigQuery. The existing process was slow and error-prone.

## What I built
I designed and delivered a funnel model from GA4 exports in BigQuery. The stack: GA4, a serverless warehouse on Google Cloud billed per query, SQL, Python.

A core piece of the implementation:

```
gtag('event', 'purchase', { value: 42 })
```

## Outcome
The result reallocated 27% of ad spend.
